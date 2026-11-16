"""Focused tests for F2 sentiment language-alias resolution.

Verifies that human-readable language labels resolve to the correct
SENTIMENT_PROMPTS key, and that genuinely unknown values fall back to French.
Provider calls are mocked; no real API calls are made.
"""

from datetime import date, time
from unittest.mock import patch

from django.test import TestCase

from accounts.models import CustomUser
from ai_service.services import (
    SENTIMENT_PROMPTS,
    analyze_session_sentiment,
)
from consultations.models import Consultation, Message as ConsultationMessage


class SentimentLanguageAliasTests(TestCase):
    def setUp(self):
        self.patient = CustomUser.objects.create_user(
            username="alias-patient", password="x", user_type="patient"
        )
        self.psychologist = CustomUser.objects.create_user(
            username="alias-psychologist", password="x", user_type="psychologue"
        )
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            psychologue=self.psychologist,
            date=date(2026, 10, 20),
            start_time=time(10),
            end_time=time(10, 50),
            duration_minutes=50,
            price="3200.00",
        )
        ConsultationMessage.objects.create(
            consultation=self.consultation,
            expediteur=self.patient,
            contenu="Je me sens stressé.",
            type_message=ConsultationMessage.TypeMessage.TEXTE,
        )

    def _run(self, language):
        with patch("ai_service.services._ask") as ask:
            ask.return_value = {
                "sentiment": "negative",
                "emotions": ["stress"],
                "risk_level": "low",
                "themes": ["stress"],
                "keywords": ["stress"],
            }
            result = analyze_session_sentiment(self.consultation.pk, language=language)
            self.assertTrue(result["success"])
            return ask.call_args.args[0]

    def test_arabic_selects_ar_prompt(self):
        self.assertEqual(self._run("arabic"), SENTIMENT_PROMPTS["ar"])

    def test_english_selects_en_prompt(self):
        self.assertEqual(self._run("english"), SENTIMENT_PROMPTS["en"])

    def test_french_selects_fr_prompt(self):
        self.assertEqual(self._run("french"), SENTIMENT_PROMPTS["fr"])

    def test_darija_selects_darija_prompt(self):
        self.assertEqual(self._run("darija"), SENTIMENT_PROMPTS["darija"])

    def test_canonical_ar_fr_en_resolve_to_themselves(self):
        self.assertEqual(self._run("ar"), SENTIMENT_PROMPTS["ar"])
        self.assertEqual(self._run("fr"), SENTIMENT_PROMPTS["fr"])
        self.assertEqual(self._run("en"), SENTIMENT_PROMPTS["en"])

    def test_default_language_is_french(self):
        self.assertEqual(self._run("fr"), SENTIMENT_PROMPTS["fr"])

    def test_unknown_language_falls_back_to_french(self):
        self.assertEqual(self._run("klingon"), SENTIMENT_PROMPTS["fr"])