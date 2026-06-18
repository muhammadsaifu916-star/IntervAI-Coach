"""Interview question selection from local CSV (quiz-style) with dynamic fallback."""

from __future__ import annotations

import secrets

from .dynamic_question_builder import build_role_experience_question
from .interview_csv_bank import pick_interview_question_from_csv
from .question_quality import normalize_question_text as _quality_normalize
from .question_quality import normalize_for_dedupe
from .reference_answer_scoring import build_reference_metadata
from .role_interview_constants import ROLE_INTERVIEW_SKILLS


def selection_mode_label() -> str:
    return "local_csv"


def normalize_question_text(text: str) -> str:
    return _quality_normalize(text)


def normalize_exclude_set(exclude: set[str] | list[str] | None) -> set[str]:
    result: set[str] = set()
    for item in (exclude or set()):
        text = normalize_question_text(item)
        if text:
            result.add(text)
            result.add(normalize_for_dedupe(text))
    return result


def select_interview_question(
    *,
    focus_area: str,
    job_role: str,
    years_experience: float,
    experience_band: str,
    difficulty: str,
    primary_skill: str,
    rng=None,
    exclude: set[str] | None = None,
    predicted_family: str | None = None,
    slot_index: int = 0,
) -> tuple[str, str, str, str, str]:
    """
    Return (question_text, category, generation_source, reference_keywords, reference_points).
    Primary source: interview_question_bank.csv (same pattern as quiz question_bank.csv).
    """
    exclude = normalize_exclude_set(exclude)
    category = primary_skill if focus_area == "technical" else "Behavioral"
    extra_skills = ROLE_INTERVIEW_SKILLS.get(job_role, [primary_skill])

    csv_pick = pick_interview_question_from_csv(
        focus_area=focus_area,
        job_role=job_role,
        experience_band=experience_band,
        difficulty=difficulty,
        rng=rng,
        exclude=exclude,
        slot_index=slot_index,
    )
    if csv_pick:
        question_text, topic, reference_keywords, reference_points = csv_pick
        if normalize_for_dedupe(question_text) not in exclude and question_text not in exclude:
            if focus_area == "technical" and topic:
                category = topic
            return question_text, category, "csv", reference_keywords, reference_points

    dynamic = build_role_experience_question(
        focus_area=focus_area,
        job_role=job_role,
        years_experience=years_experience,
        experience_band=experience_band,
        difficulty=difficulty,
        primary_skill=primary_skill,
        question_family=predicted_family,
        slot_index=slot_index,
        rng=rng if rng is not None else secrets.randbelow(2**31),
        exclude=exclude,
        extra_skills=extra_skills,
    )
    reference_keywords, reference_points = build_reference_metadata(
        dynamic, category, focus_area, job_role
    )
    source = "ml_guided" if predicted_family else "dynamic"
    return dynamic, category, source, reference_keywords, reference_points
