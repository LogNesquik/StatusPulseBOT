import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.monitoring.models import Incident, Monitor, TelegramConnection, TelegramLinkCode


class BotInternalPermission(permissions.BasePermission):
    """Authenticate calls made by our private bot container to internal endpoints."""
    def has_permission(self, request, view):
        configured = settings.BOT_INTERNAL_TOKEN
        provided = request.headers.get("X-Bot-Token", "")
        return bool(configured) and hmac.compare_digest(configured, provided)


class TelegramLinkCodeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # Expire older codes so abandoned links don't accumulate indefinitely.
        TelegramLinkCode.objects.filter(user=request.user, used_at__isnull=True).delete()
        code = secrets.token_hex(5).upper()
        link = TelegramLinkCode.objects.create(
            user=request.user,
            code=code,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        return Response({
            "code": link.code,
            "expires_at": link.expires_at,
            "instructions": f"Open your Telegram bot and send /link {link.code} within 10 minutes.",
        }, status=status.HTTP_201_CREATED)


class BotLinkView(APIView):
    authentication_classes = []
    permission_classes = [BotInternalPermission]

    def post(self, request):
        code = str(request.data.get("code", "")).strip().upper()
        try:
            chat_id = int(request.data.get("chat_id"))
        except (TypeError, ValueError):
            return Response({"detail": "chat_id must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
        if not code or chat_id <= 0:
            return Response({"detail": "A valid code and private chat_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            link = TelegramLinkCode.objects.select_for_update().select_related("user").filter(code=code).first()
            if link is None or not link.is_valid():
                return Response({"detail": "This link code is invalid or expired. Generate a new one."}, status=status.HTTP_400_BAD_REQUEST)
            if TelegramConnection.objects.filter(chat_id=chat_id).exclude(user=link.user).exists():
                return Response({"detail": "This Telegram account is already linked to another account."}, status=status.HTTP_409_CONFLICT)
            try:
                # A savepoint keeps the outer transaction usable if the unique chat_id
                # constraint catches a concurrent attempt to link the same Telegram account.
                with transaction.atomic():
                    TelegramConnection.objects.update_or_create(user=link.user, defaults={"chat_id": chat_id})
            except IntegrityError:
                return Response({"detail": "Could not link this Telegram account."}, status=status.HTTP_409_CONFLICT)
            link.used_at = timezone.now()
            link.save(update_fields=["used_at"])
        return Response({"detail": "Telegram account linked successfully.", "username": link.user.username})


class BotMonitorsView(APIView):
    authentication_classes = []
    permission_classes = [BotInternalPermission]

    def get(self, request):
        try:
            chat_id = int(request.query_params.get("chat_id", ""))
        except ValueError:
            return Response({"detail": "A valid chat_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        connection = TelegramConnection.objects.select_related("user").filter(chat_id=chat_id).first()
        if not connection:
            return Response({"detail": "Telegram account is not linked. Use /link CODE."}, status=status.HTTP_404_NOT_FOUND)
        monitors = Monitor.objects.filter(owner=connection.user).order_by("name")
        return Response({
            "username": connection.user.username,
            "monitors": [
                {
                    "id": m.id,
                    "name": m.name,
                    "url": m.url,
                    "status": m.last_status,
                    "last_checked_at": m.last_checked_at,
                    "is_active": m.is_active,
                }
                for m in monitors
            ],
        })


class BotIncidentsView(APIView):
    authentication_classes = []
    permission_classes = [BotInternalPermission]

    def get(self, request):
        try:
            chat_id = int(request.query_params.get("chat_id", ""))
        except ValueError:
            return Response({"detail": "A valid chat_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        connection = TelegramConnection.objects.filter(chat_id=chat_id).first()
        if not connection:
            return Response({"detail": "Telegram account is not linked. Use /link CODE."}, status=status.HTTP_404_NOT_FOUND)
        incidents = Incident.objects.filter(monitor__owner=connection.user).select_related("monitor").order_by("-started_at")[:10]
        return Response([
            {
                "id": incident.id,
                "monitor_name": incident.monitor.name,
                "monitor_url": incident.monitor.url,
                "state": incident.state,
                "started_at": incident.started_at,
                "resolved_at": incident.resolved_at,
                "last_error": incident.last_error,
            }
            for incident in incidents
        ])
