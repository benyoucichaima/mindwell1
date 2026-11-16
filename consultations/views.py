from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from datetime import date, datetime, timedelta
import calendar as _calendar
import json
from collections import defaultdict
from django.conf import settings
from django.db import models
from django.db.models import Q

from accounts.models import CustomUser, PsychologueProfile
from ai_service.models import SessionSummary
from ai_service.services import generate_session_summary

from .access import (
    complete_if_expired,
    consultation_has_ended,
    consultation_time_bounds,
    has_paid_confirmed_room_access,
    has_room_time_access,
)
from .models import (
    Consultation,
    Creneau,
    AvailabilityException,
    WeeklyAvailabilityRule,
    Document,
    Message,
    PaymentRecord,
    RecurringSession,
)
from .forms import AvailabilityExceptionForm, WeeklyAvailabilityRuleForm
from .scheduling import (
    ACTIVE_CONSULTATION_STATUSES,
    GENERATION_HORIZON_DAYS,
    active_consultation_overlaps,
    effective_work_periods,
    generate_slots,
    intervals_overlap,
    period_validation_error,
    slot_matches_current_schedule,
    visible_patient_slots,
)



from django.utils.translation import activate

# ============================================================================
# 1.1 Calendrier du médecin : vue mois + vue jour
# ============================================================================
WEEKDAY_LABELS = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']


def _day_state(psychologue, day, slots, is_past):
    """Compute the state of a calendar day: closed / exception / open / full.

    Today distinguishes:
      - 'closed'   : fermeture ou aucun planning ce jour            -> "Fermé"
      - 'finished' : planning existait mais tous les créneaux sont passés -> "Terminé"
      - 'no_more'  : planning existait, aucun créneau bookable futur -> "Plus de créneaux aujourd'hui"
      - 'open' / 'full' : créneaux disponibles                      -> "Ouvert (n)" / "Complet"
    """
    today = timezone.localdate()
    now = timezone.now()
    tz = timezone.get_current_timezone()
    exceptions = list(AvailabilityException.objects.filter(
        psychologue=psychologue, date=day, is_active=True,
    ))
    closed = any(e.kind == AvailabilityException.Kind.CLOSED for e in exceptions)
    if closed:
        return 'closed', exceptions
    kinds = {e.kind for e in exceptions}
    if 'replacement' in kinds or 'additional' in kinds:
        state = 'exception'
    elif slots:
        state = 'open'
    elif effective_work_periods(psychologue, day):
        state = 'open'
    else:
        state = 'closed'
    if state == 'open' and slots and all(
        slot.statut != Creneau.Statut.LIBRE or not slot.is_bookable for slot in slots
    ):
        state = 'full'

    if day == today and state in ('open', 'full') and slots:
        future_bookable = False
        all_past = True
        for slot in slots:
            slot_start = timezone.make_aware(
                datetime.combine(slot.date, slot.heure_debut), tz,
            )
            if slot_start > now:
                all_past = False
                if slot.statut == Creneau.Statut.LIBRE and slot.is_bookable:
                    future_bookable = True
        if all_past:
            state = 'finished'
        elif not future_bookable:
            state = 'no_more'

    if is_past:
        state = f'{state}-past'
    return state, exceptions


@login_required
def availability_calendar(request):
    lang = request.GET.get('lang') or request.POST.get('lang')
    if lang in ['fr', 'ar', 'en']:
        activate(lang)
        request.LANGUAGE_CODE = lang
    if request.user.user_type != 'psychologue':
        return redirect('home')

    today = timezone.localdate()
    now = timezone.now()

    # ---- Day view (POST actions land here too) -------------------------
    if request.method == 'POST':
        action = request.POST.get('action', '')
        date_str = request.POST.get('date') or ''
        try:
            day = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, 'Date invalide.')
            return redirect('consultations:availability_calendar')
        if day < today:
            messages.error(request, 'Les jours passés sont en lecture seule.')
            return redirect('consultations:availability_calendar')

        if action == 'close_day':
            if AvailabilityException.objects.filter(
                psychologue=request.user, date=day, is_active=True,
                kind=AvailabilityException.Kind.CLOSED,
            ).exists():
                messages.info(request, 'Cette journée est déjà fermée.')
            else:
                AvailabilityException.objects.create(
                    psychologue=request.user, date=day,
                    kind=AvailabilityException.Kind.CLOSED,
                )
                result = generate_slots(request.user, start_date=day)
                messages.success(request, 'La journée a été fermée.')
                for warning in result['warnings']:
                    messages.warning(request, warning)
        elif action in ('add_exception', 'add_replacement'):
            kind = (
                AvailabilityException.Kind.REPLACEMENT
                if action == 'add_replacement'
                else request.POST.get('kind') or AvailabilityException.Kind.ADDITIONAL
            )
            try:
                
                start_time = datetime.strptime(request.POST.get('start_time') or '', '%H:%M').time()
                end_time = datetime.strptime(request.POST.get('end_time') or '', '%H:%M').time()
            except ValueError:
                messages.error(request, 'Heures invalides.')
                return redirect('consultations:availability_calendar')
            error = None
            if end_time <= start_time:
                error = 'L’heure de fin doit suivre l’heure de début.'
            elif day == today and timezone.make_aware(
                datetime.combine(day, start_time), timezone.get_current_timezone(),
            ) <= now:
                error = 'Pour aujourd’hui, seuls les horaires futurs sont acceptés.'
            else:
                error = period_validation_error(
                    request.user, day, kind, start_time, end_time,
                )
            if error:
                messages.error(request, error)
            else:
                AvailabilityException.objects.create(
                    psychologue=request.user, date=day, kind=kind,
                    start_time=start_time, end_time=end_time,
                )
                result = generate_slots(request.user, start_date=day)
                messages.success(request, 'L’exception a été enregistrée et les créneaux du jour régénérés.')
                for warning in result['warnings']:
                    messages.warning(request, warning)
        return redirect(
            f'{reverse("consultations:availability_calendar")}?day={day.isoformat()}'
        )

    # ---- Month view ----------------------------------------------------
    year = int(request.GET.get('year') or today.year)
    month = int(request.GET.get('month') or today.month)
    try:
        month_first = date(year, month, 1)
    except ValueError:
        messages.error(request, 'Mois invalide.')
        return redirect('consultations:availability_calendar')
    _, days_in_month = _calendar.monthrange(year, month)
    month_last = date(year, month, days_in_month)

    month_slots = list(Creneau.objects.filter(
        psychologue=request.user, date__range=(month_first, month_last),
    ).order_by('date', 'heure_debut'))
    slots_by_date = {}
    for slot in month_slots:
        slots_by_date.setdefault(slot.date, []).append(slot)

    leading_blanks = month_first.weekday()  # Monday=0 grid
    calendar_days = []
    for _ in range(leading_blanks):
        calendar_days.append(None)
    for day_number in range(1, days_in_month + 1):
        day = date(year, month, day_number)
        slots = slots_by_date.get(day, [])
        is_past = day < today
        state, _exceptions = _day_state(request.user, day, slots, is_past)
        calendar_days.append({
            'date': day,
            'is_today': day == today,
            'is_past': is_past,
            'read_only': is_past,
            'state': state,
            'slot_count': len(slots),
        })

    prev_month = (month_first - timedelta(days=1))
    next_month = (month_last + timedelta(days=1))
    month_name = f'{month_first:%B %Y}'

    # ---- Day view (selected day) ---------------------------------------
    day_str = request.GET.get('day')
    selected_day = None
    day_slots = []
    day_state = None
    day_exceptions = []
    if day_str:
        try:
            selected_day = datetime.strptime(day_str, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, 'Date invalide.')
        if selected_day:
            day_slots = list(Creneau.objects.filter(
                psychologue=request.user, date=selected_day,
            ).order_by('heure_debut'))
            is_past = selected_day < today
            day_state, day_exceptions = _day_state(
                request.user, selected_day, day_slots, is_past,
            )
            for slot in day_slots:
                slot_start = timezone.make_aware(
                    datetime.combine(slot.date, slot.heure_debut),
                    timezone.get_current_timezone(),
                )
                if slot.statut == Creneau.Statut.RESERVE or (
                    slot.is_bookable and slot.statut != Creneau.Statut.BLOQUE
                    and slot.consultations.filter(
                        status__in=ACTIVE_CONSULTATION_STATUSES,
                    ).exists()
                ):
                    slot.display_state = 'reserved'
                elif not slot.is_bookable or slot.statut == Creneau.Statut.BLOQUE:
                    slot.display_state = 'disabled'
                elif slot_start <= now:
                    slot.display_state = 'past'
                else:
                    slot.display_state = 'free'

    # Status message: how many slots are visible to patients today.
    visibility = visible_patient_slots(request.user.pk)
    if visibility['closed']:
        status_message = 'Aucun créneau visible pour les patients aujourd’hui : fermeture.'
    elif not visibility['visible']:
        hidden = visibility['hidden']
        reasons = []
        if hidden['past']:
            reasons.append(f"{hidden['past']} passé(s)")
        if hidden['reserved']:
            reasons.append(f"{hidden['reserved']} réservé(s)")
        if hidden['not_bookable']:
            reasons.append(f"{hidden['not_bookable']} retiré(s)")
        detail = f' ({" ; ".join(reasons)})' if reasons else ''
        status_message = (
            f'Aucun créneau visible pour les patients aujourd’hui{detail} : '
            f'vérifiez la génération et le planning hebdomadaire.'
        )
    else:
        status_message = (
            f"{len(visibility['visible'])} créneau(x) visible(s) pour les patients aujourd’hui."
        )

    return render(request, 'consultations/availability_calendar.html', {
        'calendar_days': calendar_days,
        'leading_blanks': range(leading_blanks),
        'weekday_labels': WEEKDAY_LABELS,
        'month_name': month_name,
        'year': year,
        'month': month,
        'prev_year': prev_month.year, 'prev_month': prev_month.month,
        'next_year': next_month.year, 'next_month': next_month.month,
        'today': today,
        'selected_day': selected_day,
        'day_slots': day_slots,
        'day_state': day_state,
        'day_exceptions': day_exceptions,
        'status_message': status_message,
        'duration_choices': PsychologueProfile.SESSION_DURATION_CHOICES,
        'current_duration': getattr(request.user, 'psychologue_profile', None)
        and request.user.psychologue_profile.session_duration or None,
        'kind_choices': AvailabilityException.Kind.choices,
        'now_time': timezone.localtime(now).strftime('%H:%M'),
    })


@login_required
def manage_availability(request):
    lang = request.GET.get('lang') or request.POST.get('lang')
    if lang in ['fr', 'ar', 'en']:
        activate(lang)
        request.LANGUAGE_CODE = lang
    if request.user.user_type != 'psychologue':
        return redirect('home')
    profile = getattr(request.user, 'psychologue_profile', None)
    if profile is None or not profile.is_verified:
        messages.error(request, 'Votre profil doit être vérifié avant de publier vos disponibilités.')
        return redirect('consultations:upload_document')
    
    if request.method == 'POST':
        action = request.POST.get('action', 'manual_slot')
        if action in ('add_weekly', 'update_weekly'):
            rule = None
            if action == 'update_weekly':
                rule = get_object_or_404(
                    WeeklyAvailabilityRule,
                    pk=request.POST.get('rule_id'),
                    psychologue=request.user,
                )
            form = WeeklyAvailabilityRuleForm(
                request.POST,
                instance=rule,
                profile=profile,
            )
            if form.is_valid():
                candidate = form.save(commit=False)
                conflicts = WeeklyAvailabilityRule.objects.filter(
                    psychologue=request.user,
                    weekday=candidate.weekday,
                    start_time__lt=candidate.end_time,
                    end_time__gt=candidate.start_time,
                )
                if rule:
                    conflicts = conflicts.exclude(pk=rule.pk)
                has_conflict = conflicts.filter(start_time=candidate.start_time).exists()
                has_conflict = has_conflict or (
                    candidate.is_active and conflicts.filter(is_active=True).exists()
                )
                if has_conflict:
                    messages.error(request, 'Cette règle chevauche une autre période hebdomadaire active.')
                else:
                    candidate.psychologue = request.user
                    candidate.save()
                    profile.session_duration = form.cleaned_data['session_duration']
                    profile.save(update_fields=['session_duration'])
                    result = generate_slots(request.user)
                    messages.success(request, 'La règle hebdomadaire a été enregistrée.')
                    for warning in result['warnings']:
                        messages.warning(request, warning)
            else:
                messages.error(request, 'Règle invalide : ' + ' '.join(
                    str(error) for error in form.errors.values()
                ))
        elif action == 'disable_weekly':
            rule = get_object_or_404(
                WeeklyAvailabilityRule,
                pk=request.POST.get('rule_id'),
                psychologue=request.user,
            )
            rule.is_active = False
            rule.save(update_fields=['is_active', 'updated_at'])
            result = generate_slots(request.user)
            messages.success(request, 'La règle hebdomadaire a été désactivée.')
            for warning in result['warnings']:
                messages.warning(request, warning)
        elif action == 'add_exception':
            form = AvailabilityExceptionForm(request.POST)
            if form.is_valid():
                candidate = form.save(commit=False)
                error = None
                if candidate.date < timezone.localdate():
                    error = 'La date de l’exception ne peut pas être passée.'
                elif (
                    candidate.date == timezone.localdate()
                    and candidate.start_time
                    and timezone.make_aware(
                        datetime.combine(candidate.date, candidate.start_time),
                        timezone.get_current_timezone(),
                    ) <= timezone.now()
                ):
                    error = "Pour aujourd'hui, l'heure de début doit être dans le futur."
                else:
                    error = period_validation_error(
                        request.user,
                        candidate.date,
                        candidate.kind,
                        candidate.start_time,
                        candidate.end_time,
                    )
                if error:
                    messages.error(request, error)
                else:
                    candidate.psychologue = request.user
                    candidate.save()
                    result = generate_slots(request.user)
                    messages.success(request, 'L’exception a été enregistrée.')
                    for warning in result['warnings']:
                        messages.warning(request, warning)
            else:
                messages.error(request, 'Exception invalide : ' + ' '.join(
                    str(error) for error in form.errors.values()
                ))
        elif action == 'disable_exception':
            exception = get_object_or_404(
                AvailabilityException,
                pk=request.POST.get('exception_id'),
                psychologue=request.user,
            )
            exception.is_active = False
            exception.save(update_fields=['is_active'])
            result = generate_slots(request.user)
            messages.success(request, 'L’exception a été désactivée.')
            for warning in result['warnings']:
                messages.warning(request, warning)
        elif action == 'delete_weekly':
            rule = get_object_or_404(
                WeeklyAvailabilityRule,
                pk=request.POST.get('rule_id'),
                psychologue=request.user,
            )
            rule.delete()
            result = generate_slots(request.user)
            messages.success(request, 'La règle hebdomadaire a été supprimée.')
            for warning in result['warnings']:
                messages.warning(request, warning)
        elif action == 'delete_exception':
            exception = get_object_or_404(
                AvailabilityException,
                pk=request.POST.get('exception_id'),
                psychologue=request.user,
            )
            exception.delete()
            result = generate_slots(request.user)
            messages.success(request, 'L’exception a été supprimée.')
            for warning in result['warnings']:
                messages.warning(request, warning)
        elif action == 'generate':
            result = generate_slots(request.user)
            messages.success(request, f"{result['created']} nouveau(x) créneau(x) généré(s) sur 28 jours.")
            for warning in result['warnings']:
                messages.warning(request, warning)
        else:
            date_str = request.POST.get('date')
            heure_debut = request.POST.get('heure_debut')
            heure_fin = request.POST.get('heure_fin')
            try:
                date_obj = datetime.strptime(date_str or '', '%Y-%m-%d').date()
                start_time = datetime.strptime(heure_debut or '', '%H:%M').time()
                end_time = datetime.strptime(heure_fin or '', '%H:%M').time()
            except ValueError:
                messages.error(request, 'Veuillez saisir une date et des horaires valides.')
            else:
                if date_obj < timezone.localdate() or end_time <= start_time:
                    messages.error(request, 'Choisissez une date actuelle ou future et une heure de fin après le début.')
                elif timezone.make_aware(
                    datetime.combine(date_obj, start_time), timezone.get_current_timezone()
                ) <= timezone.now():
                    messages.error(request, "Pour aujourd'hui, l'heure de début doit être dans le futur.")
                elif Creneau.objects.filter(
                    psychologue=request.user,
                    date=date_obj,
                    heure_debut__lt=end_time,
                    heure_fin__gt=start_time,
                ).exists() or active_consultation_overlaps(
                    request.user, date_obj, start_time, end_time
                ):
                    messages.error(request, 'Ce créneau chevauche une disponibilité ou un rendez-vous existant.')
                else:
                    Creneau.objects.create(
                        psychologue=request.user,
                        date=date_obj,
                        heure_debut=start_time,
                        heure_fin=end_time,
                        statut=Creneau.Statut.LIBRE,
                        is_generated=False,
                        is_bookable=True,
                    )
                    messages.success(request, 'Votre créneau manuel a été ajouté.')
        return redirect('consultations:manage_availability')

    creneaux = Creneau.objects.filter(
        psychologue=request.user,
        date__gte=timezone.localdate(),
    ).order_by('date', 'heure_debut')

    # Group upcoming slots by date so the template can render a collapsible
    # accordion (one section per day) instead of a single flat table.
    creneaux_grouped = defaultdict(list)
    for creneau in creneaux:
        creneaux_grouped[creneau.date].append(creneau)

    patients = CustomUser.objects.filter(
        user_type='patient',
        is_active=True,
    ).order_by('first_name', 'last_name', 'username')[:500]
    return render(request, 'consultations/manage_availability.html', {
        'creneaux_grouped': dict(creneaux_grouped),
        'patients': patients,
        'weekly_rules': WeeklyAvailabilityRule.objects.filter(psychologue=request.user),
        'exceptions': AvailabilityException.objects.filter(psychologue=request.user, is_active=True),
        'weekly_form': WeeklyAvailabilityRuleForm(profile=profile),
        'exception_form': AvailabilityExceptionForm(),
        'duration_choices': PsychologueProfile.SESSION_DURATION_CHOICES,
        'weekday_choices': WeeklyAvailabilityRule.WEEKDAY_CHOICES,
        'recurring_sessions': RecurringSession.objects.filter(
            psychologue=request.user,
        ).select_related('patient').order_by('-created_at')[:50],
    })


# ============================================================================
# 2. رفع الوثائق الثبوتية (للأخصائي النفسي فقط)
# ============================================================================
@login_required
def upload_document(request):
    if request.user.user_type != 'psychologue':
        return redirect('home')
    
    if request.method == 'POST':
        type_document = request.POST.get('type_document')
        fichier = request.FILES.get('fichier')
        
        valid_types = dict(Document.TypeDocument.choices)
        if type_document in valid_types and fichier:
            Document.objects.create(
                psychologue=request.user,
                type_document=type_document,
                fichier=fichier
            )
            messages.success(request, 'Votre document a été envoyé pour validation.')
        else:
            messages.error(request, 'Choisissez un type de document valide et ajoutez un fichier.')
    
    documents = Document.objects.filter(psychologue=request.user).order_by('-date_depot')
    return render(request, 'consultations/upload_document.html', {
        'documents': documents,
        'document_types': Document.TypeDocument.choices,
    })


# ============================================================================
# 3. غرفة الدردشة الخاصة بالجلسة (Chat Room)
# ============================================================================
@login_required
def consultation_chat(request, consultation_id):
    if request.user.user_type not in ('patient', 'psychologue'):
        raise PermissionDenied

    participant_filter = (
        models.Q(patient=request.user)
        if request.user.user_type == 'patient'
        else models.Q(psychologue=request.user)
    )
    consultation = get_object_or_404(
        Consultation.objects.filter(participant_filter).select_related('patient', 'psychologue'),
        id=consultation_id,
    )
    now = timezone.now()
    if consultation_has_ended(consultation, now):
        complete_if_expired(consultation, now)
        messages.info(request, "انتهت مدة هذه الجلسة ولا يمكن الدخول إليها.")
        dashboard = (
            'accounts:psychologue_dashboard'
            if request.user.user_type == 'psychologue'
            else 'accounts:patient_dashboard'
        )
        return redirect(dashboard)

    if consultation.status not in (
        Consultation.Status.CONFIRMED,
        Consultation.Status.IN_PROGRESS,
    ):
        raise PermissionDenied('Cette consultation ne permet pas l’accès à la salle.')
    if not has_room_time_access(consultation, now):
        messages.warning(request, "لا يمكن الدخول إلى الجلسة قبل موعدها المحدد.")
        dashboard = (
            'accounts:psychologue_dashboard'
            if request.user.user_type == 'psychologue'
            else 'accounts:patient_dashboard'
        )
        return redirect(dashboard)
    if consultation.payment_status != Consultation.PaymentStatus.PAID:
        raise PermissionDenied('Le paiement simulé est requis pour accéder à la salle.')
    try:
        payment = consultation.payment_record
    except PaymentRecord.DoesNotExist:
        raise PermissionDenied('Aucun paiement valide n’est enregistré pour cette consultation.')
    if payment.status != 'success' or payment.amount != consultation.price:
        raise PermissionDenied('Le paiement enregistré ne correspond pas à cette consultation.')

    if consultation.status == Consultation.Status.CONFIRMED:
        consultation.status = Consultation.Status.IN_PROGRESS
        consultation.save(update_fields=['status', 'updated_at'])
    
    if request.method == 'POST':
        contenu = request.POST.get('contenu', '').strip()
        fichier = request.FILES.get('fichier')
        
        if contenu or fichier:
            Message.objects.create(
                consultation=consultation,
                expediteur=request.user,
                contenu=contenu,
                fichier=fichier,
                type_message='fichier' if fichier else 'texte'
            )
        return redirect('consultations:consultation_chat', consultation_id=consultation.id)
    
    latest_summary = (
        SessionSummary.objects.filter(consultation=consultation).first()
        if request.user.user_type == 'psychologue'
        else None
    )
    return render(request, 'consultations/chat_room.html', {
        'consultation': consultation,
        'session_end_iso': timezone.localtime(
            consultation_time_bounds(consultation)[1]
        ).isoformat(timespec='seconds'),
        'server_now_iso': timezone.localtime(now).isoformat(timespec='seconds'),
        'messages': consultation.messages.all().order_by('date_envoi'),
        'is_psychologue': request.user.user_type == 'psychologue',
        'ai_summary': latest_summary,
        'doctor_only_ai_summary': (
            consultation.doctor_only_ai_summary
            if request.user.user_type == 'psychologue'
            else None
        ),
        'webrtc_ice_servers': settings.WEBRTC_ICE_SERVERS,
    })


@login_required
@require_POST
def update_audio_transcription_consent(request, consultation_id):
    if request.user.user_type != 'patient':
        return JsonResponse({'status': 'error', 'message': 'غير مصرح'}, status=403)

    consultation = get_object_or_404(
        Consultation,
        pk=consultation_id,
        patient=request.user,
    )
    if not has_paid_confirmed_room_access(consultation):
        return JsonResponse(
            {'status': 'error', 'message': 'La consultation doit être confirmée et payée.'},
            status=403,
        )

    consent_value = request.POST.get('consent')
    if consent_value not in {'true', 'false'}:
        return JsonResponse(
            {'status': 'error', 'message': 'Consentement invalide.'},
            status=400,
        )

    consultation.audio_transcription_consent = consent_value == 'true'
    consultation.audio_transcription_consent_at = (
        timezone.now() if consultation.audio_transcription_consent else None
    )
    consultation.save(
        update_fields=[
            'audio_transcription_consent',
            'audio_transcription_consent_at',
            'updated_at',
        ]
    )
    return JsonResponse({
        'status': 'success',
        'consent': consultation.audio_transcription_consent,
    })


# ============================================================================
# 4. الذكاء الاصطناعي: طلب تحليل الجلسة (AI Analysis)
# ============================================================================
@login_required
@require_POST
def request_ai_analysis(request, consultation_id):
    if request.user.user_type != 'psychologue':
        return JsonResponse({'status': 'error', 'message': 'غير مصرح'}, status=403)
    
    consultation = get_object_or_404(
        Consultation.objects.select_related('payment_record'),
        id=consultation_id,
    )
    if consultation.psychologue != request.user:
        return JsonResponse({'status': 'error', 'message': 'غير مصرح'}, status=403)
    if not has_paid_confirmed_room_access(consultation):
        return JsonResponse(
            {'status': 'error', 'message': 'La consultation doit être confirmée et payée.'},
            status=403,
        )

    try:
        raw_body = request.body
    except Exception:
        raw_body = b''
    custom_text = request.POST.get('custom_text') or request.POST.get('notes_text')
    if not custom_text and raw_body:
        try:
            payload = json.loads(raw_body or b'{}')
        except (ValueError, TypeError):
            payload = None
        if isinstance(payload, dict):
            custom_text = payload.get('custom_text') or payload.get('notes_text')
    custom_text = (custom_text or '').strip() or None

    result = generate_session_summary(consultation.pk, custom_text=custom_text)
    if not result.get('success'):
        if result.get('reason') == 'no_input':
            return JsonResponse(
                {'status': 'no_input', 'message': result.get('error')},
                status=200,
            )
        return JsonResponse(
            {'status': 'error', 'message': result.get('error', 'Le résumé IA est indisponible.')},
            status=503,
        )

    data = result['data']
    consultation.ai_summary = data['summary']
    consultation.save(update_fields=['ai_summary', 'updated_at'])
    return JsonResponse({
        'status': 'success',
        'summary': data['summary'],
        'emotions': data.get('emotions', []),
        'themes': data['themes'],
        'risk_level': data['risk_level'],
        'requires_professional_review': True,
    })


# ============================================================================
# 5. API: الحصول على الفترات المتاحة (AJAX)
# ============================================================================
@login_required
def get_available_slots(request, psychologue_id, date_str):
    if request.user.user_type != 'patient':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    horizon_end = timezone.localdate() + timedelta(days=28)
    creneaux = Creneau.objects.filter(
        psychologue_id=psychologue_id,
        psychologue__user_type='psychologue',
        psychologue__is_active=True,
        psychologue__psychologue_profile__is_verified=True,
        date=date_obj,
        statut=Creneau.Statut.LIBRE,
        is_bookable=True,
    ).filter(Q(is_generated=False) | Q(date__lt=horizon_end))
    now = timezone.now()
    candidates = list(creneaux)
    date_slots = list(
        Creneau.objects.filter(psychologue_id=psychologue_id, date=date_obj)
    )
    slots = []
    for creneau in candidates:
        start = timezone.make_aware(
            datetime.combine(date_obj, creneau.heure_debut),
            timezone.get_current_timezone(),
        )
        if start <= now:
            continue
        if not slot_matches_current_schedule(creneau.psychologue, creneau):
            continue
        if active_consultation_overlaps(
            creneau.psychologue,
            date_obj,
            creneau.heure_debut,
            creneau.heure_fin,
        ):
            continue
        if any(
            other.pk != creneau.pk
            and other.is_bookable
            and other.statut != Creneau.Statut.BLOQUE
            and intervals_overlap(
                creneau.heure_debut,
                creneau.heure_fin,
                other.heure_debut,
                other.heure_fin,
            )
            for other in date_slots
        ):
            continue
        slots.append({
            'id': creneau.id,
            'heure_debut': creneau.heure_debut.strftime('%H:%M'),
            'heure_fin': creneau.heure_fin.strftime('%H:%M'),
        })
    
    return JsonResponse({'slots': slots})