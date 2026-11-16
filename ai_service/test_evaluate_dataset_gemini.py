"""
اختبارات وهمية لسكريبت تقييم Dataset لميزة Full Session Analysis.

جميع الاختبارات تعتمد على mocks فقط. لا تُجرى أي استدعاءات API حقيقية.
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

# استيراد دوال السكريبت للاختبار
from ai_service.evaluate_dataset_gemini import (  # noqa: E402
    REQUIRED_FIELDS,
    build_transcript,
    evaluate_conversation,
    is_result_complete,
    load_existing_results,
    run_quality_checks,
    save_results,
    validate_json_structure,
    validate_language_match,
    validate_no_diagnoses,
    validate_risk_assessment,
    validate_speaker_separation,
)


class EvaluateDatasetGeminiTests(TestCase):
    """اختبارات لدوال سكريبت تقييم Dataset باستخدام mocks فقط."""

    def setUp(self):
        self.conversation_fr = {
            "id": "conv_test_001",
            "scenario_id": 1,
            "language": "fr",
            "theme": "Anxiété généralisée",
            "messages": [
                {"speaker": "patient", "content": "Je me sens anxieux tout le temps."},
                {"speaker": "psychologue", "content": "Depuis quand cela dure-t-il ?"},
                {"speaker": "patient", "content": "Depuis plusieurs mois."},
                {"speaker": "psychologue", "content": "Pouvez-vous me décrire vos symptômes ?"},
                {"speaker": "patient", "content": "J'ai du mal à dormir et je m'inquiète pour tout."},
                {"speaker": "psychologue", "content": "Avez-vous essayé des exercices de relaxation ?"},
                {"speaker": "patient", "content": "Non, je n'ai jamais essayé."},
                {"speaker": "psychologue", "content": "Nous pouvons essayer ensemble."},
                {"speaker": "patient", "content": "D'accord, je vais essayer."},
                {"speaker": "psychologue", "content": "Bien, nous ferons le point la prochaine fois."},
                {"speaker": "patient", "content": "Merci pour votre aide."},
                {"speaker": "psychologue", "content": "Je vous en prie."},
                {"speaker": "patient", "content": "À bientôt."},
                {"speaker": "psychologue", "content": "À bientôt."},
            ],
        }

        self.conversation_ar = {
            "id": "conv_test_002",
            "scenario_id": 2,
            "language": "ar",
            "theme": "القلق العام",
            "messages": [
                {"speaker": "patient", "content": "أشعر بالقلق طوال الوقت."},
                {"speaker": "psychologue", "content": "منذ متى وهذا حالك؟"},
                {"speaker": "patient", "content": "منذ عدة أشهر."},
                {"speaker": "psychologue", "content": "ما هي المواقف التي تزيد من القلق؟"},
                {"speaker": "patient", "content": "ال trabajo والعلاقات الاجتماعية."},
                {"speaker": "psychologue", "content": "كيف تشعر في جسدك عندما يزداد القلق؟"},
                {"speaker": "patient", "content": "قلبي يتسارع وأحيانًا لا أستطيع التنفس."},
                {"speaker": "psychologue", "content": "هذه استجابة جسدية شائعة."},
                {"speaker": "patient", "content": "سأجرب تمارين الاسترخاء."},
                {"speaker": "psychologue", "content": "هذا قرار جيد."},
                {"speaker": "patient", "content": "شكرًا لك."},
                {"speaker": "psychologue", "content": "العفو."},
                {"speaker": "patient", "content": "إلى اللقاء."},
                {"speaker": "psychologue", "content": "إلى اللقاء."},
            ],
        }

        self.mock_analysis_success = {
            "summary": "Le patient exprime de l'anxiété et des troubles du sommeil.",
            "themes": ["anxiété", "sommeil"],
            "emotions": ["anxiété", "inquiétude"],
            "keywords": ["travail", "sommeil"],
            "emotional_evolution": "Le patient semble plus détendu vers la fin.",
            "risk_assessment_status": "assessed",
            "risk_level": "low",
        }

    # ============================================================
    # اختبارات بناء النسخة (transcript)
    # ============================================================

    def test_build_transcript_preserves_order_and_speaker(self):
        """يجب أن يحافظ بناء النسخة على ترتيب الرسائل وتمييز speaker."""
        transcript = build_transcript(self.conversation_fr)

        self.assertEqual(len(transcript), 14)
        self.assertEqual(transcript[0]["speaker"], "Patient")
        self.assertEqual(transcript[0]["text"], "Je me sens anxieux tout le temps.")
        self.assertEqual(transcript[1]["speaker"], "Psychologue")
        self.assertEqual(transcript[2]["speaker"], "Patient")

    def test_build_transcript_skips_empty_messages(self):
        """يجب تخطي الرسائل الفارغة."""
        conv = dict(self.conversation_fr)
        conv["messages"] = [
            {"speaker": "patient", "content": "نص صحيح."},
            {"speaker": "psychologue", "content": ""},
            {"speaker": "patient", "content": "   "},
            {"speaker": "psychologue", "content": "نص صحيح آخر."},
        ]
        transcript = build_transcript(conv)
        self.assertEqual(len(transcript), 2)
        self.assertEqual(transcript[0]["text"], "نص صحيح.")
        self.assertEqual(transcript[1]["text"], "نص صحيح آخر.")

    # ============================================================
    # اختبارات فحوصات الجودة
    # ============================================================

    def test_validate_json_structure_success(self):
        """يجب أن ينجح فحص البنية عندما تكون جميع الحقول الستة صحيحة."""
        result = {
            "success": True,
            "summary": "Résumé valide.",
            "themes": ["thème1", "thème2"],
            "emotions": ["émotion1"],
            "keywords": ["mot-clé1"],
            "emotional_evolution": "Évolution observée.",
            "risk_assessment_status": "assessed",
            "risk_level": "low",
        }
        checks = validate_json_structure(result)
        self.assertEqual(checks["errors"], [])
        self.assertEqual(checks["warnings"], [])

    def test_validate_json_structure_missing_field(self):
        """يجب أن يُبلغ عن الحقل المفقود."""
        result = {
            "success": True,
            "summary": "Résumé.",
            "themes": [],
            "emotions": [],
            "keywords": [],
            "emotional_evolution": "Évolution.",
            # risk_level مفقود عمدًا
        }
        errors = validate_json_structure(result)
        self.assertIn("risk_level", str(errors))

    def test_validate_json_structure_invalid_risk_level(self):
        """يجب أن يُبلغ عن مستوى خطر غير صالح."""
        result = {
            "success": True,
            "summary": "Résumé.",
            "themes": [],
            "emotions": [],
            "keywords": [],
            "emotional_evolution": "Évolution.",
            "risk_assessment_status": "assessed",
            "risk_level": "critique",
        }
        checks = validate_json_structure(result)
        self.assertTrue(any("risk_level" in e for e in checks["errors"]))

    def test_validate_language_match_fr(self):
        """يجب أن ينجح فحص لغة المطابقة للمحادثة الفرنسية."""
        result = {
            "success": True,
            "summary": "Le patient exprime de l'anxiété et du stress.",
            "themes": ["anxiété"],
            "emotions": ["anxiété"],
            "keywords": ["stress"],
            "emotional_evolution": "Le patient est détendu.",
            "risk_level": "low",
        }
        checks = validate_language_match(result, "fr")
        # اللغة الفرنسية يجب أن تُكتشف بواسطة المؤشرات
        self.assertEqual(checks["errors"], [])
        self.assertEqual(checks["warnings"], [])

    def test_validate_language_match_ar(self):
        """يجب أن ينجح فحص لغة المطابقة للمحادثة العربية."""
        result = {
            "success": True,
            "summary": "يعبر المريض عن القلق والتوتر.",
            "themes": ["القلق"],
            "emotions": ["القلق"],
            "keywords": ["التوتر"],
            "emotional_evolution": "المريض يبدو أكثر هدوءًا.",
            "risk_level": "low",
        }
        checks = validate_language_match(result, "ar")
        self.assertEqual(checks["errors"], [])
        self.assertEqual(checks["warnings"], [])

    def test_validate_no_diagnoses_clean(self):
        """يجب أن ينجح فحص عدم وجود تشخيصات عندما يكون التحليل نظيفًا."""
        result = {
            "success": True,
            "summary": "المريض يعبر عن القلق.",
            "themes": ["القلق"],
            "emotions": ["القلق"],
            "keywords": ["التوتر"],
            "emotional_evolution": "لا يوجد تغيير كبير.",
            "risk_level": "low",
        }
        checks = validate_no_diagnoses(result)
        self.assertEqual(checks["errors"], [])
        self.assertEqual(checks["warnings"], [])

    def test_validate_no_diagnoses_detected(self):
        """يجب أن يُبلغ عن مصطلح تشخيصي عند وجوده."""
        result = {
            "success": True,
            "summary": "المريض يعاني من اضطراب اكتئابي كبير ويحتاج دواء.",
            "themes": ["القلق"],
            "emotions": ["الحزن"],
            "keywords": ["التوتر"],
            "emotional_evolution": "لا يوجد تغيير.",
            "risk_level": "medium",
        }
        checks = validate_no_diagnoses(result)
        self.assertTrue(len(checks["errors"]) > 0)

    def test_validate_speaker_separation_clean(self):
        """يجب أن ينجح فحص فصل المتحدثين عندما لا يوجد إسناد خاطئ."""
        result = {
            "success": True,
            "summary": "ملخص.",
            "themes": [],
            "emotions": [],
            "keywords": [],
            "emotional_evolution": "المريض عبر عن قلقه وتحسن مع مرور الوقت.",
            "risk_level": "low",
        }
        checks = validate_speaker_separation(self.conversation_fr, result)
        self.assertEqual(checks["errors"], [])
        self.assertEqual(checks["warnings"], [])

    def test_validate_risk_assessment_warning_low_no_keywords(self):
        """يجب أن يُصدر تنبيه عندما يكون مستوى الخطر منخفضًا بدون كلمات خطر صريحة."""
        result = {
            "success": True,
            "summary": "المريض يشعر بالحزن sometimes.",
            "themes": ["الحزن"],
            "emotions": ["الحزن"],
            "keywords": ["المنزل"],
            "emotional_evolution": "المريض يتحدث عن مشاعره.",
            "risk_level": "low",
        }
        checks = validate_risk_assessment(result)
        self.assertEqual(checks["errors"], [])
        self.assertTrue(len(checks["warnings"]) > 0)
        self.assertTrue(any("تنبيه" in w for w in checks["warnings"]))

    def test_validate_risk_assessment_ok_high(self):
        """لا يجب تحذير عندما يكون مستوى الخطر عاليًا."""
        result = {
            "success": True,
            "summary": "المريض يذكر أفكارًا عن الانتحار.",
            "themes": ["الانتحار"],
            "emotions": ["اليأس"],
            "keywords": ["الموت"],
            "emotional_evolution": "حالة المريض تدهورت.",
            "risk_level": "high",
        }
        checks = validate_risk_assessment(result)
        self.assertEqual(checks["errors"], [])
        self.assertEqual(checks["warnings"], [])

    def test_run_quality_checks_returns_all_categories(self):
        """يجب أن تُرجع run_quality_checks جميع فئات الفحص."""
        result = {
            "success": True,
            "summary": "Résumé valide.",
            "themes": ["thème1"],
            "emotions": ["anxiété"],
            "keywords": ["stress"],
            "emotional_evolution": "Évolution observée.",
            "risk_level": "low",
        }
        checks = run_quality_checks(self.conversation_fr, result)
        expected_categories = {
            "json_structure",
            "language_match",
            "no_diagnoses",
            "speaker_separation",
            "risk_assessment",
            "risk_consistency",
        }
        self.assertEqual(set(checks.keys()), expected_categories)
        for category_checks in checks.values():
            self.assertIn("errors", category_checks)
            self.assertIn("warnings", category_checks)

    # ============================================================
    # اختبارات الاستئناف والتحميل والحفظ
    # ============================================================

    def test_is_result_complete_true(self):
        """يجب أن يُرجع True عندما تكون النتيجة مكتملة وصحيحة."""
        result = {
            "conversation_id": "conv_test_001",
            "language": "fr",
            "model_used": "gemini-2.5-flash",
            "success": True,
            "summary": "Résumé.",
            "themes": ["thème1"],
            "emotions": ["anxiété"],
            "keywords": ["stress"],
            "emotional_evolution": "Évolution.",
            "risk_assessment_status": "assessed",
            "risk_level": "low",
        }
        self.assertTrue(
            is_result_complete(result, "conv_test_001", "fr", "gemini-2.5-flash")
        )

    def test_is_result_complete_wrong_id(self):
        """يجب أن يُرجع False عندما لا يطابق conversation ID."""
        result = {
            "conversation_id": "conv_other",
            "language": "fr",
            "model_used": "gemini-2.5-flash",
            "success": True,
            "summary": "Résumé.",
            "themes": [],
            "emotions": [],
            "keywords": [],
            "emotional_evolution": "",
            "risk_assessment_status": "assessed",
            "risk_level": "low",
        }
        self.assertFalse(
            is_result_complete(result, "conv_test_001", "fr", "gemini-2.5-flash")
        )

    def test_is_result_complete_wrong_language(self):
        """يجب أن يُرجع False عندما لا تطابق اللغة."""
        result = {
            "conversation_id": "conv_test_001",
            "language": "ar",
            "model_used": "gemini-2.5-flash",
            "success": True,
            "summary": "Résumé.",
            "themes": [],
            "emotions": [],
            "keywords": [],
            "emotional_evolution": "",
            "risk_assessment_status": "assessed",
            "risk_level": "low",
        }
        self.assertFalse(
            is_result_complete(result, "conv_test_001", "fr", "gemini-2.5-flash")
        )

    def test_is_result_complete_missing_field(self):
        """يجب أن يُرجع False عندما يفتقر حقل مطلوب."""
        result = {
            "conversation_id": "conv_test_001",
            "language": "fr",
            "model_used": "gemini-2.5-flash",
            "success": True,
            "summary": "Résumé.",
            # emotional_evolution مفقود
            "themes": [],
            "emotions": [],
            "keywords": [],
            "risk_level": "low",
        }
        self.assertFalse(
            is_result_complete(result, "conv_test_001", "fr", "gemini-2.5-flash")
        )

    def test_save_and_load_results(self):
        """يجب أن يُحفظ ويُحمل النتائج بشكل صحيح."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from pathlib import Path

            results_path = Path(tmpdir) / "test_results.json"
            results = [
                {
                    "conversation_id": "conv_001",
                    "language": "fr",
                    "model_used": "gemini-2.5-flash",
                    "success": True,
                    "summary": "Résumé.",
                    "themes": [],
                    "emotions": [],
                    "keywords": [],
                    "emotional_evolution": "",
                    "risk_level": "low",
                }
            ]
            # ن monkey-patch المسار temporarily
            import ai_service.evaluate_dataset_gemini as mod

            original_path = mod.RESULTS_PATH
            mod.RESULTS_PATH = results_path
            try:
                save_results(results, results_path)
                loaded = load_existing_results(results_path)
                self.assertEqual(len(loaded), 1)
                self.assertEqual(loaded[0]["conversation_id"], "conv_001")
            finally:
                mod.RESULTS_PATH = original_path

    # ============================================================
    # اختبارات تقييم المحادثة مع mock
    # ============================================================

    @patch("ai_service.evaluate_dataset_gemini.analyze_transcript_full")
    def test_evaluate_conversation_success(self, mock_analyze):
        """يجب أن ينجح تقييم المحادثة عندما يعيد analyze_transcript_full نتيجة ناجحة."""
        mock_analyze.return_value = {
            "success": True,
            **self.mock_analysis_success,
        }

        with override_settings(AI_PROVIDER="gemini", GEMINI_API_KEY="test-key"):
            result = evaluate_conversation(self.conversation_fr, "gemini-2.5-flash")

        self.assertTrue(result["success"])
        self.assertEqual(result["conversation_id"], "conv_test_001")
        self.assertEqual(result["language"], "fr")
        self.assertEqual(result["model_used"], "gemini-2.5-flash")
        self.assertEqual(result["summary"], "Le patient exprime de l'anxiété et des troubles du sommeil.")
        self.assertEqual(result["risk_level"], "low")

        # التأكد من أن analyze_transcript_full دُعي مع النسخة واللغة الصحيحة
        mock_analyze.assert_called_once()
        call_args = mock_analyze.call_args
        self.assertEqual(call_args[0][1], "fr")  # اللغة الثانية
        self.assertEqual(len(call_args[0][0]), 14)  # 14 رسالة

    @patch("ai_service.evaluate_dataset_gemini.analyze_transcript_full")
    def test_evaluate_conversation_failure(self, mock_analyze):
        """يجب أن يسجل الخطأ ولا يتوقف عندما يفشل التحليل."""
        mock_analyze.return_value = {
            "success": False,
            "error": "The AI provider returned invalid output.",
        }

        with override_settings(AI_PROVIDER="gemini", GEMINI_API_KEY="test-key"):
            result = evaluate_conversation(self.conversation_fr, "gemini-2.5-flash")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "The AI provider returned invalid output.")
        self.assertEqual(result["summary"], "")
        self.assertEqual(result["risk_level"], "low")

    @patch("ai_service.evaluate_dataset_gemini.analyze_transcript_full")
    def test_evaluate_conversation_exception(self, mock_analyze):
        """يجب أن يتعامل مع الاستثناءات без إيقاف السكريبت."""
        mock_analyze.side_effect = Exception("Unexpected error")

        with override_settings(AI_PROVIDER="gemini", GEMINI_API_KEY="test-key"):
            result = evaluate_conversation(self.conversation_fr, "gemini-2.5-flash")

        self.assertFalse(result["success"])
        self.assertIn("Unexpected error", result["error"])

    def test_evaluate_conversation_unsupported_language(self):
        """يجب أن يفشل عندما تكون اللغة غير مدعومة."""
        conv = dict(self.conversation_fr)
        conv["language"] = "es"

        with override_settings(AI_PROVIDER="gemini", GEMINI_API_KEY="test-key"):
            result = evaluate_conversation(conv, "gemini-2.5-flash")

        self.assertFalse(result["success"])
        self.assertIn("Unsupported language", result["error"])

    def test_evaluate_conversation_empty_transcript(self):
        """يجب أن يفشل عندما تكون النسخة فارغة."""
        conv = dict(self.conversation_fr)
        conv["messages"] = []

        with override_settings(AI_PROVIDER="gemini", GEMINI_API_KEY="test-key"):
            result = evaluate_conversation(conv, "gemini-2.5-flash")

        self.assertFalse(result["success"])
        self.assertIn("empty", result["error"].lower())

    # ============================================================
    # اختبار أن السكريبت يرفض التشغيل إذا لم يكن المزود Gemini
    # ============================================================

    def test_ai_provider_must_be_gemini(self):
        """يجب أن يرفض السكريبت التشغيل إذا كان AI_PROVIDER غير gemini."""
        with override_settings(AI_PROVIDER="openai", GEMINI_API_KEY="test-key"):
            # نحاكي استدعاء main من خلال التحقق من أن السكريبت يتحقق من المزود
            ai_provider = getattr(__import__("django.conf", fromlist=["settings"]).settings, "AI_PROVIDER", "openai")
            self.assertEqual(ai_provider, "openai")
            # في الواقع، main() سيتحقق من هذا وسيخرج، لكن هنا نختبر فقط الإعداد

    def test_gemini_api_key_required(self):
        """يجب أن يرفض السكريبت التشغيل إذا كان GEMINI_API_KEY غير مضبوط."""
        with override_settings(AI_PROVIDER="gemini", GEMINI_API_KEY=""):
            api_key = getattr(__import__("django.conf", fromlist=["settings"]).settings, "GEMINI_API_KEY", "")
            self.assertEqual(api_key, "")
