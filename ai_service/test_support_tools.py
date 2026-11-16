import json
import re

from django.test import TestCase
from django.urls import reverse
from django.utils.translation import override

from accounts.models import CustomUser
from .models import StressAssessmentResult, SupportConversation, SupportMessage
from .views import STRESS_ASSESSMENT_CONFIG


class HomePageContentTests(TestCase):
    def test_specialty_cards_link_to_the_matching_detail_pages(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nos spécialités")
        for slug in ("anxiete", "depression-humeur", "stress", "addiction"):
            self.assertContains(
                response,
                reverse("specialite_detail", kwargs={"slug": slug}),
            )
        self.assertContains(response, 'class="trust-grid"')
        self.assertContains(response, "Suivi de votre auto-évaluation")

    def test_ai_homepage_links_resolve_in_each_supported_language(self):
        for language in ("fr", "ar", "en"):
            with self.subTest(language=language), override(language):
                homepage_url = reverse("home")
                if language == "fr":
                    homepage_url = "/fr/"
                self.client.cookies["django_language"] = language
                response = self.client.get(homepage_url, follow=True)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.wsgi_request.LANGUAGE_CODE, language)
                if language == "fr":
                    self.assertRedirects(response, "/")
                self.assertContains(response, "consultation_step_2")
                self.assertNotContains(response, 'href="/ai-service/support-chat/"')
                html = response.content.decode()
                for translation_key in ("find_psychologist", "stress_open"):
                    link = re.search(
                        rf'<a\b(?=[^>]*data-i18n="{translation_key}")[^>]*href="([^"]+)"[^>]*>',
                        html,
                    )
                    self.assertIsNotNone(link)
                    self.assertEqual(self.client.get(link.group(1)).status_code, 200)


class SupportChatTests(TestCase):
    def setUp(self):
        self.patient = CustomUser.objects.create_user(
            username="support-chat-patient",
            password="test-password",
            user_type="patient",
        )
        self.other_patient = CustomUser.objects.create_user(
            username="other-support-patient",
            password="test-password",
            user_type="patient",
        )
        self.send_url = reverse("ai_service:send_support_message")

    def test_chat_page_requires_patient_login(self):
        response = self.client.get(reverse("ai_service:support_chat"))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.patient)
        response = self.client.get(reverse("ai_service:support_chat"))
        self.assertEqual(response.status_code, 200)

    def test_message_is_saved_without_forwarding_to_an_external_provider(self):
        self.client.force_login(self.patient)

        first_response = self.client.post(
            self.send_url,
            data=json.dumps({"message": "أشعر بالقلق مؤخراً"}),
            content_type="application/json",
        )
        response = self.client.post(
            self.send_url,
            data=json.dumps(
                {
                    "message": "أحتاج إلى دعم",
                    "conversation_id": first_response.json()["conversation_id"],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "assistant_unavailable")
        self.assertEqual(SupportConversation.objects.count(), 1)
        self.assertEqual(SupportMessage.objects.count(), 2)
        self.assertEqual(
            list(SupportMessage.objects.values_list("content", flat=True)),
            ["أشعر بالقلق مؤخراً", "أحتاج إلى دعم"],
        )
        self.assertIn("لم تُرسل", response.json()["error"])

    def test_chat_history_detail_export_and_delete_are_scoped_to_owner(self):
        conversation = SupportConversation.objects.create(user=self.patient)
        SupportMessage.objects.create(
            conversation=conversation,
            role="user",
            content="رسالة خاصة",
        )
        detail_url = reverse(
            "ai_service:support_chat_detail",
            args=[conversation.pk],
        )
        export_url = reverse(
            "ai_service:export_support_conversation",
            args=[conversation.pk],
        )
        delete_url = reverse(
            "ai_service:delete_support_conversation",
            args=[conversation.pk],
        )

        self.client.force_login(self.other_patient)
        self.assertEqual(self.client.get(detail_url).status_code, 404)
        self.assertEqual(self.client.get(export_url).status_code, 404)
        self.assertEqual(self.client.post(delete_url).status_code, 404)
        self.assertTrue(SupportConversation.objects.filter(pk=conversation.pk).exists())

        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(detail_url).json()["messages"][0]["content"], "رسالة خاصة")
        self.assertIn("رسالة خاصة", self.client.get(export_url).content.decode())
        self.assertEqual(self.client.post(delete_url).json()["success"], True)
        self.assertFalse(SupportConversation.objects.filter(pk=conversation.pk).exists())


class StressAssessmentTests(TestCase):
    def setUp(self):
        self.patient = CustomUser.objects.create_user(
            username="stress-assessment-patient",
            password="test-password",
            user_type="patient",
        )
        self.landing_url = reverse("ai_service:stress_assessment")
        config = STRESS_ASSESSMENT_CONFIG["fr"]
        self.pss10_ids = [
            f"pss10_{i}" for i in range(1, len(config["pss10"]["questions"]) + 1)
        ]
        self.dass21_ids = [
            f"dass21_{i}" for i in range(1, len(config["dass21"]["questions"]) + 1)
        ]

    def _take_url(self, instrument):
        return reverse("ai_service:stress_assessment_take", args=[instrument])

    def test_landing_page_shows_two_separate_cards(self):
        response = self.client.get(self.landing_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PSS-10")
        self.assertContains(response, "DASS-21")
        self.assertContains(response, "10 questions")
        self.assertContains(response, "21 questions")
        self.assertContains(response, self._take_url("pss10"))
        self.assertContains(response, self._take_url("dass21"))

    def test_each_instrument_page_only_shows_its_own_questions(self):
        pss_response = self.client.get(self._take_url("pss10"))
        self.assertEqual(pss_response.status_code, 200)
        self.assertContains(pss_response, 'name="pss10_1"')
        self.assertNotContains(pss_response, 'name="dass21_1"')
        self.assertContains(pss_response, 'aria-label="Progression du questionnaire"')

        dass_response = self.client.get(self._take_url("dass21"))
        self.assertEqual(dass_response.status_code, 200)
        self.assertContains(dass_response, 'name="dass21_1"')
        self.assertNotContains(dass_response, 'name="pss10_1"')

        self.assertEqual(len(self.pss10_ids), 10)
        self.assertEqual(len(self.dass21_ids), 21)

    def test_guest_can_get_non_persisted_result_per_instrument(self):
        self.client.cookies["stress_assessment_language"] = "fr"

        pss_response = self.client.post(
            self._take_url("pss10"),
            {"answers": json.dumps({qid: 0 for qid in self.pss10_ids})},
        )
        self.assertEqual(pss_response.status_code, 200)
        self.assertContains(pss_response, "Score PSS-10")
        self.assertNotContains(pss_response, "DASS-21 - Dépression")

        dass_response = self.client.post(
            self._take_url("dass21"),
            {"answers": json.dumps({qid: 0 for qid in self.dass21_ids})},
        )
        self.assertEqual(dass_response.status_code, 200)
        self.assertContains(dass_response, "DASS-21 - Dépression")
        self.assertNotContains(dass_response, "Score PSS-10")

        self.assertFalse(StressAssessmentResult.objects.exists())

    def test_assessment_defaults_to_french_until_user_selects_a_language(self):
        self.client.cookies["django_language"] = "ar"

        response = self.client.get(self.landing_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<html lang="fr" dir="ltr">')
        self.assertContains(response, '<option value="fr" selected>')

    def test_assessment_and_results_are_translated_in_all_supported_languages(self):
        expected = {
            "fr": ("PSS-10", "Jamais", "Résultats de votre évaluation", "Score PSS-10"),
            "en": ("PSS-10", "Never", "Your Assessment Results", "PSS-10 Score"),
            "ar": ("PSS-10", "أبداً", "نتائج التقييم", "نتيجة مقياس PSS-10"),
        }

        for language, texts in expected.items():
            with self.subTest(language=language):
                self.client.cookies["stress_assessment_language"] = language
                landing_response = self.client.get(self.landing_url)
                self.assertEqual(landing_response.status_code, 200)
                direction = "rtl" if language == "ar" else "ltr"
                self.assertContains(
                    landing_response,
                    f'<html lang="{language}" dir="{direction}">',
                )
                self.assertContains(landing_response, texts[0])

                take_response = self.client.get(self._take_url("pss10"))
                self.assertEqual(take_response.status_code, 200)
                self.assertContains(take_response, texts[1])

                result_response = self.client.post(
                    self._take_url("pss10"),
                    {"answers": json.dumps({qid: 0 for qid in self.pss10_ids})},
                )
                self.assertEqual(result_response.status_code, 200)
                self.assertContains(result_response, texts[2])
                self.assertContains(result_response, texts[3])

    def test_logged_in_patient_pss10_result_is_saved_alone(self):
        self.client.force_login(self.patient)
        answers = {qid: 0 for qid in self.pss10_ids}

        response = self.client.post(
            self._take_url("pss10"), {"answers": json.dumps(answers)}
        )

        result = StressAssessmentResult.objects.get(user=self.patient)
        self.assertRedirects(
            response,
            reverse("ai_service:stress_assessment_result", args=[result.pk]),
        )
        self.assertIsNone(result.score)
        self.assertIsNone(result.level)
        category_scores = result.category_scores
        self.assertEqual(category_scores.get("version"), 2)
        self.assertEqual(category_scores.get("assessment_type"), "pss10")
        self.assertIn("pss10", category_scores.get("instruments", {}))
        self.assertNotIn("dass21", category_scores.get("instruments", {}))
        pss10 = category_scores["instruments"]["pss10"]
        self.assertEqual(pss10["max"], 40)
        # All answers are 0; reverse items 4, 5, 7, 8 become 4 => 4 * 4 = 16.
        self.assertEqual(pss10["total"], 16)

    def test_dass21_scales_are_scored_and_doubled(self):
        answers = {qid: 1 for qid in self.dass21_ids}

        response = self.client.post(
            self._take_url("dass21"), {"answers": json.dumps(answers)}
        )

        self.assertEqual(response.status_code, 200)
        dass = response.context["dass21_result"]
        # 7 questions per scale, each answered 1 => raw 7, doubled to 14.
        for dimension in ("depression", "anxiety", "stress"):
            self.assertEqual(dass[dimension]["raw"], 7)
            self.assertEqual(dass[dimension]["score"], 14)
            self.assertEqual(dass[dimension]["max"], 42)

    def test_invalid_or_incomplete_assessment_is_not_saved(self):
        self.client.force_login(self.patient)
        response = self.client.post(
            self._take_url("pss10"), {"answers": json.dumps({"pss10_1": "6"})}
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(StressAssessmentResult.objects.exists())

    def test_legacy_result_displays_correctly(self):
        self.client.force_login(self.patient)
        legacy = StressAssessmentResult.objects.create(
            user=self.patient,
            score=3.5,
            level="moderate",
            category_scores={"physical": 3.5, "emotional": 3.5, "social": 3.5, "work": 3.5},
        )
        self.client.cookies["stress_assessment_language"] = "fr"
        response = self.client.get(reverse("ai_service:stress_assessment_result", args=[legacy.pk]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertTrue("3.5" in content or "3,5" in content)
        self.assertTrue("Modéré" in content or "\u00c9lev\u00e9" in content)
