from django.db import models
from django.conf import settings


class Resume(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='resumes'
    )
    job_role = models.CharField(max_length=100)
    years_experience = models.FloatField()
    file = models.FileField(upload_to='resumes/')
    score = models.FloatField(null=True, blank=True)
    feedback = models.JSONField(null=True, blank=True)
    analysis_data = models.JSONField(default=dict, blank=True)
    strengths = models.JSONField(default=list, blank=True)
    weaknesses = models.JSONField(default=list, blank=True)
    improvement_plan = models.JSONField(default=dict, blank=True)
    quality_analysis = models.JSONField(default=dict, blank=True)
    grammar_issues = models.JSONField(default=list, blank=True)
    missing_sections = models.JSONField(default=list, blank=True)
    detected_role = models.CharField(max_length=100, blank=True, null=True)
    grade = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} – {self.job_role} (score: {self.score})"