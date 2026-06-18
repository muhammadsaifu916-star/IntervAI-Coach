from django.db import models
from django.conf import settings


class InterviewSession(models.Model):
    """One interview attempt per user. Stores metadata and final scores."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='interview_sessions',
    )
    job_role            = models.CharField(max_length=100)
    years_experience    = models.FloatField(default=0.0)
    experience_band     = models.CharField(max_length=40, blank=True, default='')
    attempt_number      = models.PositiveIntegerField(default=1)
    started_at          = models.DateTimeField(auto_now_add=True)
    submitted_at        = models.DateTimeField(null=True, blank=True)

    # Scores (populated on submit)
    technical_score     = models.FloatField(null=True, blank=True)
    personality_score   = models.FloatField(null=True, blank=True)
    attentiveness_score = models.FloatField(null=True, blank=True)
    eye_contact_score   = models.FloatField(null=True, blank=True)
    score               = models.FloatField(null=True, blank=True)  # overall average
    passed              = models.BooleanField(null=True, blank=True)
    cooldown_until      = models.DateTimeField(null=True, blank=True)

    # Extended AI analysis (mirrors resumes.analysis_data pattern)
    communication_score = models.FloatField(null=True, blank=True)
    grammar_score       = models.FloatField(null=True, blank=True)
    confidence_score    = models.FloatField(null=True, blank=True)
    filler_ratio        = models.FloatField(null=True, blank=True)
    analysis_data       = models.JSONField(default=dict, blank=True)
    improvement_plan    = models.TextField(blank=True, default='')
    progress_report     = models.JSONField(default=dict, blank=True)
    monitoring_data     = models.JSONField(default=dict, blank=True)
    answer_timings      = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.user.username} – Interview #{self.attempt_number} (score: {self.score})"


class InterviewQuestion(models.Model):
    """A single question tied to an interview session."""

    TYPES = [('technical', 'Technical'), ('personality', 'Personality')]

    session       = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=TYPES)
    category      = models.CharField(max_length=100)
    generation_source = models.CharField(
        max_length=20,
        blank=True,
        default='curated',
        help_text='csv | curated | dataset | ml_guided | dynamic',
    )
    reference_keywords = models.TextField(blank=True, default='')
    reference_points = models.TextField(blank=True, default='')
    order         = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"Q{self.order + 1}: {self.question_text[:60]}"


class InterviewAnswer(models.Model):
    """The candidate's spoken transcript for a single question."""

    session     = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name='answers')
    question    = models.ForeignKey(InterviewQuestion, on_delete=models.CASCADE, related_name='submitted_answers')
    transcript  = models.TextField(blank=True, default='')
    score       = models.FloatField(null=True, blank=True)
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('session', 'question')
        ordering = ['question__order']

    def __str__(self):
        return f"{self.session.user.username} – Q{self.question.order + 1}"
