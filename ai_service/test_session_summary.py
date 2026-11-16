from datetime import date, time
import json
import re
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import Conversation, CustomUser, Message as ConversationMessage
from ai_service.models import SessionSummary
from consultations.models import Consultation, Message as ConsultationMessage


class SessionSummaryTests(TestCase):
    def setUp(self):
        self.patient = CustomUser.objects.create_user(
            username="summary-patient",
            password="test-password",
            user_type="patient",
        )
        self.psychologist = CustomUser.objects.create_user(
            username="summary-psychologist",
            password="test-password",
            user_type="psychologue",
        )
        self.other_psychologist = CustomUser.objects.create_user(
            username="other-summary-psychologist",
            password="test-password",
            user_type="psychologue",
        )
        self.consultation = self.create_consultation(self.psychologist)

    def create_consultation(self, psychologist):
        return Consultation.objects.create(
            patient=self.patient,
            psychologue=psychologist,
            date=date(2026, 10, 20),
            start_time=time(10),
            end_time=time(10, 50),
            duration_minutes=50,
            price="3200.00",
        )

    def add_message(self, consultation, sender, content, message_type="texte"):
        return ConsultationMessage.objects.create(
            consultation=consultation,
            expediteur=sender,
            contenu=content,
            type_message=message_type,
        )

    def valid_provider_output(self):
        return {
            "summary": "La personne décrit une période de stress et les stratégies discutées.",
            "themes": ["stress", "stratégies d'adaptation"],
            "risk_level": "low",
        }

    @patch("ai_service.services._ask")
    def test_transcript_uses_only_text_messages_from_consultation_participants(self, ask):
        from ai_service.services import generate_session_summary

        self.add_message(self.consultation, self.patient, "Je me sens souvent anxieux.")
        self.add_message(
            self.consultation,
            self.psychologist,
            "Parlons des stratégies qui vous aident.",
        )
        other_consultation = self.create_consultation(self.other_psychologist)
        self.add_message(other_consultation, self.patient, "Private text from another appointment.")
        outsider = CustomUser.objects.create_user(
            username="summary-outsider",
            password="test-password",
            user_type="admin",
        )
        self.add_message(self.consultation, outsider, "Out-of-session content.")
        self.add_message(
            self.consultation,
            self.patient,
            "Attachment metadata should not enter the transcript.",
            message_type=ConsultationMessage.TypeMessage.FICHIER,
        )
        conversation = Conversation.objects.create(
            patient=self.patient,
            psychologue=self.psychologist,
        )
        ConversationMessage.objects.create(
            conversation=conversation,
            sender=self.patient,
            content="Unlinked account conversation message.",
        )
        self.consultation.patient_notes = "Private clinical notes are not transcript messages."
        self.consultation.psychologue_notes = "Separate clinical notes."
        self.consultation.save(update_fields=["patient_notes", "psychologue_notes"])
        ask.return_value = self.valid_provider_output()

        result = generate_session_summary(self.consultation.pk)

        self.assertTrue(result["success"])
        transcript = json.loads(ask.call_args.args[1])
        self.assertIn(
            {"speaker": "Patient", "text": "Je me sens souvent anxieux."},
            transcript,
        )
        self.assertIn(
            {"speaker": "Psychologue", "text": "Parlons des stratégies qui vous aident."},
            transcript,
        )
        serialized_transcript = json.dumps(transcript, ensure_ascii=False)
        self.assertNotIn("another appointment", serialized_transcript)
        self.assertNotIn("Out-of-session content", serialized_transcript)
        self.assertNotIn("Attachment metadata", serialized_transcript)
        self.assertNotIn("Unlinked account conversation", serialized_transcript)
        self.assertNotIn("clinical notes", serialized_transcript)
        self.assertIn("untrusted source material", ask.call_args.args[0])
        self.assertIn("Algerian Darija", ask.call_args.args[0])
        ask.assert_called_once()

    @patch("ai_service.services._ask")
    def test_empty_transcript_reports_failure_without_calling_provider(self, ask):
        from ai_service.services import generate_session_summary

        result = generate_session_summary(self.consultation.pk)

        self.assertFalse(result["success"])
        self.assertEqual(result.get("reason"), "no_input")
        self.assertIn("notes", result["error"].lower())
        ask.assert_not_called()
        self.assertFalse(SessionSummary.objects.filter(consultation=self.consultation).exists())

    @patch("ai_service.services._ask")
    def test_falls_back_to_psychologist_notes_when_no_messages(self, ask):
        """Audio/video session: no text messages, but saved notes exist."""
        from ai_service.services import generate_session_summary

        ask.return_value = {
            "summary": "Résumé de la séance.",
            "themes": ["Sommeil"],
            "risk_assessment_status": "insufficient_information",
            "risk_level": None,
        }
        Consultation.objects.filter(pk=self.consultation.pk).update(
            psychologue_notes="Le patient décrit des troubles du sommeil depuis un mois."
        )

        result = generate_session_summary(self.consultation.pk)

        self.assertTrue(result["success"], result)
        ask.assert_called_once()
        # The notes text must be forwarded to the provider.
        sent = ask.call_args[0][1]
        self.assertIn("troubles du sommeil", sent)

    @patch("ai_service.services._ask")
    def test_custom_text_takes_priority_over_notes(self, ask):
        from ai_service.services import generate_session_summary

        ask.return_value = {
            "summary": "Résumé.",
            "themes": ["Sommeil"],
            "risk_assessment_status": "insufficient_information",
            "risk_level": None,
        }
        Consultation.objects.filter(pk=self.consultation.pk).update(
            psychologue_notes="Anciennes notes."
        )

        result = generate_session_summary(
            self.consultation.pk, custom_text="Résumé manuel de la visio."
        )

        self.assertTrue(result["success"], result)
        sent = ask.call_args[0][1]
        self.assertIn("manuel de la visio", sent)
        self.assertNotIn("Anciennes notes", sent)

    @patch("ai_service.services._ask", side_effect=RuntimeError("provider secret details"))
    def test_provider_failure_does_not_create_summary_or_expose_details(self, ask):
        from ai_service.services import generate_session_summary

        self.add_message(self.consultation, self.patient, "A sufficiently useful session message.")
        result = generate_session_summary(self.consultation.pk)

        self.assertFalse(result["success"])
        self.assertNotIn("provider secret details", result["error"])
        self.assertFalse(SessionSummary.objects.filter(consultation=self.consultation).exists())
        ask.assert_called_once()

    @override_settings(AI_PROVIDER="openai")
    @patch("ai_service.services.get_openai_client", return_value=None)
    def test_missing_provider_does_not_create_a_summary(self, get_client):
        from ai_service.services import generate_session_summary

        self.add_message(self.consultation, self.patient, "A sufficiently useful session message.")

        result = generate_session_summary(self.consultation.pk)

        self.assertFalse(result["success"])
        self.assertIn("service is unavailable", result["error"])
        self.assertFalse(SessionSummary.objects.filter(consultation=self.consultation).exists())
        get_client.assert_called_once_with()

    @patch("ai_service.services._ask")
    def test_invalid_provider_output_does_not_create_or_overwrite_summary(self, ask):
        from ai_service.services import generate_session_summary

        self.add_message(self.consultation, self.patient, "A sufficiently useful session message.")
        existing = SessionSummary.objects.create(
            consultation=self.consultation,
            summary="Existing reviewed record",
            themes=["existing"],
            risk_level="medium",
        )
        ask.return_value = {"summary": "", "themes": [], "risk_level": "unknown"}

        result = generate_session_summary(self.consultation.pk)

        self.assertFalse(result["success"])
        self.assertIn("invalid summary", result["error"])
        existing.refresh_from_db()
        self.assertEqual(existing.summary, "Existing reviewed record")
        self.assertEqual(existing.themes, ["existing"])

    @patch("ai_service.services._ask")
    def test_omitted_optional_fields_do_not_retain_stale_summary_content(self, ask):
        from ai_service.services import generate_session_summary

        self.add_message(self.consultation, self.patient, "A sufficiently useful session message.")
        existing = SessionSummary.objects.create(
            consultation=self.consultation,
            summary="Old summary",
            themes=["old theme"],
            emotions=["old emotion"],
            risk_level="medium",
            recommendations="Old recommendation",
            red_flags=["old flag"],
        )
        ask.return_value = self.valid_provider_output()

        result = generate_session_summary(self.consultation.pk)

        self.assertTrue(result["success"])
        existing.refresh_from_db()
        self.assertEqual(existing.summary, self.valid_provider_output()["summary"])
        self.assertEqual(existing.emotions, [])
        self.assertEqual(existing.recommendations, "")
        self.assertEqual(existing.red_flags, [])

    @patch("ai_service.services._ask")
    def test_success_saves_provider_draft_and_identifies_review_requirement(self, ask):
        from ai_service.services import generate_session_summary

        self.add_message(self.consultation, self.patient, "A sufficiently useful session message.")
        provider_output = self.valid_provider_output()
        provider_output.update({
            "emotions": ["stress"],
            "progress_notes": "The patient identified a coping strategy.",
            "recommendations": "Review the strategy at the next session.",
            "red_flags": [],
        })
        ask.return_value = provider_output

        result = generate_session_summary(self.consultation.pk)

        self.assertTrue(result["success"])
        self.assertTrue(result["is_draft"])
        self.assertTrue(result["requires_professional_review"])
        summary = SessionSummary.objects.get(consultation=self.consultation)
        self.assertEqual(summary.summary, provider_output["summary"])
        self.assertEqual(summary.themes, provider_output["themes"])
        self.assertEqual(summary.emotions, provider_output["emotions"])
        self.assertEqual(summary.progress_notes, provider_output["progress_notes"])
        self.assertEqual(summary.recommendations, provider_output["recommendations"])
        self.assertEqual(summary.risk_level, "low")

    def test_summary_generation_is_post_only_and_requires_assigned_psychologist(self):
        url = reverse(
            "ai_service:generate_session_summary",
            args=[self.consultation.pk],
        )
        self.assertEqual(self.client.post(url).status_code, 302)

        self.client.force_login(self.patient)
        self.assertEqual(self.client.post(url).status_code, 403)

        self.client.force_login(self.other_psychologist)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_patient_file_and_sentiment_analysis_require_an_assigned_psychologist(self):
        self.client.force_login(self.other_psychologist)

        patient_file = self.client.get(
            reverse("ai_service:patient_file", args=[self.patient.pk]),
        )
        sentiment_url = reverse("ai_service:analyze_sentiment", args=[self.consultation.pk])
        sentiment_response = self.client.post(sentiment_url)

        self.assertEqual(patient_file.status_code, 404)
        self.assertEqual(sentiment_response.status_code, 404)

    @patch("ai_service.services._ask")
    def test_assigned_psychologist_can_generate_summary_as_draft(self, ask):
        self.add_message(self.consultation, self.patient, "A sufficiently useful session message.")
        ask.return_value = self.valid_provider_output()
        self.client.force_login(self.psychologist)
        url = reverse(
            "ai_service:generate_session_summary",
            args=[self.consultation.pk],
        )

        response = self.client.post(url)

        self.assertRedirects(
            response,
            reverse("ai_service:patient_file", args=[self.patient.pk]),
        )
        self.assertTrue(SessionSummary.objects.filter(consultation=self.consultation).exists())
        self.assertContains(
            self.client.get(reverse("ai_service:patient_file", args=[self.patient.pk])),
            "non un diagnostic",
        )

    @patch("ai_service.services._ask")
    def test_sentiment_analysis_uses_only_patient_text_and_persists_result(self, ask):
        from ai_service.services import analyze_session_sentiment

        self.add_message(self.consultation, self.patient, "Je me sens stressé mais motivé.")
        self.add_message(self.consultation, self.psychologist, "Que souhaitez-vous travailler ?")
        self.add_message(
            self.consultation,
            self.patient,
            "document metadata",
            message_type=ConsultationMessage.TypeMessage.FICHIER,
        )
        ask.return_value = {
            "sentiment": "negative",
            "emotions": ["stress", "motivation"],
            "risk_level": "low",
            "themes": ["stress"],
            "keywords": ["motivé"],
            "message_analyses": [
                {"message": 1, "sentiment": "negative", "emotions": ["stress"]},
            ],
        }

        result = analyze_session_sentiment(self.consultation.pk)

        self.assertTrue(result["success"])
        self.assertEqual(result["sentiment"], "negative")
        self.assertEqual(result["emotions"], ["stress", "motivation"])
        analyzed_messages = json.loads(ask.call_args.args[1])
        self.assertEqual(
            analyzed_messages,
            [
                {"message": 1, "text": "Je me sens stressé mais motivé."},
            ],
        )
        self.assertIn("Analysez les messages du patient suivants en français.", ask.call_args.args[0])
        self.assertEqual(len(result["message_analyses"]), 1)
        saved = SessionSummary.objects.get(consultation=self.consultation)
        self.assertEqual(saved.sentiment, "negative")
        self.assertEqual(saved.emotions, ["stress", "motivation"])
        self.assertEqual(saved.themes, ["stress"])

    @override_settings(AI_PROVIDER="openai")
    @patch("ai_service.services._ask")
    def test_invalid_provider_key_returns_actionable_error_without_exposing_credentials(self, ask):
        class InvalidProviderKey(Exception):
            status_code = 401
            code = "invalid_api_key"

        ask.side_effect = InvalidProviderKey()
        self.add_message(self.consultation, self.patient, "A synthetic patient statement for testing.")

        from ai_service.services import analyze_session_sentiment
        result = analyze_session_sentiment(self.consultation.pk)

        self.assertFalse(result["success"])
        self.assertIn("rejected the configured API key", result["error"])
        self.assertIn("OPENAI_API_KEY", result["error"])
        self.assertNotIn("synthetic patient statement", result["error"])
        self.assertFalse(SessionSummary.objects.filter(consultation=self.consultation).exists())

    @patch("ai_service.services._ask")
    def test_assigned_psychologist_can_run_sentiment_analysis_from_patient_file(self, ask):
        self.add_message(self.consultation, self.patient, "I have felt worried throughout this week.")
        ask.return_value = {
            "sentiment": "negative",
            "emotions": ["anxiety"],
            "risk_level": "low",
            "themes": ["work stress"],
            "keywords": ["worry"],
        }
        self.client.force_login(self.psychologist)
        url = reverse("ai_service:analyze_sentiment", args=[self.consultation.pk])

        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sentiment"], "negative")
        self.assertTrue(SessionSummary.objects.filter(consultation=self.consultation).exists())
        self.assertContains(
            self.client.get(reverse("ai_service:patient_file", args=[self.patient.pk])),
            "Analyser les sentiments",
        )

    @patch("ai_service.views.analyze_session_sentiment")
    def test_patient_file_disables_caching_and_accepts_its_csrf_token(self, analyze):
        analyze.return_value = {
            "success": True,
            "sentiment": "neutral",
            "emotions": [],
            "themes": [],
            "keywords": [],
            "message_analyses": [],
            "risk_level": "low",
            "risk_assessment_status": "assessed",
            "requires_professional_review": True,
        }
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.psychologist)

        patient_file = csrf_client.get(
            reverse("ai_service:patient_file", args=[self.patient.pk]),
        )

        self.assertIn("no-store", patient_file.headers["Cache-Control"])
        token_match = re.search(
            r'name="csrfmiddlewaretoken" value="([^"]+)"',
            patient_file.content.decode(),
        )
        self.assertIsNotNone(token_match)

        response = csrf_client.post(
            reverse("ai_service:analyze_sentiment", args=[self.consultation.pk]),
            HTTP_X_CSRFTOKEN=token_match.group(1),
        )

        self.assertEqual(response.status_code, 200)
        analyze.assert_called_once_with(self.consultation.pk, custom_text=None)

    @patch("ai_service.views.generate_session_summary")
    def test_chat_summary_api_accepts_uuid_and_returns_provider_summary(self, generate):
        generate.return_value = {
            "success": True,
            "data": {
                "summary": "A concise reviewed draft.",
                "themes": ["stress"],
                "emotions": ["anxiety"],
            },
        }
        self.client.force_login(self.psychologist)
        url = reverse("ai_service:ai_generate_summary", args=[self.consultation.pk])

        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"], "A concise reviewed draft.")
        self.assertEqual(response.json()["themes"], ["stress"])
        self.assertEqual(response.json()["emotions"], ["anxiety"])
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.ai_summary, "A concise reviewed draft.")
        generate.assert_called_once_with(self.consultation.pk, custom_text=None)

    @override_settings(AI_PROVIDER="openai")
    @patch("ai_service.services._ask")
    def test_sentiment_endpoint_reports_invalid_provider_key_actionably(self, ask):
        class InvalidProviderKey(Exception):
            status_code = 401
            code = "invalid_api_key"

        self.add_message(self.consultation, self.patient, "Synthetic test message only.")
        ask.side_effect = InvalidProviderKey()
        self.client.force_login(self.psychologist)

        response = self.client.post(
            reverse("ai_service:analyze_sentiment", args=[self.consultation.pk]),
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("OPENAI_API_KEY", response.json()["message"])
        self.assertNotIn("Synthetic test message", response.content.decode())
