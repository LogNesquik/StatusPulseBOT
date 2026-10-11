from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from .models import CheckResult, Incident, Monitor
from .tasks import _check_url

User = get_user_model()


class MonitorApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="test-password-123")
        self.other_user = User.objects.create_user(username="bob", password="test-password-123")
        self.client.force_authenticate(self.user)

    def test_user_only_sees_own_monitors(self):
        own = Monitor.objects.create(owner=self.user, name="My API", url="https://example.com/health")
        Monitor.objects.create(owner=self.other_user, name="Other API", url="https://example.org/health")
        response = self.client.get("/api/v1/monitors/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["id"] for row in response.data["results"]], [own.id])

    def test_monitor_creation_rejects_loopback_url(self):
        response = self.client.post("/api/v1/monitors/", {
            "name": "Private target", "url": "http://127.0.0.1:8000/health/", "interval_seconds": 300,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("url", response.data)

    def test_user_cannot_fetch_another_users_monitor(self):
        monitor = Monitor.objects.create(owner=self.other_user, name="Private API", url="https://example.org/health")
        response = self.client.get(f"/api/v1/monitors/{monitor.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_stats_returns_uptime_and_average_latency(self):
        monitor = Monitor.objects.create(owner=self.user, name="My API", url="https://example.com/health")
        now = timezone.now()
        CheckResult.objects.create(monitor=monitor, status=CheckResult.Status.UP, status_code=200, response_time_ms=100, checked_at=now)
        CheckResult.objects.create(monitor=monitor, status=CheckResult.Status.UP, status_code=200, response_time_ms=300, checked_at=now)
        CheckResult.objects.create(monitor=monitor, status=CheckResult.Status.DOWN, error_message="timeout", checked_at=now)
        response = self.client.get(f"/api/v1/monitors/{monitor.id}/stats/?days=7")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_checks"], 3)
        self.assertEqual(response.data["uptime_percentage"], 66.67)
        self.assertEqual(response.data["average_response_time_ms"], 200)

    def test_invalid_stats_period_is_rejected(self):
        monitor = Monitor.objects.create(owner=self.user, name="My API", url="https://example.com/health")
        response = self.client.get(f"/api/v1/monitors/{monitor.id}/stats/?days=999")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class UrlCheckTests(APITestCase):
    @patch("apps.monitoring.tasks._assert_public_destination")
    @patch("apps.monitoring.tasks.httpx.get")
    def test_2xx_response_is_up(self, mocked_get, _mocked_destination):
        response = Mock()
        response.status_code = 200
        mocked_get.return_value = response
        result = _check_url("https://example.com/health", 5, None)
        self.assertEqual(result["status"], CheckResult.Status.UP)
        self.assertEqual(result["status_code"], 200)
        self.assertGreaterEqual(result["response_time_ms"], 0)

    @patch("apps.monitoring.tasks._assert_public_destination")
    @patch("apps.monitoring.tasks.httpx.get")
    def test_wrong_expected_status_is_down(self, mocked_get, _mocked_destination):
        response = Mock()
        response.status_code = 200
        mocked_get.return_value = response
        result = _check_url("https://example.com/health", 5, 204)
        self.assertEqual(result["status"], CheckResult.Status.DOWN)
        self.assertIn("Unexpected HTTP status", result["error_message"])

    @patch("apps.monitoring.tasks._assert_public_destination", side_effect=ValueError("private target"))
    def test_private_destination_is_rejected_without_http_request(self, _mocked_destination):
        with patch("apps.monitoring.tasks.httpx.get") as mocked_get:
            result = _check_url("http://127.0.0.1", 5, None)
        mocked_get.assert_not_called()
        self.assertEqual(result["status"], CheckResult.Status.DOWN)
