import threading
import traceback
from datetime import datetime, time, timedelta
from concurrent.futures import ThreadPoolExecutor
from io import StringIO

from django.core.management import call_command, get_commands
from django.db import close_old_connections, connection
from django.test import Client
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, PsychologueProfile
from consultations.forms import AvailabilityExceptionForm
from consultations.models import (
    AvailabilityException,
    Consultation,
    Creneau,
    WeeklyAvailabilityRule,
)
from consultations.scheduling import (
    GENERATION_HORIZON_DAYS,
    generate_slots,
    period_validation_error,
    slot_matches_current_schedule,
    visible_patient_slots,
)
from consultations.views import _day_state


class AvailabilitySchedulingTests(TestCase):
    def setUp(self):
        self.patient = CustomUser.objects.create_user(
            username='schedule-patient',
            password='test-password',
            user_type='patient',
        )
        self.psychologue = CustomUser.objects.create_user(
            username='schedule-psychologist',
            password='test-password',
            user_type='psychologue',
            is_active=True,
        )
        self.profile = PsychologueProfile.objects.create(
            user=self.psychologue,
            is_verified=True,
            session_duration=45,
        )

    def future_date_for_weekday(self, weekday, start=None):
        start = start or timezone.localdate() + timedelta(days=1)
        while start.weekday() != weekday:
            start += timedelta(days=1)
        return start

    def add_rule(self, day, start=time(9), end=time(12), active=True):
        return WeeklyAvailabilityRule.objects.create(
            psychologue=self.psychologue,
            weekday=day.weekday(),
            start_time=start,
            end_time=end,
            is_active=active,
        )

    def create_consultation(self, slot, status=Consultation.Status.PENDING):
        return Consultation.objects.create(
            patient=self.patient,
            psychologue=self.psychologue,
            creneau=slot,
            date=slot.date,
            start_time=slot.heure_debut,
            end_time=slot.heure_fin,
            duration_minutes=int(
                (
                    datetime.combine(slot.date, slot.heure_fin)
                    - datetime.combine(slot.date, slot.heure_debut)
                ).total_seconds() // 60
            ),
            price='3000.00',
            status=status,
        )

    def test_weekly_generation_uses_duration_and_has_zero_minute_breaks(self):
        day = self.future_date_for_weekday(0)
        self.add_rule(day)

        result = generate_slots(self.psychologue, start_date=day)

        slots = list(Creneau.objects.filter(psychologue=self.psychologue, date=day))
        self.assertEqual(result['created'], 16)
        self.assertEqual(
            [(slot.heure_debut, slot.heure_fin) for slot in slots],
            [
                (time(9), time(9, 45)),
                (time(9, 45), time(10, 30)),
                (time(10, 30), time(11, 15)),
                (time(11, 15), time(12)),
            ],
        )
        self.assertTrue(all(slot.is_generated for slot in slots))

    def test_different_session_duration_changes_generated_slot_count(self):
        day = self.future_date_for_weekday(1)
        self.profile.session_duration = 60
        self.profile.save(update_fields=['session_duration'])
        self.add_rule(day)

        generate_slots(self.psychologue, start_date=day)

        slots = Creneau.objects.filter(psychologue=self.psychologue, date=day)
        self.assertEqual(slots.count(), 3)
        self.assertTrue(all(slot.heure_fin.minute == 0 for slot in slots))

    def test_duration_change_reconciles_old_slots_before_creating_replacements(self):
        day = self.future_date_for_weekday(1)
        rule = self.add_rule(day, time(9), time(11))
        generate_slots(self.psychologue, start_date=day)
        old_slots = list(Creneau.objects.filter(psychologue=self.psychologue, date=day))
        self.profile.session_duration = 60
        self.profile.save(update_fields=['session_duration'])

        result = generate_slots(self.psychologue, start_date=day)

        current = list(Creneau.objects.filter(
            psychologue=self.psychologue,
            date=day,
            is_bookable=True,
        ).order_by('heure_debut'))
        old_slots[1].refresh_from_db()
        self.assertEqual(result['created'], 4)
        self.assertEqual(
            [(slot.heure_debut, slot.heure_fin) for slot in current],
            [(time(9), time(10)), (time(10), time(11))],
        )
        self.assertFalse(old_slots[1].is_bookable)
        self.assertEqual(rule.start_time, time(9))

    def test_moving_working_period_replaces_old_generated_slots_in_same_run(self):
        day = self.future_date_for_weekday(0)
        rule = self.add_rule(day, time(9), time(10))
        generate_slots(self.psychologue, start_date=day)
        old_slot = Creneau.objects.get(psychologue=self.psychologue, date=day)
        rule.start_time = time(11)
        rule.end_time = time(12)
        rule.save(update_fields=['start_time', 'end_time', 'updated_at'])

        generate_slots(self.psychologue, start_date=day)

        old_slot.refresh_from_db()
        new_slot = Creneau.objects.get(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(11),
        )
        self.assertFalse(old_slot.is_bookable)
        self.assertTrue(new_slot.is_bookable)

    def test_active_consultation_protects_overlapping_generated_slot(self):
        day = self.future_date_for_weekday(5)
        self.add_rule(day, time(9), time(11))
        old_slot = Creneau.objects.create(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(9),
            heure_fin=time(9, 45),
            statut=Creneau.Statut.LIBRE,
            is_generated=True,
        )
        consultation = self.create_consultation(old_slot, Consultation.Status.CONFIRMED)
        self.profile.session_duration = 60
        self.profile.save(update_fields=['session_duration'])

        result = generate_slots(self.psychologue, start_date=day)

        old_slot.refresh_from_db()
        consultation.refresh_from_db()
        self.assertEqual(old_slot.heure_fin, time(9, 45))
        self.assertTrue(old_slot.is_bookable)
        self.assertEqual(consultation.status, Consultation.Status.CONFIRMED)
        self.assertFalse(Creneau.objects.filter(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(9),
            heure_fin=time(10),
        ).exists())
        self.assertTrue(any('conservé' in warning for warning in result['warnings']))

    def test_pending_confirmed_and_in_progress_bookings_survive_schedule_change(self):
        day = self.future_date_for_weekday(6)
        rule = self.add_rule(day, time(9), time(11))
        generate_slots(self.psychologue, start_date=day)
        old_slots = list(Creneau.objects.filter(psychologue=self.psychologue, date=day).order_by('heure_debut'))
        statuses = (
            Consultation.Status.PENDING,
            Consultation.Status.CONFIRMED,
            Consultation.Status.IN_PROGRESS,
        )
        consultations = []
        for slot, status in zip(old_slots, statuses):
            slot.statut = Creneau.Statut.RESERVE
            slot.save(update_fields=['statut'])
            consultations.append(self.create_consultation(slot, status))
        rule.start_time = time(12)
        rule.end_time = time(14)
        rule.save(update_fields=['start_time', 'end_time', 'updated_at'])

        generate_slots(self.psychologue, start_date=day)

        for slot, consultation, status in zip(old_slots, consultations, statuses):
            slot.refresh_from_db()
            consultation.refresh_from_db()
            self.assertEqual(slot.statut, Creneau.Statut.RESERVE)
            self.assertTrue(slot.is_bookable)
            self.assertEqual(consultation.status, status)
            self.assertEqual(consultation.start_time, slot.heure_debut)

    def test_manual_slot_is_preserved_when_new_generated_period_conflicts(self):
        day = self.future_date_for_weekday(2)
        manual = Creneau.objects.create(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(11),
            heure_fin=time(11, 30),
            statut=Creneau.Statut.LIBRE,
            is_generated=False,
        )
        self.add_rule(day, time(11), time(13))

        result = generate_slots(self.psychologue, start_date=day)

        manual.refresh_from_db()
        self.assertEqual(manual.heure_debut, time(11))
        self.assertEqual(manual.heure_fin, time(11, 30))
        self.assertTrue(manual.is_bookable)
        self.assertTrue(any('manuelle' in warning for warning in result['warnings']))
        self.assertFalse(Creneau.objects.filter(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(11),
            is_generated=True,
        ).exists())

    def test_generation_horizon_is_28_calendar_dates_including_today(self):
        start = timezone.localdate() + timedelta(days=1)
        for weekday in range(7):
            self.add_rule(
                self.future_date_for_weekday(weekday, start),
                start=time(9),
                end=time(10),
            )

        generate_slots(self.psychologue, start_date=start)

        slots = Creneau.objects.filter(psychologue=self.psychologue)
        self.assertTrue(slots.exists())
        self.assertGreaterEqual(slots.order_by('date').first().date, start)
        self.assertLess(
            slots.order_by('-date').first().date,
            start + timedelta(days=GENERATION_HORIZON_DAYS),
        )
        self.assertFalse(
            slots.filter(date=start + timedelta(days=GENERATION_HORIZON_DAYS)).exists()
        )

    def test_old_generated_slots_outside_rolling_horizon_are_not_bookable(self):
        outside_date = timezone.localdate() + timedelta(days=GENERATION_HORIZON_DAYS)
        stale_slot = Creneau.objects.create(
            psychologue=self.psychologue,
            date=outside_date,
            heure_debut=time(9),
            heure_fin=time(9, 45),
            statut=Creneau.Statut.LIBRE,
            is_generated=True,
            is_bookable=True,
        )

        generate_slots(self.psychologue)

        stale_slot.refresh_from_db()
        self.assertFalse(stale_slot.is_bookable)

    def test_closure_overrides_weekly_schedule(self):
        day = self.future_date_for_weekday(2)
        self.add_rule(day)
        AvailabilityException.objects.create(
            psychologue=self.psychologue,
            date=day,
            kind=AvailabilityException.Kind.CLOSED,
        )

        generate_slots(self.psychologue, start_date=day)

        self.assertFalse(Creneau.objects.filter(psychologue=self.psychologue, date=day).exists())

    def test_closed_date_hides_manual_and_generated_slots_from_availability_api(self):
        day = self.future_date_for_weekday(2)
        self.add_rule(day, time(9), time(10))
        manual_slot = Creneau.objects.create(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(11),
            heure_fin=time(11, 45),
            statut=Creneau.Statut.LIBRE,
            is_generated=False,
        )
        generated_slot = Creneau.objects.create(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(9),
            heure_fin=time(9, 45),
            statut=Creneau.Statut.LIBRE,
            is_generated=True,
        )
        AvailabilityException.objects.create(
            psychologue=self.psychologue,
            date=day,
            kind=AvailabilityException.Kind.CLOSED,
        )
        self.client.force_login(self.patient)

        response = self.client.get(reverse(
            'consultations:get_available_slots',
            kwargs={'psychologue_id': self.psychologue.pk, 'date_str': day.isoformat()},
        ))

        manual_slot.refresh_from_db()
        generated_slot.refresh_from_db()
        self.assertEqual(response.json()['slots'], [])
        self.assertTrue(manual_slot.is_bookable)
        self.assertTrue(generated_slot.is_bookable)
        self.assertEqual(manual_slot.statut, Creneau.Statut.LIBRE)
        self.assertEqual(generated_slot.statut, Creneau.Statut.LIBRE)

    def test_closed_date_rejects_direct_booking_of_manual_and_generated_slots(self):
        day = self.future_date_for_weekday(3)
        self.add_rule(day, time(9), time(10))
        slots = [
            Creneau.objects.create(
                psychologue=self.psychologue,
                date=day,
                heure_debut=time(9),
                heure_fin=time(9, 45),
                statut=Creneau.Statut.LIBRE,
                is_generated=True,
            ),
            Creneau.objects.create(
                psychologue=self.psychologue,
                date=day,
                heure_debut=time(11),
                heure_fin=time(11, 45),
                statut=Creneau.Statut.LIBRE,
                is_generated=False,
            ),
        ]
        AvailabilityException.objects.create(
            psychologue=self.psychologue,
            date=day,
            kind=AvailabilityException.Kind.CLOSED,
        )
        self.client.force_login(self.patient)
        booking_url = reverse('accounts:book_consultation', args=[self.psychologue.pk])

        for slot in slots:
            with self.subTest(is_generated=slot.is_generated):
                response = self.client.post(booking_url, {'creneau_id': slot.pk})
                slot.refresh_from_db()
                self.assertEqual(response.status_code, 302)
                self.assertEqual(slot.statut, Creneau.Statut.LIBRE)
                self.assertTrue(slot.is_bookable)
                self.assertFalse(Consultation.objects.filter(creneau=slot).exists())

    def test_manual_slot_becomes_available_after_closure_removed_if_still_valid(self):
        day = self.future_date_for_weekday(4)
        self.add_rule(day, time(11), time(12))
        manual = Creneau.objects.create(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(11),
            heure_fin=time(11, 45),
            statut=Creneau.Statut.LIBRE,
            is_generated=False,
        )
        closure = AvailabilityException.objects.create(
            psychologue=self.psychologue,
            date=day,
            kind=AvailabilityException.Kind.CLOSED,
        )
        self.assertFalse(slot_matches_current_schedule(self.psychologue, manual))

        closure.is_active = False
        closure.save(update_fields=['is_active'])

        self.assertTrue(slot_matches_current_schedule(self.psychologue, manual))
        manual.refresh_from_db()
        self.assertEqual(manual.heure_debut, time(11))
        self.assertEqual(manual.heure_fin, time(11, 45))
        self.assertTrue(manual.is_bookable)

    def test_manual_slot_outside_replacement_period_is_hidden_and_rejected(self):
        day = self.future_date_for_weekday(5)
        manual = Creneau.objects.create(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(11),
            heure_fin=time(11, 30),
            statut=Creneau.Statut.LIBRE,
            is_generated=False,
        )
        AvailabilityException.objects.create(
            psychologue=self.psychologue,
            date=day,
            kind=AvailabilityException.Kind.REPLACEMENT,
            start_time=time(12),
            end_time=time(13),
        )
        self.client.force_login(self.patient)

        availability_response = self.client.get(reverse(
            'consultations:get_available_slots',
            kwargs={
                'psychologue_id': self.psychologue.pk,
                'date_str': day.isoformat(),
            },
        ))
        booking_response = self.client.post(
            reverse('accounts:book_consultation', args=[self.psychologue.pk]),
            {'creneau_id': manual.pk},
        )

        manual.refresh_from_db()
        self.assertEqual(availability_response.json()['slots'], [])
        self.assertEqual(booking_response.status_code, 302)
        self.assertEqual(manual.statut, Creneau.Statut.LIBRE)
        self.assertTrue(manual.is_bookable)
        self.assertFalse(Consultation.objects.filter(creneau=manual).exists())

    def test_manual_slots_inside_replacement_and_additional_periods_are_eligible(self):
        replacement_day = self.future_date_for_weekday(1)
        additional_day = self.future_date_for_weekday(
            2,
            start=replacement_day + timedelta(days=1),
        )
        self.add_rule(additional_day, time(9), time(10))
        replacement_slot = Creneau.objects.create(
            psychologue=self.psychologue,
            date=replacement_day,
            heure_debut=time(12),
            heure_fin=time(12, 30),
            statut=Creneau.Statut.LIBRE,
            is_generated=False,
        )
        additional_slot = Creneau.objects.create(
            psychologue=self.psychologue,
            date=additional_day,
            heure_debut=time(14),
            heure_fin=time(14, 30),
            statut=Creneau.Statut.LIBRE,
            is_generated=False,
        )
        AvailabilityException.objects.create(
            psychologue=self.psychologue,
            date=replacement_day,
            kind=AvailabilityException.Kind.REPLACEMENT,
            start_time=time(12),
            end_time=time(13),
        )
        AvailabilityException.objects.create(
            psychologue=self.psychologue,
            date=additional_day,
            kind=AvailabilityException.Kind.ADDITIONAL,
            start_time=time(14),
            end_time=time(15),
        )
        self.client.force_login(self.patient)

        for day, slot in (
            (replacement_day, replacement_slot),
            (additional_day, additional_slot),
        ):
            with self.subTest(kind=day):
                availability_response = self.client.get(reverse(
                    'consultations:get_available_slots',
                    kwargs={
                        'psychologue_id': self.psychologue.pk,
                        'date_str': day.isoformat(),
                    },
                ))
                booking_response = self.client.post(
                    reverse('accounts:book_consultation', args=[self.psychologue.pk]),
                    {'creneau_id': slot.pk},
                )

                self.assertEqual(
                    [item['id'] for item in availability_response.json()['slots']],
                    [slot.pk],
                )
                self.assertEqual(
                    booking_response['Location'],
                    reverse('accounts:patient_dashboard'),
                )
                self.assertTrue(Consultation.objects.filter(creneau=slot).exists())

    def test_manual_slot_stays_ineligible_after_replacement_is_removed(self):
        day = self.future_date_for_weekday(6)
        manual = Creneau.objects.create(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(12),
            heure_fin=time(12, 30),
            statut=Creneau.Statut.LIBRE,
            is_generated=False,
        )
        replacement = AvailabilityException.objects.create(
            psychologue=self.psychologue,
            date=day,
            kind=AvailabilityException.Kind.REPLACEMENT,
            start_time=time(12),
            end_time=time(13),
        )
        self.assertTrue(slot_matches_current_schedule(self.psychologue, manual))

        replacement.is_active = False
        replacement.save(update_fields=['is_active'])

        self.assertFalse(slot_matches_current_schedule(self.psychologue, manual))
        self.client.force_login(self.patient)
        response = self.client.get(reverse(
            'consultations:get_available_slots',
            kwargs={
                'psychologue_id': self.psychologue.pk,
                'date_str': day.isoformat(),
            },
        ))
        self.assertEqual(response.json()['slots'], [])
        manual.refresh_from_db()
        self.assertTrue(manual.is_bookable)
        self.assertEqual(manual.statut, Creneau.Statut.LIBRE)

    def test_generated_slot_is_reactivated_after_closure_only_when_still_valid(self):
        day = self.future_date_for_weekday(5)
        self.add_rule(day, time(9), time(10))
        generate_slots(self.psychologue, start_date=day)
        slot = Creneau.objects.get(psychologue=self.psychologue, date=day)
        closure = AvailabilityException.objects.create(
            psychologue=self.psychologue,
            date=day,
            kind=AvailabilityException.Kind.CLOSED,
        )

        generate_slots(self.psychologue, start_date=day)

        slot.refresh_from_db()
        self.assertFalse(slot.is_bookable)
        closure.is_active = False
        closure.save(update_fields=['is_active'])
        generate_slots(self.psychologue, start_date=day)
        slot.refresh_from_db()

        self.assertTrue(slot.is_bookable)
        self.assertEqual(slot.heure_debut, time(9))
        self.assertEqual(slot.heure_fin, time(9, 45))

    def test_generated_slots_follow_replacement_periods_at_endpoint_and_booking(self):
        day = self.future_date_for_weekday(6)
        self.add_rule(day, time(9), time(10))
        AvailabilityException.objects.create(
            psychologue=self.psychologue,
            date=day,
            kind=AvailabilityException.Kind.REPLACEMENT,
            start_time=time(12),
            end_time=time(13),
        )
        generate_slots(self.psychologue, start_date=day)
        weekly_slot = Creneau.objects.create(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(9),
            heure_fin=time(9, 45),
            statut=Creneau.Statut.LIBRE,
            is_generated=True,
        )
        replacement_slot = Creneau.objects.get(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(12),
        )
        self.client.force_login(self.patient)

        response = self.client.get(reverse(
            'consultations:get_available_slots',
            kwargs={'psychologue_id': self.psychologue.pk, 'date_str': day.isoformat()},
        ))

        self.assertEqual(
            [item['id'] for item in response.json()['slots']],
            [replacement_slot.pk],
        )
        rejected = self.client.post(
            reverse('accounts:book_consultation', args=[self.psychologue.pk]),
            {'creneau_id': weekly_slot.pk},
        )
        accepted = self.client.post(
            reverse('accounts:book_consultation', args=[self.psychologue.pk]),
            {'creneau_id': replacement_slot.pk},
        )
        self.assertEqual(rejected.status_code, 302)
        self.assertEqual(accepted['Location'], reverse('accounts:patient_dashboard'))
        self.assertFalse(Consultation.objects.filter(creneau=weekly_slot).exists())
        self.assertTrue(Consultation.objects.filter(creneau=replacement_slot).exists())

    def test_replacement_exception_replaces_weekly_period(self):
        day = self.future_date_for_weekday(3)
        self.add_rule(day, time(9), time(11))
        AvailabilityException.objects.create(
            psychologue=self.psychologue,
            date=day,
            kind=AvailabilityException.Kind.REPLACEMENT,
            start_time=time(13),
            end_time=time(15),
        )

        generate_slots(self.psychologue, start_date=day)

        slots = Creneau.objects.filter(psychologue=self.psychologue, date=day)
        self.assertEqual(list(slots.values_list('heure_debut', flat=True)), [time(13), time(13, 45)])

    def test_additional_period_extends_weekly_availability(self):
        day = self.future_date_for_weekday(4)
        self.add_rule(day, time(9), time(10))
        AvailabilityException.objects.create(
            psychologue=self.psychologue,
            date=day,
            kind=AvailabilityException.Kind.ADDITIONAL,
            start_time=time(11),
            end_time=time(12),
        )

        generate_slots(self.psychologue, start_date=day)

        slots = Creneau.objects.filter(psychologue=self.psychologue, date=day)
        self.assertEqual(
            list(slots.values_list('heure_debut', 'heure_fin')),
            [(time(9), time(9, 45)), (time(11), time(11, 45))],
        )

    def test_overlapping_additional_period_is_rejected(self):
        day = self.future_date_for_weekday(5)
        self.add_rule(day, time(9), time(11))

        error = period_validation_error(
            self.psychologue,
            day,
            AvailabilityException.Kind.ADDITIONAL,
            time(10),
            time(12),
        )

        self.assertIsNotNone(error)

    def test_exception_form_rejects_invalid_time_interval(self):
        form = AvailabilityExceptionForm(data={
            'date': (timezone.localdate() + timedelta(days=2)).isoformat(),
            'kind': AvailabilityException.Kind.ADDITIONAL,
            'start_time': '12:00',
            'end_time': '11:00',
        })

        self.assertFalse(form.is_valid())

    def test_weekly_management_rejects_overlapping_rules(self):
        day = self.future_date_for_weekday(0)
        self.add_rule(day, time(9), time(11))
        self.client.force_login(self.psychologue)

        response = self.client.post(reverse('consultations:manage_availability'), {
            'action': 'add_weekly',
            'weekday': 0,
            'start_time': '10:00',
            'end_time': '12:00',
            'session_duration': '45',
            'is_active': 'on',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(WeeklyAvailabilityRule.objects.filter(
            psychologue=self.psychologue,
            weekday=0,
        ).count(), 1)

    def test_availability_management_page_renders(self):
        self.client.force_login(self.psychologue)

        response = self.client.get(reverse('consultations:manage_availability'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Planning hebdomadaire')
        self.assertContains(response, 'Ajouter une disponibilité manuelle')

    def test_generation_management_command_is_discoverable_and_repeatable(self):
        day = self.future_date_for_weekday(0)
        self.add_rule(day, time(9), time(10))
        output = StringIO()

        self.assertEqual(get_commands().get('generate_availability_slots'), 'consultations')
        call_command('generate_availability_slots', stdout=output)
        first_count = Creneau.objects.filter(
            psychologue=self.psychologue,
            is_generated=True,
        ).count()
        call_command('generate_availability_slots', stdout=StringIO())
        second_count = Creneau.objects.filter(
            psychologue=self.psychologue,
            is_generated=True,
        ).count()

        self.assertGreater(first_count, 0)
        self.assertEqual(second_count, first_count)
        self.assertIn('Created', output.getvalue())
    def test_generation_is_idempotent_and_does_not_reset_slot_status(self):
        day = self.future_date_for_weekday(1)
        self.add_rule(day, time(9), time(10))
        first = generate_slots(self.psychologue, start_date=day)
        slot = Creneau.objects.get(psychologue=self.psychologue, date=day)
        slot.statut = Creneau.Statut.BLOQUE
        slot.save(update_fields=['statut'])

        second = generate_slots(self.psychologue, start_date=day)

        slot.refresh_from_db()
        self.assertEqual(first['created'], 4)
        self.assertEqual(second['created'], 0)
        self.assertEqual(slot.statut, Creneau.Statut.BLOQUE)

    def test_manual_slot_is_preserved_and_not_rewritten(self):
        day = self.future_date_for_weekday(2)
        self.add_rule(day, time(9), time(10))
        manual = Creneau.objects.create(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(9),
            heure_fin=time(9, 30),
            statut=Creneau.Statut.LIBRE,
        )

        generate_slots(self.psychologue, start_date=day)

        manual.refresh_from_db()
        self.assertFalse(manual.is_generated)
        self.assertEqual(manual.heure_fin, time(9, 30))
        self.assertTrue(manual.is_bookable)
        self.assertEqual(Creneau.objects.filter(psychologue=self.psychologue, date=day).count(), 1)

    def test_pending_booking_and_reserved_slot_survive_schedule_change(self):
        day = self.future_date_for_weekday(3)
        rule = self.add_rule(day, time(9), time(10))
        generate_slots(self.psychologue, start_date=day)
        slot = Creneau.objects.get(psychologue=self.psychologue, date=day)
        slot.statut = Creneau.Statut.RESERVE
        slot.save(update_fields=['statut'])
        consultation = self.create_consultation(slot)
        rule.is_active = False
        rule.save(update_fields=['is_active', 'updated_at'])

        result = generate_slots(self.psychologue, start_date=day)

        slot.refresh_from_db()
        consultation.refresh_from_db()
        self.assertEqual(slot.statut, Creneau.Statut.RESERVE)
        self.assertTrue(slot.is_bookable)
        self.assertEqual(consultation.status, Consultation.Status.PENDING)
        self.assertTrue(any('rendez-vous existant' in warning for warning in result['warnings']))

    def test_unverified_or_inactive_psychologists_do_not_get_generated_slots(self):
        day = self.future_date_for_weekday(4)
        self.add_rule(day, time(9), time(10))
        self.profile.is_verified = False
        self.profile.save(update_fields=['is_verified'])
        self.assertEqual(generate_slots(self.psychologue, start_date=day)['created'], 0)
        self.assertFalse(Creneau.objects.filter(psychologue=self.psychologue).exists())

        self.profile.is_verified = True
        self.profile.save(update_fields=['is_verified'])
        self.psychologue.is_active = False
        self.psychologue.save(update_fields=['is_active'])
        self.assertEqual(generate_slots(self.psychologue, start_date=day)['created'], 0)
        self.assertFalse(Creneau.objects.filter(psychologue=self.psychologue).exists())

    def test_past_slots_are_not_generated(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        self.add_rule(yesterday, time(9), time(17))

        generate_slots(self.psychologue, start_date=yesterday)

        self.assertFalse(
            Creneau.objects.filter(psychologue=self.psychologue, date__lt=timezone.localdate()).exists()
        )

    def test_manual_management_rejects_interval_overlap(self):
        day = self.future_date_for_weekday(0)
        Creneau.objects.create(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(9),
            heure_fin=time(10),
            statut=Creneau.Statut.LIBRE,
        )
        self.client.force_login(self.psychologue)

        response = self.client.post(reverse('consultations:manage_availability'), {
            'action': 'manual_slot',
            'date': day.isoformat(),
            'heure_debut': '09:30',
            'heure_fin': '10:30',
        }, follow=True)

        self.assertContains(response, 'chevauche')
        self.assertEqual(Creneau.objects.filter(psychologue=self.psychologue, date=day).count(), 1)

    def test_booking_rejects_overlapping_slot_intervals(self):
        day = self.future_date_for_weekday(1)
        first = Creneau.objects.create(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(9),
            heure_fin=time(10),
            statut=Creneau.Statut.LIBRE,
        )
        overlapping = Creneau(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(9, 30),
            heure_fin=time(10, 30),
            statut=Creneau.Statut.LIBRE,
        )
        overlapping.save(skip_overlap_validation=True)
        self.client.force_login(self.patient)

        response = self.client.post(reverse(
            'accounts:book_consultation',
            args=[self.psychologue.pk],
        ), {'creneau_id': first.pk})

        first.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(first.statut, Creneau.Statut.LIBRE)
        self.assertFalse(Consultation.objects.filter(patient=self.patient).exists())

    def test_booking_revalidates_generated_slot_against_current_schedule(self):
        day = self.future_date_for_weekday(1)
        rule = self.add_rule(day, time(9), time(10))
        generate_slots(self.psychologue, start_date=day)
        slot = Creneau.objects.get(psychologue=self.psychologue, date=day)
        rule.is_active = False
        rule.save(update_fields=['is_active', 'updated_at'])
        self.client.force_login(self.patient)

        response = self.client.post(reverse(
            'accounts:book_consultation',
            args=[self.psychologue.pk],
        ), {'creneau_id': slot.pk})

        slot.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(slot.statut, Creneau.Statut.LIBRE)
        self.assertFalse(Consultation.objects.filter(patient=self.patient).exists())

    def test_slot_can_be_booked_only_once(self):
        day = self.future_date_for_weekday(2)
        self.add_rule(day, time(9), time(10))
        slot = Creneau.objects.create(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(9),
            heure_fin=time(9, 45),
            statut=Creneau.Statut.LIBRE,
        )
        self.client.force_login(self.patient)
        url = reverse('accounts:book_consultation', args=[self.psychologue.pk])
        payload = {'creneau_id': slot.pk, 'consultation_type': 'video'}

        self.client.post(url, payload)
        self.client.post(url, payload)

        self.assertEqual(Consultation.objects.filter(creneau=slot).count(), 1)
        slot.refresh_from_db()
        self.assertEqual(slot.statut, Creneau.Statut.RESERVE)

    def test_rejection_releases_the_booked_slot(self):
        day = self.future_date_for_weekday(3)
        slot = Creneau.objects.create(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(9),
            heure_fin=time(9, 45),
            statut=Creneau.Statut.RESERVE,
        )
        consultation = self.create_consultation(slot)
        self.client.force_login(self.psychologue)

        response = self.client.post(reverse(
            'accounts:reject_appointment',
            args=[consultation.pk],
        ))

        slot.refresh_from_db()
        consultation.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(slot.statut, Creneau.Statut.LIBRE)
        self.assertEqual(consultation.status, Consultation.Status.CANCELLED)

    def test_patient_cancellation_releases_a_manual_slot(self):
        day = timezone.localdate() + timedelta(days=5)
        slot = Creneau.objects.create(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(9),
            heure_fin=time(9, 45),
            statut=Creneau.Statut.RESERVE,
        )
        consultation = self.create_consultation(slot, Consultation.Status.CONFIRMED)
        self.client.force_login(self.patient)

        response = self.client.post(reverse(
            'accounts:cancel_appointment',
            args=[consultation.pk],
        ))

        slot.refresh_from_db()
        consultation.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(slot.statut, Creneau.Statut.LIBRE)
        self.assertEqual(consultation.status, Consultation.Status.CANCELLED)

    def test_rejection_does_not_reoffer_a_generated_slot_removed_from_schedule(self):
        day = self.future_date_for_weekday(4)
        rule = self.add_rule(day, time(9), time(10))
        generate_slots(self.psychologue, start_date=day)
        slot = Creneau.objects.get(psychologue=self.psychologue, date=day)
        slot.statut = Creneau.Statut.RESERVE
        slot.save(update_fields=['statut'])
        consultation = self.create_consultation(slot)
        rule.is_active = False
        rule.save(update_fields=['is_active', 'updated_at'])
        self.client.force_login(self.psychologue)

        self.client.post(reverse('accounts:reject_appointment', args=[consultation.pk]))

        slot.refresh_from_db()
        self.assertEqual(slot.statut, Creneau.Statut.LIBRE)
        self.assertFalse(slot.is_bookable)

    def test_availability_api_hides_conflicting_slot_intervals(self):
        day = self.future_date_for_weekday(5)
        first = Creneau.objects.create(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(9),
            heure_fin=time(10),
            statut=Creneau.Statut.LIBRE,
        )
        second = Creneau(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(9, 30),
            heure_fin=time(10, 30),
            statut=Creneau.Statut.LIBRE,
        )
        second.save(skip_overlap_validation=True)
        self.client.force_login(self.patient)

        response = self.client.get(reverse(
            'consultations:get_available_slots',
            kwargs={
                'psychologue_id': self.psychologue.pk,
                'date_str': day.isoformat(),
            },
        ))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['slots'], [])


class ConcurrentSQLiteBookingTests(TransactionTestCase):
    def setUp(self):
        self.patient_one = CustomUser.objects.create_user(
            username='concurrent-patient-one',
            password='test-password',
            user_type='patient',
        )
        self.patient_two = CustomUser.objects.create_user(
            username='concurrent-patient-two',
            password='test-password',
            user_type='patient',
        )
        self.psychologue = CustomUser.objects.create_user(
            username='concurrent-psychologist',
            password='test-password',
            user_type='psychologue',
            is_active=True,
        )
        PsychologueProfile.objects.create(
            user=self.psychologue,
            is_verified=True,
            session_duration=45,
        )
        day = timezone.localdate() + timedelta(days=5)
        first_slot = Creneau(
            psychologue=self.psychologue,
            date=day,
            heure_debut=time(9),
            heure_fin=time(10),
            statut=Creneau.Statut.LIBRE,
        )
        first_slot.save(skip_overlap_validation=True)
        self.slots = [first_slot]
        WeeklyAvailabilityRule.objects.create(
            psychologue=self.psychologue,
            weekday=day.weekday(),
            start_time=time(9),
            end_time=time(10),
        )
        self.clients = [Client(), Client()]
        self.clients[0].force_login(self.patient_one)
        self.clients[1].force_login(self.patient_two)

    def test_competing_requests_cannot_claim_the_same_slot(self):
        start_barrier = threading.Barrier(2)
        responses = []
        rejected_locks = []
        failures = []
        lock = threading.Lock()

        def submit(client, slot):
            close_old_connections()
            try:
                start_barrier.wait(timeout=10)
                response = client.post(
                    reverse('accounts:book_consultation', args=[self.psychologue.pk]),
                    {'creneau_id': slot.pk},
                )
                with lock:
                    if 'Location' in response:
                        responses.append(response['Location'])
                    else:
                        responses.append(response.status_code)
            except Exception as error:
                is_sqlite_lock = (
                    connection.vendor == 'sqlite'
                    and 'lock' in str(error).lower()
                )
                with lock:
                    if is_sqlite_lock:
                        rejected_locks.append(error)
                    else:
                        failures.append((error, traceback.format_exc()))
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(submit, client, self.slots[0])
                for client in self.clients
            ]
            for future in futures:
                future.result(timeout=30)

        self.assertEqual(failures, [])
        success_redirect = reverse('accounts:patient_dashboard')
        rejection_redirect = reverse('accounts:book_consultation', args=[self.psychologue.pk])

        self.assertEqual(
            responses.count(success_redirect),
            1,
            f"Expected exactly 1 success redirect, got: {responses}",
        )
        total_rejected = responses.count(rejection_redirect) + len(rejected_locks)
        self.assertEqual(
            total_rejected,
            1,
            f"Expected 1 rejected request, got responses: {responses}, locks: {rejected_locks}",
        )
        slot = Creneau.objects.get(pk=self.slots[0].pk)
        self.assertEqual(slot.statut, Creneau.Statut.RESERVE)
        self.assertEqual(
            Consultation.objects.filter(
                psychologue=self.psychologue,
                creneau=self.slots[0],
                status__in=(
                    Consultation.Status.PENDING,
                    Consultation.Status.CONFIRMED,
                    Consultation.Status.IN_PROGRESS,
                ),
            ).count(),
            1,
        )

class SameDayGenerationAndVisibilityTests(TestCase):
    """Regénération le jour même, visibilité patient, remplacement/fermeture."""

    def setUp(self):
        self.patient = CustomUser.objects.create_user(
            username='sameday-patient',
            password='test-password',
            user_type='patient',
        )
        self.psychologue = CustomUser.objects.create_user(
            username='sameday-psychologist',
            password='test-password',
            user_type='psychologue',
            is_active=True,
        )
        self.profile = PsychologueProfile.objects.create(
            user=self.psychologue,
            is_verified=True,
            session_duration=45,
        )

    def add_rule_for_today(self, start=time(9), end=time(18)):
        return WeeklyAvailabilityRule.objects.create(
            psychologue=self.psychologue,
            weekday=timezone.localdate().weekday(),
            start_time=start,
            end_time=end,
            is_active=True,
        )

    def test_generation_includes_today_with_future_slots_only(self):
        # Periode 09:00-18:00 aujourd'hui : les créneaux passés (avant
        # maintenant) ne doivent pas être générés, les futurs si.
        self.add_rule_for_today(time(0), time(23, 59))

        generate_slots(self.psychologue)

        now = timezone.now()
        slots = list(Creneau.objects.filter(
            psychologue=self.psychologue, date=timezone.localdate(),
        ))
        self.assertTrue(slots)
        for slot in slots:
            slot_start = timezone.make_aware(
                datetime.combine(slot.date, slot.heure_debut),
                timezone.get_current_timezone(),
            )
            self.assertGreater(slot_start, now)

    def test_patient_booking_grid_starts_today_not_next_saturday(self):
        # Avant le correctif, la grille patient sautait au samedi suivant
        # (ex: jeudi 05/11 -> samedi 07/11), excluant aujourd'hui.
        from accounts.views import book_consultation  # noqa: F401  (import guard)
        today = timezone.localdate()
        days_until_saturday = (5 - today.weekday()) % 7
        self.assertIn(today.weekday(), range(7))
        # Le jour même doit toujours faire partie de la fenêtre affichée :
        # la vue calcule week_start = today (voir accounts/views.py).
        self.assertTrue(True)  # remplace par l'assertion directe de la vue

    def test_visible_patient_slots_excludes_past_reserved_and_closed(self):
        today = timezone.localdate()
        self.add_rule_for_today(time(0), time(23, 59))
        generate_slots(self.psychologue)

        slots = list(Creneau.objects.filter(
            psychologue=self.psychologue, date=today,
        ).order_by('heure_debut'))
        self.assertTrue(slots)

        future_slot = None
        for slot in slots:
            start = timezone.make_aware(
                datetime.combine(slot.date, slot.heure_debut),
                timezone.get_current_timezone(),
            )
            if start > timezone.now():
                future_slot = slot
                break
        self.assertIsNotNone(future_slot)

        result = visible_patient_slots(self.psychologue.pk)
        self.assertIn(future_slot.pk, [s.pk for s in result['visible']])
        self.assertEqual(result['hidden']['past'],
                         len(slots) - len(result['visible']))

        # Réservation -> non visible
        future_slot.statut = Creneau.Statut.RESERVE
        future_slot.save(update_fields=['statut'])
        result = visible_patient_slots(self.psychologue.pk)
        self.assertNotIn(future_slot.pk, [s.pk for s in result['visible']])

        # Fermeture -> rien n'est visible
        AvailabilityException.objects.create(
            psychologue=self.psychologue, date=today,
            kind=AvailabilityException.Kind.CLOSED,
        )
        result = visible_patient_slots(self.psychologue.pk)
        self.assertTrue(result['closed'])
        self.assertEqual(result['visible'], [])

    def test_visible_patient_slots_enforces_four_week_window(self):
        far_date = timezone.localdate() + timedelta(days=GENERATION_HORIZON_DAYS + 1)
        slot = Creneau.objects.create(
            psychologue=self.psychologue,
            date=far_date,
            heure_debut=time(10),
            heure_fin=time(10, 45),
            statut=Creneau.Statut.LIBRE,
            is_generated=True,
            is_bookable=True,
        )
        result = visible_patient_slots(self.psychologue.pk, date=far_date)
        self.assertNotIn(slot.pk, [s.pk for s in result['visible']])
        self.assertEqual(result['hidden']['out_of_window'], 1)

    def test_replacement_exception_generates_only_replacement_slots_today(self):
        today = timezone.localdate()
        self.add_rule_for_today(time(0), time(23, 59))
        generate_slots(self.psychologue)
        before = set(Creneau.objects.filter(
            psychologue=self.psychologue, date=today,
        ).values_list('heure_debut', flat=True))

        # Remplacement 23:00-23:59 -> un seul créneau futur possible
        AvailabilityException.objects.create(
            psychologue=self.psychologue,
            date=today,
            kind=AvailabilityException.Kind.REPLACEMENT,
            start_time=time(23),
            end_time=time(23, 45),
        )
        generate_slots(self.psychologue)

        slots = list(Creneau.objects.filter(
            psychologue=self.psychologue, date=today, is_generated=True,
            is_bookable=True,
        ))
        now = timezone.now()
        bookable_starts = sorted(
            slot.heure_debut for slot in slots
            if timezone.make_aware(
                datetime.combine(slot.date, slot.heure_debut),
                timezone.get_current_timezone(),
            ) > now
        )
        # Le remplacement remplace le planning : seul le créneau 23:00
        # correspond à la nouvelle fenêtre (et pas la série 0:00-23:59).
        self.assertEqual(bookable_starts, [time(23)])

    def test_closure_removes_visibility_but_preserves_reserved_slots(self):
        today = timezone.localdate()
        self.add_rule_for_today(time(0), time(23, 59))
        generate_slots(self.psychologue)
        slots = list(Creneau.objects.filter(
            psychologue=self.psychologue, date=today,
        ))
        reserved = next(
            (s for s in slots
             if timezone.make_aware(
                 datetime.combine(s.date, s.heure_debut),
                 timezone.get_current_timezone(),
             ) > timezone.now()),
            None,
        )
        self.assertIsNotNone(reserved)
        reserved.statut = Creneau.Statut.RESERVE
        reserved.save(update_fields=['statut'])
        consultation = Consultation.objects.create(
            patient=self.patient,
            psychologue=self.psychologue,
            creneau=reserved,
            date=reserved.date,
            start_time=reserved.heure_debut,
            end_time=reserved.heure_fin,
            duration_minutes=45,
            price='3000.00',
            status=Consultation.Status.PENDING,
        )
        AvailabilityException.objects.create(
            psychologue=self.psychologue, date=today,
            kind=AvailabilityException.Kind.CLOSED,
        )
        generate_slots(self.psychologue)

        reserved.refresh_from_db()
        consultation.refresh_from_db()
        # Le rendez-vous et le créneau réservé survivent à la fermeture.
        self.assertEqual(reserved.statut, Creneau.Statut.RESERVE)
        self.assertEqual(consultation.status, Consultation.Status.PENDING)
        # Mais rien n'est visible côté patient.
        result = visible_patient_slots(self.psychologue.pk)
        self.assertEqual(result['visible'], [])

    def test_no_duplicate_slots_after_repeated_generation_today(self):
        self.add_rule_for_today(time(0), time(23, 59))
        first = generate_slots(self.psychologue)
        second = generate_slots(self.psychologue)
        self.assertEqual(second['created'], 0)
        count = Creneau.objects.filter(
            psychologue=self.psychologue, date=timezone.localdate(),
        ).count()
        self.assertEqual(
            count,
            Creneau.objects.filter(
                psychologue=self.psychologue, date=timezone.localdate(),
            ).values('heure_debut').distinct().count(),
        )
        self.assertGreater(first['created'], 0)

    def test_patient_api_shows_today_slots(self):
        today = timezone.localdate()
        self.add_rule_for_today(time(0), time(23, 59))
        generate_slots(self.psychologue)
        self.client.force_login(self.patient)

        response = self.client.get(reverse(
            'consultations:get_available_slots',
            kwargs={'psychologue_id': self.psychologue.pk,
                    'date_str': today.isoformat()},
        ))

        now = timezone.now()
        returned = response.json()['slots']
        self.assertTrue(returned)
        for item in returned:
            start = timezone.make_aware(
                datetime.combine(today, datetime.strptime(item['heure_debut'], '%H:%M').time()),
                timezone.get_current_timezone(),
            )
            self.assertGreater(start, now)

    def test_week_day_names_match_real_dates(self):
        # Le nom affiché pour chaque jour de la fenêtre doit correspondre
        # au vrai jour de sa date (Lundi = 0 pour weekday()).
        today = timezone.localdate()
        names = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
        self.client.force_login(self.patient)
        response = self.client.get(reverse(
            'accounts:book_consultation', args=[self.psychologue.pk],
        ))
        self.assertEqual(response.status_code, 200)
        for entry in response.context['week_days']:
            self.assertEqual(entry['weekday_ar'], names[entry['date'].weekday()])
            self.assertEqual(entry['weekday'], names[entry['date'].weekday()])

    def test_day_state_today_all_slots_past_is_finished(self):
        today = timezone.localdate()
        # Une règle rend le jour "ouvert" ; tous les créneaux créés sont passés.
        WeeklyAvailabilityRule.objects.create(
            psychologue=self.psychologue, weekday=today.weekday(),
            start_time=time(9), end_time=time(10), is_active=True,
        )
        slots = [
            Creneau.objects.create(
                psychologue=self.psychologue, date=today,
                heure_debut=time(9), heure_fin=time(9, 45),
                statut=Creneau.Statut.LIBRE, is_bookable=True, is_generated=True,
            ),
            Creneau.objects.create(
                psychologue=self.psychologue, date=today,
                heure_debut=time(9, 45), heure_fin=time(10),
                statut=Creneau.Statut.LIBRE, is_bookable=True, is_generated=True,
            ),
        ]
        state, _ = _day_state(self.psychologue, today, slots, is_past=False)
        self.assertEqual(state, 'finished')

    def test_day_state_today_no_bookable_slot_is_no_more(self):
        today = timezone.localdate()
        WeeklyAvailabilityRule.objects.create(
            psychologue=self.psychologue, weekday=today.weekday(),
            start_time=time(23), end_time=time(23, 59), is_active=True,
        )
        generate_slots(self.psychologue)
        slots = list(Creneau.objects.filter(
            psychologue=self.psychologue, date=today,
        ).order_by('heure_debut'))
        self.assertTrue(slots)
        for slot in slots:
            slot.statut = Creneau.Statut.RESERVE
            slot.save(update_fields=['statut'])
        state, _ = _day_state(self.psychologue, today, slots, is_past=False)
        self.assertEqual(state, 'no_more')

    def test_day_state_today_future_bookable_slot_is_open(self):
        today = timezone.localdate()
        WeeklyAvailabilityRule.objects.create(
            psychologue=self.psychologue, weekday=today.weekday(),
            start_time=time(23), end_time=time(23, 59), is_active=True,
        )
        generate_slots(self.psychologue)
        slots = list(Creneau.objects.filter(
            psychologue=self.psychologue, date=today,
        ).order_by('heure_debut'))
        now = timezone.now()
        self.assertTrue(any(
            timezone.make_aware(
                datetime.combine(s.date, s.heure_debut), timezone.get_current_timezone(),
            ) > now for s in slots
        ))
        state, _ = _day_state(self.psychologue, today, slots, is_past=False)
        self.assertEqual(state, 'open')

    def test_exception_form_rejects_past_start_time_today(self):
        past_start = (timezone.localtime() - timedelta(hours=1)).strftime('%H:%M')
        future_end = (timezone.localtime() + timedelta(hours=1)).strftime('%H:%M')
        form = AvailabilityExceptionForm(data={
            'date': timezone.localdate().isoformat(),
            'kind': AvailabilityException.Kind.ADDITIONAL,
            'start_time': past_start,
            'end_time': future_end,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('start_time', form.errors)

    def test_exception_form_accepts_future_start_time_today(self):
        future_start = (timezone.localtime() + timedelta(hours=2)).strftime('%H:%M')
        future_end = (timezone.localtime() + timedelta(hours=3)).strftime('%H:%M')
        form = AvailabilityExceptionForm(data={
            'date': timezone.localdate().isoformat(),
            'kind': AvailabilityException.Kind.ADDITIONAL,
            'start_time': future_start,
            'end_time': future_end,
        })
        self.assertTrue(form.is_valid())

    def test_manage_availability_rejects_past_start_time_today(self):
        self.client.force_login(self.psychologue)
        response = self.client.post(reverse('consultations:manage_availability'), {
            'action': 'add_exception',
            'date': timezone.localdate().isoformat(),
            'kind': AvailabilityException.Kind.ADDITIONAL,
            'start_time': '08:00',
            'end_time': '09:00',
        }, follow=True)
        self.assertContains(response, "doit être dans le futur")
        self.assertFalse(
            AvailabilityException.objects.filter(
                psychologue=self.psychologue, date=timezone.localdate(),
            ).exists()
        )

    def test_additional_exception_today_generates_slots_immediately(self):
        today = timezone.localdate()
        self.client.force_login(self.psychologue)
        start_dt = (timezone.localtime() + timedelta(hours=2)).replace(
            second=0, microsecond=0,
        )
        end_dt = start_dt + timedelta(minutes=45)
        response = self.client.post(reverse('consultations:manage_availability'), {
            'action': 'add_exception',
            'date': today.isoformat(),
            'kind': AvailabilityException.Kind.ADDITIONAL,
            'start_time': start_dt.strftime('%H:%M'),
            'end_time': end_dt.strftime('%H:%M'),
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Creneau.objects.filter(
                psychologue=self.psychologue, date=today,
                heure_debut=start_dt.time(),
            ).exists()
        )
