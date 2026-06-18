"""Rebuild interview_question_bank.csv from role/experience catalogs.

Experience band is stored in CSV metadata only — question text no longer
embeds years-of-experience or seniority labels.
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from interviews.services.question_quality import (  # noqa: E402
    is_polished_interview_question,
    normalize_for_dedupe,
    question_embeds_experience_markers,
    question_matches_experience_band,
    strip_experience_markers,
)
from interviews.services.reference_answer_scoring import build_reference_metadata  # noqa: E402
from interviews.services.role_interview_constants import (  # noqa: E402
    DIFFICULTY_BY_BAND,
    ROLE_INTERVIEW_SKILLS,
)
from interviews.services.role_question_catalog import (  # noqa: E402
    PERSONALITY_CATALOG,
    TECHNICAL_CATALOG,
)

CSV_PATH = Path(__file__).resolve().parents[1] / "services" / "interview_question_bank.csv"
FIELDNAMES = (
    "question_id",
    "question",
    "role",
    "experience_band",
    "difficulty",
    "focus_area",
    "topic",
    "reference_keywords",
    "reference_points",
)


def _collect_rows() -> list[dict[str, str]]:
    collected: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()

    for focus_area, catalog in (
        ("technical", TECHNICAL_CATALOG),
        ("personality", PERSONALITY_CATALOG),
    ):
        for (role, band, difficulty), questions in sorted(catalog.items()):
            allowed = DIFFICULTY_BY_BAND.get(band, ["medium"])
            if difficulty not in allowed:
                continue

            topic = (
                ROLE_INTERVIEW_SKILLS.get(role, ["Software Engineering"])[0]
                if focus_area == "technical"
                else "Behavioral"
            )

            for raw in questions:
                question = strip_experience_markers(str(raw or "").strip())
                if not question or not is_polished_interview_question(question):
                    continue
                if question_embeds_experience_markers(question):
                    continue
                if not question_matches_experience_band(question, band):
                    continue

                dedupe_key = (role, band, difficulty, focus_area, normalize_for_dedupe(question))
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                reference_keywords, reference_points = build_reference_metadata(
                    question,
                    topic,
                    focus_area,
                    role,
                )
                collected.append(
                    {
                        "question": question,
                        "role": role,
                        "experience_band": band,
                        "difficulty": difficulty,
                        "focus_area": focus_area,
                        "topic": topic,
                        "reference_keywords": reference_keywords,
                        "reference_points": reference_points,
                    }
                )

    collected.sort(
        key=lambda row: (
            row["role"],
            row["experience_band"],
            row["difficulty"],
            row["focus_area"],
            row["question"],
        )
    )

    for index, row in enumerate(collected, start=1):
        row["question_id"] = f"INT_{index:05d}"
    return collected


def main() -> int:
    rows = _collect_rows()
    if len(rows) < 4000:
        print(f"ERROR: only {len(rows)} questions collected (need at least 4000).")
        return 1

    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    unique_texts = {row["question"] for row in rows}
    print(f"Wrote {len(rows)} rows ({len(unique_texts)} unique texts) to {CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
