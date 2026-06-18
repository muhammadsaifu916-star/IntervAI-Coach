"""One-off analysis: find question tokens not covered by reference keywords."""
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
    build_reference_metadata,
    parse_reference_keywords,
)
from interviews.services.role_interview_constants import (  # noqa: E402
    ROLE_INTERVIEW_SKILLS,
    USER_APPROVED_JOB_ROLES,
)
from interviews.services.role_question_catalog import (  # noqa: E402
    PERSONALITY_CATALOG,
    TECHNICAL_CATALOG,
)

BASE = Path(__file__).resolve().parents[1] / "services"

STOP = {
    "would", "could", "should", "explain", "describe", "tell", "walk", "share",
    "about", "your", "when", "what", "how", "with", "during", "through", "role",
    "developer", "engineer", "scientist", "analyst", "experience", "professional",
    "veteran", "senior", "junior", "handle", "problem", "constraints", "trade",
    "offs", "validation", "dashboard", "time", "years", "career", "starting",
    "design", "compare", "given", "need", "outline", "approach", "feature",
    "production", "debug", "choose", "between", "without", "using", "built",
    "write", "find", "belong", "department", "last", "days", "joined", "employees",
    "duplicate", "first", "log", "user", "ids", "array", "linked", "list", "binary",
    "search", "complexity", "cache", "merge", "sorted", "walk", "through", "the",
    "and", "for", "that", "this", "from", "have", "has", "are", "was", "were",
    "you", "they", "their", "them", "into", "over", "under", "after", "before",
    "while", "where", "which", "will", "can", "may", "might", "also", "such",
    "each", "other", "some", "any", "all", "not", "but", "than", "then", "there",
    "here", "being", "been", "being", "would", "could", "should", "does", "did",
    "doing", "done", "make", "made", "take", "took", "use", "used", "using",
    "work", "working", "worked", "help", "helps", "helped", "keep", "kept",
    "show", "shows", "showed", "give", "gives", "gave", "get", "gets", "got",
    "set", "sets", "put", "puts", "run", "runs", "ran", "one", "two", "three",
    "four", "five", "six", "seven", "eight", "nine", "ten", "new", "old", "good",
    "bad", "best", "worst", "more", "most", "less", "least", "much", "many",
    "few", "large", "small", "high", "low", "long", "short", "fast", "slow",
    "real", "world", "example", "concrete", "project", "team", "company",
    "client", "customer", "product", "service", "system", "process", "plan",
    "step", "steps", "way", "ways", "case", "cases", "type", "types", "part",
    "parts", "point", "points", "issue", "issues", "risk", "risks", "task",
    "tasks", "goal", "goals", "data", "information", "details", "detail",
    "question", "answer", "interview", "job", "position", "candidate",
}


def token_covered(token: str, parsed: set[str]) -> bool:
    if token in parsed:
        return True
    return any(token in p or p in token for p in parsed)


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
                if "personality" in fa or "behavioral" in fa:
                    fa = "personality"
                else:
                    fa = "technical"
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


def main():
    questions = collect_questions()
    print(f"Total questions: {len(questions)}")

    role_uncovered: dict[str, Counter] = defaultdict(Counter)
    for role, topic, fa, q in questions:
        if role not in USER_APPROVED_JOB_ROLES:
            continue
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9+\-]{2,}", q.lower())
        keywords, _ = build_reference_metadata(q, topic or "Software Engineering", fa, role)
        parsed = set(parse_reference_keywords(keywords))
        for token in tokens:
            if token in STOP or len(token) <= 2:
                continue
            if not token_covered(token, parsed):
                role_uncovered[role][token] += 1

    for role in USER_APPROVED_JOB_ROLES:
        top = role_uncovered[role].most_common(20)
        if top:
            print(f"\n{role}:")
            print(", ".join(f"{t}({c})" for t, c in top))


if __name__ == "__main__":
    main()
