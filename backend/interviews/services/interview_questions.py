"""Interview question generation — delegates to the AI interview engine."""

from .interview_engine import generate_questions


def generate_interview_questions(job_role: str, num_questions: int = 6, years_experience: float = 0.0) -> list[dict]:
    """
    Return a list of question dicts with keys: text, type, category.
    Half technical, half personality (interleaved).
    """
    return generate_questions(
        job_role=job_role,
        years_experience=years_experience,
        num_questions=num_questions,
    )
