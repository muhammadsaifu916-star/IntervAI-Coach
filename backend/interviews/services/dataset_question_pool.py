"""Filtered real interview questions from training CSV datasets (candidate-facing `question` column)."""

from __future__ import annotations

import os
import random as py_random
import re
from functools import lru_cache

import pandas as pd

BASE_DIR = os.path.join(os.path.dirname(__file__), 'interview_ai', 'dataset')

GENERIC_PATTERN = re.compile(
    r'^how would you handle a .* problem (for|during|in|inside)',
    re.IGNORECASE,
)
META_PROMPT_MARKERS = (
    'question id',
    'ask a easy',
    'ask a medium',
    'ask a hard',
    'include practical constraints and evaluation points',
    'the answer should show examples, ownership, and reflection',
)


def _is_usable_question(text: str) -> bool:
    cleaned = str(text or '').strip()
    if len(cleaned) < 25:
        return False
    lower = cleaned.lower()
    if GENERIC_PATTERN.match(cleaned):
        return False
    if any(marker in lower for marker in META_PROMPT_MARKERS):
        return False
    return True


@lru_cache(maxsize=1)
def _load_technical_pool() -> pd.DataFrame:
    path = os.path.join(BASE_DIR, 'technical_interview_dataset.csv')
    df = pd.read_csv(path)[['skill_area', 'experience_band', 'question']].dropna()
    df = df[df['question'].apply(_is_usable_question)].drop_duplicates(subset=['question'])
    return df.reset_index(drop=True)


@lru_cache(maxsize=1)
def _load_personality_pool() -> pd.DataFrame:
    path = os.path.join(BASE_DIR, 'personality_interview_dataset.csv')
    df = pd.read_csv(path)[['trait', 'experience_band', 'question']].dropna()
    df = df[df['question'].apply(_is_usable_question)].drop_duplicates(subset=['question'])
    return df.reset_index(drop=True)


def _collect_from_pool(
    pool: pd.DataFrame,
    key_col: str,
    category: str,
    experience_band: str,
    exclude: set[str],
) -> list[str]:
    tiers = [
        pool[(pool[key_col] == category) & (pool['experience_band'] == experience_band)],
        pool[pool[key_col] == category],
        pool[pool['experience_band'] == experience_band],
        pool,
    ]
    for tier in tiers:
        if tier.empty:
            continue
        candidates = [
            str(row['question']).strip()
            for _, row in tier.iterrows()
            if str(row['question']).strip() not in exclude
        ]
        if candidates:
            return candidates
    return []


def pick_dataset_question(
    *,
    focus_area: str,
    category: str,
    experience_band: str,
    exclude: set[str] | None,
    rng,
) -> str | None:
    exclude = exclude or set()
    if focus_area == 'technical':
        pool = _load_technical_pool()
        key_col = 'skill_area'
    else:
        pool = _load_personality_pool()
        key_col = 'trait'

    candidates = _collect_from_pool(pool, key_col, category, experience_band, exclude)
    if not candidates:
        return None
    picker = rng if hasattr(rng, 'choice') else py_random.Random(int(rng))
    return str(picker.choice(candidates))
