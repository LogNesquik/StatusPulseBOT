from rest_framework import serializers
from .models import CheckResult, Incident, Monitor
from .validators import validate_monitor_url


class MonitorSerializer(serializers.ModelSerializer):
    current_status = serializers.CharField(source="get_last_status_display", read_only=True)

    class Meta:
        model = Monitor
        fields = (
            "id", "name", "url", "interval_seconds", "timeout_seconds",
            "expected_status_code", "is_active", "last_status", "current_status",
            "last_checked_at", "next_check_at", "created_at", "updated_at",
        )
        read_only_fields = ("id", "last_status", "last_checked_at", "next_check_at", "created_at", "updated_at")

    def validate_url(self, value):
        validate_monitor_url(value)
        return value

    def validate_timeout_seconds(self, value):
        if value < 2 or value > 30:
            raise serializers.ValidationError("Timeout must be between 2 and 30 seconds.")
        return value

    def validate_expected_status_code(self, value):
        if value is not None and not 100 <= value <= 599:
            raise serializers.ValidationError("HTTP status code must be between 100 and 599.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        owner = getattr(request, "user", None)
        url = attrs.get("url", getattr(self.instance, "url", None))
        if owner and url:
            duplicates = Monitor.objects.filter(owner=owner, url=url)
            if self.instance:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise serializers.ValidationError({"url": "You already monitor this URL."})
        return attrs

    def create(self, validated_data):
        from django.utils import timezone
        return Monitor.objects.create(owner=self.context["request"].user, next_check_at=timezone.now(), **validated_data)


class CheckResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = CheckResult
        fields = ("id", "status", "status_code", "response_time_ms", "error_message", "checked_at")


class IncidentSerializer(serializers.ModelSerializer):
    monitor_name = serializers.CharField(source="monitor.name", read_only=True)
    monitor_url = serializers.URLField(source="monitor.url", read_only=True)

    class Meta:
        model = Incident
        fields = ("id", "monitor", "monitor_name", "monitor_url", "state", "started_at", "resolved_at", "last_status_code", "last_error", "updated_at")
        read_only_fields = fields
