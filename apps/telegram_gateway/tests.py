from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.monitoring.models import TelegramConnection, TelegramLinkCode

User = get_user_model()

@override_settings(BOT_INTERNAL_TOKEN="test-internal-secret")
class TelegramLinkTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="telegram-user", password="test-password-123")
        self.code = TelegramLinkCode.objects.create(
            user=self.user,
            code="ABC123XYZ9",
            expires_at=timezone.now() + timedelta(minutes=10),
        )

    def test_link_requires_internal_token(self):
        response = self.client.post("/api/v1/telegram/bot/link/", {"code": self.code.code, "chat_id": 12345}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_valid_code_links_telegram_and_is_one_time(self):
        self.client.credentials(HTTP_X_BOT_TOKEN="test-internal-secret")
        response = self.client.post("/api/v1/telegram/bot/link/", {"code": self.code.code, "chat_id": 12345}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(TelegramConnection.objects.filter(user=self.user, chat_id=12345).exists())
        second_response = self.client.post("/api/v1/telegram/bot/link/", {"code": self.code.code, "chat_id": 12345}, format="json")
        self.assertEqual(second_response.status_code, status.HTTP_400_BAD_REQUEST)
