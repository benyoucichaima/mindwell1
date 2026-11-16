"""
Unit tests for validate_risk_consistency validator.
All tests use mocks only. No real API calls.
"""

from __future__ import annotations

import json
from django.test import TestCase

from ai_service.evaluate_dataset_gemini import (
    validate_risk_consistency,
    run_quality_checks,
)


class ValidateRiskConsistencyTests(TestCase):
    """اختبارات لـ validate_risk_consistency."""

    def setUp(self):
        # Helper to create base conversation structure
        self.base_conversation = {
            "id": "test_001",
            "scenario_id": 99,
            "language": "fr",
            "theme": "Test",
            "messages": [],
        }

    def _make_conv(self, messages, language="fr"):
        """Create conversation dict with given messages."""
        conv = dict(self.base_conversation)
        conv["messages"] = messages
        conv["language"] = language
        return conv

    def _make_result(self, risk_level, summary="", emotional_evolution=""):
        """Create result dict with given risk_level."""
        return {
            "success": True,
            "summary": summary,
            "themes": ["test"],
            "emotions": ["test"],
            "keywords": ["test"],
            "emotional_evolution": emotional_evolution,
            "risk_level": risk_level,
        }

    # ============================================================
    # HIGH risk tests
    # ============================================================

    def test_high_explicit_suicidal_ideation_triggers_no_warning(self):
        """Explicit suicidal ideation with HIGH risk_level should not warn."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "Je veux me tuer."},
            {"speaker": "psychologue", "content": "Écoutez-moi..."},
        ])
        result = self._make_result("high", "Patient exprime désir de suicide.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertEqual(len(warnings), 0)

    def test_high_explicit_self_harm_triggers_no_warning(self):
        """Explicit self-harm intent with HIGH risk_level should not warn."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "Je vais me faire du mal ce soir."},
        ])
        result = self._make_result("high", "Patient planifie automutilation.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertEqual(len(warnings), 0)

    def test_high_without_indicators_triggers_warning(self):
        """HIGH risk_level without explicit ideation in transcript should warn."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "Je suis très anxieux."},
        ])
        result = self._make_result("high", "Patient très anxieux.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertTrue(len(warnings) > 0)
        self.assertTrue(any("risk_level=high but no explicit" in w for w in warnings))

    def test_high_negated_statement_not_counted(self):
        """Negated suicidal statement should not count as HIGH indicator."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "Je ne veux pas me tuer, ce sont juste des pensées."},
        ])
        result = self._make_result("high", "Patient a des pensées sombres.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertTrue(len(warnings) > 0)
        self.assertTrue(any("risk_level=high but no explicit" in w for w in warnings))

    def test_high_arabic_explicit_ideation(self):
        """Arabic explicit suicidal ideation should be detected."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "أريد أن أقتل نفسي."},
        ], language="ar")
        result = self._make_result("high", "Patient exprime idéation suicidaire.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertEqual(len(warnings), 0)

    def test_high_english_explicit_ideation(self):
        """English explicit suicidal ideation should be detected."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "I want to kill myself."},
        ], language="en")
        result = self._make_result("high", "Patient expresses suicidal ideation.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertEqual(len(warnings), 0)

    def test_high_darija_explicit_ideation(self):
        """Darija explicit suicidal ideation should be detected."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "بغيت نقتل روحي."},
        ], language="ar")
        result = self._make_result("high", "Patient exprime idéation suicidaire en darija.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertEqual(len(warnings), 0)

    # ============================================================
    # MEDIUM risk tests
    # ============================================================

    def test_medium_explicit_hopelessness_triggers_no_warning(self):
        """Explicit hopelessness with MEDIUM risk_level should not warn."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "Plus rien n'a de sens. J'abandonne complètement."},
        ])
        result = self._make_result("medium", "Patient exprime désespoir total.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertEqual(len(warnings), 0)

    def test_medium_substance_misuse_triggers_no_warning(self):
        """Explicit substance misuse with MEDIUM risk_level should not warn."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "Je bois jusqu'à m'évanouir chaque soir."},
        ])
        result = self._make_result("medium", "Patient utilise alcool pour coping.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertEqual(len(warnings), 0)

    def test_medium_loss_of_control_triggers_no_warning(self):
        """Explicit loss of safety control with MEDIUM risk_level should not warn."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "Je ne me fais plus confiance. J'ai été proche de passer à l'acte."},
        ])
        result = self._make_result("medium", "Patient perd contrôle sécurité.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertEqual(len(warnings), 0)

    def test_medium_without_indicators_triggers_warning(self):
        """MEDIUM risk_level without explicit indicators should warn."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "Je suis anxieux et je dors mal."},
        ])
        result = self._make_result("medium", "Patient anxieux avec troubles sommeil.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertTrue(len(warnings) > 0)
        self.assertTrue(any("risk_level=medium but no explicit" in w for w in warnings))

    def test_medium_arabic_hopelessness(self):
        """Arabic explicit hopelessness with MEDIUM should not warn."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "لم يعد لأي شيء معنى. استسلمت تماماً."},
        ], language="ar")
        result = self._make_result("medium", "Patient exprime désespoir total en arabe.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertEqual(len(warnings), 0)

    def test_medium_darija_hopelessness(self):
        """Darija explicit hopelessness with MEDIUM should not warn."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "ما بقاش في شي معنى. مشيت فيها، ما باقيش نقدر."},
        ], language="ar")
        result = self._make_result("medium", "Patient exprime désespoir en darija.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertEqual(len(warnings), 0)

    # ============================================================
    # LOW risk tests
    # ============================================================

    def test_low_anxiety_impairment_no_warning(self):
        """Anxiety with functional impairment, LOW risk_level should not warn."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "Je suis anxieux tout le temps, je dors mal, le travail est devenu impossible."},
        ])
        result = self._make_result("low", "Patient anxieux avec troubles sommeil.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        # May have insufficient-evidence warning but not medium/high mismatch
        high_medium_warnings = [w for w in warnings if "risk_level=low but explicit" in w]
        self.assertEqual(len(high_medium_warnings), 0)

    def test_low_grief_with_safety_statement_no_warning(self):
        """Grief with explicit safety statement, LOW risk_level should not warn."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "Ma mère est morte. Je pleure mais je n'ai pas envie de me faire du mal."},
        ])
        result = self._make_result("low", "Deuil sans idéation suicidaire.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        high_medium_warnings = [w for w in warnings if "risk_level=low but explicit" in w]
        self.assertEqual(len(high_medium_warnings), 0)

    def test_low_burnout_with_safety_statement_no_warning(self):
        """Burnout with explicit safety statement, LOW risk_level should not warn."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "Je suis épuisé par le travail. Je n'ai jamais pensé à me faire du mal."},
        ])
        result = self._make_result("low", "Burnout sans risque.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        high_medium_warnings = [w for w in warnings if "risk_level=low but explicit" in w]
        self.assertEqual(len(high_medium_warnings), 0)

    def test_low_with_explicit_hopelessness_triggers_warning(self):
        """LOW risk_level with explicit hopelessness should warn if not acknowledged."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "Plus rien n'a de sens. J'abandonne complètement."},
        ])
        result = self._make_result("low", "Patient va bien.")  # Doesn't acknowledge
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertTrue(len(warnings) > 0)
        self.assertTrue(any("risk_level=low with explicit hopelessness" in w for w in warnings))

    def test_low_with_explicit_hopelessness_acknowledged_no_warning(self):
        """LOW risk_level with explicit hopelessness acknowledged in summary should not warn."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "Plus rien n'a de sens. J'abandonne complètement."},
        ])
        result = self._make_result("low", "Patient exprime désespoir mais risk_level mis à low car aucune intention d'agir explicite. Information insuffisante.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        # Should not warn about unacknowledged medium indicators
        medium_warnings = [w for w in warnings if "risk_level=low with explicit hopelessness" in w]
        self.assertEqual(len(medium_warnings), 0)

    def test_low_with_high_indicators_triggers_urgent_warning(self):
        """LOW risk_level with explicit suicidal ideation should trigger URGENT warning."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "Je veux me tuer. Je ne vois plus d'issue."},
        ])
        result = self._make_result("low", "Patient va bien.")  # Model error
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertTrue(len(warnings) > 0)
        self.assertTrue(any("URGENT" in w for w in warnings))

    def test_insufficient_evidence_triggers_note_warning(self):
        """LOW risk_level with no indicators should warn about missing insufficient-evidence note."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "Je ne vais pas bien. Je me sens mal."},
        ])
        result = self._make_result("low", "Patient ne va pas bien.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertTrue(len(warnings) > 0)
        self.assertTrue(any("insufficient evidence" in w or "insuffisant" in w for w in warnings))

    def test_low_arabic_anxiety_no_warning(self):
        """Arabic anxiety with LOW risk should not warn."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "أشعر بالقلق طوال الوقت، لا أنام جيداً."},
        ], language="ar")
        result = self._make_result("low", "Patient يعاني من القلق.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        high_medium_warnings = [w for w in warnings if "risk_level=low but explicit" in w]
        self.assertEqual(len(high_medium_warnings), 0)

    def test_low_darija_anxiety_no_warning(self):
        """Darija anxiety with LOW risk should not warn."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "نعايش قلق متواصل، ما نقدرش نعطس راحة."},
        ], language="ar")
        result = self._make_result("low", "Patient يعايش قلق.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        high_medium_warnings = [w for w in warnings if "risk_level=low but explicit" in w]
        self.assertEqual(len(high_medium_warnings), 0)

    # ============================================================
    # Negation tests
    # ============================================================

    def test_negated_suicidal_not_counted_as_high(self):
        """'Je ne veux pas me tuer' should not count as HIGH indicator."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "Parfois j'ai des pensées sombres mais je ne veux pas me tuer."},
        ])
        result = self._make_result("high", "Patient veut mourir.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertTrue(len(warnings) > 0)
        self.assertTrue(any("risk_level=high but no explicit" in w for w in warnings))

    def test_negated_self_harm_not_counted(self):
        """'Je ne vais pas me faire de mal' should not count as HIGH indicator."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "J'ai pensé à me faire du mal mais je ne le ferais jamais."},
        ])
        result = self._make_result("high", "Patient planifie automutilation.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertTrue(len(warnings) > 0)
        self.assertTrue(any("risk_level=high but no explicit" in w for w in warnings))

    def test_english_negation_handled(self):
        """English negation 'don't want to kill myself' should be handled."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "I don't want to kill myself. These are just thoughts."},
        ], language="en")
        result = self._make_result("high", "Patient suicidal.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertTrue(len(warnings) > 0)
        self.assertTrue(any("risk_level=high but no explicit" in w for w in warnings))

    def test_arabic_negation_handled(self):
        """Arabic negation should be handled."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "لا أريد أن أقتل نفسي. مجرد أفكار."},
        ], language="ar")
        result = self._make_result("high", "Patient veut se suicider.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertTrue(len(warnings) > 0)
        self.assertTrue(any("risk_level=high but no explicit" in w for w in warnings))

    def test_darija_negation_handled(self):
        """Darija negation should be handled."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "مرات تجيني أفكار سودانية ما باغيتش نقتل روشي."},
        ], language="ar")
        result = self._make_result("high", "Patient veut se suicider.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        self.assertTrue(len(warnings) > 0)
        self.assertTrue(any("risk_level=high but no explicit" in w for w in warnings))

    # ============================================================
    # Psychologist messages excluded tests
    # ============================================================

    def test_psychologist_statements_excluded(self):
        """Psychologist statements should not trigger risk indicators."""
        conv = self._make_conv([
            {"speaker": "psychologue", "content": "Avez-vous des idées suicidaires ?"},
            {"speaker": "patient", "content": "Non, jamais."},
        ])
        result = self._make_result("low", "Patient nie idéation.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        # Should not warn about HIGH indicators from psychologist
        high_warnings = [w for w in warnings if "risk_level=low but explicit self-harm" in w]
        self.assertEqual(len(high_warnings), 0)

    def test_multiple_patient_messages(self):
        """Multiple patient messages should all be checked."""
        conv = self._make_conv([
            {"speaker": "patient", "content": "Je vais bien."},
            {"speaker": "psychologue", "content": "Et le travail ?"},
            {"speaker": "patient", "content": "Le travail est stressant mais je ne veux pas mourir."},
        ])
        result = self._make_result("low", "Patient stressé au travail.")
        warnings = validate_risk_consistency(conv, result)["warnings"]
        high_warnings = [w for w in warnings if "risk_level=low but explicit self-harm" in w]
        self.assertEqual(len(high_warnings), 0)


class RunQualityChecksIntegrationTests(TestCase):
    """Integration tests for run_quality_checks with risk_consistency."""

    def setUp(self):
        self.conversation = {
            "id": "test_001",
            "scenario_id": 99,
            "language": "fr",
            "theme": "Test",
            "messages": [
                {"speaker": "patient", "content": "Je veux me tuer."},
            ],
        }

    def test_risk_consistency_included_in_quality_checks(self):
        """run_quality_checks should include risk_consistency category."""
        result = {
            "success": True,
            "summary": "Patient exprime idéation suicidaire.",
            "themes": ["suicide"],
            "emotions": ["détresse"],
            "keywords": ["mort"],
            "emotional_evolution": "Patient en crise.",
            "risk_level": "high",
        }
        checks = run_quality_checks(self.conversation, result)
        self.assertIn("risk_consistency", checks)
        self.assertIn("errors", checks["risk_consistency"])
        self.assertIn("warnings", checks["risk_consistency"])
        # Should be warnings only, no errors
        self.assertEqual(checks["risk_consistency"]["errors"], [])

    def test_risk_consistency_warnings_returned(self):
        """risk_consistency should return warnings for mismatched risk levels."""
        result = {
            "success": True,
            "summary": "Patient va bien.",
            "themes": [],
            "emotions": [],
            "keywords": [],
            "emotional_evolution": "Patient stable.",
            "risk_level": "low",
        }
        checks = run_quality_checks(self.conversation, result)
        self.assertTrue(len(checks["risk_consistency"]["warnings"]) > 0)
        self.assertTrue(any("URGENT" in w for w in checks["risk_consistency"]["warnings"]))