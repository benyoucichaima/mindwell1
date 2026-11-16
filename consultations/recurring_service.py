from datetime import datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import PsychologueProfile

from .models import (
    AvailabilityException,
    Consultation,
    Creneau,
    RecurringOccurrence,
    RecurringSession,
    WeeklyAvailabilityRule,
)
from .scheduling import (
    generate_slots,
    slot_matches_current_schedule,
)

DEFAULT_SERIES_WEEKS = 4


def _aware(date_value, time_value):
    """Combine a date + time into an aware datetime in the current tz."""
    return timezone.make_aware(
        datetime.combine(date_value, time_value),
        timezone.get_current_timezone(),
    )


def _occurrences_for_weekday(weekday, start_date, end_date, start_time):
    """Yield every date in [start_date, end_date] whose weekday matches.

    A series anchored to ``weekday`` only lands on matching weekdays. The
    ``start_time`` argument is accepted so callers can filter by time-of-day
    without recomputing it here; this helper only enumerates dates.
    """
    current = start_date
    while current <= end_date:
        if current.weekday() == weekday:
            yield current
        current += timedelta(days=1)


def _series_is_valid(psychologue, patient):
    if not psychologue.is_active or psychologue.user_type != 'psychologue':
        return 'Le psychologue est introuvable ou inactif.'
    profile = PsychologueProfile.objects.filter(user=psychologue).first()
    if profile is None or not profile.is_verified:
        return 'Le profil du psychologue doit être vérifié.'
    if patient.user_type != 'patient' or not patient.is_active:
        return 'Le patient est introuvable ou inactif.'
    return None


def create_recurring_session(
    *,
    psychologue,
    patient,
    weekday,
    start_time,
    start_date,
    end_date=None,
    occurrence_count=None,
    created_by=None,
    generate=True,
):
    """Create a recurring series and (by default) its planned occurrences.

    Exactly one of ``end_date`` or ``occurrence_count`` should be provided.
    When neither is given, the series spans ``DEFAULT_SERIES_WEEKS`` weeks from
    ``start_date``. Occurrences are created even when the target date falls in
    the future beyond the current 4-week generation window; those occurrences
    remain planned and become bookable only once the window reaches them (see
    ``generate_slots``).

    Returns ``(session, warnings)``. Raises ``ValidationError`` on bad input.
    """
    error = _series_is_valid(psychologue, patient)
    if error:
        raise ValidationError(error)

    if not (0 <= int(weekday) <= 6):
        raise ValidationError('Jour de la semaine invalide.')
    if not isinstance(start_time, time):
        raise ValidationError('Heure de début invalide.')

    profile = PsychologueProfile.objects.get(user=psychologue)
    duration = profile.session_duration
    if datetime.combine(start_date, start_time) + timedelta(minutes=duration) > datetime.combine(
        start_date, time(23, 59, 59)
    ) + timedelta(seconds=1):
        raise ValidationError("La séance dépasse la fin de journée.")

    # Resolve the effective end date from either explicit end_date or count.
    if occurrence_count is not None:
        if int(occurrence_count) <= 0:
            raise ValidationError('Le nombre de séances doit être positif.')
        # The Nth matching weekday from start_date.
        matching = list(_occurrences_for_weekday(weekday, start_date, start_date + timedelta(weeks=520), start_time))
        if len(matching) < int(occurrence_count):
            raise ValidationError("Impossible de placer ce nombre de séances.")
        computed_end = matching[int(occurrence_count) - 1]
    else:
        computed_end = end_date

    if computed_end is None:
        computed_end = start_date + timedelta(weeks=DEFAULT_SERIES_WEEKS) - timedelta(days=1)
    if computed_end < start_date:
        raise ValidationError('La date de fin précède la date de début.')

    warnings = []
    with transaction.atomic():
        session = RecurringSession.objects.create(
            patient=patient,
            psychologue=psychologue,
            weekday=int(weekday),
            start_time=start_time,
            duration_minutes=duration,
            start_date=start_date,
            end_date=computed_end,
            occurrence_count=occurrence_count,
            status=RecurringSession.Status.PROPOSED,
            created_by=created_by,
        )

        dates = list(
            _occurrences_for_weekday(
                int(weekday), start_date, computed_end, start_time
            )
        )
        planned = []
        now = timezone.now()
        for date_value in dates:
            # Skip dates the psychologue has fully closed for that day.
            if AvailabilityException.objects.filter(
                psychologue=psychologue,
                date=date_value,
                is_active=True,
                kind=AvailabilityException.Kind.CLOSED,
            ).exists():
                warnings.append(
                    f"{date_value}: journée fermée, occurrence ignorée."
                )
                continue
            # Never plan occurrences in the past.
            if _aware(date_value, start_time) <= now:
                continue
            planned.append(
                RecurringOccurrence(
                    recurring_session=session,
                    occurrence_date=date_value,
                )
            )
        # A series with no future occurrence is unusable (the patient has nothing
        # to accept). Reject it rather than persist an empty PROPOSED series.
        if not planned:
            raise ValidationError(
                "Aucune séance future : la date de début est déjà passée ou "
                "toutes les dates sont fermées. Choisissez une date à venir."
            )
        RecurringOccurrence.objects.bulk_create(planned)

    # Reconcile generated Creneaux within the 4-week window so occurrences can
    # be booked against real slots (best-effort; outside-window slots appear
    # later when generate_slots runs again).
    if generate:
        generate_slots(psychologue)

    return session, warnings


def _materialize_creneau(occurrence, session, profile):
    """Find a bookable slot for the occurrence, else create a manual one.

    Returns the ``Creneau`` or ``None`` when the slot cannot be used
    (e.g. an overlapping active consultation blocks it). Never creates a
    duplicate ``Creneau``: it reuses any existing non-blocked slot that starts
    at the same time, and only inserts a new row when none exists.
    """
    date_value = occurrence.occurrence_date
    start_time = session.start_time
    end_time = (datetime.combine(date_value, start_time) + timedelta(minutes=session.duration_minutes)).time()

    # Reuse an existing slot at the same start time (idempotent reconciliation).
    slot = (
        Creneau.objects.filter(
            psychologue=session.psychologue,
            date=date_value,
            heure_debut=start_time,
        )
        .exclude(statut=Creneau.Statut.BLOQUE)
        .order_by('-is_generated', 'pk')
        .first()
    )
    if slot is not None:
        if slot.is_bookable and slot_matches_current_schedule(session.psychologue, slot):
            return slot
        # An existing slot at this time that is not bookable cannot be reused.
        return None

    # No slot at this time: refuse to auto-create inside a closed date or when
    # an active consultation already occupies the interval.
    if AvailabilityException.objects.filter(
        psychologue=session.psychologue,
        date=date_value,
        is_active=True,
        kind=AvailabilityException.Kind.CLOSED,
    ).exists():
        return None
    from .scheduling import active_consultation_overlaps

    if active_consultation_overlaps(
        session.psychologue, date_value, start_time, end_time
    ):
        return None
    try:
        slot = Creneau.objects.create(
            psychologue=session.psychologue,
            date=date_value,
            heure_debut=start_time,
            heure_fin=end_time,
            statut=Creneau.Statut.LIBRE,
            is_generated=False,
            is_bookable=True,
        )
    except ValidationError:
        return None
    if not slot_matches_current_schedule(session.psychologue, slot):
        return None
    return slot


@transaction.atomic
def accept_recurring_occurrence(occurrence_id, patient):
    """Accept the *first* occurrence of a proposed series.

    On the first acceptance the series flips from ``PROPOSED`` to ``ACTIVE`` and
    every remaining future occurrence is materialized as ``CONFIRMED``
    (explicit patient consent for the recurring commitment). Subsequent
    acceptances of an already-active series simply materialize that one
    occurrence. Returns ``(occurrence, consultation, error)``.
    """
    occurrence = (
        RecurringOccurrence.objects.select_for_update()
        .select_related('recurring_session', 'recurring_session__psychologue')
        .filter(pk=occurrence_id)
        .first()
    )
    if occurrence is None:
        return None, None, "Cette occurrence est introuvable."
    session = occurrence.recurring_session
    # Explicit ownership guard — never rely on implicit filtering.
    if session.patient_id != patient.pk:
        return None, None, "Cette série ne vous appartient pas."
    if occurrence.is_cancelled:
        return occurrence, None, "Cette occurrence a été annulée."
    if occurrence.consultation_id:
        return occurrence, occurrence.consultation, None

    # Allow acceptance of a PROPOSED series (activation path) as well as one
    # already active/paused.
    if session.status not in (
        RecurringSession.Status.PROPOSED,
        RecurringSession.Status.ACTIVE,
        RecurringSession.Status.PAUSED,
    ):
        return occurrence, None, "Cette série n'accepte plus de réservation."

    activating = session.status == RecurringSession.Status.PROPOSED
    profile = PsychologueProfile.objects.filter(user=session.psychologue).first()
    if profile is None or not profile.is_verified:
        return occurrence, None, "Le profil du psychologue doit être vérifié."

    slot = _materialize_creneau(occurrence, session, profile)
    if slot is None:
        return occurrence, None, "Aucun créneau disponible pour cette date."

    # Re-validate the slot is still free, then claim it.
    claimed = Creneau.objects.filter(
        pk=slot.pk,
        statut=Creneau.Statut.LIBRE,
        is_bookable=True,
    ).update(statut=Creneau.Statut.RESERVE)
    if not claimed:
        return occurrence, None, "Ce créneau vient d'être réservé."

    # When the psychologist proposed the series, the first patient acceptance
    # confirms the whole series: the first occurrence is CONFIRMED and the rest
    # are materialized as CONFIRMED too. When the series is already ACTIVE, the
    # newly accepted occurrence stays PENDING (psychologist still confirms).
    first_status = (
        Consultation.Status.CONFIRMED
        if activating
        else Consultation.Status.PENDING
    )
    consultation = Consultation.objects.create(
        patient=patient,
        psychologue=session.psychologue,
        creneau=slot,
        date=slot.date,
        start_time=slot.heure_debut,
        end_time=slot.heure_fin,
        duration_minutes=session.duration_minutes,
        session_type=Consultation.SessionType.VIDEO,
        price=profile.hourly_rate,
        status=first_status,
        recurring_session=session,
    )
    occurrence.creneau = slot
    occurrence.consultation = consultation
    occurrence.save(update_fields=['creneau', 'consultation'])

    if activating:
        session.status = RecurringSession.Status.ACTIVE
        session.save(update_fields=['status', 'updated_at'])
        # Materialize all remaining future occurrences as CONFIRMED.
        _materialize_remaining(session, patient, confirmed=True)

    return occurrence, consultation, None


def _materialize_remaining(session, patient, confirmed=False):
    """Materialize every remaining future occurrence of ``session``.

    Idempotent: skips occurrences already fulfilled, cancelled, or materialized.
    Returns ``(created_count, warnings)``. Uses per-row ``update`` (not N+1
    queries beyond the single prefetch of occurrences + per-slot claim).
    """
    occurrences = list(
        RecurringOccurrence.objects.filter(recurring_session=session)
        .select_related('creneau')
        .order_by('occurrence_date')
    )
    profile = PsychologueProfile.objects.filter(user=session.psychologue).first()
    if profile is None or not profile.is_verified:
        return 0, ["Le profil du psychologue doit être vérifié."]

    created = 0
    warnings = []
    today = timezone.localdate()
    to_update = []
    for occurrence in occurrences:
        if occurrence.occurrence_date < today:
            continue
        if occurrence.is_cancelled or occurrence.consultation_id:
            continue
        slot = _materialize_creneau(occurrence, session, profile)
        if slot is None:
            warnings.append(f"{occurrence.occurrence_date}: aucun créneau disponible.")
            continue
        claimed = Creneau.objects.filter(
            pk=slot.pk,
            statut=Creneau.Statut.LIBRE,
            is_bookable=True,
        ).update(statut=Creneau.Statut.RESERVE)
        if not claimed:
            warnings.append(f"{occurrence.occurrence_date}: créneau déjà réservé.")
            continue
        consultation = Consultation.objects.create(
            patient=patient,
            psychologue=session.psychologue,
            creneau=slot,
            date=slot.date,
            start_time=slot.heure_debut,
            end_time=slot.heure_fin,
            duration_minutes=session.duration_minutes,
            session_type=Consultation.SessionType.VIDEO,
            price=profile.hourly_rate,
            status=(
                Consultation.Status.CONFIRMED
                if confirmed
                else Consultation.Status.PENDING
            ),
            recurring_session=session,
        )
        occurrence.creneau = slot
        occurrence.consultation = consultation
        to_update.append(occurrence)
        created += 1

    # Single bulk update for all newly-linked occurrences.
    if to_update:
        RecurringOccurrence.objects.bulk_update(
            to_update, ['creneau', 'consultation']
        )
    return created, warnings


@transaction.atomic
def skip_occurrence(occurrence_id, user):
    """Cancel a single occurrence without touching the series.

    ``user`` may be either the owning patient or the assigned psychologist.
    Raises ``PermissionDenied`` when neither owns the occurrence (explicit
    ownership guard). If the occurrence was already materialized, its
    consultation is cancelled and the physical slot is freed.
    Returns ``(occurrence, error)``.
    """
    from django.core.exceptions import PermissionDenied

    occurrence = (
        RecurringOccurrence.objects.select_for_update()
        .select_related('recurring_session')
        .filter(pk=occurrence_id)
        .first()
    )
    if occurrence is None:
        return None, "Cette occurrence est introuvable."
    session = occurrence.recurring_session
    is_owner = (
        session.patient_id == user.pk
        or session.psychologue_id == user.pk
    )
    if not is_owner:
        raise PermissionDenied("Cette occurrence ne vous appartient pas.")
    if occurrence.is_cancelled:
        return occurrence, None
    if occurrence.consultation_id and occurrence.consultation.status not in (
        Consultation.Status.CANCELLED,
        Consultation.Status.COMPLETED,
    ):
        consultation = occurrence.consultation
        consultation.status = Consultation.Status.CANCELLED
        consultation.cancelled_at = timezone.now()
        consultation.save(update_fields=['status', 'cancelled_at', 'updated_at'])
        if consultation.creneau_id:
            Creneau.objects.filter(
                pk=consultation.creneau_id,
                statut=Creneau.Statut.RESERVE,
            ).update(statut=Creneau.Statut.LIBRE)
    occurrence.is_cancelled = True
    occurrence.cancelled_at = timezone.now()
    occurrence.save(update_fields=['is_cancelled', 'cancelled_at'])
    return occurrence, None


@transaction.atomic
def decline_series(session_id, patient):
    """Patient declines a PROPOSED series.

    Only the owning patient may decline, and only while the series is still
    ``PROPOSED`` (an ACTIVE series is cancelled via skip/cancel flows).
    Cancels the series itself and every future occurrence. Returns
    ``(session, error)``.
    """
    from django.core.exceptions import PermissionDenied

    session = (
        RecurringSession.objects.select_for_update()
        .filter(pk=session_id)
        .first()
    )
    if session is None:
        return None, "Cette série est introuvable."
    if session.patient_id != patient.pk:
        raise PermissionDenied("Cette série ne vous appartient pas.")
    if session.status == RecurringSession.Status.CANCELLED:
        return session, None
    if session.status != RecurringSession.Status.PROPOSED:
        return session, "Cette série n'est plus en attente de confirmation."

    session.status = RecurringSession.Status.CANCELLED
    session.save(update_fields=['status', 'updated_at'])

    today = timezone.localdate()
    occurrences = list(
        RecurringOccurrence.objects.filter(
            recurring_session=session,
            is_cancelled=False,
            occurrence_date__gte=today,
        ).select_related('consultation', 'creneau')
    )
    for occurrence in occurrences:
        # A PROPOSED series should have no materialized consultations, but be
        # defensive: cancel anything that exists and free the slot.
        if occurrence.consultation_id and occurrence.consultation.status not in (
            Consultation.Status.CANCELLED,
            Consultation.Status.COMPLETED,
        ):
            consultation = occurrence.consultation
            consultation.status = Consultation.Status.CANCELLED
            consultation.cancelled_at = timezone.now()
            consultation.save(update_fields=['status', 'cancelled_at', 'updated_at'])
            if consultation.creneau_id:
                Creneau.objects.filter(
                    pk=consultation.creneau_id,
                    statut=Creneau.Statut.RESERVE,
                ).update(statut=Creneau.Statut.LIBRE)
        occurrence.is_cancelled = True
        occurrence.cancelled_at = timezone.now()
    if occurrences:
        RecurringOccurrence.objects.bulk_update(
            occurrences, ['is_cancelled', 'cancelled_at']
        )
    return session, None


def cancel_series(session_id, user):
    """Cancel an entire series. Only the assigned psychologist may cancel.

    Raises ``PermissionDenied`` for anyone else. Cancels every future
    non-cancelled occurrence and materialized consultation.
    """
    from django.core.exceptions import PermissionDenied

    session = (
        RecurringSession.objects.select_for_update()
        .filter(pk=session_id)
        .first()
    )
    if session is None:
        return None, "Cette série est introuvable."
    if session.psychologue_id != user.pk:
        raise PermissionDenied("Seul le psychologue assigné peut annuler la série.")
    if session.status == RecurringSession.Status.CANCELLED:
        return session, None
    session.status = RecurringSession.Status.CANCELLED
    session.save(update_fields=['status', 'updated_at'])

    today = timezone.localdate()
    occurrences = list(
        RecurringOccurrence.objects.filter(
            recurring_session=session,
            is_cancelled=False,
            occurrence_date__gte=today,
        ).select_related('consultation', 'creneau')
    )
    for occurrence in occurrences:
        if occurrence.consultation_id and occurrence.consultation.status not in (
            Consultation.Status.CANCELLED,
            Consultation.Status.COMPLETED,
        ):
            consultation = occurrence.consultation
            consultation.status = Consultation.Status.CANCELLED
            consultation.cancelled_at = timezone.now()
            consultation.save(update_fields=['status', 'cancelled_at', 'updated_at'])
            if consultation.creneau_id:
                Creneau.objects.filter(
                    pk=consultation.creneau_id,
                    statut=Creneau.Statut.RESERVE,
                ).update(statut=Creneau.Statut.LIBRE)
        occurrence.is_cancelled = True
        occurrence.cancelled_at = timezone.now()
    if occurrences:
        RecurringOccurrence.objects.bulk_update(
            occurrences, ['is_cancelled', 'cancelled_at']
        )
    return session, None


def upcoming_occurrences_for_patient(patient):
    """Planned, non-cancelled, future occurrences visible to a patient.

    Materialized occurrences (with a consultation) are included too, since the
    patient must see them in their dashboard immediately. PROPOSED series are
    included so the patient can review and accept them.
    """
    today = timezone.localdate()
    return (
        RecurringOccurrence.objects.filter(
            recurring_session__patient=patient,
            recurring_session__status__in=[
                RecurringSession.Status.PROPOSED,
                RecurringSession.Status.ACTIVE,
                RecurringSession.Status.PAUSED,
            ],
            is_cancelled=False,
            occurrence_date__gte=today,
        )
        .select_related('recurring_session', 'recurring_session__psychologue', 'consultation', 'creneau')
        .order_by('occurrence_date')
    )


def occurrences_for_psychologue(psychologue, status=None):
    qs = RecurringOccurrence.objects.filter(
        recurring_session__psychologue=psychologue,
    ).select_related('recurring_session', 'recurring_session__patient', 'consultation', 'creneau')
    if status is not None:
        qs = qs.filter(recurring_session__status=status)
    return qs.order_by('occurrence_date')


@transaction.atomic
def materialize_series_for_consultation(consultation):
    """When a consultation belonging to a recurring series is confirmed,
    materialize every remaining future occurrence of the same series.

    Thin wrapper over the bulk ``_materialize_remaining`` helper: idempotent,
    skips fulfilled/cancelled/past occurrences, and bulk-updates linked rows.
    Returns ``(created_count, warnings)``.
    """
    if consultation.recurring_session_id is None:
        return 0, []
    session = consultation.recurring_session
    return _materialize_remaining(
        session, consultation.patient, confirmed=True
    )


@transaction.atomic
def request_reschedule(session_id, patient, note):
    """Patient asks the psychologist to change the proposed schedule.

    Only the owning patient may request a change, and only while the series is
    still ``PROPOSED`` (once ``ACTIVE`` the patient uses skip instead). Stores
    the note and flags the series for psychologist review. Returns
    ``(session, error)``; raises ``PermissionDenied`` for non-owners.
    """
    from django.core.exceptions import PermissionDenied

    session = RecurringSession.objects.select_for_update().filter(pk=session_id).first()
    if session is None:
        return None, "Cette série est introuvable."
    if session.patient_id != patient.pk:
        raise PermissionDenied("Cette série ne vous appartient pas.")
    if session.status != RecurringSession.Status.PROPOSED:
        return session, "Cette série n'est plus en attente de confirmation."

    session.patient_note = (note or '').strip()
    session.reschedule_requested = True
    session.reschedule_request_at = timezone.now()
    session.reschedule_reviewed = False
    session.save(
        update_fields=[
            'patient_note',
            'reschedule_requested',
            'reschedule_request_at',
            'reschedule_reviewed',
            'updated_at',
        ]
    )
    return session, None