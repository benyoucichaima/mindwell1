from datetime import date, time

from django.test import TestCase
from django.urls import reverse
from django.utils.translation import gettext, override

from accounts.models import CustomUser, PsychologueProfile
from consultations.models import Consultation


class AppointmentLanguageTests(TestCase):
    def setUp(self):
        self.patient = CustomUser.objects.create_user(
            username="i18n-patient",
            password="test-password",
            user_type="patient",
        )
        self.psychologist = CustomUser.objects.create_user(
            username="i18n-psychologist",
            password="test-password",
            user_type="psychologue",
        )
        PsychologueProfile.objects.create(
            user=self.psychologist,
            is_verified=True,
            hourly_rate="3200.00",
            session_duration=45,
        )
        Consultation.objects.create(
            patient=self.patient,
            psychologue=self.psychologist,
            date=date(2026, 11, 3),
            start_time=time(10),
            end_time=time(10, 50),
            duration_minutes=50,
            price="3200.00",
        )
        self.client.force_login(self.psychologist)

    def test_appointments_page_uses_selected_language_and_rtl_for_arabic(self):
        with override("fr"):
            appointment_url = reverse("accounts:rendez_vous")

        for language, direction in (("fr", "ltr"), ("ar", "rtl"), ("en", "ltr")):
            with self.subTest(language=language):
                self.client.cookies["django_language"] = language
                response = self.client.get(appointment_url)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.wsgi_request.LANGUAGE_CODE, language)
                self.assertContains(response, f'lang="{language}" dir="{direction}"')
                self.assertContains(response, "appointmentTranslations")
                self.assertIn("Cookie", response["Vary"])

    def test_psychologist_dashboard_uses_selected_language_and_direction(self):
        with override("fr"):
            dashboard_url = reverse("accounts:psychologue_dashboard")

        expected_directions = {"fr": "ltr", "ar": "rtl", "en": "ltr"}
        expected_labels = {
            "fr": "Espace clinique",
            "ar": "الملفات السريرية",
            "en": "Clinical records",
        }
        for language, direction in expected_directions.items():
            with self.subTest(language=language):
                self.client.cookies["django_language"] = language
                response = self.client.get(dashboard_url)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.wsgi_request.LANGUAGE_CODE, language)
                self.assertContains(response, f'lang="{language}" dir="{direction}"')
                self.assertContains(response, expected_labels[language])
                self.assertContains(response, 'data-i18n="ai_analytics"')
                self.assertContains(response, f'setLanguage("{language}")')
                self.assertNotIn("django_language", response.cookies)

    def test_patient_dashboard_uses_selected_language_and_direction(self):
        with override("fr"):
            dashboard_url = reverse("accounts:patient_dashboard")

        expected = {
            "fr": ("ltr", "Mes prochains rendez-vous"),
            "ar": ("rtl", "مواعيدي القادمة"),
            "en": ("ltr", "My upcoming appointments"),
        }
        self.client.force_login(self.patient)

        for language, (direction, dashboard_label) in expected.items():
            with self.subTest(language=language):
                self.client.cookies["django_language"] = language
                response = self.client.get(dashboard_url)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.wsgi_request.LANGUAGE_CODE, language)
                self.assertContains(response, f'lang="{language}" dir="{direction}"')
                self.assertContains(response, dashboard_label)
                self.assertIn("Cookie", response["Vary"])

    def test_login_page_uses_selected_language(self):
        self.client.logout()
        expected = {
            "fr": (
                "ltr",
                "Se connecter",
                "Mot de passe",
                "Mot de passe oublié ?",
                "Créer votre espace MindWell",
            ),
            "ar": (
                "rtl",
                "تسجيل الدخول",
                "كلمة المرور",
                "هل نسيت كلمة المرور؟",
                "أنشئ مساحتك على MindWell",
            ),
            "en": (
                "ltr",
                "Sign in",
                "Password",
                "Forgot your password?",
                "Create your MindWell space",
            ),
        }

        for language, (direction, sign_in, password, forgot_password, register) in expected.items():
            with self.subTest(language=language):
                self.client.cookies["django_language"] = language
                response = self.client.get(reverse("accounts:login"))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'<html lang="{language}" dir="{direction}">')
                self.assertContains(response, sign_in)
                self.assertContains(response, password)
                self.assertContains(response, forgot_password)
                self.assertContains(response, register)
                if language != "fr":
                    self.assertNotContains(response, "Retrouvez votre espace personnel")

    def test_appointment_action_messages_have_french_arabic_and_english(self):
        message = "Rendez-vous %(reference)s confirmé."
        expected = {
            "fr": "Rendez-vous MW-123 confirmé.",
            "ar": "تم تأكيد الموعد MW-123.",
            "en": "Appointment MW-123 confirmed.",
        }

        for language, translated_message in expected.items():
            with self.subTest(language=language), override(language):
                self.assertEqual(
                    gettext(message) % {"reference": "MW-123"},
                    translated_message,
                )
