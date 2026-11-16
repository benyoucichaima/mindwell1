from datetime import date, time

from django.test import TestCase
from django.urls import reverse
from django.utils.translation import override

from accounts.models import CustomUser, PsychologueProfile
from consultations.models import Consultation

from .models import ContactMessage


class HelpCenterViewsTests(TestCase):
    def localized_url(self, name, language):
        with override(language):
            return reverse(name)

    def test_help_contact_and_faq_render_in_all_supported_languages(self):
        expected_directions = {"ar": "rtl", "fr": "ltr", "en": "ltr"}
        expected_content = {
            "ar": {
                "help": "مركز المساعدة",
                "contact": "تواصل معنا",
                "faq": "الأسئلة المتكررة",
            },
            "fr": {
                "help": "Centre d'aide",
                "contact": "Contactez-nous",
                "faq": "Questions fréquemment posées",
            },
            "en": {
                "help": "Help Center",
                "contact": "Contact us",
                "faq": "Frequently asked questions",
            },
        }
        page_names = ("aide", "contact", "faq")

        for language, direction in expected_directions.items():
            self.client.cookies["django_language"] = language
            for page_name in page_names:
                with self.subTest(language=language, page=page_name):
                    response = self.client.get(self.localized_url(page_name, language))

                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.wsgi_request.LANGUAGE_CODE, language)
                    self.assertContains(response, f'lang="{language}" dir="{direction}"')
                    self.assertContains(
                        response,
                        expected_content[language][
                            {"aide": "help", "contact": "contact", "faq": "faq"}[
                                page_name
                            ]
                        ],
                    )

    def test_help_links_use_existing_and_new_named_routes(self):
        for name in (
            "comment_ca_marche",
            "accounts:rendez_vous",
            "accounts:register_patient",
            "accounts:parametres",
            "accounts:delete_account",
            "psychologists",
            "accounts:login",
            "faq",
            "contact",
        ):
            with self.subTest(name=name):
                with override("fr"):
                    destination = reverse(name)
                    help_url = reverse("aide")
                response = self.client.get(help_url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'href="{destination}"')

    def test_public_help_destinations_render_successfully(self):
        for name in (
            "comment_ca_marche",
            "accounts:register_patient",
            "psychologists",
            "accounts:login",
            "faq",
            "contact",
        ):
            with self.subTest(name=name), override("fr"):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)

    def test_contact_form_persists_submission_in_every_language(self):
        payload = {
            "name": "Alex User",
            "email": "alex@example.com",
            "subject": "general",
            "message": "I need help with my account.",
        }

        for language in ("ar", "fr", "en"):
            with self.subTest(language=language):
                self.client.cookies["django_language"] = language
                response = self.client.post(
                    self.localized_url("contact", language),
                    payload,
                    follow=True,
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(ContactMessage.objects.count(), 1)
                self.assertTrue(response.context["messages"])
                self.assertEqual(response.wsgi_request.LANGUAGE_CODE, language)
                ContactMessage.objects.all().delete()

    def test_contact_form_shows_validation_errors(self):
        with override("fr"):
            contact_url = reverse("contact")

        response = self.client.post(
            contact_url,
            {"name": "", "email": "invalid", "subject": "", "message": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Veuillez corriger les erreurs du formulaire.")
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_help_language_switcher_keeps_the_current_page(self):
        with override("ar"):
            arabic_url = reverse("aide")
        with override("en"):
            english_url = reverse("aide")
        with override("fr"):
            set_language_url = reverse("set_language")

        self.client.cookies["django_language"] = "ar"
        response = self.client.get(arabic_url)
        self.assertContains(response, f'name="next" value="{english_url}"')

        response = self.client.post(
            set_language_url,
            {"language": "en", "next": english_url},
        )
        self.assertRedirects(response, english_url, fetch_redirect_response=False)

    def test_default_language_is_french_and_other_pages_keep_their_destination(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.wsgi_request.LANGUAGE_CODE, "fr")
        self.assertContains(response, '<html lang="fr" dir="ltr" id="htmlRoot">')

        with override("ar"):
            arabic_contact_url = reverse("contact")

        response = self.client.get(reverse("contact"))

        self.assertContains(
            response,
            f'name="next" value="{arabic_contact_url}"',
        )
        self.assertContains(response, 'name="language" value="ar"')

    def test_protected_help_destinations_redirect_anonymous_users_to_login(self):
        for name in (
            "accounts:rendez_vous",
            "accounts:parametres",
            "accounts:delete_account",
        ):
            with self.subTest(name=name), override("fr"):
                destination = reverse(name)
                response = self.client.get(destination)

                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("accounts:login"), response["Location"])
                self.assertIn("next=", response["Location"])

    def test_account_deletion_requires_correct_password_and_confirmation(self):
        user = CustomUser.objects.create_user(
            username="help-center-patient",
            email="patient@example.com",
            password="Secure-test-Password-1",
            user_type="patient",
        )
        psychologist = CustomUser.objects.create_user(
            username="help-center-psychologist",
            email="psychologist@example.com",
            password="Secure-test-Password-2",
            user_type="psychologue",
        )
        consultation = Consultation.objects.create(
            patient=user,
            psychologue=psychologist,
            date=date(2026, 11, 3),
            start_time=time(10),
            end_time=time(10, 50),
            duration_minutes=50,
            price="3200.00",
        )
        self.client.force_login(user)
        with override("fr"):
            delete_url = reverse("accounts:delete_account")

        response = self.client.post(
            delete_url,
            {"password": "wrong-password", "confirm": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(CustomUser.objects.filter(pk=user.pk).exists())

        response = self.client.post(
            delete_url,
            {"password": "Secure-test-Password-1", "confirm": "on"},
        )
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertNotEqual(user.email, "patient@example.com")
        self.assertFalse(user.check_password("Secure-test-Password-1"))
        self.assertTrue(
            Consultation.objects.filter(
                pk=consultation.pk,
                patient=user,
            ).exists()
        )


class SpecialistPhotoListTests(TestCase):
    def test_specialist_lists_use_profile_photo_instead_of_stale_user_avatar(self):
        specialist = CustomUser.objects.create_user(
            username="specialist-photo-list",
            first_name="Amel",
            last_name="Benali",
            user_type="psychologue",
        )
        specialist.avatar = "avatars/175b12d44f20edb22bdd90dea1f012d3.jpg"
        specialist.save(update_fields=["avatar"])
        profile = PsychologueProfile.objects.create(
            user=specialist,
            is_verified=True,
        )
        profile.photo = "psychologues/photos/Amel_Benali.jpg"
        profile.save(update_fields=["photo"])

        for page_name in ("nos_specialistes", "psychologists"):
            with self.subTest(page=page_name):
                response = self.client.get(reverse(page_name))

                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response,
                    'src="/media/psychologues/photos/Amel_Benali.jpg"',
                )
                self.assertNotContains(
                    response,
                    "/media/avatars/175b12d44f20edb22bdd90dea1f012d3.jpg",
                )
