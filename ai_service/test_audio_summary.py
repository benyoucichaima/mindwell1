import json
import os
import tempfile
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase

from accounts.models import CustomUser
from consultations.models import Consultation
from .audio_summary import generate_ai_summary


class GenerateAudioSummaryTests(TestCase):
    def setUp(self):
        self.patient = CustomUser.objects.create_user(
            username="audio-summary-patient",
            password="test-password",
            user_type="patient",
        )
        self.psychologist = CustomUser.objects.create_user(
            username="audio-summary-doctor",
            password="test-password",
            user_type="psychologue",
        )
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            psychologue=self.psychologist,
            date=date(2026, 11, 1),
            start_time=time(10),
            end_time=time(10, 50),
            duration_minutes=50,
            price="3200.00",
        )
        self.consultation.audio_transcription_consent = True
        self.consultation.save(update_fields=["audio_transcription_consent"])

    @patch("ai_service.audio_summary.get_openai_client")
    def test_audio_is_not_processed_without_patient_consent(self, get_client):
        self.consultation.audio_transcription_consent = False
        self.consultation.save(update_fields=["audio_transcription_consent"])

        result = generate_ai_summary(
            str(self.consultation.pk),
            "C:\\missing\\mindwell-audio-file.wav",
        )

        self.assertFalse(result["success"])
        self.assertEqual(
            result["error"],
            "Patient consent is required for audio transcription.",
        )
        get_client.assert_not_called()

    @patch("ai_service.audio_summary.get_openai_client")
    def test_transcribes_parses_and_saves_doctor_only_json(self, get_client):
        summary = {"chief_complaints": ["Stress"], "risk_flags": []}
        client = SimpleNamespace(
            audio=SimpleNamespace(
                transcriptions=SimpleNamespace(
                    create=Mock(return_value=SimpleNamespace(text="Patient: stress"))
                )
            ),
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=Mock(
                        return_value=SimpleNamespace(
                            choices=[
                                SimpleNamespace(
                                    message=SimpleNamespace(content=f"```json\n{json.dumps(summary)}\n```")
                                )
                            ]
                        )
                    )
                )
            ),
        )
        get_client.return_value = client
        with tempfile.NamedTemporaryFile(delete=False) as audio_file:
            audio_path = audio_file.name
        try:
            result = generate_ai_summary(str(self.consultation.pk), audio_path)
        finally:
            os.unlink(audio_path)

        self.assertTrue(result["success"])
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.doctor_only_ai_summary, summary)
        client.audio.transcriptions.create.assert_called_once()
        client.chat.completions.create.assert_called_once()

    @patch("ai_service.audio_summary.get_openai_client")
    def test_missing_audio_returns_failure_without_calling_provider(self, get_client):
        client = SimpleNamespace(
            audio=SimpleNamespace(
                transcriptions=SimpleNamespace(create=Mock())
            )
        )
        get_client.return_value = client
        result = generate_ai_summary(
            str(self.consultation.pk),
            "C:\\missing\\mindwell-audio-file.wav",
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Audio file not found.")
        client.audio.transcriptions.create.assert_not_called()

    @patch("ai_service.audio_summary.get_openai_client")
    def test_invalid_json_is_not_saved(self, get_client):
        client = SimpleNamespace(
            audio=SimpleNamespace(
                transcriptions=SimpleNamespace(
                    create=Mock(return_value=SimpleNamespace(text="Transcript"))
                )
            ),
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=Mock(
                        return_value=SimpleNamespace(
                            choices=[
                                SimpleNamespace(
                                    message=SimpleNamespace(content="```json\n{broken}\n```")
                                )
                            ]
                        )
                    )
                )
            ),
        )
        get_client.return_value = client
        with tempfile.NamedTemporaryFile(delete=False) as audio_file:
            audio_path = audio_file.name
        try:
            result = generate_ai_summary(str(self.consultation.pk), audio_path)
        finally:
            os.unlink(audio_path)

        self.assertFalse(result["success"])
        self.assertEqual(
            result["error"],
            "The AI provider returned invalid JSON.",
        )
        self.consultation.refresh_from_db()
        self.assertIsNone(self.consultation.doctor_only_ai_summary)
