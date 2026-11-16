from django.db import models


class SupportConversation(models.Model):
    user = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.CASCADE,
        related_name="support_ai_conversations",
    )
    title = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]


class SupportMessage(models.Model):
    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
    ]

    conversation = models.ForeignKey(
        SupportConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class StressAssessmentResult(models.Model):
    LEVEL_CHOICES = [
        ("low", "منخفض"),
        ("moderate", "متوسط"),
        ("high", "مرتفع"),
        ("severe", "شديد"),
    ]

    user = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.CASCADE,
        related_name="stress_assessment_results",
    )
    score = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    level = models.CharField(
        max_length=10, choices=LEVEL_CHOICES, null=True, blank=True
    )
    category_scores = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class MessageAnalysis(models.Model):
    message = models.OneToOneField(
        "accounts.Message", on_delete=models.CASCADE, related_name="analysis"
    )
    sentiment = models.CharField(max_length=50, blank=True)
    risk_level = models.CharField(max_length=50, default="low")
    emotions = models.JSONField(default=list)
    key_points = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)


class ConversationSummary(models.Model):
    conversation = models.OneToOneField(
        "accounts.Conversation", on_delete=models.CASCADE, related_name="ai_summary"
    )
    summary = models.TextField(blank=True)
    themes = models.JSONField(default=list)
    risk_level = models.CharField(max_length=50, default="low")
    updated_at = models.DateTimeField(auto_now=True)


class SessionSummary(models.Model):
    RISK_ASSESSMENT_STATUS_CHOICES = [
        ("assessed", "Evaluated"),
        ("insufficient_information", "Insufficient information"),
    ]

    consultation = models.OneToOneField(
        "consultations.Consultation",
        on_delete=models.CASCADE,
        related_name="ai_session_summary",
    )
    summary = models.TextField(blank=True, help_text="ملخص شامل للحصة")
    sentiment = models.CharField(max_length=20, blank=True)
    themes = models.JSONField(default=list, help_text="المواضيع الرئيسية")
    emotions = models.JSONField(default=list, help_text="المشاعر السائدة")

    risk_level = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        default="low",
        choices=[
            ("low", "منخفض"),
            ("medium", "متوسط"),
            ("high", "عالي"),
        ],
    )

    risk_assessment_status = models.CharField(
        max_length=30,
        choices=RISK_ASSESSMENT_STATUS_CHOICES,
        default="assessed",
    )

    progress_notes = models.TextField(blank=True, help_text="ملاحظات التقدم")
    recommendations = models.TextField(blank=True, help_text="توصيات للجلسة القادمة")
    red_flags = models.JSONField(default=list, help_text="علامات تحذيرية")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        risk_assessment_status="assessed",
                        risk_level__in=["low", "medium", "high"],
                    )
                    | models.Q(
                        risk_assessment_status="insufficient_information",
                        risk_level__isnull=True,
                    )
                ),
                name="session_risk_status_consistent",
            ),
        ]

    def __str__(self):
        return f"ملخص حصة {self.consultation.id} - {self.consultation.date}"


class EvolutionReport(models.Model):
    patient = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.CASCADE,
        related_name="evolution_reports",
    )
    psychologue = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.CASCADE,
        related_name="patient_evolution_reports",
    )
    period_start = models.DateField()
    period_end = models.DateField()
    overall_trend = models.CharField(
        max_length=20,
        default="stable",
        choices=[("improving", "يتحسن"), ("stable", "مستقر"), ("declining", "يتدهور")],
    )
    sessions_count = models.IntegerField(default=0)
    summary = models.TextField(blank=True, help_text="تقرير التطور الشامل")
    risk_evolution = models.JSONField(default=list, help_text="تطور مستوى الخطورة")
    themes_evolution = models.JSONField(default=list, help_text="تطور المواضيع")
    improvements = models.TextField(blank=True, help_text="ما تحسّن")
    concerns = models.TextField(blank=True, help_text="ما يستدعي الانتباه")
    recommendations = models.TextField(blank=True, help_text="توصيات المرحلة القادمة")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"تقرير تطور {self.patient.get_full_name()} - {self.period_end}"
