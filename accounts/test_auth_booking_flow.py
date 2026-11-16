import re
from tempfile import TemporaryDirectory
from urllib.parse import urlencode

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser, PsychologueProfile


class GuestBookingAuthenticationTests(TestCase):
    def setUp(self):
        self.psychologue = CustomUser.objects.create_user(
            username='dr-martin',
            first_name='Alice',
            last_name='Martin',
            user_type='psychologue',
            is_active=True,
        )
        PsychologueProfile.objects.create(
            user=self.psychologue,
            is_verified=True,
        )
        self.booking_url = reverse(
            'accounts:book_consultation',
            args=[self.psychologue.pk],
        )
        self.login_url = reverse('accounts:login')

    def test_guest_booking_redirects_to_login_with_booking_as_next(self):
        response = self.client.get(self.booking_url)

        self.assertRedirects(
            response,
            f'{self.login_url}?{urlencode({"next": self.booking_url})}',
            fetch_redirect_response=False,
        )

    def test_login_page_names_the_specialist_and_preserves_next_for_signup(self):
        response = self.client.get(
            self.login_url,
            {'next': self.booking_url},
        )

        self.assertContains(
            response,
            'Veuillez vous connecter ou créer un compte pour terminer votre '
            'réservation avec Dr. Alice Martin.',
        )
        self.assertContains(
            response,
            f'{reverse("accounts:choose_account_type")}?next={self.booking_url}',
        )

        choice_response = self.client.get(
            reverse('accounts:choose_account_type'),
            {'next': self.booking_url},
        )
        self.assertContains(
            choice_response,
            f'{reverse("accounts:register_patient")}?next={self.booking_url}',
        )

        registration_response = self.client.get(
            reverse('accounts:register_patient'),
            {'next': self.booking_url},
        )
        self.assertContains(
            registration_response,
            f'<input type="hidden" name="next" value="{self.booking_url}">',
            html=True,
        )

    def test_successful_login_returns_to_booking(self):
        patient = CustomUser.objects.create_user(
            username='patient',
            email='patient@example.com',
            password='test-password',
            user_type='patient',
        )

        response = self.client.post(
            self.login_url,
            {
                'email': patient.email,
                'password': 'test-password',
                'next': self.booking_url,
            },
        )

        self.assertRedirects(response, self.booking_url, fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), patient.pk)

    def test_patient_registration_returns_to_booking(self):
        register_url = reverse('accounts:register_patient')

        response = self.client.post(
            register_url,
            {
                'first_name': 'New',
                'last_name': 'Patient',
                'email': 'new-patient@example.com',
                'phone': '',
                'password': 'test-password',
                'password_confirm': 'test-password',
                'next': self.booking_url,
            },
        )

        self.assertRedirects(response, self.booking_url, fetch_redirect_response=False)
        self.assertEqual(
            int(self.client.session['_auth_user_id']),
            CustomUser.objects.get(email='new-patient@example.com').pk,
        )

    def test_login_rejects_external_next_url(self):
        patient = CustomUser.objects.create_user(
            username='safe-patient',
            email='safe-patient@example.com',
            password='test-password',
            user_type='patient',
        )

        response = self.client.post(
            self.login_url,
            {
                'email': patient.email,
                'password': 'test-password',
                'next': '//example.com/booking/',
            },
        )

        self.assertRedirects(
            response,
            reverse('accounts:patient_dashboard'),
            fetch_redirect_response=False,
        )

    def test_csrf_protected_login_form_completes_booking_redirect(self):
        patient = CustomUser.objects.create_user(
            username='csrf-patient',
            email='csrf-patient@example.com',
            password='test-password',
            user_type='patient',
        )
        csrf_client = Client(enforce_csrf_checks=True)
        login_page = csrf_client.get(
            self.login_url,
            {'next': self.booking_url},
        )
        token = re.search(
            rb'name="csrfmiddlewaretoken" value="([^"]+)"',
            login_page.content,
        )

        self.assertIsNotNone(token)
        self.assertIn('no-store', login_page.headers['Cache-Control'])

        response = csrf_client.post(
            self.login_url,
            {
                'email': patient.email,
                'password': 'test-password',
                'next': self.booking_url,
                'csrfmiddlewaretoken': token.group(1).decode(),
            },
        )

        self.assertRedirects(response, self.booking_url, fetch_redirect_response=False)
        booking_page = csrf_client.get(self.booking_url)
        self.assertEqual(booking_page.status_code, 200)

    def test_csrf_protected_patient_registration_form_submits(self):
        register_url = reverse('accounts:register_patient')
        csrf_client = Client(enforce_csrf_checks=True)
        registration_page = csrf_client.get(
            register_url,
            {'next': self.booking_url},
        )
        token = re.search(
            rb'name="csrfmiddlewaretoken" value="([^"]+)"',
            registration_page.content,
        )

        self.assertIsNotNone(token)
        self.assertIn('no-store', registration_page.headers['Cache-Control'])

        response = csrf_client.post(
            register_url,
            {
                'first_name': 'New',
                'last_name': 'Patient',
                'email': 'csrf-new-patient@example.com',
                'phone': '',
                'password': 'test-password',
                'password_confirm': 'test-password',
                'next': self.booking_url,
                'csrfmiddlewaretoken': token.group(1).decode(),
            },
        )

        self.assertRedirects(response, self.booking_url, fetch_redirect_response=False)
        booking_page = csrf_client.get(self.booking_url)
        self.assertEqual(booking_page.status_code, 200)

    def test_psychologist_registration_saves_uploaded_verification_documents(self):
        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    reverse('accounts:register_psychologue'),
                    {
                        'first_name': 'Nadia',
                        'last_name': 'Test',
                        'email': 'nadia-test@example.com',
                        'phone': '0550000000',
                        'password': 'test-password',
                        'password_confirm': 'test-password',
                        'specialites': 'clinique',
                        'experience': '5',
                        'license_number': 'ADELI-123',
                        'city': 'Alger',
                        'diploma_file': SimpleUploadedFile(
                            'diploma.pdf',
                            b'%PDF-1.4 diploma',
                            content_type='application/pdf',
                        ),
                        'id_document_file': SimpleUploadedFile(
                            'identity.pdf',
                            b'%PDF-1.4 identity',
                            content_type='application/pdf',
                        ),
                        'registration_file': SimpleUploadedFile(
                            'registration.pdf',
                            b'%PDF-1.4 registration',
                            content_type='application/pdf',
                        ),
                    },
                )

                self.assertEqual(response.status_code, 302)
                profile = PsychologueProfile.objects.get(
                    user__email='nadia-test@example.com',
                )
                self.assertEqual(
                    profile.diploma_file.name,
                    'psychologues/docs/diplomas/diploma.pdf',
                )
                self.assertEqual(
                    profile.id_document_file.name,
                    'psychologues/docs/ids/identity.pdf',
                )
                self.assertEqual(
                    profile.registration_file.name,
                    'psychologues/docs/registrations/registration.pdf',
                )

    def test_booking_form_token_remains_valid_after_authenticated_page_load(self):
        patient = CustomUser.objects.create_user(
            username='booking-csrf-patient',
            password='test-password',
            user_type='patient',
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(patient)

        booking_page = csrf_client.get(self.booking_url)
        token = re.search(
            rb'name="csrfmiddlewaretoken" value="([^"]+)"',
            booking_page.content,
        )

        self.assertEqual(booking_page.status_code, 200)
        self.assertIsNotNone(token)
        self.assertIn('no-store', booking_page.headers['Cache-Control'])

        response = csrf_client.post(
            self.booking_url,
            {
                'creneau_id': 'invalid',
                'consultation_type': 'video',
                'csrfmiddlewaretoken': token.group(1).decode(),
            },
        )

        self.assertRedirects(
            response,
            self.booking_url,
            fetch_redirect_response=False,
        )
