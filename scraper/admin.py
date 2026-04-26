from django.contrib import admin
from .models import ScraperJob


@admin.register(ScraperJob)
class ScraperJobAdmin(admin.ModelAdmin):
    list_display = ['search_term', 'country', 'status', 'total_leads', 'created_at']
    list_filter = ['status']
    readonly_fields = ['job_id', 'created_at', 'updated_at']
