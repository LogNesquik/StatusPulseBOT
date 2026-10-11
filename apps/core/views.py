from django.http import JsonResponse
from django.views import View

class HealthView(View):
    """Lightweight liveness endpoint used by Docker's health check."""
    def get(self, request):
        return JsonResponse({"status": "ok", "service": "statuspulse-api"})
