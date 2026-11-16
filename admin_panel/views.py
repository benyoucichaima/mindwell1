import json
import logging
import mimetypes
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from accounts.models import CustomUser, Notification, PsychologueProfile
from consultations.models import Consultation, Document
from mindwell.models import ContactMessage
from .models import Report

logger = logging.getLogger(__name__)

ADMIN_SECTIONS = {
    "users": (_("Utilisateurs"), _("Tous les comptes de la plateforme")),
    "patients": (_("Patients"), _("Comptes patients enregistrés")),
    "psychologues": (_("Psychologues"), _("Profils psychologues enregistrés")),
    "verifications": (_("Vérifications"), _("Demandes de validation en attente")),
    "appointments": (_("Rendez-vous"), _("Consultations enregistrées")),
    "statistics": (
        _("Statistiques"),
        _("Indicateurs calculés à partir des données disponibles"),
    ),
    "reports": (_("Signalements"), _("Signalements reçus par la plateforme")),
    "contact_messages": (
        _("Messages de contact"),
        _("Messages envoyés à la plateforme"),
    ),
    "settings": (_("Paramètres"), _("Paramètres de la console d’administration")),
}


def _notification_context(user):
    notifications = Notification.objects.filter(user=user)
    return {
        "admin_notifications": notifications.order_by("is_read", "-created_at")[:8],
        "unread_notification_count": notifications.filter(is_read=False).count(),
    }


@ensure_csrf_cookie
@login_required
@user_passes_test(lambda user: user.is_superuser)
def dashboard(request):
    user_stats = CustomUser.objects.aggregate(
        total_patients=Count(
            "id",
            filter=Q(user_type="patient", is_superuser=False),
        ),
    )
    psychologist_stats = PsychologueProfile.objects.aggregate(
        verified_psychologues=Count(
            "id",
            filter=Q(
                is_verified=True,
                user__user_type="psychologue",
                user__is_active=True,
            ),
        ),
        pending_verifications=Count(
            "id",
            filter=Q(
                is_verified=False,
                verification_status="pending",
                user__user_type="psychologue",
            ),
        ),
    )
    consultation_stats = Consultation.objects.aggregate(
        active_appointments=Count(
            "id",
            filter=Q(
                status__in=[
                    Consultation.Status.CONFIRMED,
                    Consultation.Status.IN_PROGRESS,
                ]
            ),
        ),
        total_sessions=Count(
            "id",
            filter=Q(status=Consultation.Status.COMPLETED),
        ),
    )

    unverified_psychologues = (
        PsychologueProfile.objects.filter(
            is_verified=False,
            verification_status="pending",
            user__user_type="psychologue",
        )
        .select_related("user")
        .order_by("-created_at")[:5]
    )
    recent_reports = (
        Report.objects.filter(is_resolved=False)
        .select_related("reporter", "target")
        .order_by("-created_at")[:3]
    )
    unresolved_report_count = Report.objects.filter(is_resolved=False).count()

    context = {
        **user_stats,
        **psychologist_stats,
        **consultation_stats,
        "unverified_psychologues": unverified_psychologues,
        "recent_reports": recent_reports,
        "unresolved_report_count": unresolved_report_count,
        **_notification_context(request.user),
        "admin_section": "dashboard",
    }
    return render(request, "admin_panel/dashboard.html", context)


@login_required
@user_passes_test(lambda user: user.is_superuser)
def admin_section(request, section):
    if section not in ADMIN_SECTIONS:
        raise Http404

    users = CustomUser.objects.all().order_by("last_name", "first_name", "username")
    psychologues = PsychologueProfile.objects.select_related("user").order_by(
        "user__last_name", "user__first_name"
    )
    consultations = Consultation.objects.select_related(
        "patient", "psychologue"
    ).order_by("-date", "-start_time")
    reports = Report.objects.select_related("reporter", "target").order_by(
        "-created_at"
    )
    contact_messages = ContactMessage.objects.all()

    rows = {
        "users": users,
        "patients": users.filter(user_type="patient"),
        "psychologues": psychologues,
        "verifications": psychologues.filter(
            is_verified=False,
            verification_status="pending",
            user__user_type="psychologue",
        ),
        "appointments": consultations,
        "reports": reports,
        "contact_messages": contact_messages,
    }.get(section, ())

    statistics = {
        "total_patients": CustomUser.objects.filter(
            user_type="patient",
            is_superuser=False,
        ).count(),
        "verified_psychologues": psychologues.filter(
            is_verified=True,
            user__user_type="psychologue",
            user__is_active=True,
        ).count(),
        "pending_verifications": psychologues.filter(
            is_verified=False,
            verification_status="pending",
            user__user_type="psychologue",
        ).count(),
        "active_appointments": consultations.filter(
            status__in=[Consultation.Status.CONFIRMED, Consultation.Status.IN_PROGRESS]
        ).count(),
        "total_sessions": consultations.filter(
            status=Consultation.Status.COMPLETED
        ).count(),
        "unresolved_reports": reports.filter(is_resolved=False).count(),
    }

    return render(
        request,
        "admin_panel/section.html",
        {
            "section": section,
            "section_title": ADMIN_SECTIONS[section][0],
            "section_description": ADMIN_SECTIONS[section][1],
            "admin_sections": [
                ("dashboard", _("Tableau de bord"), "fa-th-large", "dashboard"),
                ("users", _("Utilisateurs"), "fa-users", "admin_users"),
                ("patients", _("Patients"), "fa-user", "admin_patients"),
                ("psychologues", _("Psychologues"), "fa-user-md", "admin_psychologues"),
                (
                    "verifications",
                    _("Vérifications"),
                    "fa-clipboard-check",
                    "admin_verifications",
                ),
                (
                    "appointments",
                    _("Rendez-vous"),
                    "fa-calendar-alt",
                    "admin_appointments",
                ),
                ("statistics", _("Statistiques"), "fa-chart-bar", "admin_statistics"),
                (
                    "reports",
                    _("Signalements"),
                    "fa-exclamation-circle",
                    "admin_reports",
                ),
                (
                    "contact_messages",
                    _("Messages de contact"),
                    "fa-envelope",
                    "admin_contact_messages",
                ),
                ("settings", _("Paramètres"), "fa-cog", "admin_settings"),
            ],
            "rows": rows,
            "statistics": statistics,
            "pending_verifications": statistics["pending_verifications"],
            "unresolved_report_count": statistics["unresolved_reports"],
            **_notification_context(request.user),
        },
    )


# ✅✅✅ الدالة المصححة لعرض تفاصيل التحقق ✅✅✅
@login_required
@user_passes_test(lambda user: user.is_staff or user.is_superuser)
def psychologist_verification_detail(request, profile_id):
    profile = get_object_or_404(
        PsychologueProfile.objects.select_related("user"),
        pk=profile_id,
        user__user_type="psychologue",
    )

    # ✅ جلب الوثائق من الموديل الصحيح باستخدام العلاقة الصحيحة
    docs_qs = Document.objects.filter(psychologue=profile.user).order_by("-date_depot")

    # ✅ قاموس لتحويل رموز نوع الوثيقة إلى تسميات مفهومة للواجهة
    doc_labels = {
        "diplome": _("Diploma"),
        "carte_ordre": _("Professional registration"),
        "piece_identite": _("Identity document"),
    }

    documents = []
    for doc in docs_qs:
        if not doc.fichier:
            continue

        file_ext = Path(doc.fichier.name).suffix.lower()
        is_image = file_ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
        is_pdf = file_ext == ".pdf"

        document_url = reverse(
            "protected_media_document", kwargs={"path": doc.fichier.name}
        )

        # ✅ إضافة 'id' ضروري جداً لعمل زر الحذف في القالب
        documents.append(
            {
                "id": doc.id,
                "label": doc_labels.get(doc.type_document, doc.type_document),
                "url": document_url,
                "download_url": f"{document_url}?download=1",
                "is_image": is_image,
                "is_pdf": is_pdf,
            }
        )

    # معالجة طلبات القبول والرفض
    if request.method == "POST":
        action = request.POST.get("action")
        reason = request.POST.get("reason", "").strip()

        if request.POST.get("confirm") != "yes":
            return JsonResponse(
                {"status": "error", "message": _("Please confirm this decision.")},
                status=400,
            )
        if action not in {"accept", "reject"}:
            return JsonResponse(
                {"status": "error", "message": _("Invalid decision.")},
                status=400,
            )
        if action == "reject" and not reason:
            return JsonResponse(
                {"status": "error", "message": _("A rejection reason is required.")},
                status=400,
            )
        if profile.verification_status != "pending":
            messages.error(request, _("This application has already been processed."))
            return redirect("admin_verifications")

        with transaction.atomic():
            profile.verification_status = (
                "approved" if action == "accept" else "rejected"
            )
            profile.is_verified = action == "accept"
            profile.verification_date = timezone.now() if action == "accept" else None
            profile.rejection_reason = reason if action == "reject" else ""
            profile.save(
                update_fields=[
                    "verification_status",
                    "is_verified",
                    "verification_date",
                    "rejection_reason",
                    "updated_at",
                ]
            )

            if action == "accept":
                profile.user.is_active = True
                profile.user.save(update_fields=["is_active"])

            title = (
                _("Psychologist profile approved")
                if action == "accept"
                else _("Psychologist profile needs changes")
            )
            message = (
                _("Your MindWell professional profile has been approved.")
                if action == "accept"
                else _("Your profile was not approved. Reason: %(reason)s")
                % {"reason": reason}
            )

            Notification.objects.create(
                user=profile.user,
                title=title,
                message=message,
                url=reverse("accounts:psychologue_dashboard"),
            )

        email_warning = ""
        if profile.user.email:
            try:
                sent_count = send_mail(
                    subject=str(title),
                    message=str(message),
                    from_email=None,
                    recipient_list=[profile.user.email],
                    fail_silently=False,
                )
                if sent_count != 1:
                    logger.error(
                        "Could not send verification email for profile %s", profile.pk
                    )
                    email_warning = _(" The email notification could not be sent.")
            except Exception:
                logger.exception("Email error for profile %s", profile.pk)
                email_warning = _(" The email notification could not be sent.")
        else:
            email_warning = _(" No email address available.")

        messages.success(
            request,
            (
                _("The psychologist was approved.")
                if action == "accept"
                else _("The psychologist application was rejected.")
            )
            + email_warning,
        )
        return redirect("admin_verifications")

    return render(
        request,
        "admin_panel/psychologist_verification_detail.html",
        {
            "profile": profile,
            "documents": documents,
            "is_pending": profile.verification_status == "pending",
            **_notification_context(request.user),
        },
    )


@login_required
@user_passes_test(lambda user: user.is_staff or user.is_superuser)
def protected_media_document(request, path):
    media_root = Path(settings.MEDIA_ROOT).resolve()

    # ✅ تصحيح المسار: إزالة التكرار إذا كان موجوداً
    if path.startswith("documents/psychologues/"):
        clean_path = path.replace("documents/psychologues/", "", 1)
    else:
        clean_path = path

    # ✅ بناء المسار الصحيح بناءً على البنية الفعلية للتخزين
    file_path = (media_root / "documents" / "psychologues" / clean_path).resolve()

    # التحقق الأمني
    allowed_root = (media_root / "documents" / "psychologues").resolve()
    if not str(file_path).startswith(str(allowed_root)):
        raise Http404("Access denied")

    try:
        file_handle = file_path.open("rb")
    except FileNotFoundError:
        raise Http404("File not found")

    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    response = FileResponse(
        file_handle,
        as_attachment=request.GET.get("download") == "1",
        filename=file_path.name,
        content_type=content_type,
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


# ✅✅✅ دالة حذف الوثيقة المصححة ✅✅✅
@login_required
@user_passes_test(lambda user: user.is_staff or user.is_superuser)
@require_POST
def delete_verification_document(request, doc_id):
    """حذف وثيقة تحقق مع إعادة التوجيه لإظهار رسالة النجاح"""
    document = get_object_or_404(Document, pk=doc_id)

    # تحقق أمني: التأكد من أن الوثيقة تخص طبيباً قيد التحقق
    if not hasattr(document.psychologue, "psychologueprofile"):
        messages.error(request, _("Invalid document."))
        return redirect("admin_verifications")

    profile = document.psychologue.psychologueprofile
    if profile.verification_status != "pending":
        messages.error(
            request, _("Cannot delete documents for processed applications.")
        )
        return redirect("psychologist_verification_detail", profile_id=profile.pk)

    # حذف الملف الفعلي من السيرفر أولاً ثم السجل من قاعدة البيانات
    if document.fichier:
        document.fichier.delete(save=False)
    document.delete()

    messages.success(request, _("Document deleted successfully."))
    # إعادة التوجيه لنفس الصفحة لتحديث القائمة وإظهار الرسالة الخضراء
    return redirect("psychologist_verification_detail", profile_id=profile.pk)


@login_required
@user_passes_test(lambda user: user.is_staff or user.is_superuser)
def notifications_page(request):
    return render(
        request,
        "admin_panel/notifications.html",
        {
            "notifications": Notification.objects.filter(user=request.user).order_by(
                "is_read", "-created_at"
            ),
            **_notification_context(request.user),
        },
    )


@login_required
@user_passes_test(lambda user: user.is_staff or user.is_superuser)
@require_POST
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(
        Notification,
        pk=notification_id,
        user=request.user,
    )
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    target_url = notification.url or reverse("admin_notifications")
    if not url_has_allowed_host_and_scheme(
        target_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return JsonResponse(
            {"status": "error", "message": _("Invalid notification link.")}, status=400
        )
    return JsonResponse({"status": "success", "url": target_url})


@login_required
@user_passes_test(lambda user: user.is_staff or user.is_superuser)
@require_POST
def mark_all_notifications_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({"status": "success"})


@login_required
@user_passes_test(lambda user: user.is_superuser)
@require_POST
def verify_psychologue_api(request, id):
    if request.content_type != "application/json" or request.POST:
        patient_input = request.POST.get("patient_id")
        if patient_input:
            try:
                patient = CustomUser.objects.get(
                    id=int(patient_input), user_type="patient"
                )
            except (ValueError, CustomUser.DoesNotExist):
                return JsonResponse(
                    {
                        "status": "error",
                        "message": "Patient introuvable ou ID invalide.",
                    },
                    status=400,
                )
        else:
            return JsonResponse(
                {"status": "error", "message": "patient_id est requis."}, status=400
            )
        action = request.POST.get("action", "accept")
        reason = request.POST.get("reason", "").strip()
    else:
        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse(
                {"status": "error", "message": "Corps JSON invalide."},
                status=400,
            )

        if not isinstance(payload, dict):
            return JsonResponse(
                {"status": "error", "message": "Le corps JSON doit être un objet."},
                status=400,
            )

        if "patient_id" in payload:
            patient_input = payload.get("patient_id")
            if patient_input:
                try:
                    patient = CustomUser.objects.get(
                        id=int(patient_input), user_type="patient"
                    )
                except (ValueError, CustomUser.DoesNotExist):
                    return JsonResponse(
                        {
                            "status": "error",
                            "message": "Patient introuvable ou ID invalide.",
                        },
                        status=400,
                    )
            else:
                return JsonResponse(
                    {"status": "error", "message": "patient_id est requis."}, status=400
                )

        action = payload.get("action")
        reason = (
            payload.get("reason", "").strip()
            if isinstance(payload.get("reason", ""), str)
            else ""
        )

    if not isinstance(action, str) or action not in {"accept", "reject"}:
        return JsonResponse(
            {"status": "error", "message": "Action invalide."},
            status=400,
        )
    if action == "reject" and not reason:
        return JsonResponse(
            {"status": "error", "message": str(_("A rejection reason is required."))},
            status=400,
        )

    with transaction.atomic():
        profile = (
            PsychologueProfile.objects.select_for_update()
            .select_related("user")
            .filter(Q(pk=id) | Q(user__pk=id), user__user_type="psychologue")
            .first()
        )
        if profile is None:
            return JsonResponse(
                {"status": "error", "message": "Psychologue introuvable."},
                status=404,
            )

        target_status = "approved" if action == "accept" else "rejected"
        if profile.verification_status == target_status:
            return JsonResponse(
                {
                    "status": "success",
                    "message": (
                        "Ce psychologue est déjà validé."
                        if action == "accept"
                        else "Ce dossier est déjà refusé."
                    ),
                    "action": action,
                    "id": profile.pk,
                    "verified_count_delta": 0,
                    "pending_count_delta": 0,
                }
            )
        if profile.verification_status != "pending":
            return JsonResponse(
                {"status": "error", "message": "Ce dossier a déjà été traité."},
                status=409,
            )

        if action == "accept":
            profile.is_verified = True
            profile.verification_status = "approved"
            profile.verification_date = timezone.now()
            profile.rejection_reason = ""
            profile.save(
                update_fields=[
                    "is_verified",
                    "verification_status",
                    "verification_date",
                    "rejection_reason",
                    "updated_at",
                ]
            )
            profile.user.is_active = True
            profile.user.save(update_fields=["is_active"])
        else:
            profile.is_verified = False
            profile.verification_status = "rejected"
            profile.verification_date = None
            profile.rejection_reason = reason
            profile.save(
                update_fields=[
                    "is_verified",
                    "verification_status",
                    "verification_date",
                    "rejection_reason",
                    "updated_at",
                ]
            )
        decision_user = profile.user
        profile_id = profile.pk

    if action == "accept":
        notification_title = _("Psychologist profile approved")
        notification_message = _(
            "Your MindWell professional profile has been approved."
        )
    else:
        notification_title = _("Psychologist profile needs changes")
        notification_message = _(
            "Your profile was not approved. Reason: %(reason)s"
        ) % {
            "reason": reason,
        }
    Notification.objects.create(
        user=decision_user,
        title=notification_title,
        message=notification_message,
        url=reverse("accounts:psychologue_dashboard"),
    )

    email_warning = None
    if decision_user.email:
        try:
            sent_count = send_mail(
                subject=str(notification_title),
                message=str(notification_message),
                from_email=None,
                recipient_list=[decision_user.email],
                fail_silently=False,
            )
            if sent_count != 1:
                email_warning = _(" L'e-mail de bienvenue n'a pas pu être envoyé.")
        except Exception:
            logger.exception(
                "Could not send psychologist verification email for profile %s",
                profile_id,
            )
            email_warning = _(" L'e-mail de bienvenue n'a pas pu être envoyé.")
    else:
        email_warning = _(" No email address is available for this psychologist.")

    return JsonResponse(
        {
            "status": "success",
            "message": (
                str(_("The psychologist was approved.")) + (email_warning or "")
                if action == "accept"
                else str(_("The psychologist application was rejected."))
            ),
            "action": action,
            "id": profile_id,
            "verified_count_delta": 1 if action == "accept" else 0,
            "pending_count_delta": -1,
        }
    )


@login_required
@user_passes_test(lambda user: user.is_superuser)
@require_POST
def resolve_report_api(request, id):
    report = Report.objects.filter(pk=id).first()
    if report is None:
        return JsonResponse(
            {"status": "error", "message": "Signalement introuvable."},
            status=404,
        )
    if report.is_resolved:
        return JsonResponse(
            {"status": "error", "message": "Ce signalement est déjà résolu."},
            status=409,
        )
    report.is_resolved = True
    report.save(update_fields=["is_resolved"])
    return JsonResponse(
        {
            "status": "success",
            "message": "Le signalement a été marqué comme résolu.",
        }
    )
