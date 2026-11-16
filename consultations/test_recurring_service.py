from datetime import time, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, PsychologueProfile
from consultations.models import (
    AvailabilityException,
    Consultation,
    Creneau,
    RecurringOccurrence,
    RecurringSession,
    WeeklyAvailabilityRule,
)
from consultations.recurring_service import (
    DEFAULT_SERIES_WEEKS,
    accept_recurring_occurrence,
    cancel_series,
    create_recurring_session,
    materialize_series_for_consultation,
    skip_occurrence,
    upcoming_occurrences_for_patient,
)
from consultations.scheduling import generate_slots


def next_weekday(weekday, start_from=None):
    start = start_from or timezone.localdate() + timedelta(days=1)
    while start.weekday() != weekday:
        start += timedelta(days=1)
    return start


class RecurringServiceTests(TestCase):
    def setUp(self):
        self.patient = CustomUser.objects.create_user(
            username='recur-patient', password='x', user_type='patient'
        )
        self.psychologue = CustomUser.objects.create_user(
            username='recur-psych', password='x', user_type='psychologue'
        )
        self.profile = PsychologueProfile.objects.create(
            user=self.psychologue, is_verified=True, session_duration=45
        )
        # A weekly rule so generated slots exist for the weekday.
        self.start = next_weekday(1)  # Tuesday
        WeeklyAvailabilityRule.objects.create(
            psychologue=self.psychologue,
            weekday=1,
            start_time=time(9),
            end_time=time(11),
            is_active=True,
        )
        generate_slots(self.psychologue)

    def _create_series(self, **kwargs):
        defaults = dict(
            psychologue=self.psychologue,
            patient=self.patient,
            weekday=1,
            start_time=time(9),
            start_date=self.start,
            end_date=self.start + timedelta(weeks=3),
        )
        defaults.update(kwargs)
        return create_recurring_session(**defaults)

    def test_create_series_generates_planned_occurrences(self):
        session, warnings = self._create_series()

        occurrences = list(
            RecurringOccurrence.objects.filter(recurring_session=session).order_by('occurrence_date')
        )
        self.assertEqual(len(occurrences), 4)
        self.assertEqual(occurrences[0].occurrence_date, self.start)
        self.assertTrue(all(o.occurrence_date.weekday() == 1 for o in occurrences))
        self.assertTrue(all(o.consultation_id is None for o in occurrences))
        # Series starts PROPOSED (patient consent required).
        self.assertEqual(session.status, RecurringSession.Status.PROPOSED)

    def test_create_series_respects_occurrence_count(self):
        session, _ = self._create_series(occurrence_count=2)
        self.assertEqual(
            RecurringOccurrence.objects.filter(recurring_session=session).count(), 2
        )
        self.assertEqual(session.end_date, self.start + timedelta(weeks=1))

    def test_create_series_default_is_four_weeks(self):
        start = self.start
        session, _ = create_recurring_session(
            psychologue=self.psychologue,
            patient=self.patient,
            weekday=1,
            start_time=time(9),
            start_date=start,
        )
        self.assertEqual(session.end_date, start + timedelta(weeks=DEFAULT_SERIES_WEEKS) - timedelta(days=1))

    def test_create_series_rejects_unverified_psychologue(self):
        self.profile.is_verified = False
        self.profile.save(update_fields=['is_verified'])
        with self.assertRaises(ValidationError):
            self._create_series()

    def test_create_series_rejects_when_no_future_occurrence(self):
        """A series whose every date is in the past must be rejected rather than
        persisted empty (an empty PROPOSED series has nothing to accept)."""
        from datetime import timedelta as _td

        past_start = timezone.localdate() - _td(days=7)
        with self.assertRaises(ValidationError):
            create_recurring_session(
                psychologue=self.psychologue,
                patient=self.patient,
                weekday=1,
                start_time=time(9),
                start_date=past_start,
                occurrence_count=1,
            )
        self.assertFalse(
            RecurringSession.objects.filter(patient=self.patient).exists()
        )

    def test_create_series_skips_closed_dates(self):
        closed_day = self.start + timedelta(weeks=1)
        AvailabilityException.objects.create(
            psychologue=self.psychologue,
            date=closed_day,
            kind=AvailabilityException.Kind.CLOSED,
        )
        session, _ = self._create_series()
        self.assertFalse(
            RecurringOccurrence.objects.filter(
                recurring_session=session, occurrence_date=closed_day
            ).exists()
        )
        self.assertEqual(
            RecurringOccurrence.objects.filter(recurring_session=session).count(), 3
        )

    def test_accept_first_occurrence_activates_and_materializes_all_confirmed(self):
        session, _ = self._create_series(occurrence_count=3)
        occurrences = list(
            RecurringOccurrence.objects.filter(recurring_session=session).order_by('occurrence_date')
        )

        occ, consultation, error = accept_recurring_occurrence(occurrences[0].pk, self.patient)

        self.assertIsNone(error)
        self.assertIsNotNone(consultation)
        # First acceptance confirms the whole series.
        session.refresh_from_db()
        self.assertEqual(session.status, RecurringSession.Status.ACTIVE)
        self.assertEqual(consultation.status, Consultation.Status.CONFIRMED)
        self.assertEqual(consultation.date, self.start)
        # All remaining future occurrences materialized as CONFIRMED.
        self.assertEqual(
            Consultation.objects.filter(recurring_session=session).count(), 3
        )
        self.assertTrue(
            all(
                c.status == Consultation.Status.CONFIRMED
                for c in Consultation.objects.filter(recurring_session=session)
            )
        )
        occ.refresh_from_db()
        self.assertIsNotNone(occ.creneau_id)
        self.assertIsNotNone(occ.consultation_id)

    def test_accept_occurrence_rejects_other_patient(self):
        session, _ = self._create_series(occurrence_count=1)
        occurrence = RecurringOccurrence.objects.get(recurring_session=session)
        other = CustomUser.objects.create_user(
            username='other-patient', password='x', user_type='patient'
        )
        _, _, error = accept_recurring_occurrence(occurrence.pk, other)
        self.assertIsNotNone(error)

    def test_accept_occurrence_is_idempotent(self):
        session, _ = self._create_series(occurrence_count=1)
        occurrence = RecurringOccurrence.objects.get(recurring_session=session)
        _, first, _ = accept_recurring_occurrence(occurrence.pk, self.patient)
        _, second, error = accept_recurring_occurrence(occurrence.pk, self.patient)
        self.assertIsNone(error)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            Consultation.objects.filter(recurring_session=session).count(), 1
        )

    def test_skip_occurrence_cancels_and_frees_slot(self):
        session, _ = self._create_series(occurrence_count=1)
        occurrence = RecurringOccurrence.objects.get(recurring_session=session)
        _, consultation, _ = accept_recurring_occurrence(occurrence.pk, self.patient)

        occ, error = skip_occurrence(occurrence.pk, self.patient)

        self.assertIsNone(error)
        self.assertTrue(occ.is_cancelled)
        consultation.refresh_from_db()
        self.assertEqual(consultation.status, Consultation.Status.CANCELLED)
        consultation.creneau.refresh_from_db()
        self.assertEqual(consultation.creneau.statut, Creneau.Statut.LIBRE)

    def test_skip_occurrence_unmaterialized_marks_cancelled(self):
        session, _ = self._create_series(occurrence_count=2)
        occurrence = RecurringOccurrence.objects.filter(
            recurring_session=session
        ).order_by('occurrence_date').last()

        occ, error = skip_occurrence(occurrence.pk, self.patient)

        self.assertIsNone(error)
        self.assertTrue(occ.is_cancelled)
        self.assertIsNone(occ.consultation_id)

    def test_skip_occurrence_rejects_other_user(self):
        from django.core.exceptions import PermissionDenied

        session, _ = self._create_series(occurrence_count=1)
        occurrence = RecurringOccurrence.objects.get(recurring_session=session)
        other = CustomUser.objects.create_user(
            username='skip-other', password='x', user_type='patient'
        )
        with self.assertRaises(PermissionDenied):
            skip_occurrence(occurrence.pk, other)

    def test_cancel_series_cancels_remaining(self):
        session, _ = self._create_series(occurrence_count=3)
        occurrences = list(
            RecurringOccurrence.objects.filter(recurring_session=session).order_by('occurrence_date')
        )
        accept_recurring_occurrence(occurrences[0].pk, self.patient)

        result, error = cancel_series(session.pk, self.psychologue)

        self.assertIsNone(error)
        result.refresh_from_db()
        self.assertEqual(result.status, RecurringSession.Status.CANCELLED)
        remaining = RecurringOccurrence.objects.filter(
            recurring_session=session, is_cancelled=False
        ).count()
        self.assertEqual(remaining, 0)

    def test_cancel_series_rejects_non_owner(self):
        from django.core.exceptions import PermissionDenied

        session, _ = self._create_series(occurrence_count=2)
        other = CustomUser.objects.create_user(
            username='cancel-other-psych', password='x', user_type='psychologue'
        )
        with self.assertRaises(PermissionDenied):
            cancel_series(session.pk, other)

    def test_materialize_series_on_confirm_creates_remaining(self):
        session, _ = self._create_series(occurrence_count=3)
        occurrences = list(
            RecurringOccurrence.objects.filter(recurring_session=session).order_by('occurrence_date')
        )
        _, first_consultation, _ = accept_recurring_occurrence(occurrences[0].pk, self.patient)
        first_consultation.confirm()

        created, warnings = materialize_series_for_consultation(first_consultation)

        # First acceptance already materialized all 3 as CONFIRMED.
        self.assertEqual(created, 0)
        self.assertEqual(
            Consultation.objects.filter(recurring_session=session).count(), 3
        )
        self.assertEqual(
            Consultation.objects.filter(recurring_session=session, date=self.start).count(), 1
        )

    def test_patient_upcoming_includes_planned_and_materialized(self):
        session, _ = self._create_series(occurrence_count=3)
        occurrences = list(
            RecurringOccurrence.objects.filter(recurring_session=session).order_by('occurrence_date')
        )
        accept_recurring_occurrence(occurrences[0].pk, self.patient)

        upcoming = list(upcoming_occurrences_for_patient(self.patient))

        self.assertEqual(len(upcoming), 3)
        self.assertTrue(all(o.recurring_session_id == session.pk for o in upcoming))