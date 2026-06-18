from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import User, EmailVerificationOTP
from .serializers import RegisterSerializer, VerifyEmailOTPSerializer
from .services import send_email_verification_otp

from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .serializers import RegisterSerializer


@api_view(['POST'])
def register_user(request):
    serializer = RegisterSerializer(data=request.data)

    if serializer.is_valid():
        user = serializer.save()

        try:
            send_email_verification_otp(user)
        except Exception:
            user.delete()
            return Response(
                {
                    "error": "Account could not be created because the OTP email failed to send. Please check email settings."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "message": "Account created successfully. Please verify your email using the OTP sent to your inbox.",
                "email": user.email,
                "verification_required": True,
            },
            status=status.HTTP_201_CREATED,
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def verify_email_otp(request):
    serializer = VerifyEmailOTPSerializer(data=request.data)

    if serializer.is_valid():
        user = serializer.validated_data['user']
        otp_obj = serializer.validated_data['otp_obj']

        user.is_active = True
        user.email_verified = True
        user.save(update_fields=['is_active', 'email_verified'])

        otp_obj.delete()

        return Response(
            {"message": "Email verified successfully. You can now login."},
            status=status.HTTP_200_OK,
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def resend_email_otp(request):
    email_value = request.data.get('email', '')

    if isinstance(email_value, list):
        email_value = email_value[0] if email_value else ''

    if not isinstance(email_value, str):
        return Response(
            {"email": "Invalid email format."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    email = email_value.lower().strip()

    if not email:
        return Response(
            {"email": "Email is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = User.objects.filter(email__iexact=email).first()

    if not user:
        return Response(
            {"email": "No account found with this email."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if user.is_active and user.email_verified:
        return Response(
            {"email": "This email is already verified."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    otp_obj = getattr(user, 'email_otp', None)

    if otp_obj and timezone.now() - otp_obj.last_sent_at < timedelta(seconds=60):
        return Response(
            {"error": "Please wait at least 60 seconds before requesting another OTP."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    try:
        send_email_verification_otp(user)
    except Exception:
        return Response(
            {"error": "Could not send OTP email. Please try again later."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        {"message": "A new OTP has been sent to your email."},
        status=status.HTTP_200_OK,
    )
    
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        login_value = attrs.get('username')
        password = attrs.get('password', '')

        user = (
            User.objects.filter(email__iexact=login_value).first()
            or User.objects.filter(username__iexact=login_value).first()
        )

        if (
            user
            and not user.is_active
            and not user.email_verified
            and user.check_password(password)
        ):
            raise serializers.ValidationError({
                "detail": "Please verify your email before logging in.",
                "email_not_verified": True,
                "email": user.email,
            })

        return super().validate(attrs)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user(request):
    user = request.user

    # ── Latest resume ──────────────────────────────────────────────────────────
    latest_resume = user.resumes.first()

    # ── Latest quiz ────────────────────────────────────────────────────────────
    latest_quiz = (
        user.quiz_sessions
        .filter(submitted_at__isnull=False)
        .order_by('-submitted_at', '-started_at')
        .first()
    )

    # ── Latest interview ───────────────────────────────────────────────────────
    latest_interview = (
        user.interview_sessions
        .filter(submitted_at__isnull=False)
        .order_by('-submitted_at', '-started_at')
        .first()
    )

    # ── Experience tier ────────────────────────────────────────────────────────
    years_experience = latest_resume.years_experience if latest_resume else None
    experience_tier = None
    if years_experience is not None:
        if   years_experience <= 1:  experience_tier = 'Entry Level'
        elif years_experience <= 3:  experience_tier = 'Mid Level'
        else:                        experience_tier = 'Senior Level'

    # ── Candidate profile (jobseekers only) ────────────────────────────────────
    candidate_profile_data = None
    if user.role == 'jobseeker':
        from profiles.models import CandidateProfile
        profile, _ = CandidateProfile.objects.get_or_create(user=user)
        candidate_profile_data = {
            'bio':              profile.bio,
            'location':         profile.location,
            'skills':           profile.skills,
            'projects_summary': profile.projects_summary,
            'website':          profile.website,
            'linkedin':         profile.linkedin,
            'github':           profile.github,
            'show_contact':     profile.show_contact,
            'show_full_name':   profile.show_full_name,
            'published':        profile.published,
            'published_at':     profile.published_at,
        }

    # ── Final score (average of the three completed) ───────────────────────────
    scores = [s for s in [
        latest_resume.score    if latest_resume    else None,
        latest_quiz.score      if latest_quiz      else None,
        latest_interview.score if latest_interview else None,
    ] if s is not None]
    final_score = round(sum(scores) / len(scores), 1) if scores else 0
    resume_analysis = latest_resume.analysis_data or {} if latest_resume else {}

    return Response({
        "id":         user.id,
        "username":   user.username,
        "email":      user.email,
        "first_name": user.first_name,
        "last_name":  user.last_name,
        "role":       user.role,
        "phone":      user.phone,

        "latest_resume": {
            "id":               latest_resume.id,
            "job_role":         latest_resume.job_role,
            "years_experience": latest_resume.years_experience,
            "experience_tier":  experience_tier,
            "score":            latest_resume.score,
            "created_at":       latest_resume.created_at,
            "feedback":         latest_resume.feedback,
            "quiz_unlocked":    (latest_resume.score or 0) >= 70,

            # Full saved resume analysis for ResumeFeedback.tsx
            "analysis_data":    resume_analysis,
            "grade":            resume_analysis.get("grade"),
            "detected_role":    resume_analysis.get("detected_role"),
            "target_role":      resume_analysis.get("target_role"),
            "selected_role":    resume_analysis.get("selected_role"),
            "role_alignment":   resume_analysis.get("role_alignment"),
            "role_penalty":     resume_analysis.get("role_penalty", 0),
            "role_mismatch_block": resume_analysis.get("role_mismatch_block", False),
            "role_match_message":  resume_analysis.get("role_match_message"),
            "analysis_log":     resume_analysis.get("analysis_log", []),
            "strengths":        resume_analysis.get("strengths", []),
            "weaknesses":       resume_analysis.get("weaknesses", []),
            "improvement_plan": resume_analysis.get("improvement_plan", {}),
            "quality_analysis": resume_analysis.get("quality_analysis", {}),
            "grammar_issues":   resume_analysis.get("grammar_issues", []),
            "missing_sections": resume_analysis.get("missing_sections", []),
        } if latest_resume else None,

        "latest_quiz": {
            "id":             latest_quiz.id,
            "score":          latest_quiz.score,
            "passed":         latest_quiz.passed,
            "cooldown_until": latest_quiz.cooldown_until,
            "submitted_at":   latest_quiz.submitted_at,
        } if latest_quiz else None,

        "latest_interview": {
            "id":             latest_interview.id,
            "score":          latest_interview.score,
            "passed":         latest_interview.passed,
            "cooldown_until": latest_interview.cooldown_until,
            "submitted_at":   latest_interview.submitted_at,
            "attempt_number": latest_interview.attempt_number,
        } if latest_interview else None,

        "candidate_profile": candidate_profile_data,
        "final_score":       final_score,

        "quiz_attempts":      user.quiz_sessions.filter(submitted_at__isnull=False).count(),
        "interview_attempts": user.interview_sessions.filter(submitted_at__isnull=False).count(),

        # Authoritative cooldowns (survive resume re-upload, which wipes sessions)
        "quiz_cooldown_until":      user.quiz_cooldown_until,
        "interview_cooldown_until": user.interview_cooldown_until,
    })
