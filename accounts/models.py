from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.files.storage import storages


def get_psychologist_photo_storage():
    return storages["psychologist_photos"]


class CustomUser(AbstractUser):
    USER_TYPE_CHOICES = (
        ("patient", "Patient"),
        ("psychologue", "Psychologue"),
        ("admin", "Administrateur"),
    )
    user_type = models.CharField(
        max_length=20, choices=USER_TYPE_CHOICES, default="patient"
    )
    phone = models.CharField(max_length=20, blank=True, null=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    preferred_language = models.CharField(
        max_length=10,
        default="fr",
        choices=[("fr", "Français"), ("ar", "العربية"), ("en", "English")],
    )

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.get_user_type_display()})"


class Conversation(models.Model):
    psychologue = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="conversations_as_psychologue",
    )
    patient = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="conversations_as_patient"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("psychologue", "patient")
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Conversation: {self.psychologue} - {self.patient}"


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    sender = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="sent_messages"
    )
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self):
        return f"Message from {self.sender} at {self.timestamp}"


class Call(models.Model):
    TYPE_CHOICES = [
        ("video", "Vidéo"),
        ("audio", "Audio"),
    ]
    STATUS_CHOICES = [
        ("scheduled", "Planifiée"),
        ("ongoing", "En cours"),
        ("completed", "Terminée"),
        ("cancelled", "Annulée"),
    ]

    psychologue = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="calls_as_psychologue"
    )
    patient = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="calls_as_patient"
    )
    call_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default="video")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="scheduled"
    )
    room_name = models.CharField(max_length=255, unique=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Call: {self.psychologue} - {self.patient}"


class PatientProfile(models.Model):
    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, related_name="patient_profile"
    )
    medical_history = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Patient: {self.user.first_name}"


class PsychologueProfile(models.Model):
    SESSION_DURATION_CHOICES = (
        (45, "45 minutes"),
        (50, "50 minutes"),
        (60, "60 minutes"),
        (75, "75 minutes"),
    )
    SPECIALTY_CHOICES = (
        ("clinique", "Psychologie clinique"),
        ("tcc", "TCC"),
        ("psychanalyse", "Psychanalyse"),
        ("systemique", "Systémique"),
        ("humaniste", "Humaniste"),
        ("integrative", "Intégrative"),
        ("emdr", "EMDR"),
        ("enfant_ado", "Enfant et Adolescent"),
        ("travail", "Psychologie du travail"),
        ("addictologie", "Addictologie"),
        ("autre", "Autre"),
    )
    CONSULTATION_MODE_CHOICES = (
        ("online", "En ligne uniquement"),
        ("cabinet", "En cabinet uniquement"),
        ("both", "Les deux"),
    )

    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, related_name="psychologue_profile"
    )
    title = models.CharField(max_length=100, default="Psychologue clinicien")
    specialty = models.CharField(
        max_length=50, choices=SPECIALTY_CHOICES, default="clinique"
    )
    sub_specialties = models.CharField(max_length=255, blank=True, null=True)
    diploma = models.CharField(max_length=200, blank=True, null=True)
    university = models.CharField(max_length=200, blank=True, null=True)
    graduation_year = models.IntegerField(blank=True, null=True)
    experience_years = models.IntegerField(default=0)
    biography = models.TextField(blank=True, null=True)
    languages = models.CharField(max_length=100, default="Français, Arabe")
    registration_number = models.CharField(max_length=50, blank=True, null=True)
    rpps = models.CharField(max_length=50, blank=True, null=True)
    adeli = models.CharField(max_length=50, blank=True, null=True)
    consultation_mode = models.CharField(
        max_length=10, choices=CONSULTATION_MODE_CHOICES, default="both"
    )
    city = models.CharField(max_length=100, blank=True, null=True)
    hourly_rate = models.DecimalField(max_digits=6, decimal_places=2, default=3000.00)
    session_duration = models.IntegerField(
        default=45,
        choices=SESSION_DURATION_CHOICES,
    )
    work_days = models.CharField(max_length=100, default="Lundi - Vendredi")
    work_hours = models.CharField(max_length=100, default="08h00 - 17h00")
    diploma_file = models.FileField(
        upload_to="psychologues/docs/diplomas/", blank=True, null=True
    )
    id_document_file = models.FileField(
        upload_to="psychologues/docs/ids/", blank=True, null=True
    )
    registration_file = models.FileField(
        upload_to="psychologues/docs/registrations/", blank=True, null=True
    )
    is_verified = models.BooleanField(default=False)
    verification_status = models.CharField(
        max_length=10,
        choices=[
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="pending",
        db_index=True,
    )
    verification_date = models.DateTimeField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True)
    average_rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
    )
    review_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    photo = models.ImageField(
        storage=get_psychologist_photo_storage,
        upload_to="psychologues/photos/",
        null=True,
        blank=True,
        verbose_name="Photo de profil",
    )

    class Meta:
        verbose_name = "Profil Psychologue"
        verbose_name_plural = "Profils Psychologues"

    def __str__(self):
        return f"Dr. {self.user.first_name} {self.user.last_name}"


class Notification(models.Model):
    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="notifications"
    )
    title = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    url = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notification for {self.user} - {self.message[:50]}"


# ✅ تم حذف كلاس Appointment نهائياً من هنا لتجنب الازدواجية


class ClinicalRecord(models.Model):
    # ✅ استخدام String Reference لتجنب Circular Import مع Consultation
    patient = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="clinical_records"
    )
    psychologue = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="clinical_records_created"
    )
    consultation = models.ForeignKey(
        "consultations.Consultation",  # ✅ مرجع نصي بدلاً من استيراد مباشر
        on_delete=models.CASCADE,
        related_name="clinical_records",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=200)
    notes = models.TextField()
    diagnosis = models.TextField(blank=True, null=True)
    treatment_plan = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.patient.get_full_name()}"


class ConsultationNote(models.Model):
    """Manual note written by a psychologist after a consultation.

    Two strictly separated kinds:

    * ``PATIENT`` — shareable with the patient. Only persisted/sent explicitly;
      the patient sees it (and gets a notification) once ``sent_at`` is set.
    * ``PROFESSIONAL`` — private observations, never visible to the patient and
      never notified. Access is enforced in the views/querysets, never only in
      templates.

    This is independent of any AI analysis (``ai_service``).
    """

    class NoteType(models.TextChoices):
        PATIENT = "patient", "Note destinée au patient"
        PROFESSIONAL = "professional", "Note professionnelle privée"

    patient = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="consultation_notes_as_patient",
        limit_choices_to={"user_type": "patient"},
    )
    psychologue = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="consultation_notes_as_psychologue",
        limit_choices_to={"user_type": "psychologue"},
    )
    consultation = models.ForeignKey(
        "consultations.Consultation",
        on_delete=models.SET_NULL,
        related_name="consultation_notes",
        null=True,
        blank=True,
    )
    note_type = models.CharField(
        max_length=20,
        choices=NoteType.choices,
        default=NoteType.PROFESSIONAL,
        db_index=True,
    )
    content = models.TextField()
    # Set when a PATIENT note is explicitly sent; NULL for private notes and
    # for drafts not yet sent. A PATIENT note is only visible to the patient
    # once this is set.
    sent_at = models.DateTimeField(null=True, blank=True)
    # Retraction (audit trail): a sent PATIENT note can be retracted by its
    # author. The row and clinical history are kept; the content is hidden from
    # the patient and the notification is updated (never deleted).
    retracted_at = models.DateTimeField(null=True, blank=True)
    retraction_reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["patient", "note_type"]),
            models.Index(fields=["psychologue", "note_type"]),
        ]

    def __str__(self):
        return f"{self.get_note_type_display()} — {self.patient.get_full_name()}"

    @property
    def is_visible_to_patient(self):
        return (
            self.note_type == self.NoteType.PATIENT
            and self.sent_at is not None
            and self.retracted_at is None
        )

    @property
    def is_retracted(self):
        return self.retracted_at is not None


class TreatmentPlan(models.Model):
    STATUS = [
        ("active", "En cours"),
        ("improving", "En amélioration"),
        ("stable", "Stabilisé"),
        ("done", "Terminé"),
    ]

    patient = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="plans_as_patient"
    )
    psychologue = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="plans_as_psy"
    )
    title = models.CharField(max_length=150)
    status = models.CharField(max_length=12, choices=STATUS, default="active")
    sessions_planned = models.PositiveIntegerField(default=8)
    patient_note = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def progress(self):
        total = self.goals.count()
        if total == 0:
            return 0
        return int(100 * self.goals.filter(is_done=True).count() / total)


class TreatmentGoal(models.Model):
    plan = models.ForeignKey(
        TreatmentPlan, on_delete=models.CASCADE, related_name="goals"
    )
    label = models.CharField(max_length=200)
    is_done = models.BooleanField(default=False)

    def __str__(self):
        return f"Goal: {self.label} ({'Done' if self.is_done else 'Pending'})"
