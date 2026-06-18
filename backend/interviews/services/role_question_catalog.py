"""Polished role-specific interview catalog — never mixes roles or mismatched difficulty."""

from __future__ import annotations

import random as py_random

from .expanded_interview_questions import (
    build_expanded_personality_questions,
    build_expanded_technical_questions,
)
from .interview_question_variations import (
    build_variation_personality_questions,
    build_variation_technical_questions,
)
from .realistic_question_bank import (
    PERSONALITY_QUESTIONS,
    ROLE_PERSONALITY_QUESTIONS,
    ROLE_TECHNICAL_QUESTIONS,
    TECHNICAL_QUESTIONS,
)
from .question_quality import question_matches_experience_band
from .role_interview_constants import (
    DIFFICULTY_BY_BAND,
    EXPERIENCE_BAND_ORDER,
    ROLE_FORBIDDEN_FRAGMENTS,
    ROLE_INTERVIEW_SKILLS,
    ROLE_PERSONALITY_TRAITS,
    ROLE_REQUIRED_TOPIC_MARKERS,
    USER_APPROVED_JOB_ROLES,
)

_EXPLICIT_ROLE_TECHNICAL = {
    question.strip()
    for questions in ROLE_TECHNICAL_QUESTIONS.values()
    for question in questions
    if str(question).strip()
}


def _adapt_question_for_role(role: str, question: str) -> str:
    cleaned = str(question or '').strip()
    if not cleaned:
        return cleaned
    lower = cleaned.lower()
    role_lower = role.lower()
    if role_lower in lower:
        return cleaned
    if cleaned[0].isupper():
        body = cleaned[0].lower() + cleaned[1:]
    else:
        body = cleaned
    return f'As a {role}, {body}'


def is_relevant_technical_question(role: str, question: str) -> bool:
    """Drop adapted skill questions that are off-topic for the job role."""
    cleaned = str(question or '').strip()
    if not cleaned:
        return False
    if cleaned in _EXPLICIT_ROLE_TECHNICAL:
        return True

    lower = cleaned.lower()
    for fragment in ROLE_FORBIDDEN_FRAGMENTS.get(role, ()):
        if fragment in lower:
            return False

    required = ROLE_REQUIRED_TOPIC_MARKERS.get(role)
    if required and not any(marker in lower for marker in required):
        return False
    return True


def _dedupe_extend(target: dict[tuple[str, str, str], list[str]], key, values: list[str]) -> None:
    existing = set(target.get(key, []))
    bucket = target.setdefault(key, [])
    for value in values:
        text = str(value).strip()
        if text and text not in existing:
            bucket.append(text)
            existing.add(text)


def _inject_industry_veteran_extras(
    catalog: dict[tuple[str, str, str], list[str]],
    *,
    technical: bool,
) -> None:
    """Ensure the industry_veteran band has enough unique, realistic prompts."""
    for role in USER_APPROVED_JOB_ROLES:
        skill = ROLE_INTERVIEW_SKILLS.get(role, ['Software Engineering'])[0]
        for difficulty in DIFFICULTY_BY_BAND['industry_veteran']:
            key = (role, 'industry_veteran', difficulty)
            if technical:
                extras = [
                    f'As a {role}, what multi-year strategy would you recommend for maturing {skill} practice across the organization?',
                    f'As a {role}, how would you decide whether to rebuild or retire a legacy {skill} platform?',
                    f'As a {role}, describe how you would mentor leads through a high-risk {skill} migration.',
                    f'As a {role}, what executive metrics would you use to justify investment in {skill} reliability?',
                    f'As a {role}, how would you align architecture standards for {skill} across multiple product teams?',
                    f'As a {role}, explain how you would run an organization-wide review after repeated incidents tied to {skill}.',
                ]
            else:
                extras = [
                    f'As a {role}, tell me about influencing organization-wide change when teams disagreed on priorities.',
                    f'As a {role}, describe how you handled a crisis that affected customers and required cross-department coordination.',
                    f'As a {role}, share how you developed future leaders on your team during a multi-year transformation.',
                    f'As a {role}, tell me about balancing innovation with operational stability during a major platform shift.',
                    f'As a {role}, describe how you rebuilt trust with stakeholders after a significant delivery failure.',
                ]
            _dedupe_extend(catalog, key, extras)


def _build_technical_catalog() -> dict[tuple[str, str, str], list[str]]:
    catalog: dict[tuple[str, str, str], list[str]] = {}
    for key, questions in ROLE_TECHNICAL_QUESTIONS.items():
        role = key[0]
        adapted = [_adapt_question_for_role(role, q) for q in questions]
        _dedupe_extend(catalog, key, adapted)

    for key, questions in build_expanded_technical_questions().items():
        _dedupe_extend(catalog, key, questions)

    for key, questions in build_variation_technical_questions().items():
        _dedupe_extend(catalog, key, questions)

    for role in USER_APPROVED_JOB_ROLES:
        for skill in ROLE_INTERVIEW_SKILLS.get(role, ['Software Engineering']):
            for (skill_key, band, difficulty), questions in TECHNICAL_QUESTIONS.items():
                if skill_key != skill:
                    continue
                adapted = [
                    text
                    for q in questions
                    if (text := _adapt_question_for_role(role, q))
                    and is_relevant_technical_question(role, text)
                    and question_matches_experience_band(text, band)
                ]
                _dedupe_extend(catalog, (role, band, difficulty), adapted)
    _inject_industry_veteran_extras(catalog, technical=True)
    return catalog


def _build_personality_catalog() -> dict[tuple[str, str, str], list[str]]:
    catalog: dict[tuple[str, str, str], list[str]] = {}
    for key, questions in ROLE_PERSONALITY_QUESTIONS.items():
        role = key[0]
        adapted = [_adapt_question_for_role(role, q) for q in questions]
        _dedupe_extend(catalog, key, adapted)

    for key, questions in build_expanded_personality_questions().items():
        _dedupe_extend(catalog, key, questions)

    for key, questions in build_variation_personality_questions().items():
        _dedupe_extend(catalog, key, questions)

    for role in USER_APPROVED_JOB_ROLES:
        for trait in ROLE_PERSONALITY_TRAITS.get(role, ['Communication', 'Collaboration']):
            for (trait_key, band, difficulty), questions in PERSONALITY_QUESTIONS.items():
                if trait_key != trait:
                    continue
                adapted = [
                    text
                    for q in questions
                    if (text := _adapt_question_for_role(role, q))
                    and question_matches_experience_band(text, band)
                ]
                _dedupe_extend(catalog, (role, band, difficulty), adapted)
    _inject_industry_veteran_extras(catalog, technical=False)
    return catalog


TECHNICAL_CATALOG = _build_technical_catalog()
PERSONALITY_CATALOG = _build_personality_catalog()


def _normalize_difficulty(experience_band: str, difficulty: str) -> str:
    allowed = DIFFICULTY_BY_BAND.get(experience_band, ['medium'])
    if difficulty in allowed:
        return difficulty
    return allowed[0]


def _band_distance(left: str, right: str) -> int:
    try:
        return abs(EXPERIENCE_BAND_ORDER.index(left) - EXPERIENCE_BAND_ORDER.index(right))
    except ValueError:
        return 99


def _difficulty_distance(left: str, right: str) -> int:
    order = ['easy', 'medium', 'hard']
    try:
        return abs(order.index(left) - order.index(right))
    except ValueError:
        return 99


def _filter_relevant(role: str, questions: list[str]) -> list[str]:
    return [q for q in questions if is_relevant_technical_question(role, q)]


def collect_role_scoped_candidates(
    bank: dict[tuple[str, str, str], list[str]],
    job_role: str,
    experience_band: str,
    difficulty: str,
    exclude: set[str],
    *,
    focus_area: str = 'technical',
) -> list[str]:
    """Collect questions for one role only; difficulty stays within the candidate band."""
    role = str(job_role or '').strip()
    if not role:
        return []

    difficulty = _normalize_difficulty(experience_band, difficulty)
    allowed_difficulties = DIFFICULTY_BY_BAND.get(experience_band, ['medium'])

    def unused_for(key: tuple[str, str, str]) -> list[str]:
        items = [q for q in bank.get(key, []) if q not in exclude]
        if focus_area == 'technical':
            items = _filter_relevant(role, items)
        return items

    exact = unused_for((role, experience_band, difficulty))
    if exact:
        return exact

    for alt in sorted(allowed_difficulties, key=lambda d: _difficulty_distance(d, difficulty)):
        candidates = unused_for((role, experience_band, alt))
        if candidates:
            return candidates

    return []


def pick_role_interview_question(
    focus_area: str,
    job_role: str,
    experience_band: str,
    difficulty: str,
    rng,
    exclude: set[str] | None = None,
) -> str | None:
    """Pick a polished question scoped to role + experience; never cross roles."""
    exclude = exclude or set()
    bank = TECHNICAL_CATALOG if focus_area == 'technical' else PERSONALITY_CATALOG
    candidates = collect_role_scoped_candidates(
        bank,
        job_role=job_role,
        experience_band=experience_band,
        difficulty=difficulty,
        exclude=exclude,
        focus_area=focus_area,
    )
    if not candidates:
        return None
    picker = rng if hasattr(rng, 'choice') else py_random.Random(int(rng))
    return str(picker.choice(candidates))
