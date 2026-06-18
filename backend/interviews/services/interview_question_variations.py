"""Natural role-specific question variations (concise, realistic interviewer tone)."""

from __future__ import annotations

from .question_quality import is_polished_interview_question, normalize_for_dedupe
from .role_interview_constants import (
    DIFFICULTY_BY_BAND,
    EXPERIENCE_BAND_ORDER,
    ROLE_FORBIDDEN_FRAGMENTS,
    ROLE_REQUIRED_TOPIC_MARKERS,
    USER_APPROVED_JOB_ROLES,
)

# Curated variations supplement the expanded question bank; keep volume modest.
MAX_TECHNICAL_PER_BAND = 28
MAX_PERSONALITY_PER_BAND = 18

BAND_TECHNICAL_TEMPLATES: dict[str, tuple[str, ...]] = {
    "fresher": (
        "As a {role}, what would you check before your first pull request that touches {topic}?",
        "As a {role}, explain {topic} in plain language for a non-technical teammate.",
        "As a {role}, how do you break an unfamiliar {topic} task into safe, reviewable steps?",
        "As a {role}, what resources would you use to learn {topic} before changing shared team code?",
    ),
    "junior_professional": (
        "As a {role}, a teammate reports a problem related to {topic}. What is your first hour of investigation?",
        "As a {role}, what production checks do you run before shipping a change involving {topic}?",
        "As a {role}, compare two reasonable ways to implement {topic} and when you would choose each.",
        "As a {role}, how do you document and communicate a {topic} fix for reviewers and QA?",
    ),
    "mid_level_expert": (
        "As a {role}, how would you scope and deliver a fix for {topic} under a tight deadline?",
        "As a {role}, what metrics or logs would you review first when {topic} misbehaves in production?",
        "As a {role}, explain the trade-offs you would discuss with your team before changing {topic}.",
        "As a {role}, how would you reduce repeat incidents related to {topic} after a postmortem?",
    ),
    "senior_professional": (
        "As a {role}, what standards would you set for code and reviews around {topic}?",
        "As a {role}, how would you reduce operational risk when your team owns {topic}?",
        "As a {role}, how would you prioritize {topic} improvements against new feature pressure?",
        "As a {role}, what would you expect in design docs before approving a {topic} change?",
    ),
    "industry_veteran": (
        "As a {role}, how would you coach others through a complex {topic} initiative?",
        "As a {role}, what long-term improvements would you propose for systems involving {topic}?",
        "As a {role}, how would you align multiple teams on a shared approach to {topic}?",
        "As a {role}, what indicators tell you it is time to replace or rebuild {topic} architecture?",
    ),
}

BAND_PERSONALITY_TEMPLATES: dict[str, tuple[str, ...]] = {
    "fresher": (
        "Tell me about a time as a {role} when you {behavior} on a learning task.",
        "Describe how you stayed coachable as a {role} when feedback challenged your approach.",
    ),
    "junior_professional": (
        "Tell me about a time as a {role} when you {behavior} during a delivery crunch.",
        "Describe a situation where you, as a {role}, {behavior} while coordinating with another team.",
    ),
    "mid_level_expert": (
        "Tell me about a time as a {role} when you {behavior} during a production issue. What was the outcome?",
        "As a {role}, share an example of when you {behavior} while owning a critical deliverable.",
    ),
    "senior_professional": (
        "As a {role}, describe when you {behavior} while guiding others through a high-stakes delivery.",
        "Tell me about a time as a {role} when you {behavior} and changed how the team worked.",
    ),
    "industry_veteran": (
        "As a {role}, share how you {behavior} while setting direction on a multi-team initiative.",
    ),
}

BEHAVIORS = (
    "communicated clearly under pressure",
    "resolved a disagreement with a teammate",
    "recovered from a mistake that affected users",
    "prioritized conflicting urgent tasks",
    "pushed back on an unrealistic deadline",
    "helped a struggling colleague deliver on time",
    "learned a new tool quickly to unblock delivery",
    "kept quality high when scope changed late",
)

ROLE_TOPICS: dict[str, tuple[str, ...]] = {
    "SQL Developer": (
        "optimizing a slow multi-table report query",
        "index design for heavy read workloads",
        "window functions for ranking reports",
        "transaction safety for financial updates",
        "schema migration validation",
        "deadlock troubleshooting on batch jobs",
    ),
    "Python Developer": (
        "Django ORM performance issues",
        "Celery task retries and idempotency",
        "Python API error handling",
        "memory use in long-running workers",
        "async I/O in Python services",
    ),
    "React Developer": (
        "React state management on a complex form",
        "unnecessary re-renders in a dashboard",
        "accessible modal and focus handling",
        "code-splitting for a heavy SPA",
        "stale closures in useEffect",
    ),
    "Java Developer": (
        "Spring Boot service layer testing",
        "JPA N+1 query problems",
        "transaction boundaries across services",
        "JVM memory issues under load",
        "REST API validation and errors",
    ),
    "Frontend Developer": (
        "Core Web Vitals on mobile",
        "responsive layout bugs",
        "frontend bundle size reduction",
        "cross-browser CSS issues",
        "client-side routing problems",
    ),
    "Backend Developer": (
        "payment webhook idempotency",
        "API rate limiting",
        "zero-downtime schema migrations",
        "service logging and traceability",
        "caching for read-heavy endpoints",
    ),
    "Full Stack Developer": (
        "auth flows across React and API",
        "CORS and cookie issues",
        "API versioning with multiple clients",
        "full-stack production debugging",
        "feature flags across UI and backend",
    ),
    "Data Scientist": (
        "class imbalance in a model",
        "data leakage in features",
        "explaining model limits to stakeholders",
        "time-series validation design",
        "monitoring model drift",
    ),
    "Machine Learning Engineer": (
        "model serving latency",
        "training-serving skew",
        "feature store design",
        "batch versus online inference",
        "model rollback in production",
    ),
    "AI Engineer": (
        "RAG pipeline quality",
        "prompt injection mitigation",
        "LLM hallucination evaluation",
        "PII redaction before inference",
        "embedding refresh pipelines",
    ),
    "DevOps Engineer": (
        "CI/CD pipeline failures",
        "Docker image security hardening",
        "Kubernetes rollout issues",
        "secrets management in CI",
        "incident rollback with migrations",
    ),
    "Cloud Engineer": (
        "multi-AZ failover design",
        "cloud cost spikes",
        "IAM least-privilege design",
        "serverless versus container choice",
        "managed database failover",
    ),
    "Security Engineer": (
        "OWASP risks in a public API",
        "secrets rotation without downtime",
        "investigating auth anomaly spikes",
        "patch prioritization for CVEs",
        "zero-trust admin access",
    ),
    "Cybersecurity Analyst": (
        "phishing incident triage",
        "lateral movement investigation",
        "SIEM false positive tuning",
        "patch compliance reporting",
        "ransomware tabletop response",
    ),
    "QA Engineer": (
        "risk-based test planning",
        "flaky test triage",
        "API regression testing",
        "exploratory testing under time pressure",
        "test data management",
    ),
    "Software Developer": (
        "debugging intermittent production bugs",
        "code review for security issues",
        "refactoring with low test coverage",
        "breaking down vague requirements",
        "unit versus integration testing strategy",
    ),
    "Business Analyst": (
        "writing testable acceptance criteria",
        "requirements workshops with stakeholders",
        "prioritizing conflicting scope requests",
        "validating reporting metrics with operations",
        "UAT planning with business users",
    ),
    "Database Administrator": (
        "backup restore verification",
        "index maintenance on busy tables",
        "connection pool exhaustion",
        "replication lag investigation",
        "major version upgrade planning",
    ),
    "Mobile App Developer": (
        "offline sync conflicts",
        "app startup performance",
        "OS-specific crash debugging",
        "secure token storage",
        "App Store release rollback",
    ),
    "Blockchain Developer": (
        "smart contract reentrancy risks",
        "gas optimization",
        "mainnet versus testnet failures",
        "on-chain upgrade safety",
        "transaction failure debugging",
    ),
    "UI/UX  Developer": (
        "usability testing for a checkout flow",
        "design system consistency",
        "accessibility before release",
        "handoff specs for engineers",
        "UX metrics tied to business goals",
    ),
}


def _is_relevant_technical(role: str, question: str) -> bool:
    lower = str(question or "").lower()
    for fragment in ROLE_FORBIDDEN_FRAGMENTS.get(role, ()):
        if fragment in lower:
            return False
    required = ROLE_REQUIRED_TOPIC_MARKERS.get(role)
    if required and not any(marker in lower for marker in required):
        return False
    return True


def _generate_bucketed(role: str, *, technical: bool) -> dict[tuple[str, str, str], list[str]]:
    """Generate band-appropriate variations with capped volume per band/difficulty."""
    topics = ROLE_TOPICS.get(role, ("core responsibilities for this role",))
    seen: set[str] = set()
    buckets: dict[tuple[str, str, str], list[str]] = {}
    cap_per_band = MAX_TECHNICAL_PER_BAND if technical else MAX_PERSONALITY_PER_BAND

    for band in EXPERIENCE_BAND_ORDER:
        templates = (
            BAND_TECHNICAL_TEMPLATES.get(band, BAND_TECHNICAL_TEMPLATES["junior_professional"])
            if technical
            else BAND_PERSONALITY_TEMPLATES.get(band, BAND_PERSONALITY_TEMPLATES["junior_professional"])
        )
        difficulties = DIFFICULTY_BY_BAND.get(band, ["medium"])
        per_diff_cap = max(3, cap_per_band // max(1, len(difficulties)))
        if band == "industry_veteran":
            per_diff_cap = max(per_diff_cap + 8, 16)

        for difficulty in difficulties:
            key = (role, band, difficulty)
            bucket = buckets.setdefault(key, [])
            diff_total = 0

            for template in templates:
                if diff_total >= per_diff_cap:
                    break
                primary_items = topics if technical else BEHAVIORS
                for item in primary_items[:5]:
                    if diff_total >= per_diff_cap:
                        break
                    if technical:
                        question = template.format(
                            role=role,
                            topic=item,
                        )
                    else:
                        question = template.format(
                            role=role,
                            behavior=item,
                        )
                    question = " ".join(question.split())
                    dedupe_key = normalize_for_dedupe(question)
                    if dedupe_key in seen:
                        continue
                    if not is_polished_interview_question(question):
                        continue
                    if technical and not _is_relevant_technical(role, question):
                        continue
                    seen.add(dedupe_key)
                    bucket.append(question)
                    diff_total += 1
    return buckets


def build_variation_technical_questions() -> dict[tuple[str, str, str], list[str]]:
    merged: dict[tuple[str, str, str], list[str]] = {}
    for role in USER_APPROVED_JOB_ROLES:
        for key, questions in _generate_bucketed(role, technical=True).items():
            merged.setdefault(key, []).extend(questions)
    return merged


def build_variation_personality_questions() -> dict[tuple[str, str, str], list[str]]:
    merged: dict[tuple[str, str, str], list[str]] = {}
    for role in USER_APPROVED_JOB_ROLES:
        for key, questions in _generate_bucketed(role, technical=False).items():
            merged.setdefault(key, []).extend(questions)
    return merged
