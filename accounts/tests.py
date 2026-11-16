from django.test import TestCase

# Create your tests here.
# accounts/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models
from mindwell.models import Specialite  # ربط مع الموديل الموجود

class CustomUser(AbstractUser):
    """
    المستخدم المخصص - يجمع بين المريض والطبيب
    """
    USER_TYPE_CHOICES = (
        ('patient', 'Patient'),
        ('psychologue', 'Psychologue'),
        ('admin', 'Administrateur'),
    )
    
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='patient')
    phone = models.CharField(max_length=20, blank=True, null=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.user_type})"


class PatientProfile(models.Model):
    """
    الملف الإضافي للمريض
    """
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='patient_profile')
    medical_history = models.TextField(blank=True, null=True, help_text="التاريخ الطبي")
    emergency_contact = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Profil Patient'
        verbose_name_plural = 'Profils Patients'
    
    def __str__(self):
        return f"Profil de {self.user.first_name} {self.user.last_name}"


class PsychologueProfile(models.Model):
    """
    الملف الإضافي للطبيب النفسي - مرتبط بموديل Psychologue الموجود
    """
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='psychologue_profile')
    
    # ربط مع موديل Psychologue الموجود (اختياري)
    public_profile = models.OneToOneField(
        'mindwell.Psychologue', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="البروفايل العام الظاهر في الموقع"
    )
    
    # معلومات مهنية
    license_number = models.CharField(max_length=100, blank=True, null=True, help_text="رقم الرخصة المهنية")
    diploma = models.CharField(max_length=255, blank=True, null=True, help_text="الشهادة")
    experience_years = models.IntegerField(default=0)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bio = models.TextField(blank=True, null=True)
    
    # التخصصات
    specialites = models.ManyToManyField(Specialite, blank=True, related_name='psychologue_profiles')
    
    # التحقق
    is_verified = models.BooleanField(default=False, help_text="تم التحقق من الوثائق من طرف الإدارة")
    documents = models.FileField(upload_to='psychologue_documents/', blank=True, null=True, help_text="وثائق التحقق")
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Profil Psychologue'
        verbose_name_plural = 'Profils Psychologues'
    
    def __str__(self):
        return f"Dr. {self.user.first_name} {self.user.last_name}"