"""Verify generated interview questions match candidate role and experience band."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from interviews.services.interview_engine import prepare_interview_start  # noqa: E402
from interviews.services.role_interview_constants import (  # noqa: E402
    DIFFICULTY_BY_BAND,
    ROLE_FORBIDDEN_FRAGMENTS,
    ROLE_INTERVIEW_SKILLS,
    ROLE_REQUIRED_TOPIC_MARKERS,
    USER_APPROVED_JOB_ROLES,
    experience_band_from_years,
)
from interviews.services.role_question_catalog import is_relevant_technical_question  # noqa: E402

RESUME_YEARS = (1.0, 3.0, 5.0)
FORBIDDEN_PHRASES_BY_BAND = {
    "fresher": (
        "with 1-2 years",
        "with 1–2 years",
        "with 3-5 years",
        "with 3–5 years",
        "senior professional",
        "industry veteran",
    ),
    "junior_professional": (
        "starting your career",
        "starting out",
        "with 3-5 years",
        "with 3–5 years",
        "senior professional",
        "industry veteran",
    ),
    "mid_level_expert": (
        "starting your career",
        "starting out",
        "with 0-1 years",
        "entry level",
        "industry veteran",
    ),
    "senior_professional": (
        "starting your career",
        "starting out",
        "industry veteran",
    ),
    "industry_veteran": (
        "starting your career",
        "starting out",
    ),
}


def check_role_in_text(role: str, text: str) -> bool:
    lower = text.lower()
    if role.lower() in lower:
        return True
    # UI/UX role is stored with double space; CSV questions often use single space.
    if role.strip().lower().replace("  ", " ") in lower.replace("  ", " "):
        return True
    return False


def check_technical_question(role: str, question: dict) -> list[str]:
    issues: list[str] = []
    text = question.get("question_text", "")
    category = question.get("category", "")

    if not check_role_in_text(role, text):
        issues.append("missing role name in question text")

    if not is_relevant_technical_question(role, text):
        issues.append("failed is_relevant_technical_question")

    allowed_skills = set(ROLE_INTERVIEW_SKILLS.get(role, ["Software Engineering"]))
    if category and category not in allowed_skills and category != "Software Engineering":
        issues.append(f"category {category!r} not in allowed skills {sorted(allowed_skills)}")

    for fragment in ROLE_FORBIDDEN_FRAGMENTS.get(role, ()):
        if fragment in text.lower():
            issues.append(f"contains forbidden fragment {fragment!r}")

    required = ROLE_REQUIRED_TOPIC_MARKERS.get(role)
    if required and not any(marker in text.lower() for marker in required):
        issues.append("missing required topic markers for role")

    return issues


def check_experience(question: dict, band: str, years: float) -> list[str]:
    issues: list[str] = []
    text = question.get("question_text", "").lower()

    if question.get("experience_band") != band:
        issues.append(
            f"experience_band mismatch: got {question.get('experience_band')!r}, expected {band!r}"
        )

    if float(question.get("experience_years", -1)) != float(years):
        issues.append(
            f"experience_years mismatch: got {question.get('experience_years')!r}, expected {years!r}"
        )

    difficulty = str(question.get("difficulty_level", "medium")).lower()
    allowed = DIFFICULTY_BY_BAND.get(band, ["medium"])
    if difficulty not in allowed:
        issues.append(f"difficulty {difficulty!r} not allowed for band {band!r} ({allowed})")

    for phrase in FORBIDDEN_PHRASES_BY_BAND.get(band, ()):
        if phrase in text:
            issues.append(f"question text uses wrong seniority phrase {phrase!r}")

    return issues


def main() -> int:
    total_cases = 0
    failures: list[str] = []

    for role in USER_APPROVED_JOB_ROLES:
        for years in RESUME_YEARS:
            band = experience_band_from_years(years)
            total_cases += 1
            seed = hash((role, years)) % 100000

            payload = prepare_interview_start(
                quiz_passed=True,
                job_role=role,
                years_experience=years,
                num_questions=6,
                seed=seed,
            )

            if not payload.get("can_start_interview"):
                failures.append(f"{role} @ {years}y: cannot start — {payload.get('message')}")
                continue

            if payload.get("experience_band") != band:
                failures.append(
                    f"{role} @ {years}y: payload band {payload.get('experience_band')!r} != {band!r}"
                )

            questions = payload.get("questions") or []
            if len(questions) != 6:
                failures.append(f"{role} @ {years}y: expected 6 questions, got {len(questions)}")

            for idx, q in enumerate(questions, start=1):
                qtype = q.get("question_type")
                label = f"{role} @ {years}y ({band}) Q{idx} [{qtype}]"
                issues = check_experience(q, band, years)
                if qtype == "technical":
                    issues.extend(check_technical_question(role, q))
                if issues:
                    snippet = q.get("question_text", "")[:100]
                    failures.append(f"{label}: {', '.join(issues)} | {snippet!r}")

    print("=" * 72)
    print(f"Checked {total_cases} role × experience combinations ({len(USER_APPROVED_JOB_ROLES)} roles × 3 tiers)")
    print(f"Failures: {len(failures)}")
    print("=" * 72)

    if failures:
        for item in failures[:40]:
            print(f"  FAIL: {item}")
        if len(failures) > 40:
            print(f"  ... and {len(failures) - 40} more")
        return 1

    # Sample output for a few roles
    print("Sample generations (all checks passed):\n")
    samples = [
        ("Python Developer", 3.0),
        ("React Developer", 1.0),
        ("SQL Developer", 5.0),
        ("DevOps Engineer", 3.0),
    ]
    for role, years in samples:
        band = experience_band_from_years(years)
        payload = prepare_interview_start(
            quiz_passed=True,
            job_role=role,
            years_experience=years,
            num_questions=6,
            seed=42,
        )
        print(f"--- {role} | years={years} | band={band} ---")
        for q in payload["questions"]:
            print(f"  [{q['question_type']}/{q.get('category','')}] {q['question_text'][:120]}...")
        print()

    print("PASS: Generated questions align with role and experience for all combinations tested.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
