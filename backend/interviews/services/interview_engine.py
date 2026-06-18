"""
Django-facing wrapper for the AI interview module.

Mirrors resumes.services.resume_analyzer and quizzes.services.quiz_generator.
"""

from .interview_ai.engine import (
    ensure_models_loaded,
    evaluate_interview_session,
    experience_band_from_years,
)
from .interview_question_generator import generate_interview_questions, start_interview as _start_interview_local


def generate_questions(job_role: str, years_experience: float, num_questions: int = 6, seed: int | None = None):
    """Return question dicts with keys: question_text, question_type, category, order."""
    ensure_models_loaded()
    raw = generate_interview_questions(
        job_role=job_role,
        years_experience=years_experience,
        num_questions=num_questions,
        seed=seed,
    )
    return [
        {
            'text': q['question_text'],
            'type': q['question_type'],
            'category': q.get('category', ''),
        }
        for q in raw
    ]


def prepare_interview_start(
    quiz_passed: bool,
    job_role: str,
    years_experience: float,
    num_questions: int = 6,
    seed: int | None = None,
    exclude_questions: set[str] | list[str] | None = None,
):
    """Quiz gate + question generation entry point used by Django views."""
    ensure_models_loaded()
    return _start_interview_local(
        quiz_passed=quiz_passed,
        job_role=job_role,
        years_experience=years_experience,
        num_questions=num_questions,
        seed=seed,
        exclude_questions=exclude_questions,
    )


def evaluate_session(answers, session_meta, interview_expired: bool = False):
    """Score an interview session from transcripts + monitoring metadata."""
    ensure_models_loaded()
    return evaluate_interview_session(
        answers=answers,
        session_meta=session_meta,
        interview_expired=interview_expired,
    )
