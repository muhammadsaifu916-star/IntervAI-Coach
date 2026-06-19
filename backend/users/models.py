from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    ROLE_CHOICES = (
        ('jobseeker', 'Job Seeker'),
        ('employer', 'Employer'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    phone = models.CharField(max_length=20, blank=True, null=True, unique=True)

    email_verified = models.BooleanField(default=False)

    # Retry cooldowns live on the user (not the attempt) so they survive a
    # resume re-upload, which wipes quiz/interview sessions.
    quiz_cooldown_until = models.DateTimeField(null=True, blank=True)
    interview_cooldown_until = models.DateTimeField(null=True, blank=True)


class EmailVerificationOTP(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='email_otp'
    )
    code_hash = models.CharField(max_length=256)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    last_sent_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f'OTP for {self.user.email}'
