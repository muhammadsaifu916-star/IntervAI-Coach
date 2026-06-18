from django.urls import path
from .views import register_user, current_user, verify_email_otp, resend_email_otp

urlpatterns = [
    path('register/', register_user),
    path('verify-email/', verify_email_otp),
    path('resend-otp/', resend_email_otp),
    path('me/', current_user),
]