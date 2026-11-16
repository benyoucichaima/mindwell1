from django.urls import path
from . import views
from . import recurring_api
from . import replacement_api

app_name = 'consultations'

urlpatterns = [
    # 1. إدارة التوفر (للأخصائي النفسي)
    path('availability/', views.manage_availability, name='manage_availability'),
    
    # 2. رفع الوثائق الثبوتية
    path('upload-document/', views.upload_document, name='upload_document'),
    
    # 3. غرفة الدردشة الخاصة بالجلسة
    path('chat/<uuid:consultation_id>/', views.consultation_chat, name='consultation_chat'),

    # 3.1 Consentement patient pour la transcription audio
    path(
        '<uuid:consultation_id>/audio-consent/',
        views.update_audio_transcription_consent,
        name='update_audio_transcription_consent',
    ),
    
    # 4. طلب تحليل الذكاء الاصطناعي
    path('<uuid:consultation_id>/ai-analysis/', views.request_ai_analysis, name='request_ai_analysis'),
    
    # 5. API: الحصول على الفترات المتاحة (AJAX)
    # ملاحظة: احتفظنا بـ uuid فقط لأن معرفات المستخدمين في مشروعك تعتمد على UUID
    path('api/slots/<int:psychologue_id>/<str:date_str>/', views.get_available_slots, name='get_available_slots'),

    # 6. Calendrier du médecin (vue mois + vue jour)
    path('availability/calendar/', views.availability_calendar, name='availability_calendar'),

    # 7. Séances récurrentes (API JSON)
    path('api/recurring-sessions/', recurring_api.create_recurring_session_api, name='create_recurring_session'),
    path('api/recurring-sessions/upcoming/', recurring_api.upcoming_recurring_sessions_api, name='upcoming_recurring_sessions'),
    path('api/recurring-sessions/<int:session_id>/cancel/', recurring_api.cancel_recurring_session_api, name='cancel_recurring_session'),
    path('api/recurring-sessions/<int:session_id>/request-change/', recurring_api.request_recurring_change_api, name='request_recurring_change'),
    path('api/recurring-sessions/<int:session_id>/accept/', recurring_api.accept_recurring_session_api, name='accept_recurring_session'),
    path('api/recurring-sessions/<int:session_id>/decline/', recurring_api.decline_recurring_session_api, name='decline_recurring_session'),
    path('api/recurring-occurrences/<int:occurrence_id>/accept/', recurring_api.accept_recurring_occurrence_api, name='accept_recurring_occurrence'),
    path('api/recurring-occurrences/<int:occurrence_id>/skip/', recurring_api.skip_recurring_occurrence_api, name='skip_recurring_occurrence'),

    # 8. Séances de rattrapage (API JSON)
    path('api/replacements/upcoming/', replacement_api.upcoming_replacements_api, name='upcoming_replacements'),
    path('api/replacements/<uuid:consultation_id>/decline/', replacement_api.decline_replacement_api, name='decline_replacement'),
    path('api/replacements/<uuid:replacement_id>/change-request/', replacement_api.submit_change_request_api, name='submit_change_request'),
    path('api/replacement-change-requests/', replacement_api.get_change_requests_api, name='get_change_requests'),
    path('api/replacement-change-requests/<int:request_id>/respond/', replacement_api.respond_to_change_request_api, name='respond_to_change_request'),
]