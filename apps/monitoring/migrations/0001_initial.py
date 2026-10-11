# Initial schema for StatusPulse monitoring and Telegram integration.
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
from apps.monitoring.validators import validate_monitor_url


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Monitor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("url", models.URLField(max_length=2048, validators=[validate_monitor_url])),
                ("interval_seconds", models.PositiveIntegerField(choices=[(60, "Every minute"), (300, "Every 5 minutes"), (600, "Every 10 minutes"), (1800, "Every 30 minutes"), (3600, "Every hour")], default=300)),
                ("timeout_seconds", models.PositiveSmallIntegerField(default=10)),
                ("expected_status_code", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("last_status", models.CharField(choices=[("unknown", "Unknown"), ("up", "Up"), ("down", "Down")], default="unknown", max_length=10)),
                ("last_checked_at", models.DateTimeField(blank=True, null=True)),
                ("next_check_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="monitors", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-created_at",),
                "indexes": [models.Index(fields=["is_active", "next_check_at"], name="monitor_due_idx")],
                "constraints": [models.UniqueConstraint(fields=("owner", "url"), name="unique_monitor_url_per_owner")],
            },
        ),
        migrations.CreateModel(
            name="TelegramConnection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("chat_id", models.BigIntegerField(unique=True)),
                ("connected_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="telegram_connection", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="TelegramLinkCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=32, unique=True)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="telegram_link_codes", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="CheckResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("up", "Up"), ("down", "Down")], max_length=10)),
                ("status_code", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("response_time_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("error_message", models.CharField(blank=True, max_length=500)),
                ("checked_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("monitor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="checks", to="monitoring.monitor")),
            ],
            options={"ordering": ("-checked_at",), "indexes": [models.Index(fields=["monitor", "-checked_at"], name="check_monitor_date_idx")]},
        ),
        migrations.CreateModel(
            name="Incident",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("state", models.CharField(choices=[("open", "Open"), ("resolved", "Resolved")], default="open", max_length=10)),
                ("started_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("last_status_code", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, max_length=500)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("monitor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="incidents", to="monitoring.monitor")),
            ],
            options={"ordering": ("-started_at",), "indexes": [models.Index(fields=["monitor", "state"], name="incident_monitor_state_idx")]},
        ),
    ]
