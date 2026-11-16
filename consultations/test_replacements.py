from datetime import time, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, Notification, PsychologueProfile
from consultations.models import (
    Consultation,
    RecurringSession,
    ReplacementChangeRequest,
)
from consultations.replacement_service import (
    decline_replacement,
    owed_replacements_for_patient,
    serialize_replacement,
)


class ReplacementServiceTests(TestCase):
    def setUp(self):
        self.patient = CustomUser.objects.create_user(
            username='repl-patient', password='x', user_type='patient'
        )
        self.other = CustomUser.objects.create_user(
            username='repl-other', password='x', user_type='patient'
        )
        self.psych = CustomUser.objects.create_user(
            username='repl-psych', password='x', user_type='psychologue'
        )
        self.today = timezone.localdate()

    def _consultation(self, **overrides):
        defaults = dict(
            patient=self.patient,
            psychologue=self.psych,
            date=self.today,
            start_time=time(10, 0),
            duration_minutes=45,
            price=Decimal('50.00'),
            status=Consultation.Status.CANCELLED,
            cancellation_reason=Consultation.CancellationReason.PSYCHOLOGUE,
            payment_status=Consultation.PaymentStatus.PAID,
            cancelled_at=timezone.now(),
        )
        defaults.update(overrides)
        return Consultation.objects.create(**defaults)

    def test_owed_replacement_is_listed(self):
        consultation = self._consultation()
        self.assertIn(consultation, owed_replacements_for_patient(self.patient))

    def test_patient_cancelled_is_not_owed(self):
        consultation = self._consultation(
            cancellation_reason=Consultation.CancellationReason.PATIENT
        )
        self.assertNotIn(
            consultation, owed_replacements_for_patient(self.patient)
        )

    def test_technical_cancelled_by_psychologist_is_owed(self):
        consultation = self._consultation(
            cancellation_reason=Consultation.CancellationReason.TECHNICAL,
            cancelled_by=self.psych,
        )
        self.assertIn(
            consultation, owed_replacements_for_patient(self.patient)
        )

    def test_technical_cancelled_by_patient_is_not_owed(self):
        consultation = self._consultation(
            cancellation_reason=Consultation.CancellationReason.TECHNICAL,
            cancelled_by=self.patient,
        )
        self.assertNotIn(
            consultation, owed_replacements_for_patient(self.patient)
        )

    def test_unpaid_is_not_owed(self):
        consultation = self._consultation(
            payment_status=Consultation.PaymentStatus.UNPAID
        )
        self.assertNotIn(
            consultation, owed_replacements_for_patient(self.patient)
        )

    def test_already_replaced_is_excluded(self):
        original = self._consultation()
        Consultation.objects.create(
            patient=self.patient,
            psychologue=self.psych,
            date=self.today,
            start_time=time(11, 0),
            duration_minutes=45,
            price=Decimal('0.00'),
            status=Consultation.Status.PENDING,
            payment_status=Consultation.PaymentStatus.PAID,
            is_replacement=True,
            replaced_consultation=original,
        )
        self.assertNotIn(original, owed_replacements_for_patient(self.patient))

    def test_declined_is_excluded(self):
        consultation = self._consultation()
        consultation.replacement_declined_at = timezone.now()
        consultation.save(update_fields=['replacement_declined_at'])
        self.assertNotIn(
            consultation, owed_replacements_for_patient(self.patient)
        )

    def test_decline_persists(self):
        consultation = self._consultation()
        result, error = decline_replacement(consultation.pk, self.patient)
        self.assertIsNone(error)
        result.refresh_from_db()
        self.assertIsNotNone(result.replacement_declined_at)
        self.assertNotIn(result, owed_replacements_for_patient(self.patient))

    def test_decline_requires_owner(self):
        consultation = self._consultation()
        with self.assertRaises(PermissionDenied):
            decline_replacement(consultation.pk, self.other)

    def test_serialize_includes_book_url(self):
        consultation = self._consultation()
        payload = serialize_replacement(consultation)
        self.assertIn('book_url', payload)
        self.assertIn(f'/book/{self.psych.pk}/', payload['book_url'])


class ReplacementApiTests(TestCase):
    def setUp(self):
        self.patient = CustomUser.objects.create_user(
            username='repl-api-patient', password='x', user_type='patient'
        )
        self.psych = CustomUser.objects.create_user(
            username='repl-api-psych', password='x', user_type='psychologue'
        )
        self.list_url = reverse('consultations:upcoming_replacements')

    def _consultation(self):
        return Consultation.objects.create(
            patient=self.patient,
            psychologue=self.psych,
            date=timezone.localdate(),
            start_time=time(10, 0),
            duration_minutes=45,
            price=Decimal('50.00'),
            status=Consultation.Status.CANCELLED,
            cancellation_reason=Consultation.CancellationReason.PSYCHOLOGUE,
            payment_status=Consultation.PaymentStatus.PAID,
            cancelled_at=timezone.now(),
        )

    def test_patient_sees_owed_replacement(self):
        consultation = self._consultation()
        self.client.force_login(self.patient)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['replacements']), 1)
        self.assertEqual(data['replacements'][0]['id'], str(consultation.pk))

    def test_non_patient_forbidden(self):
        self.client.force_login(self.psych)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_decline_endpoint_persists(self):
        consultation = self._consultation()
        self.client.force_login(self.patient)
        response = self.client.post(
            reverse(
                'consultations:decline_replacement', args=[consultation.pk]
            )
        )
        self.assertEqual(response.status_code, 200)
        consultation.refresh_from_db()
        self.assertIsNotNone(consultation.replacement_declined_at)


class ReplacementChangeRequestTests(TestCase):
    def setUp(self):
        self.patient = CustomUser.objects.create_user(
            username='rcr-patient', password='x', user_type='patient'
        )
        self.psych = CustomUser.objects.create_user(
            username='rcr-psych', password='x', user_type='psychologue'
        )
        self.other_psych = CustomUser.objects.create_user(
            username='rcr-other-psych', password='x', user_type='psychologue'
        )
        PsychologueProfile.objects.create(user=self.psych, is_verified=True)
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            psychologue=self.psych,
            date=timezone.localdate(),
            start_time=time(10, 0),
            duration_minutes=45,
            price=Decimal('50.00'),
            status=Consultation.Status.CANCELLED,
            cancellation_reason=Consultation.CancellationReason.PSYCHOLOGUE,
            payment_status=Consultation.PaymentStatus.PAID,
            cancelled_at=timezone.now(),
        )

    def test_patient_can_submit_change_request(self):
        self.client.force_login(self.patient)
        response = self.client.post(
            reverse(
                'consultations:submit_change_request',
                args=[self.consultation.pk],
            ),
            data='{"message": "Je préfère le matin."}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        change_request = ReplacementChangeRequest.objects.get(
            replacement_consultation=self.consultation
        )
        self.assertEqual(change_request.status, 'pending')
        self.assertEqual(change_request.message, 'Je préfère le matin.')
        self.assertTrue(Notification.objects.filter(user=self.psych).exists())

    def test_duplicate_pending_request_rejected(self):
        ReplacementChangeRequest.objects.create(
            replacement_consultation=self.consultation,
            patient=self.patient,
            message='Première demande.',
        )
        self.client.force_login(self.patient)
        response = self.client.post(
            reverse(
                'consultations:submit_change_request',
                args=[self.consultation.pk],
            ),
            data='{"message": "Deuxième demande."}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            ReplacementChangeRequest.objects.filter(
                replacement_consultation=self.consultation
            ).count(),
            1,
        )

    def test_non_owed_consultation_rejected(self):
        active = Consultation.objects.create(
            patient=self.patient,
            psychologue=self.psych,
            date=timezone.localdate(),
            start_time=time(14, 0),
            duration_minutes=45,
            price=Decimal('50.00'),
            status=Consultation.Status.PENDING,
        )
        self.client.force_login(self.patient)
        response = self.client.post(
            reverse('consultations:submit_change_request', args=[active.pk]),
            data='{"message": "Bonjour"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_psychologist_can_view_change_requests(self):
        ReplacementChangeRequest.objects.create(
            replacement_consultation=self.consultation,
            patient=self.patient,
            message='Changement souhaité.',
        )
        self.client.force_login(self.psych)
        response = self.client.get(
            reverse('consultations:get_change_requests')
        )
        self.assertEqual(response.status_code, 200)
        requests = response.json()['requests']
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]['message'], 'Changement souhaité.')

    def test_psychologist_can_accept_change_request(self):
        change_request = ReplacementChangeRequest.objects.create(
            replacement_consultation=self.consultation,
            patient=self.patient,
            message='Changement souhaité.',
        )
        self.client.force_login(self.psych)
        response = self.client.post(
            reverse(
                'consultations:respond_to_change_request',
                args=[change_request.pk],
            ),
            data='{"action": "accept", "response": "D’accord."}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        change_request.refresh_from_db()
        self.assertEqual(change_request.status, 'accepted')
        self.assertTrue(Notification.objects.filter(user=self.patient).exists())

    def test_other_psychologist_cannot_respond(self):
        change_request = ReplacementChangeRequest.objects.create(
            replacement_consultation=self.consultation,
            patient=self.patient,
            message='Changement souhaité.',
        )
        self.client.force_login(self.other_psych)
        response = self.client.post(
            reverse(
                'consultations:respond_to_change_request',
                args=[change_request.pk],
            ),
            data='{"action": "reject"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_patient_submit_then_psychologist_list(self):
        # Full flow: patient submits via the API, psychologist lists via the API.
        self.client.force_login(self.patient)
        submit = self.client.post(
            reverse(
                'consultations:submit_change_request',
                args=[self.consultation.pk],
            ),
            data='{"message": "Je préfère le matin."}',
            content_type='application/json',
        )
        self.assertEqual(submit.status_code, 200, submit.content)

        self.client.force_login(self.psych)
        listing = self.client.get(
            reverse('consultations:get_change_requests')
        )
        self.assertEqual(listing.status_code, 200, listing.content)
        self.assertEqual(len(listing.json()['requests']), 1)

    def test_dashboard_renders_pending_request_server_side(self):
        ReplacementChangeRequest.objects.create(
            replacement_consultation=self.consultation,
            patient=self.patient,
            message='Message de test bien visible.',
        )
        self.client.force_login(self.psych)
        response = self.client.get(
            reverse('accounts:psychologue_dashboard')
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('id="change-requests-list"', html)
        self.assertIn('Message de test bien visible.', html)

    def test_dashboard_renders_legacy_reschedule_request(self):
        session = RecurringSession.objects.create(
            patient=self.patient,
            psychologue=self.psych,
            weekday=1,
            start_time=time(10, 0),
            duration_minutes=45,
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
            status=RecurringSession.Status.PROPOSED,
            patient_note='Message de série bien visible.',
            reschedule_requested=True,
            reschedule_request_at=timezone.now(),
        )
        self.client.force_login(self.psych)
        response = self.client.get(
            reverse('accounts:psychologue_dashboard')
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('legacy-reschedule-list', html)
        self.assertIn('Message de série bien visible.', html)
        self.assertIn(session.patient.username, html)

    def test_emergency_cancel_records_psychologue_reason(self):
        future = timezone.localdate() + timedelta(days=3)
        consultation = Consultation.objects.create(
            patient=self.patient,
            psychologue=self.psych,
            date=future,
            start_time=time(10, 0),
            duration_minutes=45,
            price=Decimal('50.00'),
            status=Consultation.Status.CONFIRMED,
            payment_status=Consultation.PaymentStatus.PAID,
        )
        self.client.force_login(self.psych)
        response = self.client.post(
            reverse(
                'accounts:emergency_cancel_appointment',
                args=[consultation.pk],
            )
        )
        self.assertEqual(response.status_code, 302)
        consultation.refresh_from_db()
        self.assertEqual(consultation.status, Consultation.Status.CANCELLED)
        self.assertEqual(
            consultation.cancellation_reason,
            Consultation.CancellationReason.PSYCHOLOGUE,
        )
        self.assertIn(consultation, owed_replacements_for_patient(self.patient))