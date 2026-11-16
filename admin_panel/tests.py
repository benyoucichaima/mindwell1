import json
from datetime import time
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from accounts.models import CustomUser, Notification, PsychologueProfile
from consultations.models import Consultation
from mindwell.models import ContactMessage
from .models import Report


class AdminDashboardTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_superuser(
            username='dashboard-admin',
            email='admin@example.test',
            password='test-password',
            user_type='admin',
        )
        self.patient = CustomUser.objects.create_user(
            username='dashboard-patient',
            user_type='patient',
        )
        self.pending_psychologue = CustomUser.objects.create_user(
            username='pending-psychologue',
            email='pending@example.test',
            user_type='psychologue',
            first_name='Pending',
        )
        self.pending_profile = PsychologueProfile.objects.create(
            user=self.pending_psychologue,
            specialty='clinique',
        )
        self.verified_psychologue = CustomUser.objects.create_user(
            username='verified-psychologue',
            user_type='psychologue',
        )
        self.verified_profile = PsychologueProfile.objects.create(
            user=self.verified_psychologue,
            is_verified=True,
            verification_status='approved',
        )

    def create_consultation(self, status):
        return Consultation.objects.create(
            patient=self.patient,
            psychologue=self.verified_psychologue,
            date=timezone.localdate(),
            start_time=time(10),
            end_time=time(11),
            duration_minutes=60,
            price='3200.00',
            status=status,
        )

    def test_dashboard_renders_database_statistics_and_recent_data(self):
        self.create_consultation(Consultation.Status.CONFIRMED)
        self.create_consultation(Consultation.Status.COMPLETED)
        report = Report.objects.create(
            reporter=self.patient,
            target=self.verified_psychologue,
            reason='Please review this account.',
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_patients'], 1)
        self.assertEqual(response.context['verified_psychologues'], 1)
        self.assertEqual(response.context['pending_verifications'], 1)
        self.assertEqual(response.context['active_appointments'], 1)
        self.assertEqual(response.context['total_sessions'], 1)
        self.assertEqual(list(response.context['unverified_psychologues']), [self.pending_profile])
        self.assertEqual(list(response.context['recent_reports']), [report])
        self.assertContains(response, 'handleVerification')
        self.assertContains(response, 'admin-notification-toggle')
        self.assertContains(response, 'Please review this account.')

    @patch('admin_panel.views.send_mail', return_value=1)
    def test_superuser_can_accept_and_email_psychologue(self, send_mail_mock):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('verify_psychologue_api', args=[self.pending_profile.pk]),
            data=json.dumps({'action': 'accept'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        self.pending_profile.refresh_from_db()
        self.assertTrue(self.pending_profile.is_verified)
        self.assertEqual(self.pending_profile.verification_status, 'approved')
        self.assertIsNotNone(self.pending_profile.verification_date)
        send_mail_mock.assert_called_once()

    def test_superuser_can_reject_psychologue_without_deleting_profile(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('verify_psychologue_api', args=[self.pending_profile.pk]),
            data=json.dumps({'action': 'reject', 'reason': 'Please submit a valid license.'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.pending_profile.refresh_from_db()
        self.assertFalse(self.pending_profile.is_verified)
        self.assertEqual(self.pending_profile.verification_status, 'rejected')
        self.assertEqual(
            self.pending_profile.rejection_reason,
            'Please submit a valid license.',
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.pending_psychologue,
                title='Modifications requises sur le profil psychologue',
            ).exists()
        )

    @patch('admin_panel.views.send_mail', side_effect=OSError('SMTP unavailable'))
    def test_email_failure_does_not_undo_psychologue_approval(self, send_mail_mock):
        self.client.force_login(self.admin)

        with self.assertLogs('admin_panel.views', level='ERROR'):
            response = self.client.post(
                reverse('verify_psychologue_api', args=[self.pending_profile.pk]),
                data=json.dumps({'action': 'accept'}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        self.assertIn("e-mail de bienvenue n'a pas pu être envoyé", response.json()['message'])
        self.pending_profile.refresh_from_db()
        self.pending_psychologue.refresh_from_db()
        self.assertEqual(self.pending_profile.verification_status, 'approved')
        self.assertTrue(self.pending_psychologue.is_active)
        send_mail_mock.assert_called_once()

    def test_repeated_verification_action_is_idempotent(self):
        self.client.force_login(self.admin)
        url = reverse('verify_psychologue_api', args=[self.pending_profile.pk])

        first_response = self.client.post(
            url,
            data=json.dumps({'action': 'reject', 'reason': 'Incomplete documents.'}),
            content_type='application/json',
        )
        repeated_response = self.client.post(
            url,
            data=json.dumps({'action': 'reject', 'reason': 'Incomplete documents.'}),
            content_type='application/json',
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.json()['pending_count_delta'], -1)
        self.assertEqual(repeated_response.status_code, 200)
        self.assertEqual(repeated_response.json()['pending_count_delta'], 0)
        self.pending_profile.refresh_from_db()
        self.assertEqual(self.pending_profile.verification_status, 'rejected')

    def test_admin_sections_have_working_named_routes(self):
        self.client.force_login(self.admin)
        routes = (
            'admin_users',
            'admin_patients',
            'admin_psychologues',
            'admin_verifications',
            'admin_appointments',
            'admin_statistics',
            'admin_reports',
            'admin_settings',
            'admin_contact_messages',
        )

        for route_name in routes:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'aria-current="page"')
                self.assertEqual(response.context['section'], route_name[len('admin_'):])

    def test_language_switcher_activates_arabic_for_admin_panel(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('set_language'),
            {'language': 'ar', 'next': reverse('dashboard')},
        )

        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(response.cookies['django_language'].value, 'ar')

        dashboard = self.client.get(reverse('dashboard'))

        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, 'lang="ar" dir="rtl"')
        self.assertContains(dashboard, 'لوحة التحكم')
        self.assertContains(dashboard, 'الإدارة')

        verification_section = self.client.get(reverse('admin_verifications'))
        self.assertEqual(verification_section.status_code, 200)
        self.assertContains(verification_section, 'lang="ar" dir="rtl"')
        self.assertContains(verification_section, 'طلبات التحقق')

    def test_report_can_be_marked_resolved(self):
        report = Report.objects.create(
            reporter=self.patient,
            target=self.verified_psychologue,
            reason='A report to resolve.',
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('resolve_report_api', args=[report.pk]),
            data='{}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        report.refresh_from_db()
        self.assertTrue(report.is_resolved)

    def test_dashboard_and_apis_require_superuser(self):
        self.client.force_login(self.patient)

        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 302)
        response = self.client.post(
            reverse('verify_psychologue_api', args=[self.pending_profile.pk]),
            data=json.dumps({'action': 'accept'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)
        self.pending_profile.refresh_from_db()
        self.assertFalse(self.pending_profile.is_verified)

    def test_verification_api_rejects_bad_json_and_unknown_action(self):
        self.client.force_login(self.admin)
        url = reverse('verify_psychologue_api', args=[self.pending_profile.pk])

        invalid_json = self.client.post(url, data='{', content_type='application/json')
        invalid_action = self.client.post(
            url,
            data=json.dumps({'action': 'approve'}),
            content_type='application/json',
        )

        self.assertEqual(invalid_json.status_code, 400)
        self.assertEqual(invalid_action.status_code, 400)
        missing_profile = self.client.post(
            reverse('verify_psychologue_api', args=[999999]),
            data=json.dumps({'action': 'accept'}),
            content_type='application/json',
        )
        self.assertEqual(missing_profile.status_code, 404)
        self.assertEqual(missing_profile.json()['status'], 'error')

    def test_verification_api_requires_a_reason_to_reject(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('verify_psychologue_api', args=[self.pending_profile.pk]),
            data=json.dumps({'action': 'reject'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.pending_profile.refresh_from_db()
        self.assertEqual(self.pending_profile.verification_status, 'pending')

    def test_staff_can_view_private_dossier_documents_but_patients_cannot(self):
        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.pending_profile.diploma_file.save(
                    'diploma.pdf',
                    ContentFile(b'%PDF-1.4 test document'),
                    save=True,
                )
                dossier_url = reverse(
                    'admin_verification_detail',
                    args=[self.pending_profile.pk],
                )
                document_url = reverse(
                    'protected_media_document',
                    kwargs={'path': self.pending_profile.diploma_file.name},
                )

                self.client.force_login(self.patient)
                self.assertEqual(self.client.get(dossier_url).status_code, 302)
                self.assertEqual(self.client.get(document_url).status_code, 302)

                staff_user = CustomUser.objects.create_user(
                    username='review-staff',
                    is_staff=True,
                )
                self.client.force_login(staff_user)
                self.assertEqual(self.client.get(dossier_url).status_code, 200)
                staff_document = self.client.get(document_url)
                self.assertEqual(staff_document.status_code, 200)
                staff_document.close()

                self.client.force_login(self.admin)
                dossier = self.client.get(dossier_url)
                self.assertEqual(dossier.status_code, 200)
                self.assertContains(dossier, 'pending@example.test')
                self.assertContains(dossier, 'diploma.pdf')
                self.assertContains(dossier, document_url)
                self.assertContains(dossier, 'Aucun document fourni')

                document = self.client.get(document_url)
                self.assertEqual(document.status_code, 200)
                self.assertEqual(document['Content-Type'], 'application/pdf')
                self.assertIn('inline', document['Content-Disposition'])
                document.close()

                download = self.client.get(f'{document_url}?download=1')
                self.assertIn('attachment', download['Content-Disposition'])
                download.close()

    def test_dossier_strings_render_in_all_supported_languages(self):
        labels = {
            'fr': 'Aucun document fourni',
            'ar': 'لم يتم تقديم أي مستند',
            'en': 'No document provided',
        }
        self.client.force_login(self.admin)
        for language, missing_document_label in labels.items():
            self.client.cookies['django_language'] = language
            with self.subTest(language=language), override(language):
                response = self.client.get(
                    reverse(
                        'admin_verification_detail',
                        args=[self.pending_profile.pk],
                    ),
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, missing_document_label)
                direction = 'rtl' if language == 'ar' else 'ltr'
                self.assertContains(response, f'lang="{language}" dir="{direction}"')

    def test_dossier_accept_and_reject_require_confirmation_and_notify_psychologist(self):
        self.client.force_login(self.admin)
        dossier_url = reverse(
            'admin_verification_detail',
            args=[self.pending_profile.pk],
        )

        missing_confirmation = self.client.post(
            dossier_url,
            {'action': 'accept'},
        )
        self.assertEqual(missing_confirmation.status_code, 400)

        accepted = self.client.post(
            dossier_url,
            {'action': 'accept', 'confirm': 'yes'},
        )
        self.assertRedirects(accepted, reverse('admin_verifications'))
        self.pending_profile.refresh_from_db()
        self.assertEqual(self.pending_profile.verification_status, 'approved')
        self.assertTrue(
            Notification.objects.filter(
                user=self.pending_psychologue,
                title='Profil psychologue approuvé',
            ).exists()
        )

        second_user = CustomUser.objects.create_user(
            username='reject-from-dossier',
            email='reject@example.test',
            user_type='psychologue',
        )
        second_profile = PsychologueProfile.objects.create(user=second_user)
        rejected = self.client.post(
            reverse('admin_verification_detail', args=[second_profile.pk]),
            {
                'action': 'reject',
                'confirm': 'yes',
                'reason': 'Please provide your professional registration.',
            },
        )
        self.assertRedirects(rejected, reverse('admin_verifications'))
        second_profile.refresh_from_db()
        self.assertEqual(second_profile.verification_status, 'rejected')
        self.assertEqual(
            second_profile.rejection_reason,
            'Please provide your professional registration.',
        )

    def test_notifications_are_created_for_new_reports_and_contact_messages(self):
        report = Report.objects.create(
            reporter=self.patient,
            target=self.verified_psychologue,
            reason='Please investigate.',
        )
        contact = ContactMessage.objects.create(
            name='Contact User',
            email='contact@example.test',
            subject='general',
            message='A question for the team.',
        )

        admin_notifications = Notification.objects.filter(user=self.admin)
        self.assertTrue(
            admin_notifications.filter(
                title='Nouveau signalement reçu',
                url=reverse('admin_reports'),
            ).exists()
        )
        self.assertTrue(
            admin_notifications.filter(
                title='Nouveau message de contact',
                url=reverse('admin_contact_messages'),
            ).exists()
        )

    def test_notification_mark_read_is_post_only_scoped_and_mark_all_works(self):
        notification = Notification.objects.create(
            user=self.admin,
            title='A notice',
            message='Please review.',
            url=reverse('admin_verifications'),
        )
        other_notification = Notification.objects.create(
            user=self.patient,
            title='Private',
            message='Not yours.',
        )
        self.client.force_login(self.patient)
        denied = self.client.post(
            reverse('admin_mark_notification_read', args=[notification.pk]),
        )
        self.assertEqual(denied.status_code, 302)

        self.client.force_login(self.admin)
        marked = self.client.post(
            reverse('admin_mark_notification_read', args=[notification.pk]),
        )
        self.assertEqual(marked.status_code, 200)
        self.assertEqual(marked.json()['url'], reverse('admin_verifications'))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

        self.client.post(reverse('admin_mark_all_notifications_read'))
        other_notification.refresh_from_db()
        self.assertFalse(other_notification.is_read)
        self.assertFalse(
            Notification.objects.filter(user=self.admin, is_read=False).exists()
        )

        page = self.client.get(reverse('admin_notifications'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Notifications')

    def test_verification_api_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        dashboard_response = csrf_client.get(reverse('dashboard'))
        self.assertEqual(dashboard_response.status_code, 200)

        rejected_without_token = csrf_client.post(
            reverse('verify_psychologue_api', args=[self.pending_profile.pk]),
            data=json.dumps({'action': 'accept'}),
            content_type='application/json',
        )
        self.assertEqual(rejected_without_token.status_code, 403)

        csrf_token = csrf_client.cookies['csrftoken'].value
        accepted_with_token = csrf_client.post(
            reverse('verify_psychologue_api', args=[self.pending_profile.pk]),
            data=json.dumps({'action': 'accept'}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(accepted_with_token.status_code, 200)

    def test_dashboard_limits_verification_table_to_latest_five(self):
        for index in range(5):
            user = CustomUser.objects.create_user(
                username=f'pending-psychologue-{index}',
                user_type='psychologue',
            )
            PsychologueProfile.objects.create(user=user)
        self.client.force_login(self.admin)

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.context['pending_verifications'], 6)
        self.assertEqual(len(response.context['unverified_psychologues']), 5)

    def test_verification_api_validates_patient_id_safely(self):
        self.client.force_login(self.admin)
        url = reverse('verify_psychologue_api', args=[self.pending_profile.pk])

        # Missing patient_id on form post
        resp_missing = self.client.post(url, {})
        self.assertEqual(resp_missing.status_code, 400)
        self.assertEqual(resp_missing.json()['message'], 'patient_id est requis.')

        # SQL injection attempt on patient_id
        resp_sqli = self.client.post(url, {'patient_id': "1' OR '1'='1", 'action': 'accept'})
        self.assertEqual(resp_sqli.status_code, 400)
        self.assertEqual(resp_sqli.json()['message'], 'Patient introuvable ou ID invalide.')

        # Non-existent patient_id
        resp_nonexistent = self.client.post(url, {'patient_id': 999999, 'action': 'accept'})
        self.assertEqual(resp_nonexistent.status_code, 400)
        self.assertEqual(resp_nonexistent.json()['message'], 'Patient introuvable ou ID invalide.')

        # Valid patient_id
        resp_valid = self.client.post(url, {'patient_id': self.patient.pk, 'action': 'accept'})
        self.assertEqual(resp_valid.status_code, 200)
        self.assertEqual(resp_valid.json()['status'], 'success')


class PublicHomepageIntegrityTests(TestCase):
    def test_homepage_does_not_claim_unverified_platform_statistics_or_certifications(self):
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '98,4%')
        self.assertNotContains(response, '+12 000')
        self.assertNotContains(response, '&lt; 48h')
        self.assertNotContains(response, 'HDS')
        self.assertNotContains(response, 'SecNumCloud')
