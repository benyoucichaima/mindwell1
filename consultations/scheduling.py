from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from accounts.models import PsychologueProfile

from .models import AvailabilityException, Consultation, Creneau, WeeklyAvailabilityRule


ACTIVE_CONSULTATION_STATUSES = (
    Consultation.Status.PENDING,
    Consultation.Status.CONFIRMED,
    Consultation.Status.IN_PROGRESS,
)
GENERATION_HORIZON_DAYS = 28


def intervals_overlap(start_a, end_a, start_b, end_b):
    return start_a < end_b and end_a > start_b


def effective_work_periods(psychologue, date):
    exceptions = list(
        AvailabilityException.objects.filter(
            psychologue=psychologue,
            date=date,
            is_active=True,
        ).order_by('start_time', 'pk')
    )
    if any(item.kind == AvailabilityException.Kind.CLOSED for item in exceptions):
        return []

    replacements = [
        (item.start_time, item.end_time)
        for item in exceptions
        if item.kind == AvailabilityException.Kind.REPLACEMENT
    ]
    if replacements:
        periods = replacements
    else:
        periods = list(
            WeeklyAvailabilityRule.objects.filter(
                psychologue=psychologue,
                weekday=date.weekday(),
                is_active=True,
            ).values_list('start_time', 'end_time')
        )
    periods.extend(
        (item.start_time, item.end_time)
        for item in exceptions
        if item.kind == AvailabilityException.Kind.ADDITIONAL
    )
    return sorted(periods)


def generated_slot_matches_schedule(psychologue, date, start_time, end_time):
    profile = PsychologueProfile.objects.filter(user=psychologue).first()
    if (
        profile is None
        or not psychologue.is_active
        or psychologue.user_type != 'psychologue'
        or not profile.is_verified
        or profile.session_duration not in dict(PsychologueProfile.SESSION_DURATION_CHOICES)
    ):
        return False

    duration_minutes = profile.session_duration
    slot_start = datetime.combine(date, start_time)
    slot_end = datetime.combine(date, end_time)
    if (slot_end - slot_start).total_seconds() != duration_minutes * 60:
        return False
    return any(
        datetime.combine(date, period_start) <= slot_start
        and slot_end <= datetime.combine(date, period_end)
        and int((slot_start - datetime.combine(date, period_start)).total_seconds() // 60)
        % duration_minutes == 0
        for period_start, period_end in effective_work_periods(psychologue, date)
    )


def slot_matches_current_schedule(psychologue, slot):
    """Require every slot to fit an effective work period for its date."""
    if slot.is_generated:
        return generated_slot_matches_schedule(
            psychologue,
            slot.date,
            slot.heure_debut,
            slot.heure_fin,
        )

    slot_start = datetime.combine(slot.date, slot.heure_debut)
    slot_end = datetime.combine(slot.date, slot.heure_fin)
    if slot_start >= slot_end:
        return False
    return any(
        datetime.combine(slot.date, period_start) <= slot_start
        and slot_end <= datetime.combine(slot.date, period_end)
        for period_start, period_end in effective_work_periods(psychologue, slot.date)
    )


def period_validation_error(psychologue, date, kind, start_time=None, end_time=None, exclude_id=None):
    active = AvailabilityException.objects.filter(
        psychologue=psychologue,
        date=date,
        is_active=True,
    )
    if exclude_id:
        active = active.exclude(pk=exclude_id)
    exceptions = list(active)
    if kind == AvailabilityException.Kind.CLOSED:
        if any(item.kind == kind for item in exceptions):
            return 'Une fermeture est déjà définie pour cette date.'
        return None
    if any(item.kind == AvailabilityException.Kind.CLOSED for item in exceptions):
        return 'Une fermeture existe déjà pour cette date.'

    candidate_periods = [(start_time, end_time)]
    if kind == AvailabilityException.Kind.REPLACEMENT:
        candidate_periods += [
            (item.start_time, item.end_time)
            for item in exceptions
            if item.kind in (AvailabilityException.Kind.REPLACEMENT, AvailabilityException.Kind.ADDITIONAL)
        ]
    else:
        replacements = [
            (item.start_time, item.end_time)
            for item in exceptions
            if item.kind == AvailabilityException.Kind.REPLACEMENT
        ]
        if not replacements:
            candidate_periods += list(
                WeeklyAvailabilityRule.objects.filter(
                    psychologue=psychologue,
                    weekday=date.weekday(),
                    is_active=True,
                ).values_list('start_time', 'end_time')
            )
        candidate_periods += [
            (item.start_time, item.end_time)
            for item in exceptions
            if item.kind == AvailabilityException.Kind.ADDITIONAL
        ]

    for index, (start, end) in enumerate(candidate_periods):
        if any(
            intervals_overlap(start, end, other_start, other_end)
            for other_start, other_end in candidate_periods[index + 1:]
        ):
            return 'Cette période chevauche une autre période de disponibilité.'
    return None


def active_consultation_overlaps(psychologue, date, start_time, end_time):
    return Consultation.objects.filter(
        psychologue=psychologue,
        date=date,
        status__in=ACTIVE_CONSULTATION_STATUSES,
        start_time__lt=end_time,
        end_time__gt=start_time,
    ).exists()


def _has_active_linked_consultation(slot):
    return slot.consultations.filter(status__in=ACTIVE_CONSULTATION_STATUSES).exists()


def _slot_conflict(slot, start_time, end_time):
    return intervals_overlap(
        start_time, end_time, slot.heure_debut, slot.heure_fin
    )


def visible_patient_slots(psychologue_id, date=None):
    """Return the slots a patient may book, with the reason each excluded slot
    is hidden. A slot is visible only if ALL conditions hold:
      1. it exists in the database (queried below);
      2. it is bookable (is_bookable=True);
      3. it is not reserved (statut == LIBRE);
      4. it is strictly in the future (date + heure_debut > now, local tz);
      5. the date has no active 'closed' exception;
      6. it is inside the 4-week generation window (today..today+28).
    """
    today = timezone.localdate()
    horizon_end = today + timedelta(days=GENERATION_HORIZON_DAYS)
    target_date = date or today
    now = timezone.now()

    closed_exists = AvailabilityException.objects.filter(
        psychologue_id=psychologue_id,
        date=target_date,
        is_active=True,
        kind=AvailabilityException.Kind.CLOSED,
    ).exists()

    reasons = {
        'closed': 'fermeture',
        'past': 'passé',
        'out_of_window': 'hors fenêtre',
        'not_bookable': 'non bookable',
        'reserved': 'réservé',
    }
    reasons['closed'] = (
        'fermeture' if closed_exists else None
    )

    rows = Creneau.objects.filter(
        psychologue_id=psychologue_id,
        date=target_date,
    ).order_by('heure_debut')

    visible = []
    hidden_counts = {key: 0 for key in ('past', 'out_of_window', 'not_bookable', 'reserved')}
    if closed_exists:
        hidden_counts['closed'] = rows.count()
    for slot in rows:
        if closed_exists:
            continue
        slot_start = timezone.make_aware(
            datetime.combine(slot.date, slot.heure_debut),
            timezone.get_current_timezone(),
        )
        if slot_start <= now:
            hidden_counts['past'] += 1
            continue
        if not (today <= slot.date <= horizon_end):
            hidden_counts['out_of_window'] += 1
            continue
        if not slot.is_bookable:
            hidden_counts['not_bookable'] += 1
            continue
        if slot.statut != Creneau.Statut.LIBRE:
            hidden_counts['reserved'] += 1
            continue
        visible.append(slot)
    return {
        'visible': visible,
        'hidden': hidden_counts,
        'closed': closed_exists,
    }


def generate_slots(psychologue, start_date=None):
    """Reconcile generated slots across today and the next 27 calendar dates."""
    # Always use the server-local date (Africa/Algiers); never tz-naive utcnow().
    today = start_date or timezone.localdate()
    profile = PsychologueProfile.objects.filter(user=psychologue).first()
    if (
        not psychologue.is_active
        or psychologue.user_type != 'psychologue'
        or profile is None
        or not profile.is_verified
        or profile.session_duration not in dict(PsychologueProfile.SESSION_DURATION_CHOICES)
    ):
        if profile is None:
            reason = 'Le profil psychologue est introuvable.'
        elif not psychologue.is_active:
            reason = 'Le compte psychologue est inactif ; aucun créneau n’a été généré.'
        elif not profile.is_verified:
            reason = 'Le profil psychologue n’est pas vérifié ; aucun créneau n’a été généré.'
        elif profile.session_duration not in dict(PsychologueProfile.SESSION_DURATION_CHOICES):
            reason = 'La durée configurée doit être 45, 50, 60 ou 75 minutes.'
        else:
            reason = 'Le compte utilisateur n’est pas un psychologue actif.'
        return {'created': 0, 'warnings': [reason]}

    now = timezone.now()
    duration = timedelta(minutes=profile.session_duration)
    warnings = []
    created = 0

    with transaction.atomic():
        expired_horizon_slots = Creneau.objects.filter(
            psychologue=psychologue,
            date__gte=today + timedelta(days=GENERATION_HORIZON_DAYS),
            is_generated=True,
            is_bookable=True,
            statut=Creneau.Statut.LIBRE,
        )
        for slot in expired_horizon_slots:
            if not _has_active_linked_consultation(slot):
                slot.is_bookable = False
                slot.save(update_fields=['is_bookable'])

        for offset in range(GENERATION_HORIZON_DAYS):
            current_date = today + timedelta(days=offset)
            periods = effective_work_periods(psychologue, current_date)
            if any(
                intervals_overlap(a_start, a_end, b_start, b_end)
                for index, (a_start, a_end) in enumerate(periods)
                for b_start, b_end in periods[index + 1:]
            ):
                warnings.append(f'{current_date}: des périodes qui se chevauchent ont été ignorées.')
                periods = []

            expected = []
            for period_start, period_end in periods:
                slot_start = datetime.combine(current_date, period_start)
                period_end_dt = datetime.combine(current_date, period_end)
                while slot_start + duration <= period_end_dt:
                    slot_end = slot_start + duration
                    aware_start = timezone.make_aware(slot_start, timezone.get_current_timezone())
                    if aware_start > now:
                        expected.append((slot_start.time(), slot_end.time()))
                    slot_start = slot_end

            date_slots = list(
                Creneau.objects.filter(psychologue=psychologue, date=current_date)
            )
            expected_by_start = {start: end for start, end in expected}

            # Retire obsolete free generated slots before checking candidates. This
            # lets a changed schedule replace old slots in this same reconciliation.
            for slot in date_slots:
                slot.refresh_from_db()
                if not slot.is_generated:
                    continue
                replacement_end = expected_by_start.get(slot.heure_debut)
                if replacement_end == slot.heure_fin:
                    continue
                manual_overlap = any(
                    other.pk != slot.pk
                    and not other.is_generated
                    and other.is_bookable
                    and other.statut != Creneau.Statut.BLOQUE
                    and _slot_conflict(slot, other.heure_debut, other.heure_fin)
                    for other in date_slots
                )
                protected = (
                    slot.statut != Creneau.Statut.LIBRE
                    or _has_active_linked_consultation(slot)
                    or manual_overlap
                    or active_consultation_overlaps(
                        psychologue,
                        current_date,
                        slot.heure_debut,
                        slot.heure_fin,
                    )
                )
                if protected:
                    warnings.append(
                        f'{current_date} {slot.heure_debut:%H:%M}: ancien créneau conservé car il est réservé ou lié à un rendez-vous actif.'
                    )
                    continue
                if slot.is_bookable:
                    slot.is_bookable = False
                    slot.save(update_fields=['is_bookable'])

            for start_time, end_time in expected:
                exact = next(
                    (slot for slot in date_slots if slot.heure_debut == start_time),
                    None,
                )
                if exact is not None:
                    try:
                        exact.refresh_from_db()
                    except Creneau.DoesNotExist:
                        continue
                    if not exact.is_generated:
                        warnings.append(
                            f'{current_date} {start_time:%H:%M}: créneau automatique ignoré car une disponibilité manuelle existe déjà.'
                        )
                        continue
                    if (
                        exact.statut != Creneau.Statut.LIBRE
                        or _has_active_linked_consultation(exact)
                        or active_consultation_overlaps(
                            psychologue,
                            current_date,
                            exact.heure_debut,
                            exact.heure_fin,
                        )
                    ):
                        if (exact.heure_debut, exact.heure_fin) != (start_time, end_time):
                            warnings.append(
                                f'{current_date} {start_time:%H:%M}: créneau réservé conservé sans modification malgré le nouveau planning.'
                            )
                        continue
                    conflict = any(
                        other.pk != exact.pk
                        and other.is_bookable
                        and other.statut != Creneau.Statut.BLOQUE
                        and _slot_conflict(other, start_time, end_time)
                        for other in date_slots
                    ) or active_consultation_overlaps(
                        psychologue,
                        current_date,
                        start_time,
                        end_time,
                    )
                    if conflict:
                        warnings.append(
                            f'{current_date} {start_time:%H:%M}: créneau automatique non modifié car il chevauche une disponibilité ou un rendez-vous.'
                        )
                        continue
                    if exact.heure_fin != end_time or not exact.is_bookable:
                        exact.heure_fin = end_time
                        exact.is_bookable = True
                        exact.save(update_fields=['heure_fin', 'is_bookable'], skip_overlap_validation=True)
                    continue

                if any(
                    slot.is_bookable
                    and slot.statut != Creneau.Statut.BLOQUE
                    and _slot_conflict(slot, start_time, end_time)
                    for slot in date_slots
                ) or active_consultation_overlaps(psychologue, current_date, start_time, end_time):
                    warnings.append(
                        f'{current_date} {start_time:%H:%M}: créneau ignoré car il chevauche une disponibilité ou un rendez-vous.'
                    )
                    continue
                new_slot = Creneau(psychologue=psychologue,
                    date=current_date,
                    heure_debut=start_time,
                    heure_fin=end_time,
                    statut=Creneau.Statut.LIBRE,
                    is_generated=True,
                    is_bookable=True,
                )
                new_slot.save(skip_overlap_validation=True)
                date_slots.append(new_slot)
                created += 1

            consultations = Consultation.objects.filter(
                psychologue=psychologue,
                date=current_date,
                status__in=ACTIVE_CONSULTATION_STATUSES,
            )
            for consultation in consultations:
                if not any(
                    start <= consultation.start_time
                    and end >= consultation.end_time
                    for start, end in periods
                ):
                    warnings.append(
                        f'{current_date} {consultation.start_time:%H:%M}: un rendez-vous existant ne correspond plus aux horaires.'
                    )

    return {'created': created, 'warnings': warnings}


def overlapping_slots(psychologue, date, start_time, end_time, exclude_id=None):
    slots = Creneau.objects.filter(
        psychologue=psychologue,
        date=date,
        is_bookable=True,
    ).exclude(statut=Creneau.Statut.BLOQUE)
    if exclude_id is not None:
        slots = slots.exclude(pk=exclude_id)
    return [
        slot for slot in slots
        if intervals_overlap(start_time, end_time, slot.heure_debut, slot.heure_fin)
    ]
