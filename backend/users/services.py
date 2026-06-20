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


def _parse_sender(raw):
    """
    Split a 'Name <email@host>' string into (name, email).
    Falls back to (None, raw) if there's no angle-bracket form.
    """
    raw = (raw or '').strip()
    if '<' in raw and raw.endswith('>'):
        name = raw[:raw.index('<')].strip()
        email = raw[raw.index('<') + 1:-1].strip()
        return (name or None), email
    return None, raw


def _send_via_brevo(to_email, subject, message):
    """
    Send through the Brevo (Sendinblue) HTTP API.

    Uses HTTPS (port 443), so it works on hosts that block outbound SMTP
    (e.g. Railway). Unlike Resend's sandbox, Brevo delivers to ANY recipient
    once the sender email is verified — no domain required. Raises on failure.
    """
    import requests

    api_key = settings.BREVO_API_KEY
    sender_name, sender_email = _parse_sender(settings.BREVO_FROM_EMAIL)

    sender = {'email': sender_email}
    if sender_name:
        sender['name'] = sender_name

    resp = requests.post(
        'https://api.brevo.com/v3/smtp/email',
        headers={
            'api-key': api_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
        json={
            'sender': sender,
            'to': [{'email': to_email}],
            'subject': subject,
            'textContent': message,
        },
        timeout=15,
    )

    # Raise for any non-2xx so registration treats it as a failed send and
    # rolls back the account (the response body names the exact problem).
    if resp.status_code >= 300:
        raise RuntimeError(f'Brevo API error {resp.status_code}: {resp.text}')

    return resp


def _send_via_resend(to_email, subject, message):
    """
    Send through the Resend HTTP API (kept as an alternative provider).
    Uses HTTPS (port 443). Raises on failure.
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

    if resp.status_code >= 300:
        raise RuntimeError(f'Resend API error {resp.status_code}: {resp.text}')

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

    # Provider priority (production on Railway, where SMTP is blocked):
    #   1. Brevo  — sends to ANY recipient with just a verified sender email.
    #   2. Resend — sandbox only delivers to the account owner's address.
    # If neither key is set, fall back to Django's email backend (console
    # locally / SMTP), so local development works unchanged.
    if getattr(settings, 'BREVO_API_KEY', ''):
        _send_via_brevo(user.email, subject, message)
    elif getattr(settings, 'RESEND_API_KEY', ''):
        _send_via_resend(user.email, subject, message)
    else:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
