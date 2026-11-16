from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

class Specialite(models.Model):
    nom = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(max_length=300, help_text="وصف قصير يظهر تحت العنوان")
    icone = models.CharField(max_length=50, default="fa-brain", help_text="اسم أيقونة FontAwesome، مثال: fa-brain")
    approche = models.TextField(help_text="طريقة العلاج المعتمدة، مثال: TCC (Thérapies Cognitivo-Comportementales)")
    symptomes = models.TextField(help_text="اكتب الأعراض وافصل بينها بفاصلة منقوطة (;)")
    ordre = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['ordre', 'nom']
        verbose_name = 'Spécialité'
        verbose_name_plural = 'Spécialités'
    
    def __str__(self):
        return self.nom
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nom)
        super().save(*args, **kwargs)

    # دالة مساعدة لتحويل النص إلى قائمة لعرضها في القالب
    def get_symptomes_list(self):
        return [s.strip() for s in self.symptomes.split(';') if s.strip()]


class Psychologue(models.Model):
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    photo = models.ImageField(upload_to='psychologues/', blank=True)
    profession = models.CharField(max_length=100, default='Psychologue clinicien')
    presentation = models.TextField()
    evaluation = models.DecimalField(max_digits=3, decimal_places=2, default=5.0)
    disponible = models.BooleanField(default=True)
    
    specialites = models.ManyToManyField(Specialite, related_name='psychologues', blank=True)
    
    class Meta:
        ordering = ['nom']
        verbose_name = 'Psychologue'
        verbose_name_plural = 'Psychologues'
    
    def __str__(self):
        return f"{self.prenom} {self.nom}"


class ContactMessage(models.Model):
    SUBJECT_CHOICES = [
        ("general", _("Question générale")),
        ("consultation", _("Consultation")),
        ("technical", _("Problème technique")),
        ("psychologist", _("Devenir psychologue partenaire")),
        ("other", _("Autre demande")),
    ]

    name = models.CharField(_("Nom complet"), max_length=150)
    email = models.EmailField(_("Adresse e-mail"))
    subject = models.CharField(_("Sujet"), max_length=30, choices=SUBJECT_CHOICES)
    message = models.TextField(_("Message"))
    created_at = models.DateTimeField(_("Date d'envoi"), auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Message de contact")
        verbose_name_plural = _("Messages de contact")

    def __str__(self):
        return f"{self.subject}: {self.name} ({self.email})"