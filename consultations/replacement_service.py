"""Compensatory ("rattrapage") sessions.

Business rule: when a patient has PAID for a consultation and the psychologist
cancels it (for personal reasons), the patient is owed a free replacement
session. This module lists the owed sessions and records a patient's refusal.

It never touches the normal consultation lifecycle — it only reads cancelled,
paid, psychologist-cancelled consultations and flags a refusal on them.
"""

from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from accounts.notifications import notify_user

from .models import Consultation, ReplacementChangeRequest


def _psychologist_cancelled():
    """Match consultations the *psychologist* cancelled.

    Historically the "Annuler en urgence" button recorded the reason as
    ``TECHNICAL`` while still being a psychologist-initiated cancellation, so
    those rows are owed too. A ``TECHNICAL`` row is only treated as a
    psychologist cancellation when ``cancelled_by`` is the assigned psychologist
    (a patient-initiated technical cancellation is not owed).
    """
    return Q(
        cancellation_reason=Consultation.CancellationReason.PSYCHOLOGUE
    ) | Q(
        cancellation_reason=Consultation.CancellationReason.TECHNICAL,
        cancelled_by_id=models.F('psychologue_id'),
    )


def _is_psychologist_cancelled(consultation):
    if consultation.cancellation_reason == (
        Consultation.CancellationReason.PSYCHOLOGUE
    ):
        return True
    return (
        consultation.cancellation_reason
        == Consultation.CancellationReason.TECHNICAL
        and consultation.cancelled_by_id is not None
        and consultation.cancelled_by_id == consultation.psychologue_id
    )


def owed_replacements_for_patient(patient):
    """Cancelled, paid consultations cancelled by the psychologist that the
    patient may still make up for free.

    A consultation is owed a replacement when:
      * it belongs to the patient,
      * it was cancelled by the psychologist (reason ``PSYCHOLOGUE``, or the
        legacy ``TECHNICAL`` reason recorded by the emergency-cancel button),
      * it was paid,
      * it is not itself a replacement session,
      * no replacement has been created for it yet,
      * the patient has not declined it.
    """
    return (
        Consultation.objects.filter(
            patient=patient,
            status=Consultation.Status.CANCELLED,
            payment_status=Consultation.PaymentStatus.PAID,
            is_replacement=False,
            replacement_declined_at__isnull=True,
        )
        .filter(_psychologist_cancelled())
        .exclude(replacements__is_replacement=True)
        .select_related('psychologue')
        .order_by('-date', '-start_time')
    )


def serialize_replacement(consultation):
    """JSON payload for one owed replacement session."""
    psychologue = consultation.psychologue
    return {
        'id': str(consultation.pk),
        'reference_number': consultation.reference_number,
        'psychologue_id': psychologue.pk,
        'psychologue_name': (
            f"Dr. {psychologue.get_full_name() or psychologue.username}"
        ),
        'date': consultation.date.isoformat(),
        'start_time': consultation.start_time.strftime('%H:%M'),
        'duration_minutes': consultation.duration_minutes,
        'cancelled_at': (
            consultation.cancelled_at.isoformat()
            if consultation.cancelled_at
            else None
        ),
        'book_url': reverse(
            'accounts:book_consultation', args=[psychologue.pk]
        ),
    }


@transaction.atomic
def decline_replacement(consultation_id, patient):
    """Patient declines an owed replacement session.

    Persists the refusal so the session is not offered again. Only the owning
    patient may decline. Returns ``(consultation, error)``; raises
    ``PermissionDenied`` for non-owners.
    """
    consultation = (
        Consultation.objects.select_for_update()
        .filter(pk=consultation_id)
        .first()
    )
    if consultation is None:
        return None, "Cette séance est introuvable."
    if consultation.patient_id != patient.pk:
        raise PermissionDenied("Cette séance ne vous appartient pas.")
    if consultation.replacement_declined_at is not None:
        return consultation, None
    consultation.replacement_declined_at = timezone.now()
    consultation.save(
        update_fields=['replacement_declined_at', 'updated_at']
    )
    return consultation, None


def _is_owed_replacement(consultation):
    """True when this consultation is an owed replacement shown to a patient."""
    return (
        consultation.is_replacement is False
        and consultation.status == Consultation.Status.CANCELLED
        and _is_psychologist_cancelled(consultation)
        and consultation.payment_status == Consultation.PaymentStatus.PAID
    )


@transaction.atomic
def submit_change_request(replacement_id, patient, message, proposed_date=None):
    """Patient asks to change the schedule of an owed replacement session.

    Only the owning patient may submit, only for an owed replacement session,
    and only one PENDING request may exist at a time. Notifies the psychologist.
    Returns ``(change_request, error)``; raises ``PermissionDenied`` for
    non-owners.
    """
    consultation = (
        Consultation.objects.select_for_update()
        .filter(pk=replacement_id)
        .first()
    )
    if consultation is None:
        return None, "Cette séance est introuvable."
    if consultation.patient_id != patient.pk:
        raise PermissionDenied("Cette séance ne vous appartient pas.")
    if not _is_owed_replacement(consultation):
        return None, "Cette séance n'est pas une séance de rattrapage."

    message = (message or '').strip()
    if not message:
        return None, "Veuillez saisir un message."

    already_pending = ReplacementChangeRequest.objects.filter(
        replacement_consultation=consultation,
        status=ReplacementChangeRequest.Status.PENDING,
    ).exists()
    if already_pending:
        return None, "Une demande est déjà en attente de réponse."

    change_request = ReplacementChangeRequest.objects.create(
        replacement_consultation=consultation,
        patient=patient,
        message=message,
        proposed_date=proposed_date,
        status=ReplacementChangeRequest.Status.PENDING,
    )
    notify_user(
        consultation.psychologue_id,
        'replacement_change_request',
        (
            f"{patient.get_full_name() or patient.username} propose un "
            "changement d'horaire pour la séance de rattrapage."
        ),
        title="Nouvelle demande de changement d'horaire",
    )
    return change_request, None


def pending_change_requests_for_psychologue(psychologue):
    """Pending change requests addressed to this psychologist."""
    return (
        ReplacementChangeRequest.objects.filter(
            replacement_consultation__psychologue=psychologue,
            status=ReplacementChangeRequest.Status.PENDING,
        )
        .select_related('replacement_consultation', 'patient')
        .order_by('-created_at')
    )


def serialize_change_request(change_request):
    """JSON payload for one change request."""
    return {
        'id': change_request.pk,
        'patient_name': (
            change_request.patient.get_full_name()
            or change_request.patient.username
        ),
        'patient_email': change_request.patient.email,
        'original_date': change_request.replacement_consultation.date.isoformat(),
        'message': change_request.message,
        'proposed_date': (
            change_request.proposed_date.isoformat()
            if change_request.proposed_date
            else None
        ),
        'status': change_request.status,
        'created_at': change_request.created_at.isoformat(),
    }


@transaction.atomic
def respond_to_change_request(
    request_id, psychologue, action, response='', new_date=None
):
    """Psychologist accepts, rejects, or counter-proposes a change request.

    Only the assigned psychologist may respond, and only while the request is
    PENDING. The patient is notified. Returns ``(change_request, error)``;
    raises ``PermissionDenied`` for other psychologists.
    """
    change_request = (
        ReplacementChangeRequest.objects.select_for_update()
        .filter(pk=request_id)
        .first()
    )
    if change_request is None:
        return None, "Cette demande est introuvable."
    if (
        change_request.replacement_consultation.psychologue_id
        != psychologue.pk
    ):
        raise PermissionDenied("Cette demande ne vous concerne pas.")
    if change_request.status != ReplacementChangeRequest.Status.PENDING:
        return change_request, "Cette demande a déjà été traitée."

    response = (response or '').strip()
    if action == 'accept':
        change_request.status = ReplacementChangeRequest.Status.ACCEPTED
        change_request.psychologist_response = response
        message = "Votre demande de changement d'horaire a été acceptée."
    elif action == 'reject':
        change_request.status = ReplacementChangeRequest.Status.REJECTED
        change_request.psychologist_response = response
        message = "Votre demande de changement d'horaire a été refusée."
    elif action == 'counter':
        change_request.status = (
            ReplacementChangeRequest.Status.COUNTER_PROPOSED
        )
        change_request.psychologist_response = response
        if new_date is not None:
            change_request.proposed_date = new_date
        message = "Votre psychologue vous a fait une contre-proposition."
    else:
        return change_request, "Action invalide."

    change_request.save()
    notify_user(
        change_request.patient_id,
        'replacement_change_response',
        message,
        title="Réponse à votre demande de changement d'horaire",
    )
    return change_request, None