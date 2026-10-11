from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status

User = get_user_model()

class RegisterApiTests(APITestCase):
    def test_register_creates_user(self):
        response = self.client.post("/api/v1/auth/register/", {
            "username": "test-user",
            "email": "test@example.com",
            "password": "A-long-test-password-2026!",
            "password_confirm": "A-long-test-password-2026!",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username="test-user").exists())
        self.assertNotIn("password", response.data)

    def test_register_rejects_mismatched_passwords(self):
        response = self.client.post("/api/v1/auth/register/", {
            "username": "test-user",
            "email": "test@example.com",
            "password": "A-long-test-password-2026!",
            "password_confirm": "not-the-same-password",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
