from django.urls import path
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from . import views

app_name = 'accounts'

urlpatterns = [
    # Auth & Registration
    path('choose-account/', views.choose_account_type, name='choose_account_type'),
    path('register-patient/', views.register_patient, name='register_patient'),
    path('register-psychologue/', views.register_psychologue, name='register_psychologue'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path(
        'password-reset/',
        auth_views.PasswordResetView.as_view(
            template_name='registration/password_reset_form.html',
            email_template_name='registration/password_reset_email.html',
            subject_template_name='registration/password_reset_subject.txt',
            success_url=reverse_lazy('accounts:password_reset_done'),
        ),
        name='password_reset',
    ),
    path(
        'password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='registration/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'password-reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='registration/password_reset_confirm.html',
            success_url=reverse_lazy('accounts:password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'password-reset/complete/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='registration/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),

    # Dashboards
    path('dashboard/patient/', views.patient_dashboard, name='patient_dashboard'),
    path('dashboard/psychologue/', views.psychologue_dashboard, name='psychologue_dashboard'),
    path('pending-verification/', views.pending_verification, name='pending_verification'),

    # Patients & Consultations
    path('mes-patients/', views.mes_patients, name='mes_patients'),
    path('rendez-vous/', views.rendez_vous, name='rendez_vous'),
    path('dossiers-cliniques/', views.dossiers_cliniques, name='dossiers_cliniques'),

    # Notes de consultation (rédigées par le psychologue)
    path('notes/', views.psychologue_notes, name='psychologue_notes'),
    path('notes/<int:note_id>/', views.patient_note_detail, name='patient_note_detail'),
    path('notes/<int:note_id>/retract/', views.psychologue_retract_note, name='retract_consultation_note'),

    # Booking & Search
    path('trouver-psychologue/', views.trouver_psychologue, name='trouver_psychologue'),
    path(
        'consultation/<uuid:consultation_id>/rating/',
        views.rate_consultation,
        name='rate_consultation',
    ),
    # ✅ تم التصحيح هنا: تغيير int إلى uuid ليتوافق مع معرفات المستخدمين
    path('book/<int:psychologue_id>/', views.book_consultation, name='book_consultation'),
    path('api/booked-slots/', views.get_booked_slots, name='get_booked_slots'),

    # Appointments Actions
    path('cancel/<uuid:appointment_id>/', views.cancel_patient_appointment, name='cancel_appointment'),
    path(
        'consultation/<uuid:consultation_id>/emergency-cancel/',
        views.emergency_cancel_appointment,
        name='emergency_cancel_appointment',
    ),
    path('confirm/<uuid:consultation_id>/', views.confirm_appointment, name='confirm_appointment'),
    path('reject/<uuid:consultation_id>/', views.reject_appointment, name='reject_appointment'),

    # Payments
    path('payment/<uuid:consultation_id>/', views.payment_page, name='payment_page'),
    path('payment/process/<uuid:consultation_id>/', views.process_payment, name='process_payment'),
    path('payment/success/<uuid:consultation_id>/', views.payment_success, name='payment_success'),

    # Messaging & Calls
    path('messages/', views.messages_list, name='messages_list'),
    path('chat/<int:conversation_id>/', views.chat_room, name='chat_room'),
    path('chat/send/<int:conversation_id>/', views.send_message, name='send_message'),
    path('call/start/<int:patient_id>/', views.start_call, name='start_call'),
    path('ai-panel/<int:conversation_id>/', views.ai_panel, name='ai_panel'),

    # Settings & Profile
    path('parametres/', views.parametres, name='parametres'),
    path('professional-profile/', views.professional_profile, name='professional_profile'),
    path('security-settings/', views.security_settings, name='security_settings'),
    path('delete-account/', views.delete_account, name='delete_account'),
    path('notifications/', views.notifications_list, name='notifications'),
    path(
        'notifications/mark-read/',
        views.mark_notifications_read,
        name='mark_notifications_read',
    ),
]