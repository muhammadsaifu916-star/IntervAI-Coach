from django.db import models
from django.conf import settings


class CandidateProfile(models.Model):
    """The public-facing profile a job seeker publishes to employers."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='candidate_profile',
    )

    # Editable profile content
    bio              = models.TextField(blank=True, default='')
    location         = models.CharField(max_length=120, blank=True, default='')
    skills           = models.JSONField(default=list, blank=True)   # list[str]
    projects_summary = models.TextField(blank=True, default='')
    website          = models.URLField(blank=True, default='')
    linkedin         = models.URLField(blank=True, default='')
    github           = models.URLField(blank=True, default='')

    # Visibility toggles (control what employers see before purchase)
    show_contact     = models.BooleanField(default=True)
    show_full_name   = models.BooleanField(default=True)

    # Publication state (managed by publish/unpublish endpoints — not by PATCH)
    published        = models.BooleanField(default=False)
    published_at     = models.DateTimeField(null=True, blank=True)

    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-published_at', '-created_at']

    def __str__(self):
        status = 'published' if self.published else 'draft'
        return f"{self.user.username} ({status})"
