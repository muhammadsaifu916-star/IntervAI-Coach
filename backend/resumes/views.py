import logging

from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status

from django.db import transaction

logger = logging.getLogger(__name__)

from .models import Resume
from .serializers import ResumeUploadSerializer
from .services.resume_analyzer import analyze_resume_file


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_resume(request):
    serializer = ResumeUploadSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    file = serializer.validated_data['file']
    job_role = serializer.validated_data['job_role']
    years_experience = serializer.validated_data['years_experience']

    # Did the user have quiz/interview progress that this re-upload will erase?
    had_progress = (
        request.user.quiz_sessions.exists()
        or request.user.interview_sessions.exists()
    )

    # Collect old resumes before creating the new one
    old_resumes = list(Resume.objects.filter(user=request.user))

    # First save the uploaded file, because the AI model needs resume.file.path
    resume = Resume.objects.create(
        user=request.user,
        job_role=job_role,
        years_experience=years_experience,
        file=file,
        score=0,
        feedback="Analysis pending...",
    )

    # Run real AI resume analysis
    try:
        analysis = analyze_resume_file(
            resume.file.path,
            target_role=job_role,
            years_of_experience=years_experience,
        )
    except Exception:
        # Clean up newly uploaded file if analysis fails
        if resume.file:
            resume.file.delete(save=False)
        resume.delete()

        # Log the full exception server-side; return a generic message so we
        # don't leak internal details (stack traces, library errors) to clients.
        logger.exception("Resume analysis failed for user %s", request.user.id)

        return Response(
            {
                "error": "Resume analysis failed. Please try again with a different file.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    score = analysis.get("score", 0)
    feedback = analysis.get("message", "")

    with transaction.atomic():
        # Save AI result to resume
        resume.score = score
        resume.feedback = feedback
        resume.grade = analysis.get("grade")
        resume.detected_role = analysis.get("detected_role")

        resume.strengths = analysis.get("strengths", [])
        resume.weaknesses = analysis.get("weaknesses", [])
        resume.improvement_plan = analysis.get("improvement_plan", {})
        resume.quality_analysis = analysis.get("quality_analysis", {})
        resume.grammar_issues = analysis.get("grammar_issues", [])
        resume.missing_sections = analysis.get("missing_sections", [])
        resume.analysis_data = analysis

        resume.save()

        # Delete old database records only after new resume is created and analyzed
        Resume.objects.filter(id__in=[old_resume.id for old_resume in old_resumes]).delete()

        # Wipe quiz & interview progress
        request.user.quiz_sessions.all().delete()
        request.user.interview_sessions.all().delete()

        # NOTE: the resume score is not stored on the User model; it is read
        # from the latest Resume row (resume.score) wherever it's needed
        # (see users.views.current_user). No user write is required here.

        # Unpublish candidate profile
        from profiles.models import CandidateProfile
        CandidateProfile.objects.filter(
            user=request.user,
            published=True
        ).update(published=False)

    # Delete old physical files only after DB transaction succeeds
    def delete_old_files():
        for old_resume in old_resumes:
            if old_resume.file:
                old_resume.file.delete(save=False)

    transaction.on_commit(delete_old_files)

    return Response(
        {
            "resume_id": resume.id,
            "score": score,
            "feedback": feedback,
            "grade": analysis.get("grade"),
            "detected_role": analysis.get("detected_role"),
            "analysis_log": analysis.get("analysis_log", []),

            # Role match / mismatch info for the feedback screen
            "target_role": analysis.get("target_role"),
            "selected_role": analysis.get("selected_role"),
            "role_alignment": analysis.get("role_alignment"),
            "role_penalty": analysis.get("role_penalty", 0),
            "role_mismatch_block": analysis.get("role_mismatch_block", False),
            "role_match_message": analysis.get("role_match_message"),

            "strengths": analysis.get("strengths", []),
            "weaknesses": analysis.get("weaknesses", []),
            "improvement_plan": analysis.get("improvement_plan", {}),
            "quality_analysis": analysis.get("quality_analysis", {}),
            "grammar_issues": analysis.get("grammar_issues", []),
            "missing_sections": analysis.get("missing_sections", []),
            "quiz_unlocked": (score or 0) >= 70,
            "progress_cleared": had_progress,
        },
        status=status.HTTP_201_CREATED,
    )