import ipaddress
import logging
import socket
import time
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import CheckResult, Incident, Monitor, TelegramConnection

logger = logging.getLogger(__name__)


def _assert_public_destination(url: str) -> None:
    """Resolve the hostname and reject private/reserved destinations at check time.

    Redirects are disabled on the HTTP request. This is defense in depth for a
    public monitoring service; a production public deployment should additionally
    enforce outbound network policy at the container/firewall layer.
    """
    hostname = urlsplit(url).hostname
    if not hostname:
        raise ValueError("URL does not contain a hostname")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError("Hostname could not be resolved") from exc
    if not addresses:
        raise ValueError("Hostname did not resolve to an address")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global or ip.is_multicast or ip.is_reserved:
            raise ValueError("Resolved hostname points to a private or reserved IP address")


def _check_url(url: str, timeout_seconds: int, expected_status_code: int | None) -> dict:
    started = time.perf_counter()
    try:
        _assert_public_destination(url)
        response = httpx.get(
            url,
            timeout=timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": "StatusPulse/1.0 (+https://github.com/LogNesquik/StatusPulse)"},
        )
        elapsed_ms = max(0, round((time.perf_counter() - started) * 1000))
        status_code = response.status_code
        is_up = status_code == expected_status_code if expected_status_code else 200 <= status_code < 400
        return {
            "status": CheckResult.Status.UP if is_up else CheckResult.Status.DOWN,
            "status_code": status_code,
            "response_time_ms": elapsed_ms,
            "error_message": "" if is_up else f"Unexpected HTTP status: {status_code}",
        }
    except (httpx.HTTPError, ValueError, OSError) as exc:
        elapsed_ms = max(0, round((time.perf_counter() - started) * 1000))
        # Keep user-provided URL details out of saved error text; the type is useful for debugging.
        reason = "Could not resolve public hostname" if isinstance(exc, ValueError) else "Request failed or timed out"
        logger.info("Monitor check failed (%s)", type(exc).__name__)
        return {
            "status": CheckResult.Status.DOWN,
            "status_code": None,
            "response_time_ms": elapsed_ms,
            "error_message": f"{reason} ({type(exc).__name__})",
        }


@shared_task(name="apps.monitoring.tasks.dispatch_due_checks")
def dispatch_due_checks() -> int:
    """Fan out due checks; check_monitor rechecks due time under a row lock."""
    due_ids = list(
        Monitor.objects.filter(is_active=True, next_check_at__lte=timezone.now())
        .order_by("next_check_at")
        .values_list("id", flat=True)[:1000]
    )
    for monitor_id in due_ids:
        check_monitor.delay(monitor_id)
    return len(due_ids)


@shared_task(name="apps.monitoring.tasks.check_monitor", bind=True, max_retries=2, default_retry_delay=5)
def check_monitor(self, monitor_id: int) -> str:
    now = timezone.now()
    with transaction.atomic():
        monitor = Monitor.objects.select_for_update().filter(pk=monitor_id, is_active=True).first()
        if monitor is None:
            return "skipped"
        if monitor.next_check_at and monitor.next_check_at > now:
            return "not_due"
        url = monitor.url
        timeout_seconds = monitor.timeout_seconds
        expected_status_code = monitor.expected_status_code
        monitor.next_check_at = now + timedelta(seconds=monitor.interval_seconds)
        monitor.save(update_fields=["next_check_at", "updated_at"])

    result = _check_url(url, timeout_seconds, expected_status_code)
    notification = None
    with transaction.atomic():
        monitor = Monitor.objects.select_for_update().filter(pk=monitor_id).first()
        if monitor is None:
            return "deleted"
        previous_status = monitor.last_status
        checked_at = timezone.now()
        CheckResult.objects.create(monitor=monitor, checked_at=checked_at, **result)
        monitor.last_status = result["status"]
        monitor.last_checked_at = checked_at
        monitor.save(update_fields=["last_status", "last_checked_at", "updated_at"])

        open_incident = Incident.objects.select_for_update().filter(monitor=monitor, state=Incident.State.OPEN).first()
        if result["status"] == CheckResult.Status.DOWN:
            if open_incident:
                open_incident.last_status_code = result["status_code"]
                open_incident.last_error = result["error_message"]
                open_incident.save(update_fields=["last_status_code", "last_error", "updated_at"])
            else:
                Incident.objects.create(
                    monitor=monitor,
                    state=Incident.State.OPEN,
                    started_at=checked_at,
                    last_status_code=result["status_code"],
                    last_error=result["error_message"],
                )
                notification = (
                    monitor.owner_id,
                    f"⚠️ StatusPulse: {monitor.name} is DOWN\nURL: {monitor.url}\n"
                    f"Status: {result['status_code'] or 'no response'}\nError: {result['error_message']}\n"
                    f"Detected: {checked_at:%Y-%m-%d %H:%M:%S} UTC",
                )
        elif open_incident:
            open_incident.state = Incident.State.RESOLVED
            open_incident.resolved_at = checked_at
            open_incident.save(update_fields=["state", "resolved_at", "updated_at"])
            notification = (
                monitor.owner_id,
                f"✅ StatusPulse: {monitor.name} is UP again\nURL: {monitor.url}\n"
                f"HTTP status: {result['status_code']}\nResponse time: {result['response_time_ms']} ms\n"
                f"Recovered: {checked_at:%Y-%m-%d %H:%M:%S} UTC",
            )
        elif previous_status == Monitor.Status.UNKNOWN:
            logger.info("Initial check completed for monitor_id=%s", monitor_id)

    if notification:
        notify_user.delay(*notification)
    return result["status"]


@shared_task(name="apps.monitoring.tasks.notify_user")
def notify_user(user_id: int, message: str) -> str:
    connection = TelegramConnection.objects.filter(user_id=user_id).first()
    if not connection:
        return "not_connected"
    send_telegram_message.delay(connection.chat_id, message)
    return "queued"


@shared_task(
    name="apps.monitoring.tasks.send_telegram_message",
    bind=True,
    autoretry_for=(httpx.HTTPError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_telegram_message(self, chat_id: int, message: str) -> str:
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN is not set; skipping notification")
        return "token_missing"
    response = httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise httpx.HTTPStatusError("Telegram API rejected the message", request=response.request, response=response)
    return "sent"
