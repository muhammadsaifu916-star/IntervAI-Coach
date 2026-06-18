from rest_framework import serializers
from .models import CandidateProfile


from rest_framework import serializers
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import CandidateProfile


class CandidateProfileSerializer(serializers.ModelSerializer):
    """For the authenticated user managing their OWN profile (GET/PATCH /api/profiles/me/)."""

    website = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    linkedin = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    github = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)

    class Meta:
        model  = CandidateProfile
        fields = [
            'bio', 'location', 'skills', 'projects_summary',
            'website', 'linkedin', 'github',
            'show_contact', 'show_full_name',
            'published', 'published_at', 'updated_at',
        ]
        read_only_fields = ['published', 'published_at', 'updated_at']

    def validate_skills(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('Skills must be a list of strings.')
        cleaned = [str(s).strip() for s in value if str(s).strip()]
        if len(cleaned) > 30:
            raise serializers.ValidationError('You can have at most 30 skills.')
        return cleaned

    def _normalize_url(self, value):
        value = (value or '').strip()

        if not value:
            return ''

        if not value.startswith(('http://', 'https://')):
            value = 'https://' + value

        validator = URLValidator()
        try:
            validator(value)
        except DjangoValidationError:
            raise serializers.ValidationError('Enter a valid URL.')

        return value

    def validate_website(self, value):
        return self._normalize_url(value)

    def validate_linkedin(self, value):
        return self._normalize_url(value)

    def validate_github(self, value):
        return self._normalize_url(value)


class PublicProfileSerializer(serializers.ModelSerializer):
    """
    Employer-facing view of a published candidate profile.

    Personally identifying / paywalled fields (name, email, phone, bio,
    projects_summary, social links) are ONLY included when the serializer
    is given context `unlocked=True`. Otherwise they are redacted.

    `unlocked` flips to True once a payment / purchase flow is in place.
    For now, the list endpoint always passes `unlocked=False`.
    """

    id                  = serializers.IntegerField(source='user.id', read_only=True)
    display_name        = serializers.SerializerMethodField()
    experience_tier     = serializers.SerializerMethodField()
    years_experience    = serializers.SerializerMethodField()
    scores              = serializers.SerializerMethodField()
    interview_breakdown = serializers.SerializerMethodField()
    unlocked            = serializers.SerializerMethodField()

    # Conditionally added in to_representation:
    # full_name, email, phone, bio, projects_summary, website, linkedin, github

    class Meta:
        model  = CandidateProfile
        fields = [
            'id', 'display_name', 'experience_tier', 'years_experience',
            'location', 'skills', 'scores', 'interview_breakdown',
            'published_at', 'unlocked',
        ]

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _is_unlocked(self) -> bool:
        return bool(self.context.get('unlocked', False))

    def _latest_resume(self, obj):
        return obj.user.resumes.first()

    def _latest_quiz(self, obj):
        return obj.user.quiz_sessions.filter(submitted_at__isnull=False, passed=True).order_by('-submitted_at').first()

    def _latest_interview(self, obj):
        return obj.user.interview_sessions.filter(submitted_at__isnull=False, passed=True).order_by('-submitted_at').first()

    # ── Field methods ──────────────────────────────────────────────────────────
    def get_display_name(self, obj) -> str:
        if self._is_unlocked() and obj.show_full_name:
            full = f"{obj.user.first_name} {obj.user.last_name}".strip()
            return full or obj.user.username
        return f"Candidate #{obj.user.id}"

    def get_experience_tier(self, obj) -> str | None:
        resume = self._latest_resume(obj)
        if not resume or resume.years_experience is None:
            return None
        y = resume.years_experience
        if   y <= 1: return 'Entry Level'
        elif y <= 3: return 'Mid Level'
        else:        return 'Senior Level'

    def get_years_experience(self, obj) -> int | None:
        resume = self._latest_resume(obj)
        return resume.years_experience if resume else None

    def get_scores(self, obj) -> dict:
        resume    = self._latest_resume(obj)
        quiz      = self._latest_quiz(obj)
        interview = self._latest_interview(obj)
        s = {
            'resume':    round(resume.score)    if resume    else 0,
            'quiz':      round(quiz.score)      if quiz      else 0,
            'interview': round(interview.score) if interview else 0,
        }
        vals = [v for v in s.values() if v > 0]
        s['final'] = round(sum(vals) / len(vals)) if vals else 0
        return s

    def get_interview_breakdown(self, obj) -> dict | None:
        interview = self._latest_interview(obj)
        if not interview:
            return None
        return {
            'technical':     round(interview.technical_score     or 0),
            'personality':   round(interview.personality_score   or 0),
            'attentiveness': round(interview.attentiveness_score or 0),
            'eye_contact':   round(interview.eye_contact_score   or 0),
        }

    def get_unlocked(self, obj) -> bool:
        return self._is_unlocked()

    # ── Inject sensitive fields only when unlocked ────────────────────────────
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if self._is_unlocked():
            data['bio']              = instance.bio
            data['projects_summary'] = instance.projects_summary
            data['website']          = instance.website
            data['linkedin']         = instance.linkedin
            data['github']           = instance.github
            if instance.show_full_name:
                full = f"{instance.user.first_name} {instance.user.last_name}".strip()
                data['full_name'] = full or instance.user.username
            if instance.show_contact:
                data['email'] = instance.user.email
                data['phone'] = instance.user.phone or ''
        return data
