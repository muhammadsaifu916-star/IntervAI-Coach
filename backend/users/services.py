import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.utils import timezone

from .models import EmailVerificationOTP

logger = logging.getLogger(__name__)

OTP_EXPIRY_MINUTES = 10


def _build_otp_email(code):
    """Return (subject, plain_text_body) for the verification email."""
    subject = 'Verify your IntervAI Coach email'
    message = (
        f'Your IntervAI Coach email verification OTP is: {code}\n\n'
        f'This OTP will expire in {OTP_EXPIRY_MINUTES} minutes.\n'
        'If you did not create this account, please ignore this email.'
    )
    return subject, message


def _send_via_resend(to_email, subject, message):
    """
    Send through the Resend HTTP API (https://resend.com).

    Uses HTTPS (port 443), so it works on hosts that block outbound SMTP
    (e.g. Railway). Raises on failure so the caller can roll back / report.
    """
    import requests

    api_key = settings.RESEND_API_KEY
    from_email = settings.RESEND_FROM_EMAIL

    resp = requests.post(
        'https://api.resend.com/emails',
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        json={
            'from': from_email,
            'to': [to_email],
            'subject': subject,
            'text': message,
        },
        timeout=15,
    )

    # Raise for any non-2xx so registration treats it as a failed send.
    if resp.status_code >= 300:
        raise RuntimeError(
            f'Resend API error {resp.status_code}: {resp.text}'
        )

    return resp


def send_email_verification_otp(user):
    code = str(secrets.randbelow(900000) + 100000)
    now = timezone.now()

    EmailVerificationOTP.objects.update_or_create(
        user=user,
        defaults={
            'code_hash': make_password(code),
            'created_at': now,
            'expires_at': now + timedelta(minutes=OTP_EXPIRY_MINUTES),
            'attempts': 0,
            'last_sent_at': now,
        }
    )

    subject, message = _build_otp_email(code)

    # Prefer the Resend HTTP API when configured (production on Railway).
    # Fall back to Django's email backend (console/SMTP) otherwise, so local
    # development keeps working exactly as before with no Resend account.
    if getattr(settings, 'RESEND_API_KEY', ''):
        _send_via_resend(user.email, subject, message)
    else:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
