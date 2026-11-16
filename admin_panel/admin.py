from django.contrib import admin
from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'reporter', 'target', 'is_resolved', 'created_at')
    list_filter = ('is_resolved', 'created_at')
    search_fields = (
        'reporter__username',
        'target__username',
        'reason',
    )
    readonly_fields = ('created_at',)
