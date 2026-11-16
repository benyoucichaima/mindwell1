from consultations.models import Consultation, PaymentRecord


class Appointment(Consultation):
    """
    Proxy Model: لا ينشئ جدولاً جديداً في قاعدة البيانات.
    يعيد استخدام جدول Consultations الاحترافي كمصدر وحيد للحقيقة.
    يحافظ على الروابط القديمة (URLs, Views) دون كسرها.
    """
    class Meta:
        proxy = True
        verbose_name = 'Rendez-vous'
        verbose_name_plural = 'Rendez-vous'
        ordering = ['-date', '-start_time']


class Payment(PaymentRecord):
    """
    Proxy Model لعمليات الدفع.
    يوجه جميع عمليات الدفع لجدول PaymentRecord المرتبط بـ Consultation.
    """
    class Meta:
        proxy = True
        verbose_name = 'Paiement'
        verbose_name_plural = 'Paiements'
        ordering = ['-created_at']