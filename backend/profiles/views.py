from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone

from .models import CandidateProfile
from .serializers import CandidateProfileSerializer, PublicProfileSerializer


# ── Helpers ───────────────────────────────────────────────────────────────────
def _get_or_create_profile(user):
    profile, _ = CandidateProfile.objects.get_or_create(user=user)

    latest_resume = user.resumes.first()
    if not latest_resume:
        return profile

    analysis = latest_resume.analysis_data or {}

    skills = analysis.get("technical_skills_list") or []
    social_links = analysis.get("social_links") or {}

    changed = False

    # Only auto-fill if the user has not already entered their own data
    if not profile.skills and skills:
        profile.skills = skills
        changed = True

    if not profile.website and social_links.get("website"):
        profile.website = social_links.get("website")
        changed = True

    if not profile.linkedin and social_links.get("linkedin"):
        profile.linkedin = social_links.get("linkedin")
        changed = True

    if not profile.github and social_links.get("github"):
        profile.github = social_links.get("github")
        changed = True

    if changed:
        profile.save(update_fields=[
            "skills",
            "website",
            "linkedin",
            "github",
            "updated_at",
        ])

    return profile


def _is_unlocked_for(employer, candidate_user_id) -> bool:
    """Has this employer unlocked this candidate via a ProfileUnlock record?"""
    if not employer or not employer.is_authenticated or employer.role != 'employer':
        return False
    from payments.models import ProfileUnlock
    return ProfileUnlock.objects.filter(
        employer=employer,
        candidate_id=candidate_user_id,
    ).exists()


# ── Owner-facing endpoints ────────────────────────────────────────────────────

@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def my_profile(request):
    if request.user.role != 'jobseeker':
        return Response({'error': 'Only job seekers have a candidate profile.'}, status=status.HTTP_403_FORBIDDEN)

    profile = _get_or_create_profile(request.user)

    if request.method == 'GET':
        return Response(CandidateProfileSerializer(profile).data)

    serializer = CandidateProfileSerializer(profile, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    serializer.save()
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def publish_profile(request):
    user = request.user
    if user.role != 'jobseeker':
        return Response({'error': 'Only job seekers can publish.'}, status=status.HTTP_403_FORBIDDEN)

    from interviews.models import InterviewSession
    if not InterviewSession.objects.filter(user=user, passed=True).exists():
        return Response(
            {'error': 'You must pass the interview before publishing your profile.', 'interview_required': True},
            status=status.HTTP_403_FORBIDDEN,
        )

    profile = _get_or_create_profile(user)
    missing = []
    if not profile.bio.strip(): missing.append('bio')
    if not profile.skills:      missing.append('at least one skill')
    if missing:
        return Response({'error': f"Please add {' and '.join(missing)} before publishing."}, status=status.HTTP_400_BAD_REQUEST)

    profile.published    = True
    profile.published_at = timezone.now()
    profile.save(update_fields=['published', 'published_at', 'updated_at'])
    return Response(CandidateProfileSerializer(profile).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unpublish_profile(request):
    if request.user.role != 'jobseeker':
        return Response({'error': 'Only job seekers can manage a profile.'}, status=status.HTTP_403_FORBIDDEN)
    profile = _get_or_create_profile(request.user)
    profile.published = False
    profile.save(update_fields=['published', 'updated_at'])
    return Response(CandidateProfileSerializer(profile).data)


# ── Employer-facing endpoints ─────────────────────────────────────────────────

EXPERIENCE_TIER_RANGES = {
    'Entry Level':   (-1,    1),    # 0 - 1 years
    'Mid Level':     (1,     3),    # <1 - 3 years
    'Senior Level':  (3,  1000),    # <3 years
}

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def public_profiles_list(request):
    """
    Browse published candidate profiles.
    The LIST view never shows redacted fields — `unlocked` flips per-candidate
    based on the employer's purchase records.
    """
    qs = (
        CandidateProfile.objects
        .filter(published=True)
        .select_related('user')
        .prefetch_related('user__resumes', 'user__quiz_sessions', 'user__interview_sessions')
    )

    tier = request.query_params.get('experience_tier')
    if tier and tier != 'all' and tier in EXPERIENCE_TIER_RANGES:
        lo, hi = EXPERIENCE_TIER_RANGES[tier]
        qs = qs.filter(user__resumes__years_experience__gt=lo,
                       user__resumes__years_experience__lte=hi).distinct()

    # Fetch the set of candidate IDs this employer has unlocked
    unlocked_ids = set()
    if request.user.role == 'employer':
        from payments.models import ProfileUnlock
        unlocked_ids = set(
            ProfileUnlock.objects
            .filter(employer=request.user)
            .values_list('candidate_id', flat=True)
        )

    # Serialize each profile with its own unlock context
    serialized = []
    for profile in qs:
        is_unlocked = profile.user.id in unlocked_ids
        data = PublicProfileSerializer(profile, context={'unlocked': is_unlocked}).data
        serialized.append(data)

    # Skill search
    search = (request.query_params.get('search') or '').strip().lower()
    if search:
        terms = [t.strip() for t in search.split(',') if t.strip()]
        serialized = [
            p for p in serialized
            if any(any(term in s.lower() for s in p.get('skills', [])) for term in terms)
        ]

    # Min score
    try:
        min_score = int(request.query_params.get('min_score', 0))
    except (TypeError, ValueError):
        min_score = 0
    if min_score > 0:
        serialized = [p for p in serialized if p.get('scores', {}).get('final', 0) >= min_score]

    serialized.sort(key=lambda p: p.get('scores', {}).get('final', 0), reverse=True)

    final_scores = [p['scores']['final'] for p in serialized if p.get('scores')]
    stats = {
        'total':     len(serialized),
        'avg_score': round(sum(final_scores) / len(final_scores)) if final_scores else 0,
        'top_rated': sum(1 for s in final_scores if s >= 90),
    }

    return Response({'stats': stats, 'results': serialized})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def public_profile_detail(request, user_id):
    """Single candidate. `unlocked=True` if employer has purchased+unlocked them."""
    try:
        profile = (
            CandidateProfile.objects
            .select_related('user')
            .get(user__id=user_id, published=True)
        )
    except CandidateProfile.DoesNotExist:
        return Response({'error': 'Profile not found or not published.'}, status=status.HTTP_404_NOT_FOUND)

    unlocked = _is_unlocked_for(request.user, user_id)
    serializer = PublicProfileSerializer(profile, context={'unlocked': unlocked})
    return Response(serializer.data)
