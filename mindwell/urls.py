from django.contrib import admin
from django.urls import path, include
from django.conf.urls.i18n import i18n_patterns
from django.conf import settings
from django.conf.urls.static import static
from django.conf import settings
from django.views.generic import RedirectView
from . import views
from admin_panel import views as admin_panel_views


urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
    path(
        'accounts/',
        RedirectView.as_view(pattern_name='accounts:choose_account_type'),
    ),
    path(
        'admin/api/verify-psychologue/<int:id>/',
        admin_panel_views.verify_psychologue_api,
        name='verify_psychologue_api',
    ),
    path(
        'admin/api/reports/<int:id>/resolve/',
        admin_panel_views.resolve_report_api,
        name='resolve_report_api',
    ),
    path("admin/", admin.site.urls),

    path("fr/", RedirectView.as_view(url="/", permanent=False), name="home_fr"),
    path('', include('core.urls')),
    path("ai-service/", include('ai_service.urls', namespace='ai_service')),
    path("admin-panel/", include("admin_panel.urls")),
    path('consultations/', include('consultations.urls')),
    
    path('appointments/' , include('appointments.urls' )),
    ]
urlpatterns += [
    path(
        'media/psychologues/docs/<path:path>',
        admin_panel_views.protected_media_document,
        name='protected_media_document',
    ),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


urlpatterns += i18n_patterns(
    path("accounts/", include("accounts.urls")),
    path("appointment/<uuid:consultation_id>/confirm/", views.confirm_appointment, name="confirm_appointment"),
    path("payment/<uuid:consultation_id>/", views.payment_page, name="payment_page"),
    path("payment/process/<uuid:consultation_id>/", views.process_payment, name="process_payment"),
    path("payment/success/<uuid:consultation_id>/", views.payment_success, name="payment_success"),
    path("", views.home, name="home"),
    path("comment-ca-marche/", views.comment_ca_marche, name="comment_ca_marche"),
    path("nos-specialistes/", views.nos_specialistes, name="nos_specialistes"),
    path("about/", views.about, name="about"),
    path("ethique/", views.ethics, name="ethics"),
    path("faq/", views.faq, name="faq"),
    path("psychologists/", views.psychologists, name="psychologists"),
    path("dashboard/patient/", views.patient_dashboard, name="patient_dashboard"),
    path("dashboard/psychologue/", views.psychologue_dashboard, name="psychologue_dashboard"),
    path("specialites/<slug:slug>/", views.specialite_detail, name="specialite_detail"),
    path("specialties/", views.specialties, name="specialties"),
    path("psychologists/", views.psychologists, name="psychologists"),
    path("psychologist/<int:psychologist_id>/", views.psychologist_detail, name="psychologist_detail"),
    path("booking/<int:psychologist_id>/", views.booking, name="booking"),
    path("booking/confirm/", views.confirm_booking, name="confirm_booking"),

    path("patient-file/<int:patient_id>/", views.patient_file, name="patient_file"),
    path("tarifs/", views.tarifs, name="tarifs"),
    path("carriere/", views.carriere, name="carriere"),
    path("presse/", views.presse, name="presse"),
    path("contact/", views.contact, name="contact"),
    path("urgence/", views.urgence, name="urgence"),
    path("aide/", views.aide, name="aide"),
    path("confidentialite/", views.confidentialite, name="confidentialite"),
    path("cgv/", views.cgv, name="cgv"),
    path("mentions-legales/", views.mentions_legales, name="mentions_legales"),
    path("cookies/", views.cookies, name="cookies"),
    path("analyze-page/", views.ai_analyze_consultation, name="ai_analyze_consultation"),
    path("blog/", views.blog, name="blog"),
    path("blog/sante-mentale/", views.article_sante_mentale, name="article_sante_mentale"),
    path("blog/stress/", views.article_stress, name="article_stress"),
    path("blog/psychologue/", views.article_psychologue, name="article_psychologue"),
    path("blog/anxiete/", views.article_anxiete, name="article_anxiete"),
    path("blog/teleconsultation/", views.article_teleconsultation, name="article_teleconsultation"),
    path("blog/bien-etre/", views.article_bien_etre, name="article_bien_etre"),

    prefix_default_language=False
)


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)