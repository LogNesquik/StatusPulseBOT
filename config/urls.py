from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from apps.core.views import HealthView
from apps.monitoring.views import IncidentViewSet, MonitorViewSet
from apps.users.views import RegisterView
from apps.telegram_gateway.views import BotIncidentsView, BotLinkView, BotMonitorsView, TelegramLinkCodeView

router = DefaultRouter()
router.register("monitors", MonitorViewSet, basename="monitor")
router.register("incidents", IncidentViewSet, basename="incident")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", HealthView.as_view(), name="health"),
    path("api/v1/auth/register/", RegisterView.as_view(), name="register"),
    path("api/v1/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/v1/telegram/link-code/", TelegramLinkCodeView.as_view(), name="telegram-link-code"),
    path("api/v1/telegram/bot/link/", BotLinkView.as_view(), name="telegram-bot-link"),
    path("api/v1/telegram/bot/monitors/", BotMonitorsView.as_view(), name="telegram-bot-monitors"),
    path("api/v1/telegram/bot/incidents/", BotIncidentsView.as_view(), name="telegram-bot-incidents"),
    path("api/v1/", include(router.urls)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
