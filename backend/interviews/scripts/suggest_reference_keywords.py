"""Generate role/topic keyword extensions from interview question datasets."""
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

import django
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from interviews.services.reference_answer_scoring import (  # noqa: E402
    QUESTION_HINT_STOPWORDS,
    TOPIC_REFERENCE_KEYWORDS,
    ROLE_REFERENCE_KEYWORDS,
    PERSONALITY_TRAIT_REFERENCE_KEYWORDS,
    parse_reference_keywords,
    build_reference_metadata,
)
from interviews.services.role_interview_constants import (  # noqa: E402
    ROLE_INTERVIEW_SKILLS,
    ROLE_PERSONALITY_TRAITS,
    ROLE_REQUIRED_TOPIC_MARKERS,
    USER_APPROVED_JOB_ROLES,
)
from interviews.services.role_question_catalog import (  # noqa: E402
    PERSONALITY_CATALOG,
    TECHNICAL_CATALOG,
)

BASE = Path(__file__).resolve().parents[1] / "services"
GENERIC = QUESTION_HINT_STOPWORDS | {
    "the", "and", "for", "that", "this", "from", "have", "has", "are", "was", "were",
    "you", "they", "their", "them", "into", "over", "under", "after", "before",
    "while", "where", "which", "will", "can", "may", "might", "also", "such",
    "each", "other", "some", "any", "all", "not", "but", "than", "then", "there",
    "here", "being", "been", "does", "did", "doing", "done", "make", "made",
    "take", "took", "use", "used", "using", "work", "working", "worked", "help",
    "keep", "kept", "show", "shows", "give", "gives", "get", "gets", "got", "set",
    "sets", "put", "puts", "run", "runs", "ran", "one", "two", "three", "four",
    "five", "six", "seven", "eight", "nine", "ten", "new", "old", "good", "bad",
    "best", "worst", "more", "most", "less", "least", "much", "many", "few",
    "large", "small", "high", "low", "long", "short", "fast", "slow", "real",
    "world", "example", "concrete", "project", "team", "company", "client",
    "customer", "product", "service", "system", "process", "plan", "step", "steps",
    "way", "ways", "case", "cases", "type", "types", "part", "parts", "point",
    "points", "issue", "issues", "risk", "risks", "task", "tasks", "goal", "goals",
    "information", "details", "detail", "question", "answer", "interview", "job",
    "position", "candidate", "include", "practical", "examples", "evaluation",
    "reflection", "ownership", "found", "failed", "date", "late", "fixed", "bug",
    "demo", "documents", "hourly", "update", "limited", "software", "engineering",
    "stack", "documents",
}


def collect_questions():
    questions = []
    csv_path = BASE / "interview_question_bank.csv"
    if csv_path.exists():
        with csv_path.open(encoding="utf-8-sig") as file:
            for row in csv.DictReader(file):
                q = (row.get("question") or "").strip()
                role = (row.get("role") or "").strip()
                topic = (row.get("topic") or "").strip()
                fa = (row.get("focus_area") or "technical").strip().lower()
                if q and role:
                    questions.append((role, topic, fa, q))

    dataset_dir = BASE / "interview_ai" / "dataset"
    for name in (
        "technical_interview_dataset.csv",
        "personality_interview_dataset.csv",
        "interview_question_generation_dataset.csv",
    ):
        path = dataset_dir / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig") as file:
            for row in csv.DictReader(file):
                q = (row.get("question_text") or row.get("question") or "").strip()
                role = (row.get("role") or row.get("job_role") or "").strip()
                topic = (
                    row.get("topic")
                    or row.get("skill_area")
                    or row.get("category")
                    or row.get("trait")
                    or ""
                ).strip()
                fa = (row.get("focus_area") or row.get("question_type") or "technical").strip().lower()
                fa = "personality" if "personality" in fa or "behavioral" in fa else "technical"
                if q:
                    questions.append((role, topic, fa, q))

    for (role, _band, _diff), qs in TECHNICAL_CATALOG.items():
        skill = ROLE_INTERVIEW_SKILLS.get(role, ["Software Engineering"])[0]
        for q in qs:
            questions.append((role, skill, "technical", q))
    for (role, _band, _diff), qs in PERSONALITY_CATALOG.items():
        for q in qs:
            questions.append((role, "Behavioral", "personality", q))
    return questions


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z0-9+\-]{2,}", str(text or "").lower())


def main():
    questions = collect_questions()
    role_tokens: dict[str, Counter] = defaultdict(Counter)
    topic_tokens: dict[str, Counter] = defaultdict(Counter)

    for role, topic, fa, q in questions:
        if role not in USER_APPROVED_JOB_ROLES:
            continue
        for token in tokenize(q):
            if token in GENERIC or len(token) <= 2:
                continue
            role_tokens[role][token] += 1
            if fa == "technical" and topic:
                topic_tokens[topic][token] += 1

    print("# Suggested ROLE extensions (top tokens not in current role keywords):")
    for role in USER_APPROVED_JOB_ROLES:
        existing = set(parse_reference_keywords("|".join(ROLE_REFERENCE_KEYWORDS.get(role, ()))))
        for skill in ROLE_INTERVIEW_SKILLS.get(role, []):
            existing.update(TOPIC_REFERENCE_KEYWORDS.get(skill, ()))
        for marker in ROLE_REQUIRED_TOPIC_MARKERS.get(role, ()):
            existing.add(marker.lower())
        extras = []
        for token, count in role_tokens[role].most_common(40):
            if token in existing:
                continue
            if any(token in e or e in token for e in existing):
                continue
            extras.append(token)
            if len(extras) >= 12:
                break
        if extras:
            print(f"  '{role}': extras -> {extras}")

    skills = sorted({s for skills in ROLE_INTERVIEW_SKILLS.values() for s in skills})
    print("\n# Suggested TOPIC extensions:")
    for skill in skills:
        existing = set(TOPIC_REFERENCE_KEYWORDS.get(skill, ()))
        extras = []
        for token, _count in topic_tokens[skill].most_common(50):
            if token in existing or any(token in e or e in token for e in existing):
                continue
            extras.append(token)
            if len(extras) >= 15:
                break
        if extras:
            print(f"  '{skill}': {extras}")


if __name__ == "__main__":
    main()
