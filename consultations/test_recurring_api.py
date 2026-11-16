import json
from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, PsychologueProfile
from consultations.models import (
    Consultation,
    Creneau,
    RecurringOccurrence,
    RecurringSession,
    WeeklyAvailabilityRule,
)
from consultations.recurring_service import create_recurring_session
from consultations.scheduling import generate_slots


def next_weekday(weekday, start_from=None):
    start = start_from or timezone.localdate() + timedelta(days=1)
    while start.weekday() != weekday:
        start += timedelta(days=1)
    return start


class RecurringApiTests(TestCase):
    def setUp(self):
        self.patient = CustomUser.objects.create_user(
            username='api-patient', password='x', user_type='patient'
        )
        self.psychologue = CustomUser.objects.create_user(
            username='api-psych', password='x', user_type='psychologue'
        )
        self.profile = PsychologueProfile.objects.create(
            user=self.psychologue, is_verified=True, session_duration=45
        )
        self.start = next_weekday(1)
        WeeklyAvailabilityRule.objects.create(
            psychologue=self.psychologue,
            weekday=1,
            start_time=time(9),
            end_time=time(11),
            is_active=True,
        )
        generate_slots(self.psychologue)

    def _create_series(self, occurrence_count=3):
        return create_recurring_session(
            psychologue=self.psychologue,
            patient=self.patient,
            weekday=1,
            start_time=time(9),
            start_date=self.start,
            occurrence_count=occurrence_count,
        )[0]

    def test_create_series_api_requires_psychologist(self):
        self.client.force_login(self.patient)
        resp = self.client.post(
            reverse('consultations:create_recurring_session'),
            data=json.dumps({'patient_id': self.patient.pk}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)

    def test_create_series_api_creates_proposed(self):
        self.client.force_login(self.psychologue)
        resp = self.client.post(
            reverse('consultations:create_recurring_session'),
            data=json.dumps({
                'patient_id': self.patient.pk,
                'weekday': 1,
                'start_time': '09:00',
                'start_date': self.start.isoformat(),
                'occurrence_count': 3,
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body['session']['status'], 'proposed')
        self.assertEqual(body['session']['upcoming_occurrences'], 3)

    def test_upcoming_api_lists_sessions(self):
        self._create_series(3)
        self.client.force_login(self.patient)
        resp = self.client.get(reverse('consultations:upcoming_recurring_sessions'))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body['sessions']), 1)
        self.assertEqual(body['sessions'][0]['status'], 'proposed')

    def test_accept_api_activates_series(self):
        session = self._create_series(3)
        occurrence = RecurringOccurrence.objects.filter(
            recurring_session=session
        ).order_by('occurrence_date').first()
        self.client.force_login(self.patient)
        resp = self.client.post(
            reverse('consultations:accept_recurring_occurrence', args=[occurrence.pk])
        )
        self.assertEqual(resp.status_code, 200)
        session.refresh_from_db()
        self.assertEqual(session.status, RecurringSession.Status.ACTIVE)

    def test_skip_api_requires_ownership(self):
        session = self._create_series(1)
        occurrence = RecurringOccurrence.objects.get(recurring_session=session)
        other = CustomUser.objects.create_user(
            username='skip-api-other', password='x', user_type='patient'
        )
        self.client.force_login(other)
        resp = self.client.post(
            reverse('consultations:skip_recurring_occurrence', args=[occurrence.pk])
        )
        self.assertEqual(resp.status_code, 403)

    def test_cancel_series_api_rejects_non_owner(self):
        session = self._create_series(2)
        other = CustomUser.objects.create_user(
            username='cancel-api-other', password='x', user_type='psychologue'
        )
        self.client.force_login(other)
        resp = self.client.post(
            reverse('consultations:cancel_recurring_session', args=[session.pk])
        )
        self.assertEqual(resp.status_code, 403)

    def test_cancel_series_api_succeeds_for_owner(self):
        session = self._create_series(2)
        self.client.force_login(self.psychologue)
        resp = self.client.post(
            reverse('consultations:cancel_recurring_session', args=[session.pk])
        )
        self.assertEqual(resp.status_code, 200)
        session.refresh_from_db()
        self.assertEqual(session.status, RecurringSession.Status.CANCELLED)

    def test_skip_then_next_occurrence_advances_without_reload(self):
        """After skipping occurrence #1, the upcoming endpoint must return
        occurrence #2 as next_occurrence so the UI can render the next skip
        button without a full page reload."""
        session = self._create_series(3)
        occurrences = list(
            RecurringOccurrence.objects.filter(
                recurring_session=session, is_cancelled=False
            ).order_by('occurrence_date')
        )
        self.assertGreaterEqual(len(occurrences), 2)
        first, second = occurrences[0], occurrences[1]

        self.client.force_login(self.patient)

        # Before skip: next_occurrence is the first occurrence.
        resp = self.client.get(
            reverse('consultations:upcoming_recurring_sessions')
        )
        next_before = resp.json()['sessions'][0]['next_occurrence']
        self.assertEqual(next_before['id'], first.pk)

        # Skip the first occurrence.
        skip_resp = self.client.post(
            reverse('consultations:skip_recurring_occurrence', args=[first.pk])
        )
        self.assertEqual(skip_resp.status_code, 200)

        # After skip (no reload): next_occurrence must now be the second one,
        # proving the patient UI can show a fresh skip button.
        resp = self.client.get(
            reverse('consultations:upcoming_recurring_sessions')
        )
        body = resp.json()
        self.assertEqual(len(body['sessions']), 1)
        next_after = body['sessions'][0]['next_occurrence']
        self.assertEqual(next_after['id'], second.pk)
        self.assertEqual(body['sessions'][0]['upcoming_occurrences'], 2)

    def test_psychologue_only_sees_own_sessions(self):
        """A psychologue must NOT see other psychologists' series via the
        upcoming endpoint (explicit ownership filter)."""
        other_patient = CustomUser.objects.create_user(
            username='own-other-patient', password='x', user_type='patient'
        )
        other_psych = CustomUser.objects.create_user(
            username='own-other-psych', password='x', user_type='psychologue'
        )
        PsychologueProfile.objects.create(
            user=other_psych, is_verified=True, session_duration=45
        )
        # A series owned by the *other* psychologist, visible to our patient.
        other_session = create_recurring_session(
            psychologue=other_psych,
            patient=self.patient,
            weekday=1,
            start_time=time(9),
            start_date=self.start,
            occurrence_count=2,
        )[0]

        self.client.force_login(self.psychologue)
        resp = self.client.get(reverse('consultations:upcoming_recurring_sessions'))
        self.assertEqual(resp.status_code, 200)
        session_ids = [s['id'] for s in resp.json()['sessions']]
        # Our psychologist has no series of their own; must NOT see the other's.
        self.assertNotIn(other_session.pk, session_ids)
        self.assertEqual(session_ids, [])

    def test_request_change_stores_note_and_flags_series(self):
        session = self._create_series(3)
        self.client.force_login(self.patient)
        resp = self.client.post(
            reverse('consultations:request_recurring_change', args=[session.pk]),
            data=json.dumps({'note': 'Le mardi matin ne me convient pas.'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        session.refresh_from_db()
        self.assertTrue(session.reschedule_requested)
        self.assertFalse(session.reschedule_reviewed)
        self.assertIsNotNone(session.reschedule_request_at)
        self.assertEqual(
            session.patient_note, 'Le mardi matin ne me convient pas.'
        )
        # Exposed to the patient via the upcoming endpoint.
        self.assertTrue(resp.json()['session']['reschedule_requested'])

    def test_request_change_requires_note(self):
        session = self._create_series(3)
        self.client.force_login(self.patient)
        resp = self.client.post(
            reverse('consultations:request_recurring_change', args=[session.pk]),
            data=json.dumps({'note': '   '}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_request_change_rejects_non_owner(self):
        session = self._create_series(3)
        other = CustomUser.objects.create_user(
            username='change-other', password='x', user_type='patient'
        )
        self.client.force_login(other)
        resp = self.client.post(
            reverse('consultations:request_recurring_change', args=[session.pk]),
            data=json.dumps({'note': 'Je veux changer.'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)

    def test_request_change_rejects_active_series(self):
        session = self._create_series(3)
        occurrence = RecurringOccurrence.objects.filter(
            recurring_session=session
        ).order_by('occurrence_date').first()
        self.client.force_login(self.patient)
        self.client.post(
            reverse('consultations:accept_recurring_occurrence', args=[occurrence.pk])
        )
        resp = self.client.post(
            reverse('consultations:request_recurring_change', args=[session.pk]),
            data=json.dumps({'note': 'Trop tard.'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)