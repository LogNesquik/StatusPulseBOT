import ipaddress
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError


def validate_monitor_url(value: str) -> None:
    """Reject malformed URLs and obvious private-network targets.

    DNS resolution is rechecked just before each request in tasks.py. Redirects are
    intentionally not followed automatically to avoid redirect-based SSRF.
    """
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        if parsed.scheme not in {"http", "https"}:
            raise ValidationError("Only http:// and https:// URLs are supported.")
        if not hostname or parsed.username or parsed.password:
            raise ValidationError("Enter a valid public URL without embedded credentials.")
        if hostname.lower() in {"localhost", "localhost.localdomain"} or hostname.lower().endswith((".localhost", ".local", ".internal")):
            raise ValidationError("Local and internal hostnames cannot be monitored.")
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            ip = None
        if ip is not None and (not ip.is_global or ip.is_multicast or ip.is_reserved):
            raise ValidationError("Private, loopback and reserved IP addresses cannot be monitored.")
        # Accessing .port forces urllib to validate malformed port values.
        _ = parsed.port
    except (ValueError, TypeError):
        raise ValidationError("Enter a valid URL, for example https://example.com/health.")
