"""DEPRECATED: External LLM API generation is disabled. Interview uses local backend AI."""

from __future__ import annotations


def llm_available() -> bool:
    return False


def generate_interview_question_llm(**kwargs) -> None:
    return None
