from django.db import models
from django.conf import settings


class QuizSession(models.Model):
    """One quiz attempt per user. Stores metadata and final score."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='quiz_sessions',
    )
    job_role        = models.CharField(max_length=100)
    attempt_number  = models.PositiveIntegerField(default=1)
    started_at      = models.DateTimeField(auto_now_add=True)
    submitted_at    = models.DateTimeField(null=True, blank=True)
    score           = models.FloatField(null=True, blank=True)
    passed          = models.BooleanField(null=True, blank=True)
    cooldown_until  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.user.username} – Quiz #{self.attempt_number} (score: {self.score})"


class QuizQuestion(models.Model):
    """A single question tied to a session. correct_answer never leaves the backend."""

    TYPES = [('mcq', 'Multiple Choice'), ('scenario', 'Scenario-based')]
    DIFFICULTIES = [('easy', 'Easy'), ('medium', 'Medium'), ('hard', 'Hard')]

    session         = models.ForeignKey(QuizSession, on_delete=models.CASCADE, related_name='questions')
    question_text   = models.TextField()
    question_type   = models.CharField(max_length=20, choices=TYPES)
    options         = models.JSONField()          # list[str] – 4 choices
    correct_answer  = models.IntegerField()       # index into options – NEVER serialized to frontend
    difficulty      = models.CharField(max_length=10, choices=DIFFICULTIES)
    topic           = models.CharField(max_length=100, blank=True, default='')
    subtopic        = models.CharField(max_length=100, blank=True, default='')
    explanation     = models.TextField(blank=True, default='')
    order           = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"Q{self.order + 1}: {self.question_text[:60]}"
    
    
class QuizAnswer(models.Model):
    session = models.ForeignKey(
        QuizSession,
        on_delete=models.CASCADE,
        related_name='answers'
    )
    question = models.ForeignKey(
        QuizQuestion,
        on_delete=models.CASCADE,
        related_name='submitted_answers'
    )
    selected_answer = models.IntegerField(null=True, blank=True)
    is_correct = models.BooleanField(default=False)
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('session', 'question')
        ordering = ['question__order']

    def __str__(self):
        return f"{self.session.user.email} - Q{self.question.order} - {'Correct' if self.is_correct else 'Wrong'}"