"""Quality and deduplication helpers for interview question text."""

from __future__ import annotations

import re

ROBOTIC_SUFFIXES = (
    "what would you do first, what trade-offs would you consider, and how would you validate the outcome",
    "what happened, what actions did you take, and what was the result",
    "what would you do first, what trade-offs would you consider",
)

ROBOTIC_PATTERNS = (
    re.compile(r"explain how you would approach .+ during .+\. what would you do first", re.I),
    re.compile(r"evaluate trade-offs when .+ during .+\. what would you do first", re.I),
    re.compile(r"walk through how you would handle .+ during .+\. what would you do first", re.I),
)

# Auto-generated variation templates that read repetitive in live interviews.
GENERIC_VARIATION_PATTERNS = (
    re.compile(r"walk through how you would ask for help when stuck on .+ during", re.I),
    re.compile(r"how would you debug .+ when .+", re.I),
    re.compile(r"design an approach to .+ for .+\. what trade-offs matter most", re.I),
    re.compile(r"describe the steps you would take to fix .+ during", re.I),
    re.compile(r"how would you lead troubleshooting for .+ during", re.I),
    re.compile(r"explain how you would prevent recurrence after handling .+ in", re.I),
)

FRESHER_ONLY_MARKERS = (
    "starting your career",
    "starting out",
    "beginning your career",
    "just starting your career",
)

SENIOR_ONLY_MARKERS = (
    "as a senior professional",
)

VETERAN_ONLY_MARKERS = (
    "as an industry veteran",
)

JUNIOR_ONLY_MARKERS = (
    "with 1–2 years of experience",
    "with 1-2 years of experience",
)

MID_ONLY_MARKERS = (
    "with 3–5 years of experience",
    "with 3-5 years of experience",
)

BAND_EXCLUSIVE_MARKERS: dict[str, tuple[str, ...]] = {
    "fresher": FRESHER_ONLY_MARKERS,
    "junior_professional": JUNIOR_ONLY_MARKERS,
    "mid_level_expert": MID_ONLY_MARKERS,
    "senior_professional": SENIOR_ONLY_MARKERS,
    "industry_veteran": VETERAN_ONLY_MARKERS,
}

ALL_EXPERIENCE_MARKERS: tuple[str, ...] = tuple(
    dict.fromkeys(
        marker
        for markers in BAND_EXCLUSIVE_MARKERS.values()
        for marker in markers
    )
) + (
    "with several years of experience",
    "with mid-level experience",
    "early in your career",
    "less than 1 year of experience",
)

_EXPERIENCE_MARKER_PATTERNS = (
    re.compile(r",?\s*starting your career,?", re.I),
    re.compile(r",?\s*just starting your career,?", re.I),
    re.compile(r",?\s*beginning your career,?", re.I),
    re.compile(r",?\s*starting out,?", re.I),
    re.compile(r",?\s*early in your career,?", re.I),
    re.compile(r",?\s*with 1–2 years of experience,?", re.I),
    re.compile(r",?\s*with 1-2 years of experience,?", re.I),
    re.compile(r",?\s*with 3–5 years of experience,?", re.I),
    re.compile(r",?\s*with 3-5 years of experience,?", re.I),
    re.compile(r",?\s*with several years of experience,?", re.I),
    re.compile(r",?\s*with mid-level experience,?", re.I),
    re.compile(r",?\s*as a senior professional,?", re.I),
    re.compile(r"\bas an industry veteran,?\s*", re.I),
    re.compile(r"\bas a senior professional,?\s*", re.I),
    re.compile(r"\bwith less than 1 year of experience\b", re.I),
    re.compile(r"\bwith \d+(?:\.\d+)? years of experience\b", re.I),
    re.compile(r"\bwith \d+(?:\.\d+)? year of experience\b", re.I),
    re.compile(
        r"\(\s*(?:junior professional|mid level expert|senior professional|industry veteran|fresher)\s*\)",
        re.I,
    ),
)


def normalize_question_text(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def normalize_for_dedupe(text: str) -> str:
    cleaned = normalize_question_text(text).lower()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return " ".join(cleaned.split())


def is_polished_interview_question(text: str) -> bool:
    """Reject repetitive auto-template phrasing; keep realistic interviewer prompts."""
    cleaned = normalize_question_text(text)
    if len(cleaned) < 35:
        return False
    if len(cleaned) > 280:
        return False

    lower = cleaned.lower()
    if any(suffix in lower for suffix in ROBOTIC_SUFFIXES):
        return False
    if any(pattern.search(cleaned) for pattern in ROBOTIC_PATTERNS):
        return False
    if any(pattern.search(cleaned) for pattern in GENERIC_VARIATION_PATTERNS):
        return False

    # Must look like a real question or interview prompt
    if not (
        lower.startswith("as a ")
        or lower.startswith("tell me")
        or lower.startswith("describe ")
        or lower.startswith("explain ")
        or lower.startswith("what ")
        or lower.startswith("how ")
        or lower.startswith("walk ")
        or lower.startswith("compare ")
        or lower.startswith("design ")
        or lower.startswith("share ")
        or lower.startswith("imagine ")
        or lower.startswith("you are ")
        or lower.startswith("in your role")
    ):
        return False

    return True


def strip_experience_markers(text: str) -> str:
    """Remove visible seniority/year phrases so prompts read like a real interview."""
    cleaned = normalize_question_text(text)
    if not cleaned:
        return cleaned

    for pattern in _EXPERIENCE_MARKER_PATTERNS:
        cleaned = pattern.sub("", cleaned)

    cleaned = re.sub(r",\s*,", ",", cleaned)
    cleaned = re.sub(r"\s+,", ",", cleaned)
    cleaned = re.sub(r",\s+", ", ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+\?", "?", cleaned)
    return cleaned.strip(" ,.")


def question_embeds_experience_markers(question: str) -> bool:
    cleaned = strip_experience_markers(question).lower()
    original = normalize_question_text(question).lower()
    return cleaned != original or any(marker in original for marker in ALL_EXPERIENCE_MARKERS)


def question_matches_experience_band(question: str, experience_band: str) -> bool:
    """Reject prompts whose wording clearly targets a different seniority band."""
    cleaned = strip_experience_markers(question).lower()
    band = str(experience_band or "").strip()

    for other_band, markers in BAND_EXCLUSIVE_MARKERS.items():
        if other_band == band:
            continue
        if any(marker in cleaned for marker in markers):
            return False

    has_fresher = any(marker in cleaned for marker in FRESHER_ONLY_MARKERS)
    has_senior = any(marker in cleaned for marker in SENIOR_ONLY_MARKERS)
    has_veteran = any(marker in cleaned for marker in VETERAN_ONLY_MARKERS)

    if band != "fresher" and has_fresher:
        return False
    if band == "fresher" and (has_senior or has_veteran):
        return False
    if band in {"fresher", "junior_professional"} and (has_senior or has_veteran):
        return False
    if band in {"fresher", "junior_professional", "mid_level_expert", "senior_professional"} and has_veteran:
        return False
    return True
