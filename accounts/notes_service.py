"""Business logic for psychologist-authored consultation notes.

Two strictly separated note kinds (see ``ConsultationNote``):

* ``PATIENT`` — shared with the patient and notified once sent.
* ``PROFESSIONAL`` — private, never visible to the patient, never notified.

Confidentiality is enforced here and in the querysets, not only in templates.
This module is independent of the AI analysis (``ai_service``).
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from consultations.models import Consultation

from .models import ConsultationNote
from .notifications import notify_user


def _clean_content(content):
    content = (content or '').strip()
    if not content:
        raise ValidationError("Le contenu de la note est requis.")
    return content


def _resolve_consultation(psychologue, patient, consultation_id):
    """Return the consultation only if it belongs to this pair.

    Raises ``ValidationError`` when an explicit ``consultation_id`` does not
    match the (psychologue, patient) pair, so a note can never be linked to a
    third party's consultation. Returns ``None`` when no id is supplied.
    """
    if not consultation_id:
        return None
    consultation = Consultation.objects.filter(
        pk=consultation_id,
        psychologue=psychologue,
        patient=patient,
    ).first()
    if consultation is None:
        raise ValidationError(
            "La consultation sélectionnée n’appartient pas à ce patient."
        )
    return consultation


def consultations_for_patient(psychologue, patient):
    """Consultations of this (psychologue, patient) pair for the selector.

    Strictly filtered by both the connected psychologist and the selected
    patient; cancelled/no-show are included so professional documentation stays
    possible.
    """
    return (
        Consultation.objects.filter(
            psychologue=psychologue, patient=patient
        )
        .order_by('-date', '-start_time')
    )


def psychologist_patients(psychologue):
    """Distinct patients the psychologist is allowed to follow."""
    from .models import CustomUser

    return (
        CustomUser.objects.filter(
            patient_consultations__psychologue=psychologue
        )
        .distinct()
        .order_by('first_name', 'last_name', 'username')
    )


# Consultation statuses that represent an actual (or completed) encounter.
_ACTIVE_ENCOUNTER_STATUSES = (
    Consultation.Status.PENDING,
    Consultation.Status.CONFIRMED,
    Consultation.Status.IN_PROGRESS,
    Consultation.Status.COMPLETED,
)


def _assert_can_note(psychologue, patient, note_type):
    """Authorize a note for this pair, per note type.

    * There must be at least one consultation between the pair (relationship).
    * ``PROFESSIONAL`` notes are always allowed (necessary documentation, even
      after a cancellation or a no-show).
    * ``PATIENT`` notes require at least one encounter that was not cancelled
      and not a no-show.
    """
    relationship = Consultation.objects.filter(
        psychologue=psychologue, patient=patient
    )
    if not relationship.exists():
        raise PermissionDenied(
            "Vous n'êtes pas autorisé à écrire des notes pour ce patient."
        )
    if note_type == ConsultationNote.NoteType.PATIENT:
        has_encounter = relationship.filter(
            status__in=_ACTIVE_ENCOUNTER_STATUSES
        ).exists()
        # A compensatory ("rattrapage") session entitles the patient to a note
        # even when the pair has no active encounter (e.g. the original session
        # was cancelled by the psychologist and only the replacement remains).
        has_replacement = relationship.filter(is_replacement=True).exists()
        if not has_encounter and not has_replacement:
            raise ValidationError(
                "Aucune consultation tenue : une note destinée au patient ne "
                "peut pas être envoyée (seule une note professionnelle privée "
                "est autorisée)."
            )


def create_patient_note(*, psychologue, patient, content, consultation_id=None):
    """Create a patient-facing note, send it, and notify the patient."""
    content = _clean_content(content)
    _assert_can_note(psychologue, patient, ConsultationNote.NoteType.PATIENT)
    consultation = _resolve_consultation(psychologue, patient, consultation_id)

    note = ConsultationNote.objects.create(
        patient=patient,
        psychologue=psychologue,
        consultation=consultation,
        note_type=ConsultationNote.NoteType.PATIENT,
        content=content,
        sent_at=timezone.now(),
    )
    notify_user(
        patient.pk,
        'clinical_note',
        "Vous avez reçu une nouvelle note de votre psychologue.",
        title="Nouvelle note de votre psychologue",
        url=reverse('accounts:patient_note_detail', args=[note.pk]),
    )
    return note


def create_professional_note(*, psychologue, patient, content, consultation_id=None):
    """Create a private note (no notification, never shown to the patient)."""
    content = _clean_content(content)
    _assert_can_note(psychologue, patient, ConsultationNote.NoteType.PROFESSIONAL)
    consultation = _resolve_consultation(psychologue, patient, consultation_id)

    return ConsultationNote.objects.create(
        patient=patient,
        psychologue=psychologue,
        consultation=consultation,
        note_type=ConsultationNote.NoteType.PROFESSIONAL,
        content=content,
    )


def notes_for_psychologue(psychologue, patient=None):
    """All notes written by this psychologist (both kinds)."""
    qs = ConsultationNote.objects.filter(
        psychologue=psychologue
    ).select_related('patient', 'psychologue', 'consultation')
    if patient is not None:
        qs = qs.filter(patient=patient)
    return qs.order_by('-created_at')


def patient_visible_notes(patient):
    """Only sent, non-retracted PATIENT notes, for the given patient."""
    return (
        ConsultationNote.objects.filter(
            patient=patient,
            note_type=ConsultationNote.NoteType.PATIENT,
            sent_at__isnull=False,
            retracted_at__isnull=True,
        )
        .select_related('psychologue')
        .order_by('-sent_at')
    )


def get_patient_note(note_id, patient):
    """Strict lookup: a patient can only read their own sent, non-retracted note."""
    return (
        ConsultationNote.objects.filter(
            pk=note_id,
            patient=patient,
            note_type=ConsultationNote.NoteType.PATIENT,
            sent_at__isnull=False,
            retracted_at__isnull=True,
        )
        .select_related('psychologue')
        .first()
    )


def get_patient_note_any_status(note_id, patient):
    """Return a PATIENT note even if retracted (to inform the patient).

    Used only after ``get_patient_note`` fails, to render a "retracted" notice
    instead of a misleading 404. Never returns private notes or other patients'
    notes.
    """
    return (
        ConsultationNote.objects.filter(
            pk=note_id,
            patient=patient,
            note_type=ConsultationNote.NoteType.PATIENT,
            sent_at__isnull=False,
        )
        .select_related('psychologue')
        .first()
    )


@transaction.atomic
def retract_note(note_id, psychologue, reason=''):
    """Retract a sent PATIENT note, keeping an audit trail.

    Only the authoring psychologist may retract, only a sent PATIENT note that is
    not already retracted. The note row and clinical history are preserved; the
    content is hidden from the patient and the related notification message is
    updated (the notification row is never deleted). Returns ``(note, error)``.
    """
    note = (
        ConsultationNote.objects.select_for_update()
        .filter(pk=note_id)
        .first()
    )
    if note is None:
        return None, "Note introuvable."
    if note.psychologue_id != psychologue.pk:
        raise PermissionDenied("Vous ne pouvez rétracter que vos propres notes.")
    if note.note_type != ConsultationNote.NoteType.PATIENT:
        return note, "Seule une note destinée au patient peut être rétractée."
    if note.sent_at is None:
        return note, "Cette note n'a pas encore été envoyée."
    if note.retracted_at is not None:
        return note, "Cette note est déjà rétractée."

    note.retracted_at = timezone.now()
    note.retraction_reason = (reason or '').strip()
    note.save(update_fields=['retracted_at', 'retraction_reason', 'updated_at'])

    # Keep the notification (history) but reflect the retraction; never delete.
    from .models import Notification

    Notification.objects.filter(
        user_id=note.patient_id,
        url=reverse('accounts:patient_note_detail', args=[note.pk]),
    ).update(
        message="Une note vous a été envoyée puis rétractée par votre psychologue.",
        is_read=True,
    )
    return note, None