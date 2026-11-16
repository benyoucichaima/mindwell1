from django.urls import path
from . import views

app_name = 'appointments'

urlpatterns = [
    # الحجز
    path('book/', views.book_appointment, name='book_appointment'),
    path('patient/', views.patient_dashboard, name='patient_dashboard'),
    path('specialist/', views.specialist_dashboard, name='specialist_dashboard'),
    path('accept/<uuid:appointment_id>/', views.accept_appointment, name='accept_appointment'),
    path('reject/<uuid:appointment_id>/', views.reject_appointment, name='reject_appointment'),
    path('cancel/<uuid:appointment_id>/', views.cancel_appointment, name='cancel_appointment'),
    
    # الدفع
    path('payment/<uuid:appointment_id>/', views.payment_page, name='payment_page'),
    path('payment/process/<uuid:appointment_id>/', views.process_payment, name='process_payment'),
    path('payment/success/<uuid:appointment_id>/', views.payment_success, name='payment_success'),
    path('payment/failed/', views.payment_failed, name='payment_failed'),
]