import secrets
import threading
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.utils import timezone
from .models import EmailVerificationOTP

OTP_EXPIRY_MINUTES = 10

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

    subject = 'Verify your IntervAI Coach email'
    message = (
        f'Your IntervAI Coach email verification OTP is: {code}\n\n'
        f'This OTP will expire in {OTP_EXPIRY_MINUTES} minutes.\n'
        'If you did not create this account, please ignore this email.'
    )

    def _send():
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=True,
            )
        except Exception:
            pass

    thread = threading.Thread(target=_send)
    thread.daemon = True
    thread.start()
