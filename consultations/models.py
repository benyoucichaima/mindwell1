from django.db import models, transaction, IntegrityError
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
import uuid


class Consultation(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'En attente'
        CONFIRMED = 'confirmed', 'Confirmé'
        IN_PROGRESS = 'in_progress', 'En cours'
        COMPLETED = 'completed', 'Terminé'
        CANCELLED = 'cancelled', 'Annulé'
        NO_SHOW = 'no_show', 'Non présenté'

    class SessionType(models.TextChoices):
        VIDEO = 'video', 'Vidéo'
        AUDIO = 'audio', 'Audio'
        CHAT = 'chat', 'Chat'

    class PaymentStatus(models.TextChoices):
        UNPAID = 'unpaid', 'Non payé'
        PAID = 'paid', 'Payé'
        REFUNDED = 'refunded', 'Remboursé'

    class CancellationReason(models.TextChoices):
        PATIENT = 'patient', 'Initié par le patient'
        PSYCHOLOGUE = 'psychologue', 'Initié par le psychologue'
        TECHNICAL = 'technical', 'Problème technique'
        OTHER = 'other', 'Autre'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference_number = models.CharField(max_length=20, unique=True, blank=True)
    
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='patient_consultations',
        limit_choices_to={'user_type': 'patient'}
    )
    psychologue = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='psychologue_consultations',
        limit_choices_to={'user_type': 'psychologue'}
    )
    creneau = models.ForeignKey(
        'Creneau',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='consultations'
    )
    
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    duration_minutes = models.PositiveIntegerField(default=50)
    session_type = models.CharField(
        max_length=10,
        choices=SessionType.choices,
        default=SessionType.VIDEO
    )
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True
    )
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    payment_status = models.CharField(
        max_length=10,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID
    )
    payment_date = models.DateTimeField(null=True, blank=True)
    
    meeting_link = models.URLField(blank=True, null=True)
    meeting_password = models.CharField(max_length=50, blank=True)
    
    patient_notes = models.TextField(blank=True)
    psychologue_notes = models.TextField(blank=True)
    ai_summary = models.TextField(blank=True)
    doctor_only_ai_summary = models.JSONField(null=True, blank=True)
    audio_transcription_consent = models.BooleanField(default=False)
    audio_transcription_consent_at = models.DateTimeField(null=True, blank=True)
    rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    patient_feedback = models.TextField(blank=True)
    
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cancelled_consultations'
    )
    cancellation_reason = models.CharField(
        max_length=20,
        choices=CancellationReason.choices,
        blank=True
    )
    cancellation_details = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    recurring_session = models.ForeignKey(
        'RecurringSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='materialized_consultations',
    )

    # Compensatory ("rattrapage") session support. A free replacement session is
    # owed when a paid consultation is cancelled by the psychologist.
    is_replacement = models.BooleanField(
        default=False, help_text="Séance de rattrapage gratuite"
    )
    replaced_consultation = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='replacements',
        help_text="La séance annulée remplacée",
    )
    replacement_declined_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date à laquelle le patient a refusé la séance de rattrapage",
    )

    class Meta:
        ordering = ['-date', '-start_time']
        verbose_name = 'Consultation'
        verbose_name_plural = 'Consultations'
        indexes = [
            models.Index(fields=['patient', 'status']),
            models.Index(fields=['psychologue', 'status']),
            models.Index(fields=['date', 'start_time']),
        ]

    def __str__(self):
        return f"Consultation #{self.reference_number} - {self.patient.get_full_name()} avec Dr. {self.psychologue.get_full_name()} ({self.date})"

    def clean(self):
        """Prevent overlapping active consultations for the same psychologue."""
        if self.psychologue_id and self.date and self.start_time and self.end_time:
            overlap = Consultation.objects.filter(
                psychologue_id=self.psychologue_id,
                date=self.date,
                status__in=[
                    self.Status.PENDING,
                    self.Status.CONFIRMED,
                    self.Status.IN_PROGRESS,
                ],
                start_time__lt=self.end_time,
                end_time__gt=self.start_time,
            )
            if self.pk:
                overlap = overlap.exclude(pk=self.pk)
            if overlap.exists():
                raise ValidationError(
                    "Cette consultation chevauche un rendez-vous actif."
                )

    def save(self, *args, **kwargs):
        # Compute end_time before any save attempt.
        if self.start_time and self.duration_minutes:
            from datetime import datetime, timedelta
            start_dt = datetime.combine(self.date, self.start_time)
            end_dt = start_dt + timedelta(minutes=self.duration_minutes)
            self.end_time = end_dt.time()

        # Enforce overlap validation for active consultations only, so resaves
        # of cancelled/completed ones can never block cancellation or rejection.
        if self.status in [
            self.Status.PENDING,
            self.Status.CONFIRMED,
            self.Status.IN_PROGRESS,
        ]:
            self.clean()

        if not self.reference_number:
            # UUID suffix instead of a counter: no two consultations can ever
            # compute the same number, so no IntegrityError can occur here.
            today = timezone.now().strftime('%Y')
            self.reference_number = f"MW-{today}-{uuid.uuid4().hex[:8].upper()}"

        super().save(*args, **kwargs)

    def cancel(self, cancelled_by, reason=CancellationReason.OTHER, details=''):
        self.status = self.Status.CANCELLED
        self.cancelled_at = timezone.now()
        self.cancelled_by = cancelled_by
        self.cancellation_reason = reason
        self.cancellation_details = details
        self.save()

    def confirm(self):
        self.status = self.Status.CONFIRMED
        self.save()

    def complete(self):
        self.status = self.Status.COMPLETED
        self.save()

    def is_upcoming(self):
        session_datetime = timezone.make_aware(
            timezone.datetime.combine(self.date, self.start_time)
        )
        return session_datetime > timezone.now() and self.status in [
            self.Status.PENDING, self.Status.CONFIRMED
        ]

    def can_be_cancelled(self):
        if self.status not in [self.Status.PENDING, self.Status.CONFIRMED]:
            return False
        session_datetime = timezone.make_aware(
            timezone.datetime.combine(self.date, self.start_time),
            timezone.get_current_timezone(),
        )
        return session_datetime > timezone.now()

    def get_patient_name(self):
        return self.patient.get_full_name() or self.patient.username

    def get_psychologue_name(self):
        return f"Dr. {self.psychologue.get_full_name()}"


class ConsultationAttachment(models.Model):
    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    file = models.FileField(upload_to='consultations/attachments/%Y/%m/')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    description = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pièce jointe'
        verbose_name_plural = 'Pièces jointes'

    def __str__(self):
        return f"Attachment for {self.consultation.reference_number}"


class ConsultationReview(models.Model):
    consultation = models.OneToOneField(
        Consultation,
        on_delete=models.CASCADE,
        related_name='review'
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    punctuality = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    professionalism = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    empathy = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    is_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Avis'
        verbose_name_plural = 'Avis'

    def __str__(self):
        return f"Avis pour {self.consultation.get_psychologue_name()} - {self.rating}/5"


class DoctorRating(models.Model):
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ratings_given",
        limit_choices_to={"user_type": "patient"},
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ratings_received",
        limit_choices_to={"user_type": "psychologue"},
    )
    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.CASCADE,
        related_name="doctor_ratings",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "doctor", "consultation"],
                name="unique_patient_doctor_consultation_rating",
            ),
        ]

    def clean(self):
        super().clean()
        if self.patient_id and self.patient.user_type != "patient":
            raise ValidationError({"patient": "يجب أن يكون صاحب التقييم مريضاً."})
        if self.doctor_id and self.doctor.user_type != "psychologue":
            raise ValidationError({"doctor": "يجب أن يكون الطبيب أخصائياً نفسياً."})
        if self.consultation_id:
            if (
                self.consultation.patient_id != self.patient_id
                or self.consultation.psychologue_id != self.doctor_id
            ):
                raise ValidationError(
                    "يجب أن تتطابق الاستشارة مع المريض والأخصائي المُقيَّم."
                )
            if self.consultation.status != Consultation.Status.COMPLETED:
                raise ValidationError("لا يمكن تقييم استشارة لم تكتمل بعد.")

    def __str__(self):
        return f"{self.doctor} — {self.rating}/5"


# أضيفي هذا في نهاية ملف consultations/models.py

class PaymentRecord(models.Model):
    METHOD_CHOICES = [
        ('CIB', 'بطاقة CIB'),
        ('EDAHABIA', 'البطاقة الذهبية EDAHABIA'),
    ]
    STATUS_CHOICES = [
        ('pending', 'قيد الانتظار'),
        ('success', 'تم الدفع بنجاح'),
        ('failed', 'فشل الدفع'),
    ]

    consultation = models.OneToOneField(
        'Consultation', 
        on_delete=models.CASCADE, 
        related_name='payment_record'
    )
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    transaction_ref = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name="رقم المعاملة")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='success')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'سجل الدفع'
        verbose_name_plural = 'سجلات الدفع'

    def __str__(self):
        return f"دفع {self.amount} DZD - {self.transaction_ref} ({self.consultation.reference_number})"

class Creneau(models.Model):
    class Statut(models.TextChoices):
        LIBRE = 'libre', 'Disponible'
        RESERVE = 'reserve', 'Réservé'
        BLOQUE = 'bloque', 'Bloqué'
    
    psychologue = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='creneaux',
        limit_choices_to={'user_type': 'psychologue'}
    )
    date = models.DateField()
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    statut = models.CharField(
        max_length=10,
        choices=Statut.choices,
        default=Statut.LIBRE,
        db_index=True
    )
    is_generated = models.BooleanField(default=False, db_index=True)
    is_bookable = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['date', 'heure_debut']
        verbose_name = 'Créneau'
        verbose_name_plural = 'Créneaux'
        unique_together = ['psychologue', 'date', 'heure_debut']
        indexes = [
            models.Index(fields=['psychologue', 'statut']),
            models.Index(fields=['date', 'statut']),
        ]
    
    def __str__(self):
        return f"{self.date} {self.heure_debut}-{self.heure_fin} ({self.get_statut_display()})"
    
    def clean(self, skip_overlap_validation=False):
        """Prevent overlapping time intervals for the same psychologue/date."""
        if skip_overlap_validation:
            return
        if self.psychologue_id and self.date and self.heure_debut and self.heure_fin:
            overlap = Creneau.objects.filter(
                psychologue_id=self.psychologue_id,
                date=self.date,
                heure_debut__lt=self.heure_fin,
                heure_fin__gt=self.heure_debut,
            )
            if self.pk:
                overlap = overlap.exclude(pk=self.pk)
            if overlap.exists():
                raise ValidationError(
                    "Ce créneau chevauche une autre disponibilité existante."
                )

    def save(self, *args, **kwargs):
        # Enforce overlap validation on every direct save (creation and update).
        self.clean(skip_overlap_validation=kwargs.pop('skip_overlap_validation', False))
        super().save(*args, **kwargs)

    def reserver(self):
        if self.statut == self.Statut.LIBRE:
            self.statut = self.Statut.RESERVE
            self.save()
            return True
        return False
    
    def liberer(self):
        self.statut = self.Statut.LIBRE
        self.save()


class WeeklyAvailabilityRule(models.Model):
    WEEKDAY_CHOICES = (
        (0, 'Lundi'),
        (1, 'Mardi'),
        (2, 'Mercredi'),
        (3, 'Jeudi'),
        (4, 'Vendredi'),
        (5, 'Samedi'),
        (6, 'Dimanche'),
    )

    psychologue = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='weekly_availability_rules',
        limit_choices_to={'user_type': 'psychologue'},
    )
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['weekday', 'start_time']
        constraints = [
            models.UniqueConstraint(
                fields=['psychologue', 'weekday', 'start_time'],
                name='week_avail_start_unique',
            ),
            models.CheckConstraint(
                check=models.Q(start_time__lt=models.F('end_time')),
                name='week_avail_interval_ok',
            ),
        ]

    def __str__(self):
        return f"{self.psychologue} {self.get_weekday_display()} {self.start_time}-{self.end_time}"


class AvailabilityException(models.Model):
    class Kind(models.TextChoices):
        CLOSED = 'closed', 'Fermeture'
        REPLACEMENT = 'replacement', 'Remplacement des horaires'
        ADDITIONAL = 'additional', 'Période supplémentaire'

    psychologue = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='availability_exceptions',
        limit_choices_to={'user_type': 'psychologue'},
    )
    date = models.DateField()
    kind = models.CharField(max_length=20, choices=Kind.choices)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'kind', 'start_time']
        indexes = [
            models.Index(
                fields=['psychologue', 'date', 'is_active'],
                name='consultatio_psychol_8d706c_idx',
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(
                        kind='closed',
                        start_time__isnull=True,
                        end_time__isnull=True,
                    )
                    | models.Q(
                        kind__in=['replacement', 'additional'],
                        start_time__isnull=False,
                        end_time__isnull=False,
                        start_time__lt=models.F('end_time'),
                    )
                ),
                name='avail_exception_interval_ok',
            ),
            models.UniqueConstraint(
                fields=['psychologue', 'date'],
                condition=models.Q(kind='closed', is_active=True),
                name='avail_active_closure_unique',
            ),
        ]

    def __str__(self):
        return f"{self.psychologue} {self.date} {self.get_kind_display()}"


class Document(models.Model):
    class TypeDocument(models.TextChoices):
        DIPLOME = 'diplome', 'Diplôme'
        CARTE_ORDRE = 'carte_ordre', 'Carte de l\'ordre'
        AUTRE = 'autre', 'Autre'
    
    class Statut(models.TextChoices):
        EN_ATTENTE = 'en_attente', 'En attente de validation'
        VALIDE = 'valide', 'Validé'
        REJETE = 'rejete', 'Rejeté'
    
    psychologue = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='documents',
        limit_choices_to={'user_type': 'psychologue'}
    )
    type_document = models.CharField(
        max_length=20,
        choices=TypeDocument.choices
    )
    fichier = models.FileField(upload_to='documents/psychologues/%Y/%m/')
    date_depot = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.EN_ATTENTE,
        db_index=True
    )
    admin_validateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents_valides',
        limit_choices_to={'user_type': 'admin'}
    )
    date_validation = models.DateTimeField(null=True, blank=True)
    motif_rejet = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-date_depot']
        verbose_name = 'Document'
        verbose_name_plural = 'Documents'
        indexes = [
            models.Index(fields=['psychologue', 'statut']),
        ]
    
    def __str__(self):
        return f"{self.get_type_document_display()} - {self.psychologue.get_full_name()} ({self.get_statut_display()})"
    
    def valider(self, admin_user):
        self.statut = self.Statut.VALIDE
        self.admin_validateur = admin_user
        self.date_validation = timezone.now()
        self.motif_rejet = ''
        self.save()
        
        all_valides = self.psychologue.documents.exclude(statut=self.Statut.VALIDE).count() == 0
        if all_valides:
            profile = self.psychologue.psychologue_profile
            profile.is_verified = True
            profile.verification_status = 'approved'
            profile.verification_date = self.date_validation
            profile.save(update_fields=[
                'is_verified',
                'verification_status',
                'verification_date',
                'updated_at',
            ])
    
    def rejeter(self, admin_user, motif):
        self.statut = self.Statut.REJETE
        self.admin_validateur = admin_user
        self.date_validation = timezone.now()
        self.motif_rejet = motif
        self.save()
        profile = self.psychologue.psychologue_profile
        profile.is_verified = False
        profile.verification_status = 'pending'
        profile.verification_date = None
        profile.save(update_fields=[
            'is_verified',
            'verification_status',
            'verification_date',
            'updated_at',
        ])


class Message(models.Model):
    class TypeMessage(models.TextChoices):
        TEXTE = 'texte', 'Texte'
        IMAGE = 'image', 'Image'
        FICHIER = 'fichier', 'Fichier'
    
    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    expediteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='messages_envoyes'
    )
    type_message = models.CharField(
        max_length=10,
        choices=TypeMessage.choices,
        default=TypeMessage.TEXTE
    )
    contenu = models.TextField()
    fichier = models.FileField(
        upload_to='messages/attachments/%Y/%m/',
        blank=True,
        null=True
    )
    date_envoi = models.DateTimeField(auto_now_add=True)
    lu = models.BooleanField(default=False)
    date_lecture = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['date_envoi']
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
        indexes = [
            models.Index(fields=['consultation', 'date_envoi']),
            models.Index(fields=['expediteur', 'lu']),
        ]
    
    def __str__(self):
        return f"Message de {self.expediteur.get_full_name()} à {self.date_envoi}"
    
    def marquer_comme_lu(self):
        if not self.lu:
            self.lu = True
            self.date_lecture = timezone.now()
            self.save()


class AIAnalysis(models.Model):
    class Statut(models.TextChoices):
        EN_COURS = 'en_cours', 'En cours de traitement'
        TERMINE = 'termine', 'Terminé'
        ECHEC = 'echec', 'Échec'
    
    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.CASCADE,
        related_name='analyses_ia'
    )
    psychologue_demandeur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='analyses_demandees',
        limit_choices_to={'user_type': 'psychologue'}
    )
    modele_utilise = models.CharField(max_length=50, default='camembert-base')
    statut = models.CharField(
        max_length=10,
        choices=Statut.choices,
        default=Statut.EN_COURS
    )
    emotions = models.JSONField(default=dict, blank=True)
    mots_cles = models.JSONField(default=list, blank=True)
    resume = models.TextField(blank=True)
    themes = models.JSONField(default=list, blank=True)
    nombre_messages_analyses = models.PositiveIntegerField(default=0)
    date_generation = models.DateTimeField(auto_now_add=True)
    duree_traitement = models.DurationField(null=True, blank=True)
    
    class Meta:
        ordering = ['-date_generation']
        verbose_name = 'Analyse IA'
        verbose_name_plural = 'Analyses IA'
        indexes = [
            models.Index(fields=['consultation', 'statut']),
            models.Index(fields=['psychologue_demandeur']),
        ]
    
    def __str__(self):
        return f"Analyse IA #{self.id} - Consultation {self.consultation.reference_number}"
    
    def terminer(self, emotions, mots_cles, resume, themes, nombre_messages, duree):
        self.statut = self.Statut.TERMINE
        self.emotions = emotions
        self.mots_cles = mots_cles
        self.resume = resume
        self.themes = themes
        self.nombre_messages_analyses = nombre_messages
        self.duree_traitement = duree
        self.save()
        
        self.consultation.ai_summary = resume
        self.consultation.save()
    
    def echouer(self):
        self.statut = self.Statut.ECHEC
        self.save()

    
def can_cancel(self):
    """التحقق مما إذا كان يمكن إلغاء الموعد (قبل 24 ساعة)"""

    if self.status in ['cancelled', 'completed']:
        return False
    
    from django.utils import timezone
    session_datetime = timezone.make_aware(
        timezone.datetime.combine(self.date, self.start_time)
    )
    time_until_appointment = session_datetime - timezone.now()
    return time_until_appointment.total_seconds() >= 86400  # 24 ساعة


class RecurringSession(models.Model):
    """A therapy series (e.g. every Tuesday 10:00). Occurrences are planned
    rows in ``RecurringOccurrence``; a concrete ``Consultation`` is only
    materialized when the patient accepts a given occurrence.
    """

    class Status(models.TextChoices):
        PROPOSED = 'proposed', 'Proposée'
        ACTIVE = 'active', 'Active'
        PAUSED = 'paused', 'En pause'
        COMPLETED = 'completed', 'Terminée'
        CANCELLED = 'cancelled', 'Annulée'

    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='recurring_sessions_as_patient',
        limit_choices_to={'user_type': 'patient'},
    )
    psychologue = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='recurring_sessions_as_psychologue',
        limit_choices_to={'user_type': 'psychologue'},
    )
    weekday = models.PositiveSmallIntegerField(
        choices=WeeklyAvailabilityRule.WEEKDAY_CHOICES
    )
    start_time = models.TimeField()
    duration_minutes = models.PositiveIntegerField(default=45)
    start_date = models.DateField()
    end_date = models.DateField()
    occurrence_count = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_recurring_sessions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Reschedule / note request from the patient about the proposed schedule.
    patient_note = models.TextField(blank=True, default='')
    reschedule_requested = models.BooleanField(default=False)
    reschedule_request_at = models.DateTimeField(null=True, blank=True)
    reschedule_reviewed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['patient', 'status']),
            models.Index(fields=['psychologue', 'status']),
            models.Index(fields=['start_date']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_date__gte=models.F('start_date')),
                name='recurring_session_date_order',
            ),
        ]

    def __str__(self):
        return (
            f"Série {self.pk} — {self.patient.get_full_name()} / "
            f"Dr. {self.psychologue.get_full_name()} "
            f"({self.get_weekday_display()} {self.start_time:%H:%M})"
        )


class RecurringOccurrence(models.Model):
    """One planned occurrence of a ``RecurringSession`` on a concrete date.

    ``is_cancelled`` marks a skipped instance (holiday, patient request) without
    destroying the series. A ``Consultation`` is materialized only when the
    patient accepts this occurrence.
    """

    recurring_session = models.ForeignKey(
        RecurringSession,
        on_delete=models.CASCADE,
        related_name='occurrences',
    )
    occurrence_date = models.DateField()
    creneau = models.OneToOneField(
        'Creneau',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recurring_occurrence',
    )
    consultation = models.OneToOneField(
        Consultation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recurring_occurrence',
    )
    is_cancelled = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['recurring_session', 'occurrence_date']
        indexes = [
            models.Index(fields=['recurring_session', 'occurrence_date']),
            models.Index(fields=['consultation']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['recurring_session', 'occurrence_date'],
                name='recurring_occurrence_unique_date',
            ),
        ]

    def __str__(self):
        return f"{self.recurring_session_id} @ {self.occurrence_date} (annulé={self.is_cancelled})"


class ReplacementChangeRequest(models.Model):
    """A patient's request to change the schedule of an owed replacement session.

    Attached to the *owed* consultation shown on the patient's "Séances de
    rattrapage" card (the cancelled, paid session the psychologist cancelled).
    The psychologist sees pending requests in their dashboard and can accept,
    reject, or counter-propose. The patient is notified of the response.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'En attente'
        ACCEPTED = 'accepted', 'Acceptée'
        REJECTED = 'rejected', 'Refusée'
        COUNTER_PROPOSED = 'counter_proposed', 'Contre-proposition'

    replacement_consultation = models.ForeignKey(
        'Consultation',
        on_delete=models.CASCADE,
        related_name='change_requests',
    )
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='replacement_change_requests',
        limit_choices_to={'user_type': 'patient'},
    )
    proposed_date = models.DateTimeField(
        null=True, blank=True, help_text="Date/heure proposée par le patient"
    )
    message = models.TextField(blank=True, help_text="Message du patient")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    psychologist_response = models.TextField(
        blank=True, help_text="Réponse du psychologue"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['patient', 'status']),
        ]

    def __str__(self):
        return (
            f"Changement {self.get_status_display()} — "
            f"{self.patient_id} / consultation {self.replacement_consultation_id}"
        )