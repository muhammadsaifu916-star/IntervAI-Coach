"""
CSV-backed interview question bank (same pattern as quizzes.services.quiz_generator).

Reads interview_question_bank.csv and returns role + experience scoped questions.
"""

from __future__ import annotations

import csv
import random as py_random
from functools import lru_cache
from pathlib import Path
from typing import Any

from .question_quality import (
    is_polished_interview_question,
    normalize_for_dedupe,
    question_matches_experience_band,
)
from .reference_answer_scoring import build_reference_metadata
from .role_interview_constants import (
    DIFFICULTY_BY_BAND,
    EXPERIENCE_BAND_ORDER,
    USER_APPROVED_JOB_ROLES,
)
from .role_question_catalog import is_relevant_technical_question

BASE_DIR = Path(__file__).resolve().parent
INTERVIEW_QUESTION_BANK_PATH = BASE_DIR / "interview_question_bank.csv"

ROLE_ALIASES = {
    "Software Engineer": "Software Developer",
    "UI/UX Developer": "UI/UX  Developer",
    "ML Engineer": "Machine Learning Engineer",
    "Cyber Security Analyst": "Cybersecurity Analyst",
}


def normalize_csv_role(role: str) -> str:
    cleaned = str(role or "").strip()
    if not cleaned:
        return "Software Developer"
    return ROLE_ALIASES.get(cleaned, cleaned)


def normalize_focus_area(value: str) -> str:
    cleaned = str(value or "").strip().lower()
    if cleaned in {"personality", "behavioral", "soft_skill"}:
        return "personality"
    return "technical"


@lru_cache(maxsize=1)
def load_interview_question_bank() -> tuple[dict[str, Any], ...]:
    if not INTERVIEW_QUESTION_BANK_PATH.exists():
        raise FileNotFoundError(
            f"interview_question_bank.csv not found at {INTERVIEW_QUESTION_BANK_PATH}"
        )

    rows: list[dict[str, Any]] = []
    with INTERVIEW_QUESTION_BANK_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            question = str(row.get("question") or "").strip()
            role = normalize_csv_role(row.get("role") or "")
            experience_band = str(row.get("experience_band") or "").strip()
            difficulty = str(row.get("difficulty") or "medium").strip().lower()
            focus_area = normalize_focus_area(row.get("focus_area") or "technical")
            topic = str(row.get("topic") or "").strip()

            if not question or not role or not experience_band:
                continue
            if role not in USER_APPROVED_JOB_ROLES and role != "all":
                continue
            if difficulty not in {"easy", "medium", "hard"}:
                continue
            if focus_area == "technical" and not is_relevant_technical_question(role, question):
                continue
            if not is_polished_interview_question(question):
                continue
            if not question_matches_experience_band(question, experience_band):
                continue

            ref_keywords = str(row.get("reference_keywords") or "").strip()
            ref_points = str(row.get("reference_points") or "").strip()
            if not ref_keywords:
                ref_keywords, ref_points = build_reference_metadata(
                    question, topic or "Software Engineering", focus_area, role
                )
            elif not ref_points:
                _, ref_points = build_reference_metadata(
                    question, topic or "Software Engineering", focus_area, role
                )

            rows.append(
                {
                    "question_id": str(row.get("question_id") or "").strip(),
                    "question": question,
                    "role": role,
                    "experience_band": experience_band,
                    "difficulty": difficulty,
                    "focus_area": focus_area,
                    "topic": topic,
                    "reference_keywords": ref_keywords,
                    "reference_points": ref_points,
                }
            )
    return tuple(rows)


def _band_distance(left: str, right: str) -> int:
    try:
        return abs(EXPERIENCE_BAND_ORDER.index(left) - EXPERIENCE_BAND_ORDER.index(right))
    except ValueError:
        return 99


def _difficulty_distance(left: str, right: str) -> int:
    order = ["easy", "medium", "hard"]
    try:
        return abs(order.index(left) - order.index(right))
    except ValueError:
        return 99


def _normalize_difficulty(experience_band: str, difficulty: str) -> str:
    allowed = DIFFICULTY_BY_BAND.get(experience_band, ["medium"])
    if difficulty in allowed:
        return difficulty
    return allowed[0]


def _collect_csv_candidates(
    *,
    focus_area: str,
    job_role: str,
    experience_band: str,
    difficulty: str,
    exclude: set[str],
) -> list[dict[str, Any]]:
    role = normalize_csv_role(job_role)
    difficulty = _normalize_difficulty(experience_band, difficulty)
    allowed_difficulties = DIFFICULTY_BY_BAND.get(experience_band, ["medium"])
    bank = load_interview_question_bank()

    def unused(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        blocked = exclude or set()
        return [
            row for row in rows
            if normalize_for_dedupe(row["question"]) not in blocked
            and row["question"] not in blocked
            and question_matches_experience_band(row["question"], experience_band)
        ]

    def query(role_value: str, band: str, diff: str) -> list[dict[str, Any]]:
        matched = [
            row
            for row in bank
            if row["role"] == role_value
            and row["experience_band"] == band
            and row["difficulty"] == diff
            and row["focus_area"] == focus_area
        ]
        return unused(matched)

    exact = query(role, experience_band, difficulty)
    if exact:
        return exact

    for alt in sorted(allowed_difficulties, key=lambda item: _difficulty_distance(item, difficulty)):
        candidates = query(role, experience_band, alt)
        if candidates:
            return candidates

    return []


def pick_interview_question_from_csv(
    *,
    focus_area: str,
    job_role: str,
    experience_band: str,
    difficulty: str,
    rng,
    exclude: set[str] | None = None,
    slot_index: int = 0,
) -> tuple[str, str, str, str] | None:
    """Return (question_text, topic, reference_keywords, reference_points) from CSV."""
    exclude = exclude or set()
    candidates = _collect_csv_candidates(
        focus_area=focus_area,
        job_role=job_role,
        experience_band=experience_band,
        difficulty=difficulty,
        exclude=exclude,
    )
    if not candidates:
        return None

    if hasattr(rng, "shuffle"):
        picker = rng
    else:
        picker = py_random.Random(int(rng) + int(slot_index) * 7919)
    ordered = sorted(candidates, key=lambda row: str(row.get("question_id", "")))
    picker.shuffle(ordered)
    row = ordered[0]
    topic = row.get("topic") or ("Behavioral" if focus_area != "technical" else "")
    return (
        str(row["question"]),
        str(topic),
        str(row.get("reference_keywords") or ""),
        str(row.get("reference_points") or ""),
    )
