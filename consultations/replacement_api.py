"""JSON API for compensatory ("rattrapage") sessions."""

import json
import logging
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from .replacement_service import (
    decline_replacement,
    owed_replacements_for_patient,
    pending_change_requests_for_psychologue,
    respond_to_change_request,
    serialize_change_request,
    serialize_replacement,
    submit_change_request,
)

logger = logging.getLogger(__name__)


def _parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _json_body(request):
    try:
        return json.loads(request.body or '{}')
    except (TypeError, ValueError):
        return {}


@login_required
@require_GET
def upcoming_replacements_api(request):
    """List the replacement sessions owed to the logged-in patient."""
    if request.user.user_type != 'patient':
        return JsonResponse(
            {'status': 'error', 'message': 'Non autorisé.'}, status=403
        )
    replacements = owed_replacements_for_patient(request.user)
    payload = [serialize_replacement(c) for c in replacements]
    logger.debug(
        "upcoming replacements for patient %s: %s",
        request.user.pk,
        len(payload),
    )
    return JsonResponse({
        'status': 'success',
        'replacements': payload,
    })


@login_required
@require_POST
def decline_replacement_api(request, consultation_id):
    """Patient declines an owed replacement session."""
    if request.user.user_type != 'patient':
        return JsonResponse(
            {'status': 'error', 'message': 'Non autorisé.'}, status=403
        )
    try:
        consultation, error = decline_replacement(
            consultation_id, request.user
        )
    except PermissionDenied:
        return JsonResponse(
            {'status': 'error', 'message': "Cette séance ne vous appartient pas."},
            status=403,
        )
    if error:
        code = 404 if consultation is None else 400
        return JsonResponse({'status': 'error', 'message': error}, status=code)
    return JsonResponse({
        'status': 'success',
        'id': str(consultation.pk),
    })


@login_required
@require_POST
def submit_change_request_api(request, replacement_id):
    """Patient submits a time-change request for an owed replacement session."""
    if request.user.user_type != 'patient':
        return JsonResponse(
            {'status': 'error', 'message': 'Non autorisé.'}, status=403
        )
    data = _json_body(request)
    try:
        change_request, error = submit_change_request(
            replacement_id,
            request.user,
            data.get('message', ''),
            _parse_datetime(data.get('proposed_date')),
        )
    except PermissionDenied:
        return JsonResponse(
            {'status': 'error', 'message': "Cette séance ne vous appartient pas."},
            status=403,
        )
    if error:
        not_found = (
            change_request is None and error == "Cette séance est introuvable."
        )
        code = 404 if not_found else 400
        return JsonResponse({'status': 'error', 'message': error}, status=code)
    return JsonResponse({
        'status': 'success',
        'request_id': change_request.pk,
        'message': 'Demande envoyée au psychologue.',
    })


@login_required
@require_GET
def get_change_requests_api(request):
    """Psychologist lists pending change requests."""
    if request.user.user_type != 'psychologue':
        return JsonResponse(
            {'status': 'error', 'message': 'Non autorisé.'}, status=403
        )
    requests = pending_change_requests_for_psychologue(request.user)
    return JsonResponse({
        'status': 'success',
        'requests': [
            serialize_change_request(change_request)
            for change_request in requests
        ],
    })


@login_required
@require_POST
def respond_to_change_request_api(request, request_id):
    """Psychologist accepts, rejects, or counter-proposes a change request."""
    if request.user.user_type != 'psychologue':
        return JsonResponse(
            {'status': 'error', 'message': 'Non autorisé.'}, status=403
        )
    data = _json_body(request)
    try:
        change_request, error = respond_to_change_request(
            request_id,
            request.user,
            data.get('action'),
            data.get('response', ''),
            _parse_datetime(data.get('new_date')),
        )
    except PermissionDenied:
        return JsonResponse(
            {'status': 'error', 'message': 'Cette demande ne vous concerne pas.'},
            status=403,
        )
    if error:
        code = 404 if change_request is None else 400
        return JsonResponse({'status': 'error', 'message': error}, status=code)
    return JsonResponse({'status': 'success'})