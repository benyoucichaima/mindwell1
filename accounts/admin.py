from django.contrib import admin
from .models import (
    CustomUser, 
    PatientProfile, 
    PsychologueProfile, 
    Notification, 
    Conversation, 
    Message, 
    Call, 
    ClinicalRecord, 
    TreatmentPlan, 
    TreatmentGoal
    )

admin.site.register(CustomUser)
admin.site.register(PatientProfile)
admin.site.register(PsychologueProfile)
admin.site.register(Notification)
admin.site.register(Conversation)
admin.site.register(Message)
admin.site.register(Call)
admin.site.register(ClinicalRecord)
admin.site.register(TreatmentPlan)
admin.site.register(TreatmentGoal)

