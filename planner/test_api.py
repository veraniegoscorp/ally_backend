from datetime import datetime, time, timedelta, timezone

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import AvailabilityWindow, GoalEvent, StudyBlock, StudyCategory


class PlannerAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="student",
            password="Secure-test-password-2026",
        )
        self.other_user = user_model.objects.create_user(
            username="other",
            password="Secure-test-password-2026",
        )
        self.category = StudyCategory.objects.create(user=self.user, name="Examen")
        self.other_category = StudyCategory.objects.create(
            user=self.other_user,
            name="Privada",
        )
        self.client.force_authenticate(self.user)

    def test_api_requires_authentication_and_scopes_resources_to_user(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get("/api/categories/").status_code, 401)

        self.client.force_authenticate(self.user)
        response = self.client.get("/api/categories/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["name"] for item in response.data], ["Examen"])
        self.assertEqual(
            self.client.patch(
                f"/api/categories/{self.other_category.pk}/",
                {"name": "Modified"},
            ).status_code,
            404,
        )

    def test_goal_cannot_reference_another_users_category(self):
        response = self.client.post(
            "/api/goals/",
            {
                "category": self.other_category.pk,
                "title": "Meta",
                "deadline": "2027-01-08T12:00:00Z",
                "minimum_study_minutes": 60,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(GoalEvent.objects.exists())

    def test_register_and_jwt_login(self):
        register_response = self.client.post(
            "/api/auth/register/",
            {
                "username": "new-student",
                "email": "new@example.com",
                "password": "Another-secure-password-2026",
            },
        )
        self.assertEqual(register_response.status_code, 201)

        self.client.force_authenticate(user=None)
        login_response = self.client.post(
            "/api/auth/login/",
            {
                "username": "new-student",
                "password": "Another-secure-password-2026",
            },
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertIn("access", login_response.data)
        self.assertIn("refresh", login_response.data)

    def test_scheduling_and_drag_move_respect_availability_and_existing_blocks(self):
        now = datetime.now(timezone.utc)
        local_today = now.date()
        for weekday in range(7):
            AvailabilityWindow.objects.create(
                user=self.user,
                title=f"Available {weekday}",
                weekday=weekday,
                starts_at=time(0),
                ends_at=time(23, 59),
                is_available=True,
            )

        goal = GoalEvent.objects.create(
            user=self.user,
            category=self.category,
            title="Preparar examen",
            deadline=now + timedelta(days=3),
            minimum_study_minutes=60,
        )
        schedule_response = self.client.post(f"/api/goals/{goal.pk}/schedule/")
        self.assertEqual(schedule_response.status_code, 201, schedule_response.data)
        self.assertEqual(sum(block["duration_minutes"] for block in schedule_response.data), 60)

        start = datetime.combine(
            local_today + timedelta(days=4),
            time(10),
            tzinfo=timezone.utc,
        )
        manual_goal = GoalEvent.objects.create(
            user=self.user,
            category=self.category,
            title="Otro examen",
            deadline=start + timedelta(days=1),
            minimum_study_minutes=30,
        )
        payload = {
            "goal": manual_goal.pk,
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(minutes=30)).isoformat(),
        }
        first = self.client.post("/api/blocks/", payload)
        self.assertEqual(first.status_code, 201, first.data)

        overlapping = self.client.post(
            "/api/blocks/",
            {
                **payload,
                "starts_at": (start + timedelta(minutes=15)).isoformat(),
                "ends_at": (start + timedelta(minutes=45)).isoformat(),
            },
        )
        self.assertEqual(overlapping.status_code, 400)
        self.assertEqual(StudyBlock.objects.filter(user=self.user).count(), 3)
