import json
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import resolve, reverse

from accounts.models import CustomUser


class AnalyzeViewTests(TestCase):
    def setUp(self):
        self.psychologist = CustomUser.objects.create_user(
            username="ai-analysis-psychologist",
            password="test-password",
            user_type="psychologue",
        )
        self.patient = CustomUser.objects.create_user(
            username="ai-analysis-patient",
            password="test-password",
            user_type="patient",
        )
        self.url = reverse("ai_service:analyze_consultation")
        self.payload = {
            "text": "The patient described recent stress and difficulty sleeping.",
            "language": "en",
        }

    def post_json(self, client=None, payload=None):
        return (client or self.client).post(
            self.url,
            data=json.dumps(self.payload if payload is None else payload),
            content_type="application/json",
        )

    def test_analysis_url_resolves_to_request_handler(self):
        self.assertEqual(resolve(self.url).func.__name__, "analyze_view")

    def test_analysis_requires_authenticated_psychologist(self):
        self.assertEqual(self.post_json().status_code, 302)

        self.client.force_login(self.patient)
        self.assertEqual(self.post_json().status_code, 403)

    def test_analysis_requires_post_and_csrf(self):
        self.client.force_login(self.psychologist)
        self.assertEqual(self.client.get(self.url).status_code, 405)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.psychologist)
        self.assertEqual(self.post_json(client=csrf_client).status_code, 403)

    def test_analysis_validates_json_shape_text_length_and_language(self):
        self.client.force_login(self.psychologist)

        malformed = self.client.post(
            self.url, data="{", content_type="application/json"
        )
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(self.post_json(payload=[]).status_code, 400)
        self.assertEqual(self.post_json(payload={"text": "short"}).status_code, 400)
        self.assertEqual(
            self.post_json(
                payload={"text": "A sufficiently long sample text.", "language": "xx"}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.post_json(payload={"text": "x" * 20001}).status_code,
            413,
        )
        self.assertEqual(
            self.client.post(self.url, data={"text": self.payload["text"]}).status_code,
            415,
        )

    @patch("ai_service.views.analyze_consultation")
    def test_analysis_returns_provider_result(self, analyze):
        analyze.return_value = {
            "success": True,
            "summary": "A reviewed summary.",
            "emotions": ["stress"],
            "keywords": ["sleep"],
        }
        self.client.force_login(self.psychologist)

        response = self.post_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["analysis"]["summary"], "A reviewed summary.")
        analyze.assert_called_once_with(self.payload["text"], language="en")

    @patch("ai_service.views.analyze_consultation")
    def test_analysis_reports_provider_failure_without_mock_success(self, analyze):
        analyze.return_value = {"success": False, "error": "provider details"}
        self.client.force_login(self.psychologist)

        response = self.post_json()

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["success"])
        self.assertNotIn("provider details", response.content.decode())

    @patch("ai_service.services.get_groq_client", return_value=None)
    @patch("ai_service.services.get_selected_provider", return_value="groq")
    def test_service_does_not_return_a_mock_analysis_when_unconfigured(
        self, get_selected_provider, get_groq_client
    ):
        from .services import analyze_consultation

        result = analyze_consultation(self.payload["text"])

        self.assertFalse(result["success"])
        self.assertIn("error", result)
