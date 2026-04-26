import uuid
from django.db import models


class ScraperJob(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('searching', 'Searching Google Maps'),
        ('fetching', 'Fetching Details'),
        ('cleaning', 'Cleaning Data'),
        ('reading_cv', 'Reading CV'),
        ('analyzing', 'AI Analysis'),
        ('complete', 'Complete'),
        ('error', 'Error'),
    ]

    job_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    search_term = models.CharField(max_length=200)
    country = models.CharField(max_length=100)
    max_results = models.IntegerField(default=60)
    cv_path = models.CharField(max_length=500, blank=True)
    progress = models.IntegerField(default=0)
    progress_message = models.CharField(max_length=500, blank=True)
    log_messages = models.JSONField(default=list)
    total_found = models.IntegerField(default=0)
    total_leads = models.IntegerField(default=0)
    leads_json = models.JSONField(null=True, blank=True)
    ai_analysis = models.TextField(blank=True)
    csv_path = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.search_term} in {self.country} [{self.status}]'
