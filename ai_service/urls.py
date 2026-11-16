from django.urls import path
from . import views

app_name = "ai_service"

urlpatterns = [
    path("analyze/", views.analyze_view, name="analyze_consultation"),
    path("support-chat/", views.support_chat, name="support_chat"),
    path("support-chat/send/", views.send_support_message, name="send_support_message"),
    path("support-chat/history/", views.support_chat_history, name="support_chat_history"),
    path(
        "support-chat/<int:conversation_id>/",
        views.support_chat_detail,
        name="support_chat_detail",
    ),
    path(
        "support-chat/<int:conversation_id>/delete/",
        views.delete_support_conversation,
        name="delete_support_conversation",
    ),
    path(
        "support-chat/<int:conversation_id>/export/",
        views.export_support_conversation,
        name="export_support_conversation",
    ),
    path("stress-assessment/", views.stress_assessment, name="stress_assessment"),
    path(
        "stress-assessment/<int:result_id>/",
        views.stress_assessment_result,
        name="stress_assessment_result",
    ),
    path(
        "stress-assessment/<str:instrument>/",
        views.stress_assessment_take,
        name="stress_assessment_take",
    ),
    path("summaries/", views.ai_summaries_dashboard, name="ai_summaries_dashboard"),
    path(
        "generate-summary/<uuid:consultation_id>/",
        views.generate_session_summary_view,
        name="generate_session_summary",
    ),
    path(
        "generate-evolution/<int:patient_id>/",
        views.generate_evolution_report_view,
        name="generate_evolution_report",
    ),
    path("patient-file/<int:patient_id>/", views.patient_file, name="patient_file"),
    # AI Panel endpoints (psychologist only)
    path(
        "consultation/<uuid:consultation_id>/analyze-keywords/",
        views.ai_analyze_keywords,
        name="analyze_keywords",
    ),
    path(
        "consultation/<uuid:consultation_id>/analyze-sentiment/",
        views.ai_analyze_sentiment,
        name="analyze_sentiment",
    ),
    path(
        "consultation/<uuid:consultation_id>/generate-summary/",
        views.ai_generate_summary,
        name="ai_generate_summary",
    ),
    path(
        "consultation/<uuid:consultation_id>/save-notes/",
        views.ai_save_notes,
        name="ai_save_notes",
    ),
    path(
        "consultation/<uuid:consultation_id>/analyze-full/",
        views.ai_analyze_full,
        name="analyze_full",
    ),
]
