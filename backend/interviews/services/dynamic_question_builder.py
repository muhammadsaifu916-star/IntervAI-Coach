"""Role- and experience-specific question templates (backend only, no external API)."""

from __future__ import annotations

import random as py_random
import secrets

from .question_quality import strip_experience_markers

ROLE_TECHNICAL_TEMPLATES = [
    (
        'As a {role}, explain how you use {skill} in real projects involving {scenario}. '
        'Describe a concrete scenario, the approach you took, trade-offs you considered, '
        'and how you validated the result.'
    ),
    (
        'You are a {role} working on a {difficulty}-complexity {skill} task for {scenario}. '
        'Walk through how you would design the solution, handle edge cases, and communicate risks to your team.'
    ),
    (
        'In your role as a {role}, a production issue affects {scenario} built with {skill}. '
        'Explain step by step how you would investigate, fix, and prevent recurrence.'
    ),
    (
        'As a {role}, how would you review a teammate\'s {skill}-related change for {scenario}, '
        'give constructive feedback, and ensure it is production-ready?'
    ),
    (
        'Imagine you join a team as a {role}. What would you focus on in your first month '
        'to understand {scenario} systems involving {skill} and deliver value safely?'
    ),
]

ROLE_BEHAVIORAL_TEMPLATES = [
    (
        'Tell me about a time as a {role} when you handled a difficult situation at work related to {scenario}. '
        'What happened, what did you do, and what was the result?'
    ),
    (
        'Describe a situation where you had to push back or negotiate as a {role} on {scenario}. '
        'How did you communicate and what was the outcome?'
    ),
    (
        'Share an example from your work as a {role} where you made a mistake or faced a setback on {scenario}. '
        'How did you recover and what did you learn?'
    ),
    (
        'As a {role}, tell me about a time you helped a teammate or stakeholder when {scenario} was at risk.'
    ),
    (
        'Describe how you prioritize and stay effective as a {role} when requirements for {scenario} change late '
        'in a sprint or release cycle.'
    ),
]

FAMILY_TECHNICAL = {
    'conceptual': (
        'As a {role}, explain the {skill} concepts you use most often in this role and how you would mentor someone junior on {scenario}.'
    ),
    'scenario': (
        'You are a {role} facing a realistic on-the-job {skill} scenario for {scenario} with reliability and deadline pressure. '
        'Explain your approach step by step.'
    ),
    'architecture': (
        'As a {role}, outline how you would architect a {difficulty}-complexity {skill} feature for {scenario}, '
        'including trade-offs and failure handling.'
    ),
    'debugging': (
        'A critical bug appears in production for a {role} while working on {scenario} with {skill}. '
        'Walk through your debugging plan from alert to verified fix.'
    ),
    'optimization': (
        'Your team needs to improve performance for {scenario} that you own as a {role} using {skill}. '
        'How would you measure, optimize, and prove the improvement?'
    ),
}

FAMILY_BEHAVIORAL = {
    'behavioral': (
        'Tell me about a specific situation as a {role} involving {scenario} that shows how you handle pressure, teamwork, or accountability.'
    ),
    'scenario': (
        'Imagine you are a {role} facing conflict between speed and quality on {scenario}. What would you do and why?'
    ),
}

TECHNICAL_SCENARIOS = [
    'a customer-facing API',
    'a reporting dashboard',
    'a payment workflow',
    'a data migration',
    'an authentication service',
    'a background job pipeline',
    'a mobile release',
    'a production incident',
    'a legacy module refactor',
    'a cross-team integration',
]

BEHAVIORAL_SCENARIOS = [
    'a high-priority release',
    'a production outage',
    'a cross-functional project',
    'a missed deadline',
    'a code review disagreement',
    'a stakeholder escalation',
    'a team handoff',
    'a scope change',
    'a quality-versus-speed trade-off',
    'a mentoring situation',
]


def _years_label(years_experience: float, experience_band: str) -> str:
    years = float(years_experience or 0)
    if years <= 0:
        return 'less than 1 year'
    if years == 1:
        return '1 year'
    if years == int(years):
        return f'{int(years)} years'
    return f'{years:.1f} years'


def _experience_label(experience_band: str) -> str:
    return experience_band.replace('_', ' ')


def _format_context(
    *,
    role: str,
    years_experience: float,
    experience_band: str,
    difficulty: str,
    primary_skill: str,
    slot_index: int,
    focus_area: str,
) -> dict[str, str]:
    scenarios = TECHNICAL_SCENARIOS if focus_area == 'technical' else BEHAVIORAL_SCENARIOS
    return {
        'role': role or 'Software Developer',
        'years_label': _years_label(years_experience, experience_band),
        'experience_label': _experience_label(experience_band),
        'difficulty': difficulty,
        'skill': primary_skill or 'your core stack',
        'scenario': scenarios[slot_index % len(scenarios)],
    }


def _iter_dynamic_variants(
    *,
    focus_area: str,
    job_role: str,
    years_experience: float,
    experience_band: str,
    difficulty: str,
    primary_skill: str,
    question_family: str | None,
    slot_index: int,
    extra_skills: list[str] | None = None,
) -> list[str]:
    role = job_role or 'Software Developer'
    family = str(question_family or '').strip().lower()
    variants: list[str] = []
    seen: set[str] = set()

    def add(template: str, context: dict[str, str]) -> None:
        text = strip_experience_markers(template.format(**context).strip())
        if text and text not in seen:
            variants.append(text)
            seen.add(text)

    skills = [primary_skill or 'your core stack']
    for skill in extra_skills or []:
        if skill and skill not in skills:
            skills.append(skill)

    for skill_index, skill in enumerate(skills):
        for offset in range(10):
            context = _format_context(
                role=role,
                years_experience=years_experience,
                experience_band=experience_band,
                difficulty=difficulty,
                primary_skill=skill,
                slot_index=slot_index + offset + skill_index,
                focus_area=focus_area,
            )
            if focus_area == 'technical' and family in FAMILY_TECHNICAL:
                add(FAMILY_TECHNICAL[family], context)
            elif focus_area != 'technical' and family in FAMILY_BEHAVIORAL:
                add(FAMILY_BEHAVIORAL[family], context)

            templates = ROLE_TECHNICAL_TEMPLATES if focus_area == 'technical' else ROLE_BEHAVIORAL_TEMPLATES
            for template_index, template in enumerate(templates):
                add(template, {
                    **context,
                    'scenario': (
                        (TECHNICAL_SCENARIOS if focus_area == 'technical' else BEHAVIORAL_SCENARIOS)[
                            (slot_index + template_index + offset + skill_index) % 10
                        ]
                    ),
                })

            for family_name, template in (
                FAMILY_TECHNICAL.items() if focus_area == 'technical' else FAMILY_BEHAVIORAL.items()
            ):
                add(template, context)

    return variants


def build_role_experience_question(
    *,
    focus_area: str,
    job_role: str,
    years_experience: float,
    experience_band: str,
    difficulty: str,
    primary_skill: str,
    rng=None,
    question_family: str | None = None,
    slot_index: int = 0,
    exclude: set[str] | None = None,
    extra_skills: list[str] | None = None,
) -> str:
    exclude = {str(item).strip() for item in (exclude or set()) if str(item).strip()}
    picker = rng if hasattr(rng, 'choice') else py_random.Random(
        int(rng) if rng is not None else secrets.randbelow(2**31) + int(slot_index)
    )
    variants = _iter_dynamic_variants(
        focus_area=focus_area,
        job_role=job_role,
        years_experience=years_experience,
        experience_band=experience_band,
        difficulty=difficulty,
        primary_skill=primary_skill,
        question_family=question_family,
        slot_index=slot_index,
        extra_skills=extra_skills,
    )
    shuffled = variants[:]
    picker.shuffle(shuffled)
    for candidate in shuffled:
        if candidate not in exclude:
            return candidate

    context = _format_context(
        role=job_role or 'Software Developer',
        years_experience=years_experience,
        experience_band=experience_band,
        difficulty=difficulty,
        primary_skill=primary_skill,
        slot_index=slot_index,
        focus_area=focus_area,
    )
    templates = ROLE_TECHNICAL_TEMPLATES if focus_area == 'technical' else ROLE_BEHAVIORAL_TEMPLATES
    base = templates[slot_index % len(templates)].format(**context).strip()
    suffix = 1
    while True:
        candidate = (
            f'{base} Use a different real example than in your earlier answers (follow-up {suffix}).'
        )
        if candidate not in exclude:
            return candidate
        suffix += 1
