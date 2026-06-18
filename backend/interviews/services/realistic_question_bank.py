"""Curated realistic interview questions by skill/trait, experience band, and difficulty.

These override the generic template questions in the CSV datasets at runtime.
"""

from __future__ import annotations

import random as py_random

# experience_band values match engine.py
# difficulty: easy | medium | hard

TECHNICAL_QUESTIONS: dict[tuple[str, str, str], list[str]] = {
    ('DSA', 'fresher', 'easy'): [
        'Explain the difference between an array and a linked list. When would you choose one over the other?',
        'What is the time complexity of binary search, and what precondition must the input satisfy?',
        'Walk through how you would detect a cycle in a linked list.',
    ],
    ('DSA', 'junior_professional', 'medium'): [
        'Given a log of user IDs sorted by timestamp, how would you find the first duplicate in O(n) time?',
        'Compare hash map versus binary search tree trade-offs for an in-memory cache keyed by string.',
        'How would you design a function to merge two sorted arrays without using built-in sort?',
    ],
    ('DSA', 'mid_level_expert', 'hard'): [
        'Design an LRU cache with O(1) get and put. Explain the data structures and edge cases.',
        'How would you choose between Dijkstra, Bellman-Ford, and A* for a routing feature with changing edge weights?',
        'Describe how you would debug a performance regression caused by accidental O(n^2) behavior in production traffic.',
    ],
    ('DSA', 'senior_professional', 'hard'): [
        'You need a top-K streaming counter over 50M events/minute with bounded memory. Outline your approach.',
        'Explain how consistent hashing helps during cluster scale-out and what happens when nodes fail.',
        'How would you evaluate whether to replace a custom graph algorithm with an off-the-shelf library?',
    ],
    ('React', 'fresher', 'easy'): [
        'What is the difference between props and state in React? Give a concrete example.',
        'When does React re-render a component, and how can unnecessary re-renders be reduced?',
        'Explain what a React hook is and describe one hook you have used in a project.',
    ],
    ('React', 'junior_professional', 'medium'): [
        'How would you lift state versus using Context for a multi-step form shared across components?',
        'Describe how you would debug a memory leak caused by effects not cleaning up subscriptions.',
        'Compare controlled and uncontrolled components. When is each appropriate?',
    ],
    ('React', 'mid_level_expert', 'hard'): [
        'How would you architect code-splitting and lazy loading for a dashboard with heavy chart libraries?',
        'Explain your strategy for preventing stale closures in async effects and event handlers.',
        'What trade-offs would you consider between React Server Components and client-side rendering for an authenticated app?',
    ],
    ('React', 'senior_professional', 'hard'): [
        'Design a reusable data-table component that supports virtualization, sorting, and accessibility.',
        'How would you migrate a large class-based codebase to hooks without freezing feature delivery?',
        'Describe how you would measure and improve Core Web Vitals for a React SPA under slow networks.',
    ],
    ('DBMS', 'fresher', 'easy'): [
        'Explain primary keys, foreign keys, and why referential integrity matters.',
        'What is database normalization, and why might you stop at 3NF instead of going further?',
        'Write a SQL query to find employees who joined in the last 30 days and belong to a given department.',
    ],
    ('DBMS', 'junior_professional', 'medium'): [
        'How do indexes speed up reads, and what are the write-side costs of over-indexing?',
        'Explain ACID properties with an example involving a money transfer between two accounts.',
        'When would you choose a window function over a self-join in SQL?',
    ],
    ('Django', 'junior_professional', 'medium'): [
        'Explain how Django ORM lazy queryset evaluation can cause N+1 queries and how you would fix it.',
        'How would you structure authentication and permissions in a Django REST API?',
        'Describe your approach to writing migrations safely on a production database with zero downtime.',
    ],
    ('Django', 'mid_level_expert', 'hard'): [
        'Design a caching strategy for a Django view that aggregates data from three services with different SLAs.',
        'How would you debug a memory leak in a long-running Celery worker processing large payloads?',
        'Compare Django async views versus traditional sync views for an I/O-heavy endpoint.',
    ],
    ('DBMS', 'mid_level_expert', 'hard'): [
        'A nightly batch job deadlocks during peak hours. Walk through your investigation and mitigation plan.',
        'Compare row-level locking strategies in PostgreSQL versus MySQL for a high-contention inventory table.',
        'How would you design a migration from single-master to read replicas without downtime?',
    ],
    ('DBMS', 'senior_professional', 'hard'): [
        'Design a sharding strategy for a multi-tenant SaaS product with uneven tenant sizes.',
        'Explain how you would detect and fix query plan regressions after a major version upgrade.',
        'What is your approach to balancing strong consistency and availability during a regional outage?',
    ],
    ('DevOps', 'junior_professional', 'medium'): [
        'Describe a CI pipeline you would set up for a Django + React monorepo.',
        'How do you roll back a bad deployment safely when database migrations are involved?',
        'Explain blue/green versus canary deployments and when you prefer each.',
    ],
    ('DevOps', 'senior_professional', 'hard'): [
        'Design observability for a microservice that suddenly spikes 5xx errors after a config change.',
        'How would you secure secrets in CI/CD without exposing them to pull-request builds from forks?',
        'Outline your disaster recovery plan for a stateful service with RPO under 15 minutes.',
    ],
    ('Machine Learning', 'junior_professional', 'medium'): [
        'Explain precision, recall, and F1. When would you optimize recall over precision?',
        'How do you detect and mitigate data leakage during feature engineering?',
        'Describe your validation strategy for a model trained on imbalanced classes.',
    ],
    ('Machine Learning', 'senior_professional', 'hard'): [
        'How would you monitor model drift in production and trigger retraining responsibly?',
        'Compare batch inference versus online inference trade-offs for a fraud detection system.',
        'Explain how you would explain model decisions to a non-technical compliance reviewer.',
    ],
    ('Software Engineering', 'fresher', 'easy'): [
        'What is the difference between unit tests and integration tests? Give examples from your experience.',
        'How do you approach reading unfamiliar code in a team codebase?',
        'Describe a bug you fixed and how you verified the fix did not break other behavior.',
    ],
    ('Software Engineering', 'mid_level_expert', 'hard'): [
        'How would you break down a vague stakeholder request into deliverable milestones?',
        'Explain your code review checklist for security, performance, and maintainability.',
        'Describe how you would refactor a critical module with poor test coverage without stopping releases.',
    ],
    ('Networking', 'mid_level_expert', 'hard'): [
        'Explain how TLS handshakes work and what happens when certificate validation fails in production.',
        'How would you troubleshoot intermittent latency between two services in different availability zones?',
        'Compare TCP and UDP for a real-time telemetry pipeline with occasional packet loss tolerance.',
    ],
    ('Artificial Intelligence', 'senior_professional', 'hard'): [
        'How would you design guardrails for an LLM feature that summarizes user-provided documents?',
        'Explain retrieval-augmented generation and how you would evaluate hallucination rate.',
        'What metrics would you track for prompt changes that affect latency and answer quality?',
    ],
}

# Role-first questions: keyed by (job_role, experience_band, difficulty).
# These are shown before skill/trait banks so questions match the candidate profile.
ROLE_TECHNICAL_QUESTIONS: dict[tuple[str, str, str], list[str]] = {
    ('Python Developer', 'fresher', 'easy'): [
        'As a Python Developer, explain the difference between a list and a tuple. When would you choose each in real code?',
        'What is a virtual environment in Python, and why do teams use it on shared projects?',
        'Describe how you would read a CSV file in Python and handle missing values safely.',
    ],
    ('Python Developer', 'junior_professional', 'medium'): [
        'You are a Python Developer on a Django team. How would you find and fix N+1 query problems in a slow list endpoint?',
        'Explain how you would structure error handling and logging in a Python REST API used by mobile clients.',
        'Compare using dataclasses versus plain dictionaries for structured API payloads in Python.',
    ],
    ('Python Developer', 'mid_level_expert', 'hard'): [
        'As a Python Developer, design a caching strategy for a Django view that aggregates data from three services with different SLAs.',
        'As a Python Developer, walk through how you would debug a memory leak in a long-running Celery worker processing large JSON payloads.',
        'As a Python Developer, how would you migrate a synchronous Django codebase toward async views for I/O-heavy endpoints without breaking releases?',
    ],
    ('Python Developer', 'senior_professional', 'hard'): [
        'You lead Python services handling 10k requests/minute. How would you approach profiling, bottleneck isolation, and safe rollout of optimizations?',
        'Design a multi-tenant background job system in Python with fair scheduling and observability.',
        'How would you evaluate whether to replace custom Python data pipelines with managed cloud services?',
    ],
    ('React Developer', 'fresher', 'easy'): [
        'As a React Developer, explain props versus state with a simple form example from your learning or projects.',
        'What causes unnecessary re-renders in React, and name two practical ways to reduce them.',
        'Describe how you would fetch data from an API and show loading and error states in a React component.',
    ],
    ('React Developer', 'junior_professional', 'medium'): [
        'You maintain a React dashboard. How would you decide between lifting state, Context, and a state library for shared form data?',
        'Describe how you would debug a memory leak caused by effects not cleaning up subscriptions.',
        'How do you keep accessibility in mind when building custom React components such as modals or dropdowns?',
    ],
    ('React Developer', 'mid_level_expert', 'hard'): [
        'As a React Developer with production experience, how would you architect code-splitting and lazy loading for a dashboard with heavy chart libraries?',
        'Explain your strategy for preventing stale closures in async effects and event handlers at scale.',
        'What trade-offs would you weigh between server components and client-side rendering for an authenticated SaaS app?',
    ],
    ('Java Developer', 'junior_professional', 'medium'): [
        'As a Java Developer, explain how you would design a service layer that stays testable when the database and external APIs change often.',
        'Compare ArrayList versus LinkedList for a high-read, low-write workload and justify your choice.',
        'How would you handle transaction boundaries when one user action updates multiple tables?',
    ],
    ('Java Developer', 'mid_level_expert', 'hard'): [
        'Design a thread-safe in-memory cache in Java for a read-heavy catalog service. What eviction policy would you use and why?',
        'How would you troubleshoot intermittent OutOfMemoryError in a Spring Boot service under peak traffic?',
        'Explain how you would migrate a monolithic Java module to a separate service without a big-bang release.',
    ],
    ('Data Scientist', 'junior_professional', 'medium'): [
        'As a Data Scientist, explain how you would validate a classification model when classes are heavily imbalanced.',
        'How do you detect and prevent data leakage during feature engineering for a churn model?',
        'Describe how you would communicate model limitations to a product manager who wants guaranteed predictions.',
    ],
    ('Data Scientist', 'mid_level_expert', 'hard'): [
        'Design a monitoring plan for model drift in production and define when retraining should trigger.',
        'Compare batch versus online inference trade-offs for a fraud detection system with strict latency limits.',
        'How would you explain a complex model decision to a compliance reviewer without a statistics background?',
    ],
    ('DevOps Engineer', 'junior_professional', 'medium'): [
        'As a DevOps Engineer, describe a CI/CD pipeline you would set up for a Django plus React monorepo.',
        'How do you roll back a bad deployment safely when database migrations are involved?',
        'Explain blue/green versus canary deployments and when you prefer each in production.',
    ],
    ('DevOps Engineer', 'senior_professional', 'hard'): [
        'Design observability for a microservice that suddenly spikes 5xx errors after a configuration change.',
        'How would you secure secrets in CI/CD without exposing them to pull-request builds from forks?',
        'Outline a disaster recovery plan for a stateful service with RPO under 15 minutes.',
    ],
    ('Full Stack Developer', 'mid_level_expert', 'hard'): [
        'As a Full Stack Developer, how would you design authentication and authorization across a React frontend and Django API?',
        'Describe how you would debug a bug that only appears in production due to environment-specific configuration.',
        'What is your approach to API versioning when mobile and web clients release on different schedules?',
    ],
    ('Software Developer', 'fresher', 'easy'): [
        'As a Software Developer, explain the difference between unit tests and integration tests with examples.',
        'How do you approach reading unfamiliar code in a team codebase for the first time?',
        'Describe a bug you fixed and how you verified the fix did not break other behavior.',
    ],
    ('Software Developer', 'mid_level_expert', 'hard'): [
        'How would you break down a vague stakeholder request into deliverable milestones your team can estimate?',
        'Explain your code review checklist for security, performance, and maintainability.',
        'Describe how you would refactor a critical module with poor test coverage without stopping releases.',
    ],
    ('Backend Developer', 'mid_level_expert', 'hard'): [
        'As a Backend Developer, design rate limiting and idempotency for a payment webhook endpoint.',
        'How would you choose between REST, GraphQL, and gRPC for a new internal service?',
        'Describe your strategy for schema migrations on a high-traffic PostgreSQL database with zero downtime.',
    ],
    ('Frontend Developer', 'junior_professional', 'medium'): [
        'As a Frontend Developer, how would you improve Core Web Vitals on a React SPA used on slow mobile networks?',
        'Explain how you structure CSS or styling to keep large component libraries maintainable.',
        'How do you test UI components beyond snapshot tests to catch real user-facing regressions?',
    ],
    ('Machine Learning Engineer', 'mid_level_expert', 'hard'): [
        'As an ML Engineer, how would you deploy a model that must meet strict latency SLOs while allowing weekly retraining?',
        'Compare feature stores versus ad-hoc feature pipelines for a team shipping multiple models.',
        'How would you debug training-serving skew when offline metrics look good but online performance drops?',
    ],
    ('QA Engineer', 'junior_professional', 'medium'): [
        'As a QA Engineer, how would you design a test plan for a release that touches both API and UI with limited time?',
        'Explain the difference between flaky tests and environment issues. How do you triage each?',
        'When would you recommend automation versus manual exploratory testing for a new feature?',
    ],
    ('SQL Developer', 'fresher', 'easy'): [
        'As a SQL Developer, explain the difference between a primary key and a foreign key with a simple example.',
        'What is a SQL JOIN, and when would you use INNER JOIN versus LEFT JOIN?',
        'Write a basic SQL query to list the top 10 customers by total order value.',
    ],
    ('SQL Developer', 'junior_professional', 'medium'): [
        'As a SQL Developer, write how you would optimize a slow report query joining five tables with filters on date ranges.',
        'Explain when you would use window functions instead of correlated subqueries.',
        'How do you validate that a schema migration did not change business-critical report outputs?',
    ],
    ('SQL Developer', 'mid_level_expert', 'hard'): [
        'As a SQL Developer, design an indexing strategy for a 500M-row fact table with heavy read reporting and nightly ETL writes.',
        'How would you troubleshoot blocking and deadlocks during month-end batch jobs on SQL Server or PostgreSQL?',
        'Explain how you would plan a zero-downtime migration from a single database to read replicas with minimal application changes.',
    ],
    ('SQL Developer', 'senior_professional', 'hard'): [
        'As a SQL Developer leading data platform work, how would you design partitioning and archival for multi-year transactional history?',
        'Compare row-store versus column-store approaches for an analytics workload and justify your recommendation.',
        'How would you detect and fix query plan regressions after a major database version upgrade?',
    ],
    ('Cloud Engineer', 'mid_level_expert', 'hard'): [
        'As a Cloud Engineer, design a multi-region deployment for a stateful API with RPO under 15 minutes.',
        'How would you troubleshoot sudden S3/Lambda latency spikes after a configuration change?',
        'Compare managed Kubernetes versus serverless for a variable-traffic internal tool.',
    ],
    ('AI Engineer', 'mid_level_expert', 'hard'): [
        'As an AI Engineer, how would you add guardrails to an LLM feature that summarizes user documents?',
        'Explain how you would evaluate hallucination rate after a prompt or retrieval change.',
        'Design an embedding pipeline that stays fresh when source documents update hourly.',
    ],
    ('Mobile App Developer', 'junior_professional', 'medium'): [
        'As a Mobile App Developer, how do you handle offline sync conflicts between local storage and API data?',
        'Describe your approach to reducing app startup time when many SDKs are initialized at launch.',
        'How would you debug a crash that only appears on specific Android OS versions?',
    ],
    ('Business Analyst', 'junior_professional', 'medium'): [
        'As a Business Analyst, how would you translate vague stakeholder requests into testable requirements?',
        'Describe how you validate that a reporting metric matches what operations teams actually need.',
        'When developers push back on scope, how do you prioritize without losing business value?',
    ],
    ('Database Administrator', 'senior_professional', 'hard'): [
        'As a DBA, how would you plan a major PostgreSQL upgrade on a 2TB production database with minimal downtime?',
        'Explain your strategy for index maintenance on a table with heavy insert/update churn.',
        'How do you detect and resolve blocking sessions during month-end batch jobs?',
    ],
    ('Cybersecurity Analyst', 'mid_level_expert', 'hard'): [
        'As a Cybersecurity Analyst, walk through how you would investigate suspicious lateral movement alerts.',
        'How would you prioritize patching when multiple critical CVEs land the same week?',
        'Describe how you would explain a false positive to an operations team without reducing alert quality.',
    ],
    ('Blockchain Developer', 'mid_level_expert', 'hard'): [
        'As a Blockchain Developer, how would you audit a smart contract upgrade path for reentrancy and access control risks?',
        'Compare on-chain versus off-chain storage trade-offs for a high-volume dApp feature.',
        'How would you debug failed transactions that succeed in testnet but fail on mainnet?',
    ],
    ('UI/UX  Developer', 'junior_professional', 'medium'): [
        'As a UI/UX Developer, how do you balance design system consistency with product-specific usability needs?',
        'Describe how you would run a quick usability test before a major React UI release.',
        'How do you hand off accessible components to engineers with clear interaction specs?',
    ],
}

ROLE_PERSONALITY_QUESTIONS: dict[tuple[str, str, str], list[str]] = {
    ('Python Developer', 'junior_professional', 'medium'): [
        'Tell me about a time as a Python Developer when you had to explain a technical trade-off to a non-technical stakeholder.',
        'Describe a situation where code review feedback changed how you structure Python modules on your team.',
    ],
    ('Python Developer', 'mid_level_expert', 'hard'): [
        'Describe a production incident you handled as a Python Developer. How did you communicate status while debugging?',
        'Tell me about a time as a Python Developer when you pushed back on a shortcut that would have hurt long-term maintainability of the codebase.',
    ],
    ('React Developer', 'junior_professional', 'medium'): [
        'Tell me about a time you disagreed with a UX design that was hard to implement cleanly in React. How did you handle it?',
        'Describe how you collaborated with backend developers when an API contract blocked your frontend work.',
    ],
    ('React Developer', 'senior_professional', 'hard'): [
        'Describe how you aligned designers, backend engineers, and QA when a React release date could not move.',
        'Tell me about mentoring a junior React Developer who struggled with state management on a real feature.',
    ],
    ('Java Developer', 'mid_level_expert', 'hard'): [
        'Tell me about a time you inherited a legacy Java module with poor tests. How did you improve it while delivering features?',
        'Describe a conflict with a teammate about architecture in a Spring Boot project and how you resolved it.',
    ],
    ('Data Scientist', 'mid_level_expert', 'hard'): [
        'Tell me about a time stakeholders wanted a model deployed before you were confident in its reliability. What did you do?',
        'Describe how you handled pushback when your analysis contradicted a popular business assumption.',
    ],
    ('DevOps Engineer', 'senior_professional', 'hard'): [
        'Describe an outage you helped resolve as a DevOps Engineer. How did you coordinate communication across teams?',
        'Tell me about a time you had to say no to a risky production change during a tight deadline.',
    ],
    ('Full Stack Developer', 'mid_level_expert', 'hard'): [
        'Tell me about a time you owned a feature end to end across frontend and backend under an aggressive deadline.',
        'Describe how you handled conflicting priorities when both UI polish and API reliability needed attention.',
    ],
    ('Software Developer', 'fresher', 'easy'): [
        'Tell me about a time you asked for help instead of staying stuck. What did you learn from that experience?',
        'Describe feedback from a mentor or teacher that changed how you approach learning new technologies.',
    ],
    ('Software Developer', 'senior_professional', 'hard'): [
        'Describe how you influenced technical direction on a team without formal management authority.',
        'Tell me about a time you took accountability for a mistake that affected customers or teammates.',
    ],
    ('QA Engineer', 'junior_professional', 'medium'): [
        'Tell me about a bug you caught late in a release cycle. How did you communicate severity and next steps?',
        'Describe a time developers pushed back on your bug report. How did you keep the discussion productive?',
    ],
    ('Backend Developer', 'mid_level_expert', 'hard'): [
        'Tell me about a time you had to deliver bad news about API delays that blocked frontend or mobile teams.',
        'Describe how you handled on-call stress during a prolonged backend outage.',
    ],
    ('Cloud Engineer', 'senior_professional', 'hard'): [
        'Tell me about an outage you helped resolve that crossed cloud regions or providers. How did you coordinate teams?',
        'Describe a time you pushed back on a risky infrastructure change before a major launch.',
    ],
    ('AI Engineer', 'mid_level_expert', 'hard'): [
        'Tell me about a time you had to delay shipping an AI feature because safety or quality was not ready.',
        'Describe how you explained model limitations to a product team expecting deterministic answers.',
    ],
    ('Mobile App Developer', 'junior_professional', 'medium'): [
        'Tell me about a time app store review feedback forced you to change a feature quickly.',
        'Describe how you collaborated with backend engineers when an API change broke mobile releases.',
    ],
    ('Business Analyst', 'junior_professional', 'medium'): [
        'Tell me about a requirement misunderstanding that caused rework. How did you prevent it next time?',
        'Describe how you handled conflicting priorities from two stakeholders on the same deadline.',
    ],
}

PERSONALITY_QUESTIONS: dict[tuple[str, str, str], list[str]] = {
    ('Communication', 'fresher', 'easy'): [
        'Tell me about a time you had to explain a technical idea to someone without a technical background.',
        'Describe a situation where miscommunication caused a delay. What did you learn?',
    ],
    ('Communication', 'senior_professional', 'hard'): [
        'Describe how you communicated a controversial technical decision to leadership and engineering.',
        'Tell me about a time you had to deliver bad news about a missed deadline while keeping trust.',
    ],
    ('Collaboration', 'junior_professional', 'medium'): [
        'Tell me about a conflict with a teammate during a project. How did you resolve it?',
        'Describe a time you helped a struggling teammate without taking over their work.',
    ],
    ('Collaboration', 'senior_professional', 'hard'): [
        'How have you aligned multiple teams with conflicting priorities on a shared deadline?',
        'Describe a time you mediated between product and engineering when requirements kept changing.',
    ],
    ('Stress handling', 'mid_level_expert', 'hard'): [
        'Describe your most intense production incident. How did you stay effective under pressure?',
        'Tell me about a time you had competing urgent tasks. How did you prioritize?',
    ],
    ('Leadership', 'senior_professional', 'hard'): [
        'Tell me about a time you mentored someone who was underperforming. What changed?',
        'Describe a decision you made without complete information and how you handled the outcome.',
    ],
    ('Adaptability', 'junior_professional', 'medium'): [
        'Describe a time requirements changed late in a sprint. How did you adjust?',
        'Tell me about learning a new framework quickly to unblock your team.',
    ],
    ('Problem solving', 'mid_level_expert', 'hard'): [
        'Walk me through a complex bug that took days to find. How did you isolate the root cause?',
        'Describe a time your first solution failed. What was your next approach?',
    ],
    ('Time management', 'junior_professional', 'medium'): [
        'How do you estimate tasks when requirements are still fuzzy?',
        'Tell me about a time you missed a personal deadline and what you changed afterward.',
    ],
    ('Integrity', 'senior_professional', 'hard'): [
        'Describe a time you discovered a serious mistake after release. What did you do?',
        'Tell me about pushing back on a request you believed was unethical or unsafe.',
    ],
    ('Openness to learning', 'fresher', 'easy'): [
        'Describe the hardest technical topic you taught yourself recently and how you learned it.',
        'Tell me about feedback that changed how you write code or communicate.',
    ],
    ('Attention to detail', 'mid_level_expert', 'hard'): [
        'Tell me about a small oversight that caused a big problem. How do you prevent repeats?',
        'Describe your checklist before merging code that touches payments or user data.',
    ],
}


def _collect_bank_candidates(
    bank: dict[tuple[str, str, str], list[str]],
    category: str,
    experience_band: str,
    difficulty: str,
    exclude: set[str],
) -> list[str]:
    candidates = [q for q in bank.get((category, experience_band, difficulty), []) if q not in exclude]
    if candidates:
        return candidates
    for alt in ('hard', 'medium', 'easy'):
        if alt == difficulty:
            continue
        candidates = [q for q in bank.get((category, experience_band, alt), []) if q not in exclude]
        if candidates:
            return candidates
    for (cat, _band, _diff), questions in bank.items():
        if cat != category:
            continue
        candidates = [q for q in questions if q not in exclude]
        if candidates:
            return candidates
    return []


def _any_unused_in_bank(
    bank: dict[tuple[str, str, str], list[str]],
    exclude: set[str],
) -> list[str]:
    """Return any unused questions left in the bank (last resort before generated fallbacks)."""
    seen: list[str] = []
    for questions in bank.values():
        for question in questions:
            if question not in exclude and question not in seen:
                seen.append(question)
    return seen


def pick_role_interview_question(
    focus_area: str,
    job_role: str,
    experience_band: str,
    difficulty: str,
    rng,
    exclude: set[str] | None = None,
) -> str | None:
    """Delegate to the polished role catalog (strict role + experience scoping)."""
    from .role_question_catalog import pick_role_interview_question as _pick_from_catalog

    return _pick_from_catalog(
        focus_area=focus_area,
        job_role=job_role,
        experience_band=experience_band,
        difficulty=difficulty,
        rng=rng,
        exclude=exclude,
    )


def pick_curated_question(
    focus_area: str,
    category: str,
    experience_band: str,
    difficulty: str,
    rng,
    exclude: set[str] | None = None,
    job_role: str | None = None,
) -> str | None:
    """Return a curated question if available, preferring role-specific prompts."""
    exclude = exclude or set()
    role_bank = ROLE_TECHNICAL_QUESTIONS if focus_area == 'technical' else ROLE_PERSONALITY_QUESTIONS
    skill_bank = TECHNICAL_QUESTIONS if focus_area == 'technical' else PERSONALITY_QUESTIONS

    candidates: list[str] = []
    if job_role:
        candidates = _collect_bank_candidates(role_bank, job_role, experience_band, difficulty, exclude)
    if not candidates:
        candidates = _collect_bank_candidates(skill_bank, category, experience_band, difficulty, exclude)
    if not candidates and job_role:
        candidates = _any_unused_in_bank(role_bank, exclude)
    if not candidates:
        candidates = _any_unused_in_bank(skill_bank, exclude)
    if not candidates:
        return None
    picker = rng if hasattr(rng, 'choice') else py_random.Random(int(rng))
    return str(picker.choice(candidates))
