"""
Isolated Django test for Full Session Analysis frontend integration.

Uses unittest.mock.patch on consultations.access.has_room_time_access
and consultations.access.consultation_has_ended to bypass time-window
checks WITHOUT modifying production code, without changing dates, and
without creating/modifying real database records
(test database is temporary in-memory and destroyed after the test).

Run with: python manage.py test consultations.tests.test_full_session_analysis_frontend --verbosity 2
"""

from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from consultations.models import Consultation, PaymentRecord

User = get_user_model()

CONSULTATION_ID = "11635d5c-23e0-430d-af63-0de24216cb96"


class FullSessionAnalysisFrontendTest(TestCase):
    """Verify the Full Session Analysis button is rendered correctly
    in the consultation room for psychologist and hidden for patient,
    using mocked access functions (no production code changes)."""

    def setUp(self):
        self.client = Client()
        # Create test users in the temporary test database
        self.psychologist = User.objects.create_user(
            username="psy-test",
            email="psy-test@mindwell.test",
            password="test-pass-123",
            user_type="psychologue",
        )
        self.patient = User.objects.create_user(
            username="pat-test",
            email="pat-test@mindwell.test",
            password="test-pass-123",
            user_type="patient",
        )
        # Create a confirmed consultation in the temporary test database
        from django.utils import timezone
        now = timezone.now()
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            psychologue=self.psychologist,
            date=now.date(),
            start_time=now.time(),
            duration_minutes=60,
            session_type=Consultation.SessionType.CHAT,
            status=Consultation.Status.CONFIRMED,
            payment_status=Consultation.PaymentStatus.PAID,
            price="3000.00",
        )
        # Create payment record required by the view
        PaymentRecord.objects.create(
            consultation=self.consultation,
            amount=self.consultation.price,
            method="CIB",
            status="success",
            transaction_ref="TEST-FRONTEND-001",
        )

    @patch("consultations.views.has_room_time_access", return_value=True)
    @patch("consultations.views.consultation_has_ended", return_value=False)
    def test_analyze_full_button_visible_to_psychologist(self, mock_ended, mock_access):
        """The #btn-analyze-full button must appear in the psychologist's room."""
        self.client.force_login(self.psychologist)
        url = reverse("consultations:consultation_chat", args=[self.consultation.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn('id="btn-analyze-full"', html,
                      "Button #btn-analyze-full must be present for psychologist")
        self.assertIn('analyze-full/', html,
                      "Button must link to /analyze-full/ endpoint")
        self.assertIn('id="ai-full-analysis-result"', html,
                      "Result container #ai-full-analysis-result must be present")
        self.assertIn('full-analysis-summary', html)
        self.assertIn('full-analysis-themes', html)
        self.assertIn('full-analysis-emotions', html)
        self.assertIn('full-analysis-keywords', html)
        self.assertIn('full-analysis-emotional-evolution', html)
        self.assertIn('full-analysis-risk-level', html)
        mock_access.assert_called_once()

    @patch("consultations.views.has_room_time_access", return_value=True)
    @patch("consultations.views.consultation_has_ended", return_value=False)
    def test_analyze_full_button_hidden_to_patient(self, mock_ended, mock_access):
        """The #btn-analyze-full button must NOT appear for a patient."""
        self.client.force_login(self.patient)
        url = reverse("consultations:consultation_chat", args=[self.consultation.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertNotIn('id="btn-analyze-full"', html,
                         "Button #btn-analyze-full must NOT be present for patient")
        mock_access.assert_called_once()

    @patch("consultations.views.has_room_time_access", return_value=True)
    @patch("consultations.views.consultation_has_ended", return_value=False)
    def test_js_handler_sends_lang_parameter(self, mock_ended, mock_access):
        """The JS handler must send the language parameter to the endpoint."""
        self.client.force_login(self.psychologist)
        url = reverse("consultations:consultation_chat", args=[self.consultation.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        # The JS handler should call analyze-full with ?lang= parameter
        self.assertIn("/analyze-full/?lang=", html,
                      "JS handler must send lang query parameter")
        mock_access.assert_called_once()
