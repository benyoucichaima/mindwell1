import uuid
import logging
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.translation import gettext
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.db import models, transaction, OperationalError
from django.db.models import Q, Avg, Count
from django.db import IntegrityError
from django.core.exceptions import ValidationError
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_GET, require_POST
from django.core.exceptions import PermissionDenied
from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from functools import wraps
ACTIVE_CONSULTATION_STATUSES = [
    'pending',
    'confirmed',
    'in_progress',
]


logger = logging.getLogger(__name__)

# ✅ استيراد النماذج الصحيحة فقط (تم حذف Appointment نهائياً)
from .models import (
    CustomUser, PatientProfile, PsychologueProfile,
    Conversation, Message, Call, ClinicalRecord, Notification, ConsultationNote
)
from .notifications import notify_user
from . import notes_service
from consultations.models import Consultation, DoctorRating, Creneau, PaymentRecord, Document, AvailabilityException
from consultations.access import (
    complete_expired_consultations,
    has_paid_confirmed_room_access,
)
from consultations.scheduling import (
    GENERATION_HORIZON_DAYS,
    active_consultation_overlaps,
    generate_slots,
    overlapping_slots,
    slot_matches_current_schedule,
)
from consultations.recurring_service import materialize_series_for_consultation
from ai_service.models import MessageAnalysis
from .forms import (
    DoctorRatingForm,
    DeleteAccountForm,
    UserUpdateForm,
    PatientProfileForm,
    PsychologueProfileForm,
)


def verification_required(view_func):
    """
    Decorator that ensures the logged-in psychologist has been verified by admin.
    Redirects to pending_verification page if not verified.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.user_type == 'psychologue':
            profile = getattr(request.user, 'psychologue_profile', None)
            if profile is None or not profile.is_verified:
                messages.warning(
                    request,
                    "Votre compte est en attente de vérification. "
                    "Veuillez soumettre vos documents et attendre l'approbation de l'administrateur."
                )
                return redirect('accounts:pending_verification')
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
@require_POST
def cancel_patient_appointment(request, appointment_id):
    """Cancel a patient's appointment if it has not started."""
    if request.user.user_type != 'patient':
        messages.error(request, gettext("Vous n'êtes pas autorisé à effectuer cette action."))
        return redirect('home')

    # ✅ استخدام Consultation بدلاً من Appointment
    consultation = get_object_or_404(Consultation, id=appointment_id, patient=request.user)

    if consultation.status in [Consultation.Status.CANCELLED, Consultation.Status.COMPLETED]:
        messages.warning(
            request,
            gettext("Ce rendez-vous est déjà terminé ou annulé et ne peut pas être annulé."),
        )
        return redirect('accounts:rendez_vous')

    if not consultation.can_be_cancelled():
        messages.error(
            request,
            gettext("Un rendez-vous ne peut pas être annulé après le début de la séance."),
        )
    else:
        # ✅ استخدام دالة الإلغاء الرسمية لتسجيل السبب والتاريخ
        consultation.cancel(
            cancelled_by=request.user,
            reason=Consultation.CancellationReason.PATIENT,
            details='Cancelled by patient via dashboard'
        )
        # تحرير الفترة الزمنية إذا وجدت
        if consultation.creneau:
            consultation.creneau.liberer()
            if consultation.creneau.is_generated:
                result = generate_slots(consultation.psychologue)
                for warning in result['warnings']:
                    messages.warning(request, warning)
            
        messages.success(
            request,
            gettext("Le rendez-vous a été annulé. Nous vous souhaitons une bonne journée."),
        )

    return redirect('accounts:rendez_vous')


@login_required
def ai_panel(request, conversation_id):
    if request.user.user_type != "psychologue":
        raise PermissionDenied
    conv = get_object_or_404(Conversation, id=conversation_id, psychologue=request.user)
    consultation = Consultation.objects.filter(
        patient=conv.patient,
        psychologue=request.user,
        status=Consultation.Status.COMPLETED,
    ).select_related('ai_session_summary').order_by(
        '-date',
        '-start_time',
    ).first()
    return render(request, "chat/_ai_panel.html", {
        "conversation": conv,
        "consultation": consultation,
        "summary": getattr(conv, "ai_summary", None),
        "analyses": MessageAnalysis.objects.filter(message__conversation=conv)
                        .select_related("message").order_by("-id")[:20],
    })


def redirect_by_role(user):
    if user.user_type == 'admin' or user.is_staff:
        return redirect('dashboard')
    if user.user_type == 'psychologue':
        profile = getattr(user, 'psychologue_profile', None)
        if profile is None or not profile.is_verified:
            return redirect('accounts:pending_verification')
        return redirect('accounts:psychologue_dashboard')
    if user.user_type == 'patient':
        return redirect('accounts:patient_dashboard')
    return redirect('home')


def _safe_next_url(request):
    next_url = request.POST.get('next') or request.GET.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return ''


def _booking_specialist_name(next_url):
    if not next_url:
        return None

    try:
        match = resolve(urlsplit(next_url).path)
    except Resolver404:
        return None

    if match.view_name != 'accounts:book_consultation':
        return None

    psychologue = CustomUser.objects.filter(
        pk=match.kwargs.get('psychologue_id'),
        user_type='psychologue',
        is_active=True,
        psychologue_profile__is_verified=True,
    ).first()
    if psychologue is None:
        return None

    return psychologue.get_full_name() or psychologue.username


def _booking_login_message(request, next_url):
    specialist_name = _booking_specialist_name(next_url)
    if specialist_name:
        messages.info(
            request,
            f'Veuillez vous connecter ou créer un compte pour terminer votre '
            f'réservation avec Dr. {specialist_name}.',
        )


# ============================================================
#                     AUTH VIEWS
# ============================================================
@never_cache
def choose_account_type(request):
    if request.user.is_authenticated:
        next_url = _safe_next_url(request)
        if next_url:
            return redirect(next_url)
        return redirect_by_role(request.user)
    return render(request, 'accounts/choose_account_type.html', {
        'next_url': _safe_next_url(request),
    })


@never_cache
def register_patient(request):
    if request.user.is_authenticated:
        next_url = _safe_next_url(request)
        if next_url:
            return redirect(next_url)
        return redirect_by_role(request.user)

    next_url = _safe_next_url(request)

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        phone = request.POST.get('phone', '').strip()
        password1 = request.POST.get('password', '').strip()
        password2 = request.POST.get('password_confirm', '').strip()
        date_of_birth = request.POST.get('date_of_birth') or None

        if password1 != password2:
            messages.error(request, 'كلمات المرور غير متطابقة')
            return render(request, 'accounts/register_patient.html', {'next_url': next_url})

        if len(password1) < 8:
            messages.error(request, 'كلمة المرور يجب أن تكون 8 أحرف على الأقل')
            return render(request, 'accounts/register_patient.html', {'next_url': next_url})

        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, 'هذا الإيميل مستعمل من قبل')
            return render(request, 'accounts/register_patient.html', {'next_url': next_url})

        user = CustomUser.objects.create_user(
            username=email, email=email, password=password1,
            first_name=first_name, last_name=last_name,
            phone=phone, user_type='patient', is_active=True,
            date_of_birth=date_of_birth
        )
        PatientProfile.objects.create(user=user)

        login(request, user)
        messages.success(request, f'مرحباً {first_name}! تم إنشاء حسابك بنجاح')
        return redirect(next_url or 'home')

    return render(request, 'accounts/register_patient.html', {'next_url': next_url})


@never_cache
def register_psychologue(request):
    if request.user.is_authenticated:
        next_url = _safe_next_url(request)
        if next_url:
            return redirect(next_url)
        return redirect_by_role(request.user)

    next_url = _safe_next_url(request)

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        phone = request.POST.get('phone', '').strip()
        password1 = request.POST.get('password', '').strip()
        password2 = request.POST.get('password_confirm', '').strip()
        specialty = request.POST.get('specialites', '').strip()
        experience = request.POST.get('experience', '0').strip()
        license_number = request.POST.get('license_number', '').strip()
        city = request.POST.get('city', '').strip()

        if not password1:
            messages.error(request, 'Veuillez saisir un mot de passe.')
            return render(request, 'accounts/register_psychologue.html', {'next_url': next_url})

        if password1 != password2:
            messages.error(request, 'Les mots de passe ne correspondent pas.')
            return render(request, 'accounts/register_psychologue.html', {'next_url': next_url})

        if len(password1) < 8:
            messages.error(request, 'Le mot de passe doit contenir au moins 8 caractères.')
            return render(request, 'accounts/register_psychologue.html', {'next_url': next_url})

        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, 'Cet email est déjà utilisé.')
            return render(request, 'accounts/register_psychologue.html', {'next_url': next_url})

        user = CustomUser.objects.create_user(
            username=email, email=email, password=password1,
            first_name=first_name, last_name=last_name,
            phone=phone, user_type='psychologue', is_active=True, city=city
        )

        PsychologueProfile.objects.create(
            user=user, registration_number=license_number, city=city, specialty=specialty,
            experience_years=int(experience) if experience.isdigit() else 0,
            is_verified=False,
            diploma_file=request.FILES.get('diploma_file'),
            id_document_file=request.FILES.get('id_document_file'),
            registration_file=(
                request.FILES.get('registration_file')
                or request.FILES.get('professional_document')
            ),
        )

        login(request, user)
        messages.success(request, 'Votre demande a été envoyée. Votre compte sera activé après vérification.')
        return redirect(next_url or 'accounts:psychologue_dashboard')

    return render(request, 'accounts/register_psychologue.html', {'next_url': next_url})


@never_cache
@csrf_protect
def login_view(request):
    next_url = _safe_next_url(request)
    if request.user.is_authenticated:
        if next_url:
            return redirect(next_url)
        return redirect_by_role(request.user)

    _booking_login_message(request, next_url)

    if request.method == 'POST':
        identifier = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        if not identifier or not password:
            messages.error(request, 'يرجى إدخال جميع البيانات المطلوبة.')
            return render(request, 'accounts/login.html', {'next_url': next_url})

        user = None
        if '@' in identifier:
            candidates = CustomUser.objects.filter(email__iexact=identifier)
            for candidate in candidates:
                if candidate.check_password(password):
                    user = candidate
                    break
            if user is None and candidates.exists():
                user = candidates.filter(is_active=True).order_by('-last_login', '-id').first() or candidates.first()

        if user is None:
            candidates = CustomUser.objects.filter(username__iexact=identifier)
            for candidate in candidates:
                if candidate.check_password(password):
                    user = candidate
                    break
            if user is None and candidates.exists():
                user = candidates.filter(is_active=True).order_by('-last_login', '-id').first() or candidates.first()

        if user is not None:
            if user.check_password(password):
                if not user.is_active:
                    messages.error(request, 'حسابك غير مفعل حالياً. يرجى التواصل مع الإدارة.')
                    return render(request, 'accounts/login.html', {'next_url': next_url})
                login(request, user)
                display_name = user.first_name or user.username
                messages.success(request, f'مرحباً بك، {display_name}!')
                if next_url and url_has_allowed_host_and_scheme(
                    next_url,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    return redirect(next_url)
                return redirect_by_role(user)
            else:
                messages.error(request, 'كلمة المرور غير صحيحة.')
        else:
            messages.error(request, 'لا يوجد حساب بهذا الإيميل أو اسم المستخدم.')

    return render(request, 'accounts/login.html', {'next_url': next_url})


@login_required
@csrf_protect
def logout_view(request):
    logout(request)
    return redirect('home')


# ============================================================
#                     DASHBOARDS
# ============================================================
@login_required
def pending_verification(request):
    """Page shown to psychologists awaiting admin verification."""
    if request.user.user_type != 'psychologue':
        return redirect_by_role(request.user)
    profile = getattr(request.user, 'psychologue_profile', None)
    documents = Document.objects.filter(psychologue=request.user).order_by('-date_depot')
    return render(request, 'accounts/pending_verification.html', {
        'profile': profile,
        'documents': documents,
    })


@login_required
def patient_dashboard(request):
    if request.user.user_type != 'patient':
        return redirect_by_role(request.user)

    now = timezone.now()
    today = timezone.localtime(now).date()
    complete_expired_consultations(
        Consultation.objects.filter(patient=request.user),
        now,
    )

    upcoming_sessions = Consultation.objects.filter(
        patient=request.user,
        status__in=[
            Consultation.Status.PENDING,
            Consultation.Status.CONFIRMED,
            Consultation.Status.IN_PROGRESS,
        ],
        date__gte=today
    ).select_related('psychologue').order_by('date', 'start_time')[:5]

    completed_sessions = Consultation.objects.filter(
        patient=request.user,
        status=Consultation.Status.COMPLETED
    ).select_related('psychologue').order_by('-date', '-start_time')[:5]

    pending_requests = Consultation.objects.filter(
        patient=request.user,
        status=Consultation.Status.PENDING
    ).count()
    confirmed_sessions_count = Consultation.objects.filter(
        patient=request.user,
        status=Consultation.Status.CONFIRMED,
    ).count()

    pending_payments = Consultation.objects.filter(
        patient=request.user,
        status=Consultation.Status.CONFIRMED,
        payment_status=Consultation.PaymentStatus.UNPAID
    ).select_related('psychologue').order_by('date', 'start_time')

    context = {
        'user': request.user,
        'upcoming_sessions': upcoming_sessions,
        'appointments': upcoming_sessions,
        'confirmed_sessions_count': confirmed_sessions_count,
        'completed_sessions': completed_sessions,
        'pending_requests': pending_requests,
        'pending_payments': pending_payments,
        'notifications': request.user.notifications.all()[:5],
        'unread_notification_count': request.user.notifications.filter(
            is_read=False
        ).count(),
    }
    return render(request, 'patient/patient_dashboard.html', context)


@login_required
def notifications_list(request):
    notifications = request.user.notifications.all()
    return render(request, 'accounts/notifications.html', {
        'notifications': notifications,
    })


@login_required
@require_POST
def mark_notifications_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    messages.success(request, gettext('Vos notifications ont été marquées comme lues.'))
    return redirect('accounts:patient_dashboard')


@verification_required
@login_required
def psychologue_dashboard(request):
    if request.user.user_type != 'psychologue':
        messages.error(request, 'غير مصرح لك بالدخول هنا.')
        return redirect('home')

    now = timezone.now()
    today = timezone.localtime(now).date()
    complete_expired_consultations(
        Consultation.objects.filter(psychologue=request.user),
        now,
    )

    total_patients = Consultation.objects.filter(
        psychologue=request.user
    ).values('patient').distinct().count()

    completed_sessions = Consultation.objects.filter(
        psychologue=request.user, status=Consultation.Status.COMPLETED
    ).count()

    pending_requests = Consultation.objects.filter(
        psychologue=request.user, status=Consultation.Status.PENDING
    ).count()
    pending_sessions = Consultation.objects.filter(
        psychologue=request.user,
        status=Consultation.Status.PENDING,
    ).select_related('patient').order_by('date', 'start_time')[:5]

    upcoming_sessions = Consultation.objects.filter(
        psychologue=request.user,
        status__in=[
            Consultation.Status.PENDING,
            Consultation.Status.CONFIRMED,
            Consultation.Status.IN_PROGRESS,
        ],
        date__gte=today
    ).select_related('patient').order_by('date', 'start_time')[:5]

    recent_completed_sessions = Consultation.objects.filter(
        psychologue=request.user,
        status=Consultation.Status.COMPLETED,
    ).select_related('patient').order_by('-date', '-start_time')[:5]

    recent_patients = Consultation.objects.filter(
        psychologue=request.user
    ).select_related('patient').values(
        'patient', 'patient__first_name', 'patient__last_name'
    ).annotate(last_consultation=models.Max('date')).order_by('-last_consultation')[:5]

    from ai_service.models import EvolutionReport, SessionSummary
    ai_reports_count = EvolutionReport.objects.filter(psychologue=request.user).count() + \
                       SessionSummary.objects.filter(consultation__psychologue=request.user).count()

    from consultations.replacement_service import (
        pending_change_requests_for_psychologue,
    )
    change_requests = list(
        pending_change_requests_for_psychologue(request.user)
    )

    # Legacy patient change requests stored on the recurring-series model
    # (before the "Séances de rattrapage" feature existed). They are surfaced
    # here so patients who still run the old cached bundle are not ignored.
    from consultations.models import RecurringSession
    legacy_reschedule_requests = list(
        RecurringSession.objects.filter(
            psychologue=request.user,
            status=RecurringSession.Status.PROPOSED,
            reschedule_requested=True,
            reschedule_reviewed=False,
        )
        .select_related('patient')
        .order_by('-reschedule_request_at')
    )

    context = {
        'user': request.user,
        'total_patients': total_patients,
        'completed_sessions': completed_sessions,
        'pending_requests': pending_requests,
        'pending_sessions': pending_sessions,
        'upcoming_sessions': upcoming_sessions,
        'recent_completed_sessions': recent_completed_sessions,
        'recent_patients': recent_patients,
        'ai_reports_count': ai_reports_count,
        'change_requests': change_requests,
        'legacy_reschedule_requests': legacy_reschedule_requests,
    }
    return render(request, 'pages/psychologue_dashboard.html', context)


# ============================================================
#                     PATIENTS / CONSULTATIONS
# ============================================================
@verification_required
@login_required
def mes_patients(request):
    if request.user.user_type != 'psychologue':
        return redirect('home')

    patients = CustomUser.objects.filter(
        patient_consultations__psychologue=request.user
    ).distinct().select_related('patient_profile')

    return render(request, 'accounts/mes_patients.html', {'patients': patients})


@login_required
@never_cache
def rendez_vous(request):
    if request.user.user_type == 'psychologue':
        consultations = Consultation.objects.filter(psychologue=request.user)
    elif request.user.user_type == 'patient':
        consultations = Consultation.objects.filter(patient=request.user)
    else:
        return redirect('home')

    pending_count = consultations.filter(status=Consultation.Status.PENDING).count()
    confirmed_count = consultations.filter(status=Consultation.Status.CONFIRMED).count()
    completed_count = consultations.filter(status=Consultation.Status.COMPLETED).count()

    consultations = consultations.select_related('patient', 'psychologue').order_by('-date', '-start_time')

    return render(request, 'accounts/rendez_vous.html', {
        'appointments': consultations, 
        'pending_count': pending_count,
        'confirmed_count': confirmed_count,
        'completed_count': completed_count,
    })


@verification_required
@login_required
def dossiers_cliniques(request):
    if request.user.user_type == 'psychologue':
        records = ClinicalRecord.objects.filter(psychologue=request.user)
    elif request.user.user_type == 'patient':
        records = ClinicalRecord.objects.filter(patient=request.user)
    else:
        return redirect('home')

    records = records.select_related('patient', 'psychologue').order_by('-created_at')
    return render(request, 'accounts/dossiers_cliniques.html', {'records': records})


# ============================================================
#              CONSULTATION NOTES (psychologist-authored)
# ============================================================
@verification_required
@login_required
def psychologue_notes(request):
    """Two separated zones: patient-facing notes and private professional notes."""
    if request.user.user_type != 'psychologue':
        raise PermissionDenied

    patients = list(notes_service.psychologist_patients(request.user))

    selected_patient = None
    selected_patient_id = request.GET.get('patient') or request.POST.get('patient')
    if selected_patient_id:
        selected_patient = next(
            (p for p in patients if str(p.pk) == str(selected_patient_id)), None
        )

    if request.method == 'POST':
        patient = next(
            (p for p in patients if str(p.pk) == str(request.POST.get('patient'))),
            None,
        )
        note_type = request.POST.get('note_type')
        content = request.POST.get('content', '')
        consultation_id = request.POST.get('consultation') or None
        if patient is None:
            messages.error(request, gettext('Patient invalide.'))
        else:
            try:
                if note_type == ConsultationNote.NoteType.PATIENT:
                    notes_service.create_patient_note(
                        psychologue=request.user,
                        patient=patient,
                        content=content,
                        consultation_id=consultation_id,
                    )
                    messages.success(
                        request, gettext('Note enregistrée et envoyée au patient.')
                    )
                else:
                    notes_service.create_professional_note(
                        psychologue=request.user,
                        patient=patient,
                        content=content,
                        consultation_id=consultation_id,
                    )
                    messages.success(
                        request, gettext('Note professionnelle privée enregistrée.')
                    )
            except ValidationError as exc:
                messages.error(request, '; '.join(exc.messages))
            except PermissionDenied:
                messages.error(request, gettext("Action non autorisée."))
        selected_patient = patient
        redirect_url = reverse('accounts:psychologue_notes')
        if patient is not None:
            redirect_url += f'?patient={patient.pk}'
        return redirect(redirect_url)

    notes = []
    consultations = []
    if selected_patient is not None:
        notes = list(
            notes_service.notes_for_psychologue(request.user, selected_patient)
        )
        consultations = list(
            notes_service.consultations_for_patient(request.user, selected_patient)
        )

    return render(request, 'accounts/psychologue_notes.html', {
        'patients': patients,
        'selected_patient': selected_patient,
        'notes': notes,
        'consultations': consultations,
        'note_types': ConsultationNote.NoteType.choices,
    })


@verification_required
@login_required
def psychologue_retract_note(request, note_id):
    """Retract a sent patient note (author only), keeping an audit trail."""
    if request.user.user_type != 'psychologue':
        raise PermissionDenied
    if request.method != 'POST':
        raise PermissionDenied

    note = ConsultationNote.objects.filter(pk=note_id).first()
    if note is None:
        raise Http404('Note introuvable.')

    reason = request.POST.get('reason', '')
    try:
        updated, error = notes_service.retract_note(note_id, request.user, reason)
    except PermissionDenied:
        raise Http404('Note introuvable.')

    if error:
        messages.error(request, error)
    else:
        messages.success(request, gettext('Note rétractée. L’historique est conservé.'))
    return redirect('accounts:psychologue_notes')


@login_required
def patient_note_detail(request, note_id):
    """Read a patient-facing note. Strict backend ownership + type + sent checks."""
    if request.user.user_type != 'patient':
        raise PermissionDenied

    note = notes_service.get_patient_note(note_id, request.user)
    retracted = False
    if note is None:
        # Distinguish a retracted note (inform the patient) from a foreign or
        # non-existent note (404). Never expose the content of a retracted note.
        maybe = notes_service.get_patient_note_any_status(note_id, request.user)
        if maybe is not None and maybe.retracted_at is not None:
            note = maybe
            retracted = True
        else:
            raise Http404('Note introuvable.')

    if not retracted:
        # Mark the related notification as read when opened from it.
        request.user.notifications.filter(
            url=reverse('accounts:patient_note_detail', args=[note.pk])
        ).update(is_read=True)

    return render(
        request,
        'accounts/patient_note_detail.html',
        {'note': note, 'retracted': retracted},
    )


# ============================================================
#                     FIND PSYCHOLOGIST & BOOKING
# ============================================================
@login_required
def trouver_psychologue(request):
    if request.user.user_type != 'patient':
        messages.error(request, 'غير مصرح لك بالدخول هنا.')
        return redirect('home')

    psychologists_list = CustomUser.objects.filter(
        user_type='psychologue', is_active=True,
        psychologue_profile__is_verified=True
    ).select_related('psychologue_profile').annotate(
        rating_average=Avg('ratings_received__rating'),
        rating_count=Count('ratings_received', distinct=True),
    )

    specialty = request.GET.get('specialty')
    if specialty:
        psychologists_list = psychologists_list.filter(psychologue_profile__specialty=specialty)

    search_query = request.GET.get('search')
    if search_query:
        psychologists_list = psychologists_list.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(psychologue_profile__specialty__icontains=search_query)
        )

    rating_opportunities = {}
    completed_consultations = Consultation.objects.filter(
        patient=request.user,
        status=Consultation.Status.COMPLETED,
    ).exclude(
        doctor_ratings__patient=request.user,
    ).select_related('psychologue').order_by('-date', '-start_time')
    for consultation in completed_consultations:
        rating_opportunities.setdefault(consultation.psychologue_id, []).append(
            consultation
        )
    for psy in psychologists_list:
        psy.rating_consultations = rating_opportunities.get(psy.pk, [])

    context = {
        'psychologists': psychologists_list,
        'specialty_choices': PsychologueProfile.SPECIALTY_CHOICES,
        'selected_specialty': specialty,
        'search_query': search_query,
    }
    return render(request, 'pages/find_psychologist.html', context)


@login_required
@require_POST
def rate_consultation(request, consultation_id):
    if request.user.user_type != 'patient':
        messages.error(request, 'التقييم متاح للمرضى فقط.')
        return redirect('home')

    consultation = get_object_or_404(
        Consultation,
        pk=consultation_id,
        patient=request.user,
        status=Consultation.Status.COMPLETED,
    )
    if DoctorRating.objects.filter(
        patient=request.user,
        doctor=consultation.psychologue,
        consultation=consultation,
    ).exists():
        messages.info(request, 'سبق أن قيّمت هذه الاستشارة.')
        return redirect('accounts:trouver_psychologue')

    form = DoctorRatingForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'اختر تقييماً من نجمة إلى خمس نجوم.')
        return redirect('accounts:trouver_psychologue')

    rating = form.save(commit=False)
    rating.patient = request.user
    rating.doctor = consultation.psychologue
    rating.consultation = consultation
    try:
        rating.full_clean()
        rating.save()
    except (ValidationError, IntegrityError):
        logger.exception('Could not save consultation rating.')
        messages.error(request, 'تعذر حفظ التقييم. يرجى المحاولة مرة أخرى.')
        return redirect('accounts:trouver_psychologue')

    messages.success(request, 'شكراً لك، تم حفظ تقييمك.')
    return redirect('accounts:trouver_psychologue')


@login_required
@never_cache
def book_consultation(request, psychologue_id):
    if request.user.user_type != 'patient':
        messages.error(request, 'غير مصرح لك بالحجز.')
        return redirect('home')

    psychologue = CustomUser.objects.filter(
        id=psychologue_id,
        user_type='psychologue',
        is_active=True,
        psychologue_profile__is_verified=True,
    ).select_related('psychologue_profile').annotate(
        rating_average=Avg('ratings_received__rating'),
        rating_count=Count('ratings_received', distinct=True),
    ).first()
    if psychologue is None:
        messages.error(request, "Le psychologue est introuvable.")
        return redirect('accounts:trouver_psychologue')

    profile = psychologue.psychologue_profile

    # Weekly calendar data (starting today) for the booking grid.
    # Always starts at today (server-local date, Africa/Algiers) so the
    # current day is never skipped — previously the grid jumped straight
    # to the next Saturday, hiding today and tomorrow.
    from collections import defaultdict
    today = timezone.localdate()
    week_start = today
    week_end = min(week_start + timedelta(days=6), today + timedelta(days=GENERATION_HORIZON_DAYS))

    # Noms des jours calculés à partir de chaque date réelle (Lundi = 0
    # pour date.weekday(), même convention que WeeklyAvailabilityRule).
    WEEKDAY_NAMES_FR = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']

    week_days = []
    for i in range(7):
        day_date = week_start + timedelta(days=i)
        day_name = WEEKDAY_NAMES_FR[day_date.weekday()]
        week_days.append({
            'date': day_date,
            'weekday': day_name,
            'weekday_ar': day_name,
        })

    if request.method == 'POST':
        creneau_id = request.POST.get('creneau_id')
        session_type = request.POST.get('consultation_type', 'video')
        patient_notes = request.POST.get('notes', '')

        try:
            selected_creneau_id = int(creneau_id)
        except (TypeError, ValueError):
            messages.error(request, "Veuillez sélectionner un créneau disponible.")
            return redirect('accounts:book_consultation', psychologue_id=psychologue_id)

        with transaction.atomic():
            try:
                # Lock the slot row so concurrent bookings serialize here.
                creneau = Creneau.objects.select_for_update().filter(
                    pk=selected_creneau_id,
                    psychologue=psychologue,
                    statut=Creneau.Statut.LIBRE,
                    is_bookable=True,
                ).first()
            except OperationalError:
                messages.error(
                    request,
                    "La réservation est momentanément occupée par une autre opération. Veuillez réessayer.",
                )
                return redirect('accounts:book_consultation', psychologue_id=psychologue_id)
            if creneau is None:
                messages.error(
                    request,
                    "Ce créneau vient d'être réservé. Veuillez en choisir un autre.",
                )
                return redirect('accounts:book_consultation', psychologue_id=psychologue_id)

            if session_type not in Consultation.SessionType.values:
                messages.error(request, "Veuillez sélectionner un type de consultation valide.")
                return redirect('accounts:book_consultation', psychologue_id=psychologue_id)

            session_datetime = timezone.make_aware(
                datetime.combine(creneau.date, creneau.heure_debut)
            )
            if session_datetime <= timezone.now():
                messages.error(request, "Impossible de réserver un créneau passé.")
                return redirect('accounts:book_consultation', psychologue_id=psychologue_id)

            slot_duration = datetime.combine(
                creneau.date, creneau.heure_fin
            ) - datetime.combine(creneau.date, creneau.heure_debut)
            duration_minutes = int(slot_duration.total_seconds() // 60)
            if duration_minutes <= 0:
                messages.error(request, "La durée de ce créneau est invalide.")
                return redirect('accounts:book_consultation', psychologue_id=psychologue_id)

            claimed = Creneau.objects.filter(
                pk=creneau.pk,
                statut=Creneau.Statut.LIBRE,
                is_bookable=True,
            ).update(statut=Creneau.Statut.RESERVE)
            if not claimed:
                messages.error(
                    request,
                    "Ce créneau vient d'être réservé. Veuillez en choisir un autre.",
                )
                return redirect('accounts:book_consultation', psychologue_id=psychologue_id)

            if not CustomUser.objects.filter(
                pk=psychologue.pk,
                user_type='psychologue',
                is_active=True,
                psychologue_profile__is_verified=True,
            ).exists():
                Creneau.objects.filter(
                    pk=creneau.pk,
                    statut=Creneau.Statut.RESERVE,
                ).update(statut=Creneau.Statut.LIBRE)
                messages.error(request, "Ce psychologue n'est plus autorisé à recevoir des réservations.")
                return redirect('accounts:book_consultation', psychologue_id=psychologue_id)
            if not slot_matches_current_schedule(psychologue, creneau):
                Creneau.objects.filter(
                    pk=creneau.pk,
                    statut=Creneau.Statut.RESERVE,
                ).update(statut=Creneau.Statut.LIBRE)
                messages.error(request, "Ce créneau ne correspond plus aux règles de disponibilité actives.")
                return redirect('accounts:book_consultation', psychologue_id=psychologue_id)
            # Lock the overlapping active consultations for this psychologist and
            # date so two bookings of overlapping times cannot both pass this check.
            consultation_conflict = Consultation.objects.select_for_update().filter(
                psychologue=psychologue,
                date=creneau.date,
                status__in=ACTIVE_CONSULTATION_STATUSES,
                start_time__lt=creneau.heure_fin,
                end_time__gt=creneau.heure_debut,
            ).exists()
            if consultation_conflict:
                Creneau.objects.filter(
                    pk=creneau.pk,
                    statut=Creneau.Statut.RESERVE,
                ).update(statut=Creneau.Statut.LIBRE)
                messages.error(request, "Ce créneau chevauche déjà un rendez-vous actif.")
                return redirect('accounts:book_consultation', psychologue_id=psychologue_id)
            if overlapping_slots(
                psychologue,
                creneau.date,
                creneau.heure_debut,
                creneau.heure_fin,
                exclude_id=creneau.pk,
            ):
                Creneau.objects.filter(
                    pk=creneau.pk,
                    statut=Creneau.Statut.RESERVE,
                ).update(statut=Creneau.Statut.LIBRE)
                messages.error(request, "Ce créneau chevauche une autre disponibilité.")
                return redirect('accounts:book_consultation', psychologue_id=psychologue_id)

            try:
                consultation = Consultation.objects.create(
                    patient=request.user,
                    psychologue=psychologue,
                    creneau=creneau,
                    date=creneau.date,
                    start_time=creneau.heure_debut,
                    end_time=creneau.heure_fin,
                    duration_minutes=duration_minutes,
                    session_type=session_type,
                    patient_notes=patient_notes,
                    price=profile.hourly_rate,
                    status=Consultation.Status.PENDING,
                )
                notify_user(
                    psychologue.pk,
                    "session_requested",
                    "Nouvelle demande de consultation.",
                    {
                        "consultation_id": str(consultation.pk),
                        "patient_name": request.user.get_full_name() or request.user.username,
                        "session_type": consultation.session_type,
                        "action_url": reverse("accounts:rendez_vous"),
                    },
                )
            except ValidationError:
                # Model-level overlap validation failed; free the slot again.
                Creneau.objects.filter(
                    pk=creneau.pk,
                    statut=Creneau.Statut.RESERVE,
                ).update(statut=Creneau.Statut.LIBRE)
                messages.error(request, "Cette consultation chevauche un rendez-vous actif.")
                return redirect('accounts:book_consultation', psychologue_id=psychologue_id)

        messages.success(request, f"Demande de réservation envoyée à Dr. {psychologue.first_name} avec succès.")
        return redirect('accounts:patient_dashboard')

    # Build the weekly calendar data only for GET requests, outside the write
    # transaction, so concurrent POSTs never compete over these read queries.
    creneaux = Creneau.objects.filter(
        psychologue=psychologue,
        date__gte=week_start,
        date__lte=week_end,
    ).order_by('date', 'heure_debut')

    booked_consultations = Consultation.objects.filter(
        psychologue=psychologue,
        date__gte=week_start,
        date__lte=week_end,
        status__in=ACTIVE_CONSULTATION_STATUSES,
    )
    booked_keys = {
        (consultation.date, consultation.start_time)
        for consultation in booked_consultations
    }

    slots_by_day = defaultdict(list)
    for creneau in creneaux:
        is_booked = (creneau.date, creneau.heure_debut) in booked_keys
        slots_by_day[creneau.date].append({
            'id': creneau.pk,
            'start_time': creneau.heure_debut.strftime('%H:%M'),
            'end_time': creneau.heure_fin.strftime('%H:%M'),
            'is_booked': is_booked,
            'is_available': (
                creneau.statut == Creneau.Statut.LIBRE
                and creneau.is_bookable
                and not is_booked
            ),
        })
    for day in slots_by_day:
        slots_by_day[day].sort(key=lambda x: x['start_time'])
    for day_info in week_days:
        day_date = day_info['date']
        day_slots = slots_by_day.get(day_date, [])
        now = timezone.now()
        closed_exception = AvailabilityException.objects.filter(
            psychologue=psychologue,
            date=day_date,
            is_active=True,
            kind=AvailabilityException.Kind.CLOSED,
        ).exists()
        for slot_info in day_slots:
            slot_start = timezone.make_aware(
                datetime.combine(day_date, datetime.strptime(slot_info['start_time'], '%H:%M').time()),
                timezone.get_current_timezone(),
            )
            slot_info['is_past'] = slot_start <= now
            slot_info['is_available'] = (
                slot_info['is_available'] and not slot_info['is_past']
            )
        day_info['slots'] = day_slots
        day_info['is_closed'] = closed_exception
        day_info['is_today'] = day_date == today
        day_info['is_past'] = day_date < today
        if closed_exception:
            day_info['day_status'] = 'closed'
        elif day_date == today:
            if day_slots:
                if any(s['is_available'] for s in day_slots):
                    day_info['day_status'] = 'open'
                elif all(s['is_past'] for s in day_slots):
                    day_info['day_status'] = 'finished'
                else:
                    day_info['day_status'] = 'no_more'
            else:
                day_info['day_status'] = 'closed'

    return render(request, 'patient/book_consultation.html', {
        'psychologue': psychologue,
        'full_name': f"Dr. {psychologue.first_name} {psychologue.last_name}",
        'profile': profile,
        'week_days': week_days,
        'week_start': week_start,
        'price': profile.hourly_rate,
        'duration': profile.session_duration,
    })


@require_GET
def get_booked_slots(request):
    if request.user.user_type != 'patient':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    date_str = request.GET.get('date')
    psychologue_id = request.GET.get('psychologue_id')
    
    if not date_str or not psychologue_id:
        return JsonResponse({'error': 'Missing parameters'}, status=400)
    
    try:
        booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        booked_consultations = Consultation.objects.filter(
            psychologue_id=psychologue_id, date=booking_date,
            status__in=[Consultation.Status.CONFIRMED, Consultation.Status.PENDING]
        )
        booked_times = [c.start_time.strftime('%H:%M') for c in booked_consultations]
        return JsonResponse({'booked_slots': booked_times})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ============================================================
#                     MESSAGING & CALLS
# ============================================================
@login_required
def messages_list(request):
    if request.user.user_type == 'psychologue':
        conversations = Conversation.objects.filter(psychologue=request.user)
    else:
        conversations = Conversation.objects.filter(patient=request.user)
    conversations = conversations.select_related('patient', 'psychologue').order_by('-updated_at')
    return render(request, 'accounts/messages_list.html', {'conversations': conversations})


@login_required
def chat_room(request, conversation_id):
    conversations = (
        Conversation.objects.filter(psychologue=request.user) |
        Conversation.objects.filter(patient=request.user)
    )
    conversation = get_object_or_404(conversations, id=conversation_id)
    messages_qs = conversation.messages.all()
    return render(request, 'chat/room.html', {'conversation': conversation, 'messages': messages_qs})


@login_required
def send_message(request, conversation_id):
    if request.method != 'POST':
        return redirect('accounts:chat_room', conversation_id=conversation_id)

    conversations = (
        Conversation.objects.filter(psychologue=request.user) |
        Conversation.objects.filter(patient=request.user)
    )
    conversation = get_object_or_404(conversations, id=conversation_id)
    content = request.POST.get('content', '').strip()

    if content:
        Message.objects.create(conversation=conversation, sender=request.user, content=content)
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=['updated_at'])

    return redirect('accounts:chat_room', conversation_id=conversation_id)


@login_required
def start_call(request, patient_id):
    if request.user.user_type != 'psychologue':
        raise PermissionDenied

    patient = get_object_or_404(CustomUser, id=patient_id, user_type='patient')
    call_type = request.GET.get('type', 'video')
    if call_type not in dict(Call.TYPE_CHOICES):
        messages.error(request, 'Veuillez choisir un type d’appel valide.')
        return redirect('accounts:messages_list')
    room_name = f"call-{uuid.uuid4().hex[:12]}"

    Call.objects.create(
        psychologue=request.user, patient=patient,
        call_type=call_type, room_name=room_name, status='scheduled'
    )
    return render(request, 'call/room.html', {'room_name': room_name, 'patient': patient, 'call_type': call_type})


# ============================================================
#                     SETTINGS
# ============================================================
@login_required
def parametres(request):
    if request.user.user_type == 'psychologue':
        psychologue_profile, _ = PsychologueProfile.objects.get_or_create(user=request.user)
        if request.method == 'POST':
            user_form = UserUpdateForm(request.POST, request.FILES, instance=request.user)
            profile_form = PsychologueProfileForm(request.POST, request.FILES, instance=psychologue_profile)
            if user_form.is_valid() and profile_form.is_valid():
                user_form.save()
                profile_form.save()
                messages.success(request, 'Vos paramètres ont été mis à jour avec succès.')
                return redirect('accounts:parametres')
        else:
            user_form = UserUpdateForm(instance=request.user)
            profile_form = PsychologueProfileForm(instance=psychologue_profile)
    else:
        patient_profile, _ = PatientProfile.objects.get_or_create(user=request.user)
        if request.method == 'POST':
            user_form = UserUpdateForm(request.POST, request.FILES, instance=request.user)
            profile_form = PatientProfileForm(request.POST, request.FILES, instance=patient_profile)
            if user_form.is_valid() and profile_form.is_valid():
                user_form.save()
                profile_form.save()
                messages.success(request, 'Vos paramètres ont été mis à jour avec succès.')
                return redirect('accounts:parametres')
        else:
            user_form = UserUpdateForm(instance=request.user)
            profile_form = PatientProfileForm(instance=patient_profile)

    return render(request, 'accounts/parametres.html', {
        'user_form': user_form, 'profile_form': profile_form
    })


@login_required
def delete_account(request):
    if request.method == 'POST':
        form = DeleteAccountForm(request.POST, user=request.user)
        if form.is_valid():
            user = request.user
            with transaction.atomic():
                psychologist_profile = PsychologueProfile.objects.filter(user=user).first()
                if psychologist_profile is not None:
                    for field_name in (
                        'photo',
                        'diploma_file',
                        'id_document_file',
                        'registration_file',
                    ):
                        profile_file = getattr(psychologist_profile, field_name)
                        if profile_file:
                            profile_file.delete(save=False)
                    psychologist_profile.title = 'Psychologue'
                    psychologist_profile.sub_specialties = ''
                    psychologist_profile.diploma = ''
                    psychologist_profile.university = ''
                    psychologist_profile.graduation_year = None
                    psychologist_profile.biography = ''
                    psychologist_profile.registration_number = ''
                    psychologist_profile.rpps = ''
                    psychologist_profile.adeli = ''
                    psychologist_profile.city = ''
                    psychologist_profile.is_verified = False
                    psychologist_profile.save(update_fields=[
                        'title',
                        'sub_specialties',
                        'diploma',
                        'university',
                        'graduation_year',
                        'biography',
                        'registration_number',
                        'rpps',
                        'adeli',
                        'city',
                        'is_verified',
                        'photo',
                        'diploma_file',
                        'id_document_file',
                        'registration_file',
                    ])

                if user.avatar:
                    user.avatar.delete(save=False)
                user.username = f'deleted-{user.pk}-{uuid.uuid4().hex}'
                user.email = f'deleted-{user.pk}-{uuid.uuid4().hex}@deleted.invalid'
                user.first_name = ''
                user.last_name = ''
                user.phone = None
                user.date_of_birth = None
                user.city = ''
                user.last_login = None
                user.is_active = False
                user.set_unusable_password()
                user.save(update_fields=[
                    'username',
                    'email',
                    'first_name',
                    'last_name',
                    'phone',
                    'avatar',
                    'date_of_birth',
                    'city',
                    'last_login',
                    'is_active',
                    'password',
                ])
            logout(request)
            return render(request, 'accounts/delete_account.html', {'deleted': True})
    else:
        form = DeleteAccountForm(user=request.user)

    return render(request, 'accounts/delete_account.html', {'form': form})


@login_required
def professional_profile(request):
    if request.user.user_type != 'psychologue':
        return redirect('home')

    psychologue_profile, _ = PsychologueProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = PsychologueProfileForm(request.POST, request.FILES, instance=psychologue_profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Votre profil professionnel a été mis à jour avec succès.')
            return redirect('accounts:professional_profile')
    else:
        form = PsychologueProfileForm(instance=psychologue_profile)

    return render(request, 'accounts/professional_profile.html', {'form': form})


@login_required
def security_settings(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password')
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')

        if not request.user.check_password(old_password):
            messages.error(request, "L'ancien mot de passe est incorrect.")
        elif new_password1 != new_password2:
            messages.error(request, 'Les nouveaux mots de passe ne correspondent pas.')
        elif len(new_password1) < 8:
            messages.error(request, 'Le mot de passe doit contenir au moins 8 caractères.')
        else:
            request.user.set_password(new_password1)
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Votre mot de passe a été mis à jour avec succès.')
            return redirect('accounts:security_settings')

    return render(request, 'accounts/security_settings.html')


# ============================================================
#                     PAYMENT SYSTEM
# ============================================================
from django.utils.translation import activate


@login_required
@never_cache
def payment_page(request, consultation_id):
    lang = request.GET.get('lang')
    if lang in ['fr', 'ar', 'en']:
        activate(lang)
        request.LANGUAGE_CODE = lang
    if request.user.user_type != 'patient':
        raise PermissionDenied
    consultation = get_object_or_404(Consultation, id=consultation_id, patient=request.user)
    
    if consultation.status != Consultation.Status.CONFIRMED:
        messages.error(request, 'لا يمكن الدفع: الموعد لم يتم تأكيده بعد.')
        return redirect('accounts:patient_dashboard')
    
    if consultation.payment_status != Consultation.PaymentStatus.UNPAID:
        messages.info(request, 'تم الدفع مسبقاً لهذا الموعد.')
        return redirect('accounts:patient_dashboard')

    payment_record = None
    try:
        payment_record = consultation.payment_record
    except PaymentRecord.DoesNotExist:
        pass

    return render(request, 'accounts/payment.html', {
        'consultation': consultation,
        'payment_methods': PaymentRecord.METHOD_CHOICES,
        'payment_record': payment_record,
    })


@login_required
@require_POST
def process_payment(request, consultation_id):
    if request.user.user_type != 'patient':
        raise PermissionDenied
    with transaction.atomic():
        consultation = get_object_or_404(
            Consultation.objects.select_for_update(),
            id=consultation_id,
            patient=request.user,
        )

        if consultation.status != Consultation.Status.CONFIRMED:
            messages.error(request, 'لا يمكن الدفع: الموعد ليس في حالة مؤكدة.')
            return redirect('accounts:patient_dashboard')

        if consultation.payment_status != Consultation.PaymentStatus.UNPAID:
            messages.info(request, 'تم الدفع مسبقاً لهذا الموعد.')
            return redirect('accounts:patient_dashboard')

        payment_method = request.POST.get('payment_method')
        if payment_method not in dict(PaymentRecord.METHOD_CHOICES):
            messages.error(request, 'يرجى اختيار طريقة دفع صالحة.')
            return redirect('accounts:payment_page', consultation_id=consultation.id)

        card_number = ''.join(
            character
            for character in request.POST.get(
                'card_number',
                request.POST.get('test_card_number', ''),
            )
            if character in '0123456789'
        )
        cardholder_name = request.POST.get('cardholder_name', '').strip()
        expiry = request.POST.get('expiry', '').strip()
        if expiry:
            expiry_parts = expiry.split('/')
            if len(expiry_parts) == 2:
                expiry_month, expiry_year = expiry_parts
            else:
                expiry_month, expiry_year = '', ''
        else:
            expiry_month = request.POST.get('expiry_month', '')
            expiry_year = request.POST.get('expiry_year', '')
        cvv = request.POST.get('cvv', '')
        today = timezone.localdate()
        try:
            month = int(expiry_month)
            year = int(expiry_year)
            if len(expiry_year) == 2:
                year += 2000
            expiry_valid = (
                len(expiry_month) == 2
                and len(expiry_year) in (2, 4)
                and 1 <= month <= 12
                and (year, month) >= (today.year, today.month)
            )
        except (TypeError, ValueError):
            expiry_valid = False

        if (
            not 12 <= len(card_number) <= 19
            or not cardholder_name
            or len(cardholder_name) > 100
            or not expiry_valid
            or len(cvv) not in (3, 4)
            or not cvv.isascii()
            or not cvv.isdigit()
        ):
            messages.error(
                request,
                'Vérifiez les informations de test : carte, nom, expiration et code de sécurité.',
            )
            return redirect('accounts:payment_page', consultation_id=consultation.id)

        failed_test_cards = {
            'CIB': '1111111111111112',
            'EDAHABIA': '2222222222222223',
        }
        succeeded = card_number != failed_test_cards[payment_method]
        transaction_ref = f"SIM-{uuid.uuid4().hex[:10].upper()}"
        attempt_time = timezone.now()
        PaymentRecord.objects.update_or_create(
            consultation=consultation,
            defaults={
                'amount': consultation.price,
                'method': payment_method,
                'transaction_ref': transaction_ref,
                'status': 'success' if succeeded else 'failed',
                'created_at': attempt_time,
            },
        )

        if not succeeded:
            messages.error(
                request,
                'Échec de paiement simulé. Aucun paiement réel n’a été effectué. Vous pouvez réessayer.',
            )
            return redirect('accounts:payment_page', consultation_id=consultation.id)

        consultation.payment_status = Consultation.PaymentStatus.PAID
        consultation.payment_date = attempt_time
        consultation.save(update_fields=['payment_status', 'payment_date'])
    
    messages.success(
        request,
        f'Paiement simulé réussi. Aucun paiement bancaire réel n’a été effectué. Référence : {transaction_ref}',
    )
    return redirect('accounts:payment_success', consultation_id=consultation.id)


@login_required
def payment_success(request, consultation_id):
    if request.user.user_type != 'patient':
        raise PermissionDenied
    consultation = get_object_or_404(Consultation, id=consultation_id, patient=request.user)
    if consultation.payment_status != Consultation.PaymentStatus.PAID:
        messages.error(request, 'لم يتم تسجيل دفعة لهذا الموعد.')
        return redirect('accounts:patient_dashboard')
    payment = get_object_or_404(PaymentRecord, consultation=consultation)
    if payment.status != 'success' or payment.amount != consultation.price:
        messages.error(request, 'Le paiement enregistré ne peut pas être confirmé.')
        return redirect('accounts:patient_dashboard')
    return render(request, 'accounts/payment_success.html', {
        'consultation': consultation,
        'payment': payment,
    })


@verification_required
@login_required
@require_POST
def emergency_cancel_appointment(request, consultation_id):
    if request.user.user_type != 'psychologue':
        return redirect_by_role(request.user)

    generated_slot = False
    with transaction.atomic():
        consultation = get_object_or_404(
            Consultation.objects.select_for_update(),
            pk=consultation_id,
            psychologue=request.user,
        )
        complete_expired_consultations(
            Consultation.objects.filter(pk=consultation.pk),
        )
        consultation.refresh_from_db()

        if consultation.status not in (
            Consultation.Status.PENDING,
            Consultation.Status.CONFIRMED,
        ):
            messages.error(request, "لا يمكن إلغاء جلسة منتهية أو ملغاة مسبقاً.")
        elif not consultation.can_be_cancelled():
            messages.error(request, "لا يمكن إلغاء الجلسة بعد بدئها.")
        else:
            consultation.cancel(
                cancelled_by=request.user,
                reason=Consultation.CancellationReason.PSYCHOLOGUE,
                details='Urgent cancellation by psychologist',
            )
            if consultation.creneau_id:
                creneau = Creneau.objects.select_for_update().get(
                    pk=consultation.creneau_id,
                )
                generated_slot = creneau.is_generated
                creneau.liberer()
            notify_user(
                consultation.patient_id,
                "session_cancelled",
                "تم إلغاء موعدك من طرف الأخصائي. سيتم التواصل معك لتحديد موعد بديل.",
                {
                    "consultation_id": str(consultation.pk),
                    "status": consultation.status,
                    "doctor_name": request.user.get_full_name() or request.user.username,
                    "action_url": reverse("accounts:rendez_vous"),
                },
            )
            messages.success(request, "تم إلغاء الموعد وإشعار المريض.")

    if generated_slot:
        result = generate_slots(request.user)
        for warning in result['warnings']:
            messages.warning(request, warning)

    return redirect('accounts:psychologue_dashboard')


@verification_required
@login_required
@require_POST
def confirm_appointment(request, consultation_id):
    consultation = get_object_or_404(Consultation, id=consultation_id, psychologue=request.user)

    profile = getattr(request.user, 'psychologue_profile', None)
    if profile is None or not profile.is_verified:
        messages.error(request, 'Votre profil doit être vérifié avant de confirmer des rendez-vous.')
        return redirect('accounts:rendez_vous')
    
    if consultation.status == Consultation.Status.PENDING:
        consultation.confirm()
        notification_payload = {
            "consultation_id": str(consultation.pk),
            "status": consultation.status,
            "doctor_name": request.user.get_full_name() or request.user.username,
        }
        if has_paid_confirmed_room_access(consultation):
            notification_payload["room_url"] = reverse(
                "consultations:consultation_chat",
                args=[consultation.pk],
            )
        else:
            notification_payload["payment_url"] = reverse(
                "accounts:payment_page",
                args=[consultation.pk],
            )
            notification_payload["payment_required"] = True
        notify_user(
            consultation.patient_id,
            "session_accepted",
            "Votre demande de consultation a été acceptée.",
            notification_payload,
        )
        # Auto-materialize the remaining future occurrences of a recurring
        # series when its first confirmed consultation is accepted.
        if consultation.recurring_session_id is not None:
            try:
                created, warnings = materialize_series_for_consultation(consultation)
                for warning in warnings:
                    messages.warning(request, warning)
                if created:
                    messages.info(
                        request,
                        f"{created} séance(s) récurrente(s) planifiée(s) pour ce patient.",
                    )
            except Exception:
                logger.exception(
                    "Failed to materialize recurring series for consultation %s",
                    consultation.pk,
                )
                messages.error(
                    request,
                    "La série récurrente n'a pas pu être planifiée automatiquement.",
                )
        messages.success(
            request,
            gettext("Rendez-vous %(reference)s confirmé.") % {
                "reference": consultation.reference_number,
            },
        )

    return redirect('accounts:rendez_vous')


@verification_required
@login_required
@require_POST
def reject_appointment(request, consultation_id):
    consultation = get_object_or_404(Consultation, id=consultation_id, psychologue=request.user)
    
    if consultation.status == Consultation.Status.PENDING:
        consultation.cancel(
            cancelled_by=request.user,
            reason=Consultation.CancellationReason.PSYCHOLOGUE,
            details='Rejected by specialist'
        )
        if consultation.creneau:
            consultation.creneau.liberer()
            if consultation.creneau.is_generated:
                result = generate_slots(consultation.psychologue)
                for warning in result['warnings']:
                    messages.warning(request, warning)
        notify_user(
            consultation.patient_id,
            "session_rejected",
            "Votre demande de consultation a été refusée.",
            {
                "consultation_id": str(consultation.pk),
                "status": consultation.status,
                "doctor_name": request.user.get_full_name() or request.user.username,
                "action_url": reverse("accounts:rendez_vous"),
            },
        )
        messages.info(
            request,
            gettext("Rendez-vous %(reference)s refusé.") % {
                "reference": consultation.reference_number,
            },
        )
    
    return redirect('accounts:rendez_vous')