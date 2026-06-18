"""
CSV-backed local interview question generation for Django.

Mirrors quizzes.services.quiz_generator:
- Reads interview_question_bank.csv (same local CSV pattern as quiz)
- Role + experience filtering
- sklearn models in interview_ai/engine.py used for scoring only
"""

from __future__ import annotations

from .interview_ai.engine import (
    ensure_models_loaded,
    experience_band_from_years,
    generate_interview_questions as _generate_interview_questions,
    start_interview_after_quiz as _start_interview_after_quiz,
)
from .question_selector import selection_mode_label


def generate_interview_questions(
    job_role: str,
    years_experience: float,
    num_questions: int = 6,
    seed: int | None = None,
    exclude_questions: set[str] | list[str] | None = None,
) -> list[dict]:
    """Generate interview questions locally from backend AI assets."""
    ensure_models_loaded()
    return _generate_interview_questions(
        job_role=job_role,
        experience_years=years_experience,
        num_questions=num_questions,
        seed=seed,
        exclude_questions=exclude_questions,
    )


def start_interview(
    quiz_passed: bool,
    job_role: str,
    years_experience: float,
    num_questions: int = 6,
    seed: int | None = None,
    exclude_questions: set[str] | list[str] | None = None,
) -> dict:
    """Quiz gate + local question generation (same pattern as quiz start)."""
    ensure_models_loaded()
    payload = _start_interview_after_quiz(
        quiz_passed=quiz_passed,
        job_role=job_role,
        experience_years=years_experience,
        num_questions=num_questions,
        seed=seed,
        exclude_questions=exclude_questions,
    )
    payload['question_selection_mode'] = selection_mode_label()
    return payload
