from django.contrib import admin
from .models import CheckResult, Incident, Monitor, TelegramConnection, TelegramLinkCode


@admin.register(Monitor)
class MonitorAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "url", "owner", "last_status", "is_active", "last_checked_at")
    list_filter = ("last_status", "is_active", "interval_seconds")
    search_fields = ("name", "url", "owner__username", "owner__email")
    readonly_fields = ("last_status", "last_checked_at", "next_check_at", "created_at", "updated_at")


@admin.register(CheckResult)
class CheckResultAdmin(admin.ModelAdmin):
    list_display = ("id", "monitor", "status", "status_code", "response_time_ms", "checked_at")
    list_filter = ("status", "checked_at")
    search_fields = ("monitor__name", "monitor__url")
    readonly_fields = tuple(field.name for field in CheckResult._meta.fields)


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ("id", "monitor", "state", "started_at", "resolved_at")
    list_filter = ("state", "started_at")
    search_fields = ("monitor__name", "monitor__url")


admin.site.register(TelegramConnection)
admin.site.register(TelegramLinkCode)
