import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from django.utils import timezone

from accounts.models import CustomUser

from .models import RecurringOccurrence, RecurringSession
from .recurring_service import (
    accept_recurring_occurrence,
    cancel_series,
    create_recurring_session,
    decline_series,
    request_reschedule,
    skip_occurrence,
)


def _parse_time(value):
    from datetime import datetime

    if not value:
        return None
    try:
        return datetime.strptime(value, '%H:%M').time()
    except (TypeError, ValueError):
        return None


def _parse_date(value):
    from datetime import datetime

    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def serialize_session(session, upcoming_count=None, next_occurrence=None):
    if upcoming_count is None:
        upcoming_count = (
            RecurringOccurrence.objects.filter(
                recurring_session=session,
                is_cancelled=False,
            ).count()
        )
    return {
        'id': session.pk,
        'patient_id': session.patient_id,
        'patient_name': session.patient.get_full_name() or session.patient.username,
        'psychologue_id': session.psychologue_id,
        'psychologue_name': (
            f"Dr. {session.psychologue.get_full_name() or session.psychologue.username}"
        ),
        'weekday': session.weekday,
        'weekday_label': session.get_weekday_display(),
        'start_time': session.start_time.strftime('%H:%M'),
        'duration_minutes': session.duration_minutes,
        'start_date': session.start_date.isoformat(),
        'end_date': session.end_date.isoformat(),
        'occurrence_count': session.occurrence_count,
        'status': session.status,
        'upcoming_occurrences': upcoming_count,
        'next_occurrence': next_occurrence,
        'reschedule_requested': session.reschedule_requested,
        'reschedule_reviewed': session.reschedule_reviewed,
        'patient_note': session.patient_note or '',
        'reschedule_request_at': (
            session.reschedule_request_at.isoformat()
            if session.reschedule_request_at
            else None
        ),
    }


def serialize_occurrence(occurrence):
    consultation = occurrence.consultation
    return {
        'id': occurrence.pk,
        'recurring_session': occurrence.recurring_session_id,
        'occurrence_date': occurrence.occurrence_date.isoformat(),
        'is_cancelled': occurrence.is_cancelled,
        'is_materialized': occurrence.consultation_id is not None,
        'consultation_id': consultation.pk if consultation else None,
        'consultation_status': consultation.status if consultation else None,
        'creneau_id': occurrence.creneau_id,
    }


@login_required
@require_POST
def create_recurring_session_api(request):
    if request.user.user_type != 'psychologue':
        return JsonResponse(
            {'status': 'error', 'message': 'Seul un psychologue peut créer une série.'},
            status=403,
        )

    try:
        payload = json.loads(request.body or '{}')
    except (TypeError, ValueError):
        return JsonResponse(
            {'status': 'error', 'message': 'Corps JSON invalide.'}, status=400
        )

    patient = CustomUser.objects.filter(
        pk=payload.get('patient_id'),
        user_type='patient',
        is_active=True,
    ).first()
    if patient is None:
        return JsonResponse(
            {'status': 'error', 'message': 'Patient introuvable.'}, status=404
        )

    weekday = payload.get('weekday')
    start_time = _parse_time(payload.get('start_time'))
    start_date = _parse_date(payload.get('start_date'))
    end_date = _parse_date(payload.get('end_date'))
    occurrence_count = payload.get('occurrence_count')

    if weekday is None or start_time is None or start_date is None:
        return JsonResponse(
            {
                'status': 'error',
                'message': 'weekday, start_time (HH:MM) et start_date (YYYY-MM-DD) sont requis.',
            },
            status=400,
        )

    if not end_date and not occurrence_count:
        # Default to 4 weeks from start_date.
        from datetime import timedelta

        end_date = start_date + timedelta(weeks=4) - timedelta(days=1)

    try:
        session, warnings = create_recurring_session(
            psychologue=request.user,
            patient=patient,
            weekday=weekday,
            start_time=start_time,
            start_date=start_date,
            end_date=end_date,
            occurrence_count=int(occurrence_count) if occurrence_count else None,
            created_by=request.user,
        )
    except ValidationError as error:
        return JsonResponse(
            {'status': 'error', 'message': '; '.join(error.messages)}, status=400
        )
    except Exception:
        import logging

        logging.getLogger(__name__).exception('Failed to create recurring session')
        return JsonResponse(
            {'status': 'error', 'message': 'Impossible de créer la série.'},
            status=500,
        )

    return JsonResponse(
        {
            'status': 'success',
            'session': serialize_session(session),
            'warnings': warnings,
        },
        status=201,
    )


@login_required
@require_POST
def cancel_recurring_session_api(request, session_id):
    if request.user.user_type != 'psychologue':
        return JsonResponse(
            {'status': 'error', 'message': 'Seul le psychologue assigné peut annuler.'},
            status=403,
        )

    session = get_object_or_404(RecurringSession, pk=session_id)
    try:
        session, error = cancel_series(session.pk, request.user)
    except PermissionDenied:
        return JsonResponse(
            {'status': 'error', 'message': 'Seul le psychologue assigné peut annuler.'},
            status=403,
        )
    if error:
        return JsonResponse({'status': 'error', 'message': error}, status=400)
    return JsonResponse({'status': 'success', 'session': serialize_session(session)})


@login_required
@require_GET
def upcoming_recurring_sessions_api(request):
    if request.user.user_type == 'patient':
        sessions = (
            RecurringSession.objects.filter(
                patient=request.user,
                status__in=[
                    RecurringSession.Status.PROPOSED,
                    RecurringSession.Status.ACTIVE,
                    RecurringSession.Status.PAUSED,
                ],
            )
            .select_related('patient', 'psychologue')
            .order_by('start_date')
        )
    elif request.user.user_type == 'psychologue':
        sessions = (
            RecurringSession.objects.filter(
                psychologue=request.user,
                status__in=[
                    RecurringSession.Status.PROPOSED,
                    RecurringSession.Status.ACTIVE,
                    RecurringSession.Status.PAUSED,
                ],
            )
            .select_related('patient', 'psychologue')
            .order_by('start_date')
        )
    else:
        return JsonResponse(
            {'status': 'error', 'message': 'Non autorisé.'}, status=403
        )

    upcoming_counts = {}
    from .models import RecurringOccurrence

    from django.utils import timezone

    today = timezone.localdate()
    # Single query: fetch every upcoming (non-cancelled, future) occurrence for
    # the visible sessions, ordered by date. Both the per-session count and the
    # earliest "next" occurrence are derived from these rows in Python, so there
    # is exactly ONE database query and no per-session N+1.
    upcoming_rows = list(
        RecurringOccurrence.objects.filter(
            recurring_session__in=sessions,
            is_cancelled=False,
            occurrence_date__gte=today,
        )
        .order_by('occurrence_date')
        .values_list(
            'recurring_session_id', 'pk', 'occurrence_date', 'is_cancelled',
        )
    )
    for session_id, _occurrence_pk, _occurrence_date, _cancelled in upcoming_rows:
        upcoming_counts[session_id] = upcoming_counts.get(session_id, 0) + 1

    # First (earliest) non-cancelled future occurrence per session — since the
    # rows are ordered by date, the first time we see a session_id is its
    # earliest occurrence. The patient UI can accept/skip without a second
    # request; the psychologist reload logic stays on this single endpoint.
    next_occurrences = {}
    for session_id, occurrence_pk, occurrence_date, _cancelled in upcoming_rows:
        if session_id not in next_occurrences:
            next_occurrences[session_id] = (
                occurrence_pk,
                occurrence_date,
                _cancelled,
            )

    def _serialize_next(raw):
        if raw is None:
            return None
        occurrence_pk, occurrence_date, cancelled = raw
        return {
            'id': occurrence_pk,
            'occurrence_date': occurrence_date.isoformat(),
            'is_cancelled': cancelled,
        }

    return JsonResponse({
        'status': 'success',
        'sessions': [
            serialize_session(
                session,
                upcoming_counts.get(session.pk, 0),
                _serialize_next(next_occurrences.get(session.pk)),
            )
            for session in sessions
        ],
    })


@login_required
@require_POST
def accept_recurring_occurrence_api(request, occurrence_id):
    if request.user.user_type != 'patient':
        return JsonResponse(
            {'status': 'error', 'message': 'Seul le patient peut accepter.'}, status=403
        )

    try:
        occurrence, consultation, error = accept_recurring_occurrence(
            occurrence_id, request.user
        )
    except PermissionDenied:
        return JsonResponse(
            {'status': 'error', 'message': 'Cette occurrence ne vous appartient pas.'},
            status=403,
        )
    if error:
        code = 404 if occurrence is None else 400
        return JsonResponse({'status': 'error', 'message': error}, status=code)

    return JsonResponse({
        'status': 'success',
        'occurrence': serialize_occurrence(occurrence),
        'consultation_id': consultation.pk if consultation else None,
    })


@login_required
@require_POST
def skip_recurring_occurrence_api(request, occurrence_id):
    try:
        occurrence, error = skip_occurrence(occurrence_id, request.user)
    except PermissionDenied:
        return JsonResponse(
            {'status': 'error', 'message': 'Cette occurrence ne vous appartient pas.'},
            status=403,
        )
    if error:
        code = 404 if occurrence is None else 400
        return JsonResponse({'status': 'error', 'message': error}, status=code)
    return JsonResponse({'status': 'success', 'occurrence': serialize_occurrence(occurrence)})


@login_required
@require_POST
def request_recurring_change_api(request, session_id):
    """Patient sends a reschedule note/request for a proposed series."""
    if request.user.user_type != 'patient':
        return JsonResponse(
            {'status': 'error', 'message': 'Seul le patient peut demander un changement.'},
            status=403,
        )

    try:
        payload = json.loads(request.body or '{}')
    except (TypeError, ValueError):
        return JsonResponse(
            {'status': 'error', 'message': 'Corps JSON invalide.'}, status=400
        )

    note = (payload.get('note') or '').strip()
    if not note:
        return JsonResponse(
            {'status': 'error', 'message': 'Veuillez saisir un message.'}, status=400
        )

    try:
        session, error = request_reschedule(session_id, request.user, note)
    except PermissionDenied:
        return JsonResponse(
            {'status': 'error', 'message': 'Cette série ne vous appartient pas.'},
            status=403,
        )
    if error:
        code = 404 if session is None else 400
        return JsonResponse({'status': 'error', 'message': error}, status=code)

    return JsonResponse({
        'status': 'success',
        'session': serialize_session(session),
    })


@login_required
@require_POST
def accept_recurring_session_api(request, session_id):
    """Patient accepts a whole PROPOSED series: first occurrence is accepted
    (status flips to ACTIVE and every remaining occurrence is materialized as
    a CONFIRMED consultation / booked slot)."""
    if request.user.user_type != 'patient':
        return JsonResponse(
            {'status': 'error', 'message': 'Seul le patient peut accepter.'},
            status=403,
        )

    session = RecurringSession.objects.filter(pk=session_id).first()
    if session is None:
        return JsonResponse(
            {'status': 'error', 'message': 'Série introuvable.'}, status=404
        )
    if session.patient_id != request.user.pk:
        return JsonResponse(
            {'status': 'error', 'message': "Cette série ne vous appartient pas."},
            status=403,
        )

    first_occurrence = (
        RecurringOccurrence.objects.filter(
            recurring_session=session,
            is_cancelled=False,
            consultation__isnull=True,
            occurrence_date__gte=timezone.localdate(),
        )
        .order_by('occurrence_date')
        .first()
    )
    if first_occurrence is None:
        return JsonResponse(
            {
                'status': 'error',
                'message':
                    'Aucune séance à venir : cette série doit être replanifiée.',
            },
            status=400,
        )

    try:
        _occurrence, _consultation, error = accept_recurring_occurrence(
            first_occurrence.pk, request.user
        )
    except PermissionDenied:
        return JsonResponse(
            {'status': 'error', 'message': "Cette série ne vous appartient pas."},
            status=403,
        )
    if error:
        return JsonResponse({'status': 'error', 'message': error}, status=400)

    session.refresh_from_db()
    return JsonResponse({
        'status': 'success',
        'session': serialize_session(session),
    })


@login_required
@require_POST
def decline_recurring_session_api(request, session_id):
    """Patient declines/cancels a PROPOSED series."""
    if request.user.user_type != 'patient':
        return JsonResponse(
            {'status': 'error', 'message': 'Seul le patient peut refuser.'},
            status=403,
        )
    try:
        session, error = decline_series(session_id, request.user)
    except PermissionDenied:
        return JsonResponse(
            {'status': 'error', 'message': "Cette série ne vous appartient pas."},
            status=403,
        )
    if error:
        code = 404 if session is None else 400
        return JsonResponse({'status': 'error', 'message': error}, status=code)
    return JsonResponse({'status': 'success', 'session': serialize_session(session)})