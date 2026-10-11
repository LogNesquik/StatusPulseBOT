from django.conf import settings
from django.db import models
from django.utils import timezone
from .validators import validate_monitor_url


class Monitor(models.Model):
    class Status(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        UP = "up", "Up"
        DOWN = "down", "Down"

    INTERVAL_CHOICES = [
        (60, "Every minute"),
        (300, "Every 5 minutes"),
        (600, "Every 10 minutes"),
        (1800, "Every 30 minutes"),
        (3600, "Every hour"),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="monitors")
    name = models.CharField(max_length=100)
    url = models.URLField(max_length=2048, validators=[validate_monitor_url])
    interval_seconds = models.PositiveIntegerField(choices=INTERVAL_CHOICES, default=300)
    timeout_seconds = models.PositiveSmallIntegerField(default=10)
    expected_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_status = models.CharField(max_length=10, choices=Status.choices, default=Status.UNKNOWN)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    next_check_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("owner", "url"), name="unique_monitor_url_per_owner"),
        ]
        indexes = [models.Index(fields=("is_active", "next_check_at"), name="monitor_due_idx")]

    def __str__(self):
        return f"{self.name} ({self.url})"


class CheckResult(models.Model):
    class Status(models.TextChoices):
        UP = "up", "Up"
        DOWN = "down", "Down"

    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="checks")
    status = models.CharField(max_length=10, choices=Status.choices)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_time_ms = models.PositiveIntegerField(null=True, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    checked_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("-checked_at",)
        indexes = [models.Index(fields=("monitor", "-checked_at"), name="check_monitor_date_idx")]

    def __str__(self):
        return f"{self.monitor.name}: {self.status} at {self.checked_at:%Y-%m-%d %H:%M:%S}"


class Incident(models.Model):
    class State(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="incidents")
    state = models.CharField(max_length=10, choices=State.choices, default=State.OPEN)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    last_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-started_at",)
        indexes = [models.Index(fields=("monitor", "state"), name="incident_monitor_state_idx")]

    def __str__(self):
        return f"{self.monitor.name}: {self.state}"


class TelegramConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="telegram_connection")
    chat_id = models.BigIntegerField(unique=True)
    connected_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Telegram connection for user {self.user_id}"


class TelegramLinkCode(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="telegram_link_codes")
    code = models.CharField(max_length=32, unique=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def is_valid(self):
        return self.used_at is None and self.expires_at > timezone.now()
