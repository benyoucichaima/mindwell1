from datetime import time, timedelta
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, PsychologueProfile
from consultations.models import Consultation, DoctorRating


class DoctorRatingFlowTests(TestCase):
    def setUp(self):
        self.patient = CustomUser.objects.create_user(
            username='rating-patient',
            password='test-password',
            user_type='patient',
        )
        self.other_patient = CustomUser.objects.create_user(
            username='rating-other-patient',
            password='test-password',
            user_type='patient',
        )
        self.doctor = CustomUser.objects.create_user(
            username='rating-doctor',
            first_name='Amina',
            last_name='Test',
            password='test-password',
            user_type='psychologue',
            is_active=True,
        )
        self.profile = PsychologueProfile.objects.create(
            user=self.doctor,
            is_verified=True,
        )
        self.consultation = self.create_consultation(self.patient)
        self.url = reverse(
            'accounts:rate_consultation',
            args=[self.consultation.pk],
        )
        self.client.force_login(self.patient)

    def create_consultation(self, patient, status=Consultation.Status.COMPLETED):
        return Consultation.objects.create(
            patient=patient,
            psychologue=self.doctor,
            date=timezone.localdate() - timedelta(days=1),
            start_time=time(10),
            end_time=time(11),
            duration_minutes=60,
            session_type=Consultation.SessionType.VIDEO,
            price='3200.00',
            status=status,
        )

    def test_completed_consultation_can_be_rated_and_real_average_is_displayed(self):
        response = self.client.post(self.url, {'rating': '5', 'comment': 'Merci'})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            DoctorRating.objects.get().rating,
            5,
        )
        search_response = self.client.get(reverse('accounts:trouver_psychologue'))
        self.assertContains(search_response, '5,0/5')
        self.assertContains(search_response, '· 1')
        self.assertNotContains(
            search_response,
            f'data-doctor-id="{self.doctor.pk}"',
        )

    def test_homepage_uses_saved_rating_and_hides_empty_profiles_as_new(self):
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'جديد')
        self.client.post(self.url, {'rating': '5'})

        response = self.client.get(reverse('home'))

        self.assertContains(response, '5,0/5')

    def test_incomplete_consultation_cannot_be_rated(self):
        consultation = self.create_consultation(
            self.patient,
            status=Consultation.Status.CONFIRMED,
        )

        response = self.client.post(
            reverse('accounts:rate_consultation', args=[consultation.pk]),
            {'rating': '4'},
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(DoctorRating.objects.exists())

    def test_patient_cannot_rate_another_patients_consultation(self):
        consultation = self.create_consultation(self.other_patient)

        response = self.client.post(
            reverse('accounts:rate_consultation', args=[consultation.pk]),
            {'rating': '4'},
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(DoctorRating.objects.exists())

    def test_duplicate_rating_is_rejected(self):
        self.client.post(self.url, {'rating': '5'})

        response = self.client.post(self.url, {'rating': '2'})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(DoctorRating.objects.count(), 1)
        self.assertEqual(DoctorRating.objects.get().rating, 5)

    def test_rating_outside_one_to_five_is_rejected(self):
        response = self.client.post(self.url, {'rating': '6'})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(DoctorRating.objects.exists())

    def test_unrated_completed_consultation_is_offered_once(self):
        page = self.client.get(reverse('accounts:trouver_psychologue'))

        self.assertContains(page, f'action="{self.url}"')
        self.assertContains(page, f'data-doctor-id="{self.doctor.pk}"')
        self.assertContains(page, 'class="psy-modal-backdrop"')
        self.assertEqual(page.content.decode().count('id="rating-modal"'), 1)
        card = page.content.decode().split('<article class="psy-card">', 1)[1]
        card = card.split('</article>', 1)[0]
        self.assertNotIn('<form', card)
        self.assertIn('name="rating"', page.content.decode())
        self.assertIn('name="comment"', page.content.decode())

    def test_search_card_displays_profile_photo_with_broken_image_fallback(self):
        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.profile.photo.save(
                    'portrait.png',
                    SimpleUploadedFile(
                        'portrait.png',
                        b'not-decoded-by-the-template',
                        content_type='image/png',
                    ),
                    save=True,
                )

                page = self.client.get(reverse('accounts:trouver_psychologue'))

        self.assertContains(
            page,
            'src="/media/psychologues/photos/portrait.png"',
        )
        self.assertContains(page, 'alt="Photo de Amina Test"')
        self.assertContains(page, 'loading="lazy"')
        self.assertContains(
            page,
            'onerror="this.hidden = true; this.nextElementSibling.hidden = false;"',
        )
        self.assertContains(page, 'data-avatar-fallback hidden')

    def test_search_page_hero_and_rating_modal_are_localized_and_accessible(self):
        for language, direction in (('fr', 'ltr'), ('ar', 'rtl'), ('en', 'ltr')):
            with self.subTest(language=language):
                self.client.cookies['django_language'] = language
                page = self.client.get(reverse('accounts:trouver_psychologue'))

                self.assertEqual(page.status_code, 200)
                self.assertContains(page, f'lang="{language}" dir="{direction}"')
                self.assertContains(page, 'background: #070b2b')
                self.assertContains(page, 'color: #ffffff')
                self.assertContains(page, 'data-ar="تقييم استشارة"')
                self.assertContains(page, 'role="dialog"')
