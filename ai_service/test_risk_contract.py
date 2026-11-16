from django.test import SimpleTestCase

from ai_service.services import _validate_full_analysis, _validate_risk_assessment


class RiskAssessmentValidationTests(SimpleTestCase):
    def test_legacy_output_without_status_is_assessed(self):
        data = {
            "summary": "Résumé.",
            "themes": ["sommeil"],
            "emotions": ["anxiété"],
            "keywords": ["stress"],
            "emotional_evolution": "Le patient est plus détendu.",
            "risk_level": "low",
        }

        validated = _validate_full_analysis(data)

        self.assertIsNotNone(validated)
        self.assertEqual(validated["risk_assessment_status"], "assessed")
        self.assertEqual(validated["risk_level"], "low")

    def test_insufficient_information_accepts_null_level(self):
        data = {
            "summary": "Le patient reste vague; informations insuffisantes.",
            "themes": ["mal-être"],
            "emotions": [],
            "keywords": [],
            "risk_assessment_status": "insufficient_information",
            "risk_level": None,
            "emotional_evolution": "Peu d'éléments exploitables.",
        }

        validated = _validate_full_analysis(data)

        self.assertIsNotNone(validated)
        self.assertEqual(validated["risk_assessment_status"], "insufficient_information")
        self.assertIsNone(validated["risk_level"])

    def test_assessed_with_null_level_is_rejected(self):
        data = {
            "summary": "Résumé.",
            "themes": ["sommeil"],
            "emotions": [],
            "keywords": [],
            "risk_assessment_status": "assessed",
            "risk_level": None,
            "emotional_evolution": "Évolution.",
        }

        self.assertIsNone(_validate_full_analysis(data))

    def test_insufficient_information_with_non_null_level_is_rejected(self):
        data = {
            "summary": "Résumé.",
            "themes": ["sommeil"],
            "emotions": [],
            "keywords": [],
            "risk_assessment_status": "insufficient_information",
            "risk_level": "low",
            "emotional_evolution": "Évolution.",
        }

        self.assertIsNone(_validate_full_analysis(data))

    def test_missing_risk_level_is_rejected(self):
        data = {
            "summary": "Résumé.",
            "themes": ["sommeil"],
            "emotions": [],
            "keywords": [],
            "risk_assessment_status": "assessed",
            "emotional_evolution": "Évolution.",
        }

        self.assertIsNone(_validate_full_analysis(data))

    def test_invalid_status_is_rejected(self):
        data = {
            "summary": "Résumé.",
            "themes": ["sommeil"],
            "emotions": [],
            "keywords": [],
            "risk_assessment_status": "unknown",
            "risk_level": "low",
            "emotional_evolution": "Évolution.",
        }

        self.assertIsNone(_validate_full_analysis(data))

    def test_validate_risk_assessment_direct_variants(self):
        self.assertEqual(
            _validate_risk_assessment({"risk_assessment_status": "assessed", "risk_level": "high"}),
            {"risk_assessment_status": "assessed", "risk_level": "high"},
        )
        self.assertEqual(
            _validate_risk_assessment(
                {"risk_assessment_status": "insufficient_information", "risk_level": None}
            ),
            {"risk_assessment_status": "insufficient_information", "risk_level": None},
        )
        self.assertEqual(
            _validate_risk_assessment({"risk_level": "medium"}),
            {"risk_assessment_status": "assessed", "risk_level": "medium"},
        )
        self.assertIsNone(_validate_risk_assessment({"risk_assessment_status": "assessed", "risk_level": None}))
        self.assertIsNone(_validate_risk_assessment({}))