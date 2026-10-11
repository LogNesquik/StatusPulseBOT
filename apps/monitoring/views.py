from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Incident, Monitor
from .serializers import CheckResultSerializer, IncidentSerializer, MonitorSerializer


class MonitorViewSet(viewsets.ModelViewSet):
    serializer_class = MonitorSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Monitor.objects.filter(owner=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        limit = self.request.user.monitors.count()
        from django.conf import settings
        if limit >= settings.MAX_MONITORS_PER_USER:
            raise ValidationError({"detail": f"Monitor limit reached ({settings.MAX_MONITORS_PER_USER})."})
        serializer.save()

    @action(detail=True, methods=["get"])
    def checks(self, request, pk=None):
        monitor = self.get_object()
        queryset = monitor.checks.all()
        status_filter = request.query_params.get("status")
        if status_filter in {"up", "down"}:
            queryset = queryset.filter(status=status_filter)
        paginator = self.paginator
        page = paginator.paginate_queryset(queryset, request, view=self) if paginator else None
        serializer = CheckResultSerializer(page if page is not None else queryset, many=True)
        if page is not None:
            return paginator.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        monitor = self.get_object()
        try:
            days = int(request.query_params.get("days", "7"))
        except ValueError:
            raise ValidationError({"days": "Must be an integer from 1 to 90."})
        if not 1 <= days <= 90:
            raise ValidationError({"days": "Must be an integer from 1 to 90."})

        since = timezone.now() - timedelta(days=days)
        aggregate = monitor.checks.filter(checked_at__gte=since).aggregate(
            total=Count("id"),
            up=Count("id", filter=Q(status="up")),
            avg_response_time_ms=Avg("response_time_ms", filter=Q(status="up")),
        )
        total = aggregate["total"] or 0
        up = aggregate["up"] or 0
        return Response({
            "monitor_id": monitor.id,
            "period_days": days,
            "total_checks": total,
            "successful_checks": up,
            "failed_checks": total - up,
            "uptime_percentage": round((up / total) * 100, 2) if total else None,
            "average_response_time_ms": round(aggregate["avg_response_time_ms"]) if aggregate["avg_response_time_ms"] is not None else None,
        })


class IncidentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = IncidentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Incident.objects.filter(monitor__owner=self.request.user).select_related("monitor")
        state_filter = self.request.query_params.get("state")
        if state_filter in {Incident.State.OPEN, Incident.State.RESOLVED}:
            queryset = queryset.filter(state=state_filter)
        monitor_id = self.request.query_params.get("monitor")
        if monitor_id:
            queryset = queryset.filter(monitor_id=monitor_id)
        return queryset
