from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("users/", views.admin_section, {"section": "users"}, name="admin_users"),
    path("patients/", views.admin_section, {"section": "patients"}, name="admin_patients"),
    path("psychologues/", views.admin_section, {"section": "psychologues"}, name="admin_psychologues"),
    path("verifications/", views.admin_section, {"section": "verifications"}, name="admin_verifications"),
    path(
        "verifications/<int:profile_id>/",
        views.psychologist_verification_detail,
        name="admin_verification_detail",
    ),
    path("appointments/", views.admin_section, {"section": "appointments"}, name="admin_appointments"),
    path("statistics/", views.admin_section, {"section": "statistics"}, name="admin_statistics"),
    path("reports/", views.admin_section, {"section": "reports"}, name="admin_reports"),
    path("contact-messages/", views.admin_section, {"section": "contact_messages"}, name="admin_contact_messages"),
    path("notifications/", views.notifications_page, name="admin_notifications"),
    path(
        "notifications/<int:notification_id>/read/",
        views.mark_notification_read,
        name="admin_mark_notification_read",
    ),
    path(
        "notifications/read-all/",
        views.mark_all_notifications_read,
        name="admin_mark_all_notifications_read",
    ),
   
    path(
        'verifications/document/<int:doc_id>/delete/',
        views.delete_verification_document,
        name='delete_verification_document'
    ),
   
   
    path("settings/", views.admin_section, {"section": "settings"}, name="admin_settings"),
]