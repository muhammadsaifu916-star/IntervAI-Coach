"""
CSV-backed quiz generation service for Django.

This replaces the old mock _QUESTION_BANK generator.
It reads question_bank.csv and returns questions in the format expected by views.py:
[{ text, type, options, correct_answer, difficulty }, ...]
"""

import csv
import random
from functools import lru_cache
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
QUESTION_BANK_PATH = BASE_DIR / "question_bank.csv"

COMPULSORY_SUBJECTS = [
    "OOP",
    "DSA",
    "DBMS",
    "Programming Fundamentals",
]

ROLE_SUBJECT_MAPPING = {
    "AI Engineer": ["Machine Learning basics", "Python"],
    "Backend Developer": ["Django_Flask", "APIs", "Authentication", "Database"],
    "Blockchain Developer": ["Blockchain", "Solidity", "Cryptography basics"],
    "Business Analyst": ["Statistics", "SQL", "Excel", "Data Visualization"],
    "Cloud Engineer": ["Cloud basics", "Docker"],
    "Cybersecurity Analyst": ["Network Security", "OWASP", "Cryptography basics"],
    "Data Scientist": ["Python", "Machine Learning basics", "Pandas_NumPy", "Statistics"],
    "Database Administrator": ["SQL", "Databases", "Database Optimization"],
    "DevOps Engineer": ["Docker", "CI_CD", "Cloud basics", "Linux"],
    "Frontend Developer": ["HTML/CSS", "JavaScript", "React", "UI_UX_Basics"],
    "Full Stack Developer": ["HTML/CSS", "JavaScript", "React", "APIs", "Django_Flask"],
    "Java Developer": ["Java", "OOP", "Spring Boot"],
    "Machine Learning Engineer": ["Machine Learning basics", "Statistics", "Python"],
    "Mobile App Developer": ["Mobile Development"],
    "Python Developer": ["Python", "Django_Flask"],
    "QA Engineer": ["Testing"],
    "React Developer": ["React", "JavaScript", "HTML/CSS"],
    "Security Engineer": ["OWASP", "Network Security", "Linux"],
    "Software Developer": ["Programming Fundamentals", "OOP", "Git_GitHub"],
    "SQL Developer": ["SQL", "DBMS"],
    "UI/UX Developer": ["UI_UX_Basics", "HTML/CSS"],
}

ANSWER_INDEX = {
    "a": 0,
    "b": 1,
    "c": 2,
    "d": 3,
}


def _difficulty_for_experience(years_experience: float | int | str | None) -> str:
    try:
        years = float(years_experience or 0)
    except (TypeError, ValueError):
        years = 0

    if years <= 1:
        return "easy"
    if years <= 3:
        return "medium"
    return "hard"


@lru_cache(maxsize=1)
def _load_question_bank() -> list[dict[str, Any]]:
    if not QUESTION_BANK_PATH.exists():
        raise FileNotFoundError(f"question_bank.csv not found at {QUESTION_BANK_PATH}")

    questions: list[dict[str, Any]] = []

    with QUESTION_BANK_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            correct_letter = (row.get("correct_answer") or "").strip().lower()
            correct_index = ANSWER_INDEX.get(correct_letter)

            if correct_index is None:
                continue

            options = [
                (row.get("option_a") or "").strip(),
                (row.get("option_b") or "").strip(),
                (row.get("option_c") or "").strip(),
                (row.get("option_d") or "").strip(),
            ]

            if not all(options):
                continue

            questions.append(
                {
                    "question_id": (row.get("question_id") or "").strip(),
                    "text": (row.get("question") or "").strip(),
                    "topic": (row.get("topic") or "").strip(),
                    "subtopic": (row.get("subtopic") or "").strip(),
                    "role": (row.get("role") or "").strip(),
                    "difficulty": (row.get("difficulty") or "easy").strip().lower(),
                    "options": options,
                    "correct_answer": correct_index,
                    "explanation": (row.get("explanation") or "").strip(),
                }
            )

    return questions


def _pick_questions(
    pool: list[dict[str, Any]],
    count: int,
    used_ids: set[str],
) -> list[dict[str, Any]]:
    available = [q for q in pool if q["question_id"] not in used_ids]
    random.shuffle(available)
    selected = available[:count]
    used_ids.update(q["question_id"] for q in selected)
    return selected


def _filter_questions(
    questions: list[dict[str, Any]],
    *,
    topics: list[str],
    difficulty: str | None = None,
    role: str | None = None,
) -> list[dict[str, Any]]:
    result = [q for q in questions if q["topic"] in topics]

    if difficulty:
        result = [q for q in result if q["difficulty"] == difficulty]

    if role is not None:
        result = [q for q in result if q["role"] == role]

    return result


def _public_question(q: dict[str, Any]) -> dict[str, Any]:
    # Shuffle options so the correct answer is not always in the dataset's
    # original A/B/C/D position. This avoids answer-position bias.
    options_with_flags = [
        {"text": option, "is_correct": index == q["correct_answer"]}
        for index, option in enumerate(q["options"])
    ]
    random.shuffle(options_with_flags)

    return {
        "text": q["text"],
        "type": "mcq",
        "options": [item["text"] for item in options_with_flags],
        "correct_answer": next(
            index for index, item in enumerate(options_with_flags) if item["is_correct"]
        ),
        "difficulty": q["difficulty"],
        "topic": q.get("topic", ""),
        "subtopic": q.get("subtopic", ""),
        "explanation": q.get("explanation", ""),
    }


def generate_quiz_questions(
    job_role: str,
    years_experience: float,
    num_questions: int = 15,
) -> list[dict[str, Any]]:
    """
    Generate quiz questions from question_bank.csv.

    Returns the exact format expected by quizzes/views.py.
    correct_answer is a 0-based index, matching the frontend answer format.
    """
    questions = _load_question_bank()
    difficulty = _difficulty_for_experience(years_experience)
    role_subjects = ROLE_SUBJECT_MAPPING.get(job_role, [])
    used_ids: set[str] = set()
    selected: list[dict[str, Any]] = []

    # 1) Always include core/compulsory questions.
    compulsory_count = min(4, num_questions)
    compulsory_pool = _filter_questions(
        questions,
        topics=COMPULSORY_SUBJECTS,
        difficulty=difficulty,
        role="all",
    )
    selected.extend(_pick_questions(compulsory_pool, compulsory_count, used_ids))

    # 2) Add role-specific questions.
    remaining = num_questions - len(selected)
    if remaining > 0 and role_subjects:
        role_pool = _filter_questions(
            questions,
            topics=role_subjects,
            difficulty=difficulty,
            role=job_role,
        )
        selected.extend(_pick_questions(role_pool, remaining, used_ids))

    # 3) Fallback: same topics, any role, same difficulty.
    remaining = num_questions - len(selected)
    if remaining > 0:
        allowed_topics = COMPULSORY_SUBJECTS + role_subjects
        fallback_pool = _filter_questions(
            questions,
            topics=allowed_topics,
            difficulty=difficulty,
        )
        selected.extend(_pick_questions(fallback_pool, remaining, used_ids))

    # 4) Final fallback: same topics, any difficulty.
    remaining = num_questions - len(selected)
    if remaining > 0:
        allowed_topics = COMPULSORY_SUBJECTS + role_subjects
        fallback_pool = _filter_questions(questions, topics=allowed_topics)
        selected.extend(_pick_questions(fallback_pool, remaining, used_ids))

    # 5) Emergency fallback: any question, so quiz creation does not crash.
    remaining = num_questions - len(selected)
    if remaining > 0:
        selected.extend(_pick_questions(questions, remaining, used_ids))

    random.shuffle(selected)
    return [_public_question(q) for q in selected[:num_questions]]
