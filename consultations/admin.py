from django.contrib import admin
from .models import (
    Consultation, ConsultationAttachment, ConsultationReview,
    Creneau, Document, Message, AIAnalysis, PaymentRecord, DoctorRating,
    WeeklyAvailabilityRule, AvailabilityException
)

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('psychologue', 'type_document', 'statut', 'date_depot', 'admin_validateur')
    list_filter = ('statut', 'type_document')
    readonly_fields = ('date_depot', 'statut', 'admin_validateur', 'date_validation', 'motif_rejet')
    actions = ('approve_selected_documents', 'reject_selected_documents')

    @admin.action(description='Approve selected professional documents')
    def approve_selected_documents(self, request, queryset):
        for document in queryset.select_related('psychologue'):
            document.valider(request.user)
        self.message_user(request, 'Selected documents were approved.')

    @admin.action(description='Reject selected professional documents')
    def reject_selected_documents(self, request, queryset):
        for document in queryset.select_related('psychologue'):
            document.rejeter(request.user, 'Rejected by administrator.')
        self.message_user(request, 'Selected documents were rejected.')



@admin.register(WeeklyAvailabilityRule)
class WeeklyAvailabilityRuleAdmin(admin.ModelAdmin):
    list_display = ('psychologue', 'weekday', 'start_time', 'end_time', 'is_active', 'updated_at')
    list_filter = ('psychologue', 'is_active', 'weekday')
    search_fields = ('psychologue__username', 'psychologue__first_name')
    ordering = ('psychologue', 'weekday', 'start_time')
    
@admin.register(AvailabilityException)
class AvailabilityExceptionAdmin(admin.ModelAdmin):
    list_display = ('psychologue', 'date', 'kind', 'start_time', 'end_time', 'is_active')
    list_filter = ('psychologue', 'kind', 'is_active', 'date')
    search_fields = ('psychologue__username',)
    ordering = ('-date',)

@admin.register(Creneau)
class CreneauAdmin(admin.ModelAdmin):
    list_display = ('psychologue', 'date', 'heure_debut', 'heure_fin', 'statut', 'is_generated')
    list_filter = ('statut', 'is_generated', 'date')
    readonly_fields = ('created_at',)


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = ('consultation', 'amount', 'method', 'status', 'transaction_ref', 'created_at')
    list_filter = ('method', 'status', 'created_at')
    search_fields = ('transaction_ref', 'consultation__reference_number')
    readonly_fields = ('created_at',)

@admin.register(DoctorRating)
class DoctorRatingAdmin(admin.ModelAdmin):
    list_display = ('doctor', 'patient', 'rating', 'consultation', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('doctor__first_name', 'doctor__last_name', 'patient__username')
    readonly_fields = ('created_at',)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('consultation', 'expediteur', 'date_envoi', 'lu')
    list_filter = ('lu',)

@admin.register(AIAnalysis)
class AIAnalysisAdmin(admin.ModelAdmin):
    list_display = ('id', 'consultation', 'statut', 'date_generation')
    list_filter = ('statut',)
    readonly_fields = ('date_generation',)



@admin.register(ConsultationAttachment)
class ConsultationAttachmentAdmin(admin.ModelAdmin):
    list_display = ('consultation', 'file', 'uploaded_at')
    readonly_fields = ('uploaded_at',)

@admin.register(ConsultationReview)
class ConsultationReviewAdmin(admin.ModelAdmin):
    list_display = ('consultation', 'rating', 'punctuality', 'professionalism', 'empathy', 'created_at')
    readonly_fields = ('created_at',)