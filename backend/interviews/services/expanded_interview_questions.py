"""Large role-specific interview question expansion for CSV generation.

Each role gets foundational / intermediate / advanced pools mapped to
experience_band + difficulty. Questions mention the role but not years of
experience in the prompt text (seniority is stored in metadata only).
"""

from __future__ import annotations

from .question_quality import strip_experience_markers
from .role_interview_constants import DIFFICULTY_BY_BAND, ROLE_INTERVIEW_SKILLS, USER_APPROVED_JOB_ROLES

ExperienceKey = tuple[str, str]  # (experience_band, difficulty)


def _apply_experience_framing(role: str, band: str, question: str) -> str:
    """Return polished role-framed text without embedding years/seniority labels."""
    _ = role, band
    return strip_experience_markers(str(question or '').strip())


def _tier_map(
    foundational: list[str],
    intermediate: list[str],
    advanced: list[str],
) -> dict[ExperienceKey, list[str]]:
    """Map tiers onto bands with disjoint pools within each band/difficulty slot."""
    f = list(foundational)
    i = list(intermediate)
    a = list(advanced)

    def take(source: list[str], start: int, count: int) -> list[str]:
        if not source:
            return []
        if start >= len(source):
            return source[-count:] if count <= len(source) else list(source)
        return source[start : start + count]

    return {
        ('fresher', 'easy'): take(f, 0, 2) or f[:1],
        ('fresher', 'medium'): take(f, 2, 2) or f[-2:] or f[-1:],
        ('junior_professional', 'easy'): take(i, 0, 1) or take(f, 3, 1) or f[-1:],
        ('junior_professional', 'medium'): take(i, 1, 3) or i or take(f, 2, 2),
        ('mid_level_expert', 'medium'): take(i, 3, 1) + take(a, 0, 2) or i[-2:] or a[:2],
        ('mid_level_expert', 'hard'): take(a, 0, 3) or a,
        ('senior_professional', 'medium'): take(a, 1, 2) or a[:2],
        ('senior_professional', 'hard'): take(a, 2, 2) or a[-2:] or a,
        ('industry_veteran', 'medium'): take(a, 0, 2) or a[:2],
        ('industry_veteran', 'hard'): take(a, 2, 2) or a[-2:] or a,
    }


def _format_role(role: str, questions: list[str]) -> list[str]:
    formatted: list[str] = []
    role_lower = role.lower()
    for question in questions:
        text = str(question).strip()
        if not text:
            continue
        if role_lower in text.lower():
            formatted.append(text)
        elif text.startswith('Explain ') or text.startswith('Describe ') or text.startswith('What ') or text.startswith('How ') or text.startswith('Write ') or text.startswith('Compare ') or text.startswith('Tell '):
            formatted.append(f'As a {role}, {text[0].lower()}{text[1:]}')
        else:
            formatted.append(f'As a {role}, {text}')
    return formatted


# ── Technical question tiers per role ─────────────────────────────────────────

_ROLE_TECHNICAL_TIERS: dict[str, dict[str, list[str]]] = {
    'SQL Developer': {
        'foundational': [
            'Explain the difference between a primary key and a foreign key with a simple orders and customers example.',
            'What is a SQL JOIN, and when would you use INNER JOIN versus LEFT JOIN?',
            'Write a query to return the top 10 products by total sales in the last 30 days.',
            'Explain the difference between WHERE and HAVING with a grouped report example.',
        ],
        'intermediate': [
            'How would you optimize a slow report query joining five tables with date-range filters?',
            'When would you choose a window function instead of a correlated subquery?',
            'How do you validate that a schema migration did not change business-critical report outputs?',
            'Explain how covering indexes help read-heavy dashboards and what trade-offs they introduce on writes.',
        ],
        'advanced': [
            'Design an indexing and partitioning strategy for a 500M-row fact table with nightly ETL and daytime reporting.',
            'How would you troubleshoot blocking, deadlocks, and long-running locks during month-end batch jobs?',
            'Plan a zero-downtime migration from a single primary database to read replicas with minimal application changes.',
            'How would you detect and fix query plan regressions after a major database version upgrade?',
        ],
    },
    'Python Developer': {
        'foundational': [
            'Explain the difference between a list and a tuple. When would you choose each in production code?',
            'What is a virtual environment, and why do teams require it on shared Python projects?',
            'Describe how you would read a CSV in Python and handle missing or malformed values safely.',
            'Explain list comprehensions versus generator expressions and when each is appropriate.',
        ],
        'intermediate': [
            'How would you find and fix N+1 query problems in a slow Django list endpoint?',
            'Explain how you would structure error handling, logging, and retries in a Python REST API.',
            'Compare dataclasses versus plain dictionaries for structured API payloads in Python.',
            'How do you write unit tests for code that calls external HTTP services?',
        ],
        'advanced': [
            'Design a caching strategy for a Django view aggregating data from three services with different SLAs.',
            'Walk through debugging a memory leak in a long-running Celery worker processing large JSON payloads.',
            'How would you migrate synchronous Django views to async I/O-heavy endpoints without breaking releases?',
            'How would you profile Python services under 10k requests/minute and roll out optimizations safely?',
        ],
    },
    'Java Developer': {
        'foundational': [
            'Explain the four pillars of OOP with a simple Java class design example.',
            'What is the difference between an interface and an abstract class in Java?',
            'Describe how you would write a JUnit test for a service that depends on a database repository.',
            'Explain checked versus unchecked exceptions and when to use each in Java APIs.',
        ],
        'intermediate': [
            'How would you design a service layer that stays testable when databases and external APIs change often?',
            'How would you handle transaction boundaries when one user action updates multiple tables?',
            'Explain common causes of memory leaks in Java applications and how you would investigate them.',
            'Compare ArrayList versus LinkedList for a high-read catalog workload and justify your choice.',
        ],
        'advanced': [
            'Design a thread-safe in-memory cache for a read-heavy catalog service. What eviction policy would you use?',
            'How would you troubleshoot intermittent OutOfMemoryError in a Spring Boot service under peak traffic?',
            'Explain how you would extract a monolithic Java module into a separate service without a big-bang release.',
            'How would you design idempotent REST endpoints for payment callbacks in Spring Boot?',
        ],
    },
    'React Developer': {
        'foundational': [
            'Explain props versus state with a simple controlled form example.',
            'What causes unnecessary re-renders in React, and name two practical ways to reduce them.',
            'Describe how you would fetch data from an API and show loading and error states in a component.',
            'Explain the purpose of keys in lists and what bugs appear when keys are chosen poorly.',
        ],
        'intermediate': [
            'How would you decide between lifting state, Context, and a dedicated state library for shared form data?',
            'Describe how you would debug a memory leak caused by effects not cleaning up subscriptions.',
            'How do you keep accessibility in mind when building custom modals, dropdowns, and focus traps?',
            'Explain controlled versus uncontrolled components and when each is appropriate.',
        ],
        'advanced': [
            'How would you architect code-splitting and lazy loading for a dashboard with heavy chart libraries?',
            'Explain your strategy for preventing stale closures in async effects and event handlers at scale.',
            'What trade-offs would you weigh between server components and client rendering for an authenticated SaaS app?',
            'How would you measure and improve Core Web Vitals for a React SPA on slow mobile networks?',
        ],
    },
    'Frontend Developer': {
        'foundational': [
            'Explain semantic HTML and why it matters for accessibility and SEO.',
            'Describe how CSS specificity works and how you avoid unintended style overrides.',
            'How would you make a navigation menu usable on both desktop and mobile viewports?',
            'Explain the difference between defer and async when loading JavaScript files.',
        ],
        'intermediate': [
            'How would you improve Core Web Vitals on a React SPA used on slow mobile networks?',
            'Explain how you structure CSS or a design system to keep large component libraries maintainable.',
            'How do you test UI components beyond snapshot tests to catch real user-facing regressions?',
            'Describe how you handle cross-browser inconsistencies for modern CSS features.',
        ],
        'advanced': [
            'Design a reusable data-table component with virtualization, sorting, filtering, and accessibility.',
            'How would you migrate a legacy jQuery module into React incrementally without freezing delivery?',
            'Explain performance profiling for long lists and expensive re-renders in production.',
            'How would you implement secure token storage and refresh flows in a browser SPA?',
        ],
    },
    'Backend Developer': {
        'foundational': [
            'Explain the difference between authentication and authorization in a REST API.',
            'Describe how you would design CRUD endpoints for a resource with validation and error responses.',
            'What is an ORM, and what are the trade-offs versus raw SQL for simple queries?',
            'Explain HTTP status codes you use most often and when to return each.',
        ],
        'intermediate': [
            'Design rate limiting and idempotency for a payment webhook endpoint.',
            'How would you choose between REST, GraphQL, and gRPC for a new internal service?',
            'Describe your strategy for schema migrations on a high-traffic PostgreSQL database with zero downtime.',
            'How do you structure logging and correlation IDs across microservices for debugging?',
        ],
        'advanced': [
            'Design a multi-tenant API where each tenant has isolated data and configurable feature flags.',
            'How would you debug intermittent 502 errors between an API gateway and upstream services?',
            'Explain your approach to back-pressure and queueing when downstream systems are degraded.',
            'How would you implement safe rollout of breaking API changes with multiple client versions?',
        ],
    },
    'Full Stack Developer': {
        'foundational': [
            'Describe how a React frontend communicates with a Django or Node backend on a typical feature.',
            'Explain CORS in plain language and how you would fix a blocked browser request during development.',
            'How would you design a simple login flow across frontend and backend components?',
            'What is environment-based configuration, and how do you keep secrets out of the frontend bundle?',
        ],
        'intermediate': [
            'How would you design authentication and authorization across a React frontend and Django API?',
            'Describe how you would debug a bug that only appears in production due to environment configuration.',
            'What is your approach to API versioning when mobile and web clients release on different schedules?',
            'How do you coordinate database migrations with frontend feature flags during a staged rollout?',
        ],
        'advanced': [
            'Design end-to-end observability for a MERN feature from browser errors to database slow queries.',
            'How would you split a monolithic full-stack module into separate frontend and backend services safely?',
            'Explain how you would handle real-time updates between UI and API for a collaborative feature.',
            'How would you prioritize performance work across frontend bundle size and backend query latency?',
        ],
    },
    'Data Scientist': {
        'foundational': [
            'Explain the difference between supervised and unsupervised learning with one example each.',
            'What are precision, recall, and F1 score, and when would you optimize recall over precision?',
            'Describe how you would explore a new CSV dataset before building any model.',
            'Explain train/validation/test splits and why random splitting alone can fail on time-series data.',
        ],
        'intermediate': [
            'How would you validate a classification model when classes are heavily imbalanced?',
            'How do you detect and prevent data leakage during feature engineering for a churn model?',
            'Describe how you would communicate model limitations to a product manager expecting guaranteed accuracy.',
            'Compare logistic regression versus gradient boosting for a tabular fraud detection problem.',
        ],
        'advanced': [
            'Design a monitoring plan for model drift in production and define when retraining should trigger.',
            'Compare batch versus online inference trade-offs for fraud detection with strict latency limits.',
            'How would you explain a complex model decision to a compliance reviewer without a statistics background?',
            'How would you design an experiment to compare two ranking models in production safely?',
        ],
    },
    'Machine Learning Engineer': {
        'foundational': [
            'Explain the difference between training, validation, and inference in an ML system.',
            'What is overfitting, and what techniques do you use to reduce it on tabular data?',
            'Describe how you would package a scikit-learn model for deployment behind an HTTP endpoint.',
            'Explain batch inference versus online inference with one use case for each.',
        ],
        'intermediate': [
            'How would you deploy a model that must meet strict latency SLOs while allowing weekly retraining?',
            'Compare feature stores versus ad-hoc feature pipelines for a team shipping multiple models.',
            'How would you debug training-serving skew when offline metrics look good but online performance drops?',
            'Describe how you version datasets, features, and models together for reproducible releases.',
        ],
        'advanced': [
            'Design a canary deployment strategy for a new model serving 1M predictions per hour.',
            'How would you handle cold-start features for new users in a real-time recommendation pipeline?',
            'Explain how you would reduce inference cost while preserving quality for an LLM-based feature.',
            'How would you build alerting when data schema changes break a production feature pipeline?',
        ],
    },
    'AI Engineer': {
        'foundational': [
            'Explain what an embedding is and how it is used in semantic search.',
            'Describe the basic steps of retrieval-augmented generation (RAG) for document Q&A.',
            'What is prompt engineering, and give an example of a prompt improvement you would test.',
            'Explain temperature and top-p sampling in plain language for a non-technical stakeholder.',
        ],
        'intermediate': [
            'How would you add guardrails to an LLM feature that summarizes user-provided documents?',
            'Explain how you would evaluate hallucination rate after a prompt or retrieval change.',
            'Design an embedding pipeline that stays fresh when source documents update hourly.',
            'How do you redact sensitive data before sending text to an external model API?',
        ],
        'advanced': [
            'Design evaluation metrics and human review loops for a customer-facing chatbot upgrade.',
            'How would you reduce latency and cost for a RAG system serving 500 concurrent users?',
            'Explain how you would migrate from one vector database to another with minimal downtime.',
            'How would you detect and block prompt injection attempts in a production LLM endpoint?',
        ],
    },
    'DevOps Engineer': {
        'foundational': [
            'Explain the difference between CI and CD with a simple pipeline example.',
            'What is a Docker image versus a container, and why do teams use containers in deployment?',
            'Describe how you would check whether a Linux service is running and inspect its logs.',
            'Explain blue/green deployment in plain language and one benefit over direct in-place deploys.',
        ],
        'intermediate': [
            'Describe a CI/CD pipeline you would set up for a Django plus React monorepo.',
            'How do you roll back a bad deployment safely when database migrations are involved?',
            'Explain canary deployments and when you prefer them over blue/green.',
            'How would you store and inject secrets in CI/CD without exposing them to forked pull requests?',
        ],
        'advanced': [
            'Design observability for a microservice that suddenly spikes 5xx errors after a configuration change.',
            'Outline a disaster recovery plan for a stateful service with RPO under 15 minutes.',
            'How would you design autoscaling rules for a variable-traffic API without thrashing?',
            'Explain how you would harden a Kubernetes cluster for a regulated production environment.',
        ],
    },
    'Cloud Engineer': {
        'foundational': [
            'Explain IaaS, PaaS, and SaaS with one example service for each.',
            'Describe how you would host a static React site and a REST API in a cloud environment.',
            'What is object storage, and when would you choose it over block storage?',
            'Explain public versus private subnets in a VPC and why both exist.',
        ],
        'intermediate': [
            'Design a multi-AZ deployment for a stateless API with health checks and auto-healing.',
            'How would you troubleshoot sudden object storage latency spikes after a configuration change?',
            'Compare managed Kubernetes versus serverless containers for a variable-traffic internal tool.',
            'Explain how you would estimate monthly cloud cost for a new microservice before launch.',
        ],
        'advanced': [
            'Design a multi-region deployment for a stateful API with RPO under 15 minutes.',
            'How would you implement secure cross-account access for a shared logging platform?',
            'Explain your strategy for infrastructure as code reviews and drift detection in production.',
            'How would you migrate an on-prem PostgreSQL workload to a managed cloud database with minimal downtime?',
        ],
    },
    'Security Engineer': {
        'foundational': [
            'Explain the CIA triad (confidentiality, integrity, availability) with a real system example.',
            'What is the difference between authentication and authorization in an enterprise application?',
            'Describe how HTTPS protects data in transit and what happens when certificate validation fails.',
            'Explain least-privilege access and how you would apply it to a developer IAM account.',
        ],
        'intermediate': [
            'Walk through how you would investigate a spike in failed login attempts across multiple services.',
            'How would you prioritize patching when multiple critical CVEs affect the same production cluster?',
            'Describe how you would design secrets rotation for API keys used by microservices.',
            'Explain how you would harden a public-facing REST API against common OWASP Top 10 risks.',
        ],
        'advanced': [
            'Design a security monitoring workflow for detecting lateral movement in a hybrid cloud environment.',
            'How would you lead incident response when a production secret may have been exposed in a log stream?',
            'Explain how you would evaluate whether to block or rate-limit a third-party integration after suspicious traffic.',
            'How would you implement zero-trust network access for internal admin tools used by engineers?',
        ],
    },
    'Cybersecurity Analyst': {
        'foundational': [
            'Explain the difference between a vulnerability, a threat, and a risk with examples.',
            'Describe what you would check first when alerted to a possible phishing email reported by staff.',
            'What is a SIEM, and what kinds of events would you expect it to collect?',
            'Explain multi-factor authentication and why passwords alone are insufficient for admin accounts.',
        ],
        'intermediate': [
            'Walk through how you would investigate suspicious lateral movement alerts on a corporate network.',
            'How would you prioritize patching when multiple critical CVEs land the same week?',
            'Describe how you would explain a false positive to operations without reducing alert quality.',
            'How do you validate that a firewall rule change did not unintentionally expose internal services?',
        ],
        'advanced': [
            'Design a tabletop exercise for ransomware response involving backups, comms, and legal stakeholders.',
            'How would you correlate alerts from endpoint, network, and identity systems during a suspected breach?',
            'Explain how you would measure and improve mean time to detect for high-severity security events.',
            'How would you recommend containment steps when an admin account shows impossible travel login patterns?',
        ],
    },
    'QA Engineer': {
        'foundational': [
            'Explain the difference between functional and non-functional testing with examples.',
            'Describe how you would write test cases for a login form including edge cases.',
            'What is regression testing, and when do you run it in a sprint?',
            'Explain the difference between a bug report and a vague complaint, and what a good report includes.',
        ],
        'intermediate': [
            'How would you design a test plan for a release touching both API and UI with limited time?',
            'Explain the difference between flaky tests and environment issues. How do you triage each?',
            'When would you recommend automation versus manual exploratory testing for a new feature?',
            'Describe how you would test error handling when a downstream payment API is unavailable.',
        ],
        'advanced': [
            'Design a test strategy for microservices where contracts change frequently between teams.',
            'How would you build confidence in a release candidate with no manual test window left?',
            'Explain how you would introduce visual regression testing without slowing CI excessively.',
            'How would you test data integrity across ETL jobs that feed customer-facing reports?',
        ],
    },
    'Software Developer': {
        'foundational': [
            'Explain the difference between unit tests and integration tests with examples from your experience.',
            'How do you approach reading unfamiliar code in a team codebase for the first time?',
            'Describe a bug you fixed and how you verified the fix did not break other behavior.',
            'Explain version control branching strategies you have used on a small team project.',
        ],
        'intermediate': [
            'How would you break down a vague stakeholder request into deliverable milestones your team can estimate?',
            'Explain your code review checklist for security, performance, and maintainability.',
            'Describe how you would refactor a critical module with poor test coverage without stopping releases.',
            'How do you document technical decisions so future teammates understand trade-offs?',
        ],
        'advanced': [
            'Design a modular architecture for a feature that must support plugin-style extensions.',
            'How would you lead a postmortem after a customer-impacting bug reached production?',
            'Explain how you would reduce build and test time in a large monorepo without skipping coverage.',
            'How would you evaluate build-versus-buy for a common platform capability your team needs?',
        ],
    },
    'Business Analyst': {
        'foundational': [
            'Explain the difference between a requirement and a user story with an example.',
            'Describe how you would clarify an ambiguous stakeholder request before development starts.',
            'What is a acceptance criterion, and why does it matter for QA and development?',
            'Explain how you would document a simple approval workflow for a finance team.',
        ],
        'intermediate': [
            'How would you translate vague stakeholder requests into testable requirements?',
            'Describe how you validate that a reporting metric matches what operations teams actually need.',
            'When developers push back on scope, how do you prioritize without losing business value?',
            'How would you facilitate a workshop between business and engineering when estimates diverge widely?',
        ],
        'advanced': [
            'Design a requirements traceability approach for a regulated feature with audit expectations.',
            'How would you evaluate whether a proposed dashboard answers the executive question it claims to answer?',
            'Explain how you would manage changing requirements late in a release without losing trust.',
            'How would you define success metrics for a process automation initiative before build starts?',
        ],
    },
    'Database Administrator': {
        'foundational': [
            'Explain backup types (full, incremental, differential) and when you would use each for PostgreSQL.',
            'Describe how you would check disk usage growth on a database server before it becomes critical.',
            'What is connection pooling, and why does it matter for application performance?',
            'Explain read replicas and one scenario where they help and one where they do not.',
        ],
        'intermediate': [
            'How would you plan index maintenance on a table with heavy insert/update churn?',
            'Describe steps you would take when users report intermittent "too many connections" errors.',
            'How do you test and roll out parameter changes such as memory or checkpoint settings safely?',
            'Explain how you would investigate a sudden doubling of average query duration on a production DB.',
        ],
        'advanced': [
            'Plan a major PostgreSQL upgrade on a 2TB production database with minimal downtime.',
            'How do you detect and resolve blocking sessions during month-end batch jobs?',
            'Design a backup and restore drill that proves RPO/RTO targets for a critical financial database.',
            'How would you migrate databases between cloud providers with encrypted data and minimal cutover time?',
        ],
    },
    'Mobile App Developer': {
        'foundational': [
            'Explain the difference between native, hybrid, and cross-platform mobile development approaches.',
            'Describe how you would handle API errors gracefully in a mobile UI.',
            'What causes ANR or freeze issues on mobile, and how do you investigate them?',
            'Explain how you store tokens securely on a mobile device at a high level.',
        ],
        'intermediate': [
            'How do you handle offline sync conflicts between local storage and API data?',
            'Describe your approach to reducing app startup time when many SDKs initialize at launch.',
            'How would you debug a crash that only appears on specific Android OS versions?',
            'Explain how you test mobile releases across device sizes and OS versions efficiently.',
        ],
        'advanced': [
            'Design a feature flag and remote config strategy for mobile apps with long upgrade cycles.',
            'How would you diagnose battery drain regressions introduced by a background sync change?',
            'Explain how you would migrate users between two authentication providers without forced logout for all.',
            'How would you implement end-to-end encryption for sensitive user-generated content on device and server?',
        ],
    },
    'Blockchain Developer': {
        'foundational': [
            'Explain what a smart contract is and one risk if it is deployed without review.',
            'Describe the difference between a wallet address and a private key in plain language.',
            'What is a transaction hash, and how would you use a block explorer to inspect a failed transaction?',
            'Explain gas fees and why failed transactions can still consume gas on Ethereum-like networks.',
        ],
        'intermediate': [
            'How would you audit a smart contract upgrade path for reentrancy and access control risks?',
            'Compare on-chain versus off-chain storage trade-offs for a high-volume dApp feature.',
            'How would you debug failed transactions that succeed in testnet but fail on mainnet?',
            'Explain how you would test event emissions and indexing for a DeFi dashboard.',
        ],
        'advanced': [
            'Design a key management approach for admin functions in a multi-signature smart contract system.',
            'How would you mitigate front-running risks for a on-chain auction feature?',
            'Explain how you would monitor smart contracts for abnormal activity after deployment.',
            'How would you plan a migration from one chain to another for an existing NFT collection?',
        ],
    },
    'UI/UX  Developer': {
        'foundational': [
            'Explain the difference between UX research and UI implementation on a product team.',
            'Describe how you would improve form usability for a checkout flow with high drop-off.',
            'What is visual hierarchy, and how do you use it in a dashboard design?',
            'Explain accessibility basics for color contrast and keyboard navigation.',
        ],
        'intermediate': [
            'How do you balance design system consistency with product-specific usability needs?',
            'Describe how you would run a quick usability test before a major React UI release.',
            'How do you hand off accessible components to engineers with clear interaction specs?',
            'Explain how you would iterate on a design when analytics show users miss a primary action.',
        ],
        'advanced': [
            'Design a workflow for collecting user feedback and prioritizing UI debt across squads.',
            'How would you validate that a redesign improved task completion without increasing support tickets?',
            'Explain how you document motion and micro-interaction specs for engineering handoff.',
            'How would you align UX metrics (task success, time-on-task) with business KPIs for a B2B product?',
        ],
    },
}

for _role in USER_APPROVED_JOB_ROLES:
    _skills = ROLE_INTERVIEW_SKILLS.get(_role, ['Software Engineering'])
    _skill = _skills[0]
    _tiers = _ROLE_TECHNICAL_TIERS.setdefault(_role, {'foundational': [], 'intermediate': [], 'advanced': []})
    _tiers.setdefault('foundational', []).extend([
        f'What foundational {_skill} concepts should every new {_role} understand before joining a production team?',
        f'How would you validate your understanding of {_skill} after completing a tutorial or course?',
    ])
    _tiers.setdefault('intermediate', []).extend([
        f'Describe a realistic on-the-job situation where {_skill} choices affected reliability for a {_role}.',
        f'What documentation or tests would you add around {_skill} before handing work to another engineer?',
    ])
    _tiers.setdefault('advanced', []).extend([
        f'How would you plan a staged rollout for a high-risk {_skill} change owned by a {_role}?',
        f'What signals would tell you a {_skill} implementation needs refactoring in a mature {_role} codebase?',
        f'How would a {_role} evaluate build-versus-buy options for tooling that supports {_skill}?',
        f'What governance practices would you introduce as {_skill} ownership grows on a {_role} team?',
    ])


# ── Personality question tiers per role ───────────────────────────────────────

_ROLE_PERSONALITY_TIERS: dict[str, dict[str, list[str]]] = {
    role: {
        'foundational': [
            f'Tell me about a time you asked for help early as a {role} instead of staying stuck. What did you learn?',
            f'Describe feedback from a mentor or teammate that changed how you approach your work as a {role}.',
            f'Tell me about a time you had to explain a technical topic simply to a non-technical colleague.',
            f'Describe how you organized your work when you were new to a {role} team and learning the codebase.',
        ],
        'intermediate': [
            f'Tell me about a time as a {role} when you disagreed with a teammate about approach. How did you resolve it?',
            f'Describe a situation where requirements changed late and how you adjusted delivery as a {role}.',
            f'Tell me about a time you caught a mistake before it reached customers. What process helped you?',
            f'Describe a time you improved a team process as a {role} after a missed deadline or defect.',
        ],
        'advanced': [
            f'Describe a production incident you handled as a {role}. How did you communicate while troubleshooting?',
            f'Tell me about a time you pushed back on a risky shortcut as a {role}. What was the outcome?',
            f'Describe how you mentored or unblocked a junior colleague on a critical {role} deliverable.',
            f'Tell me about a cross-team conflict you resolved as a {role} without delaying the release.',
        ],
    }
    for role in USER_APPROVED_JOB_ROLES
}


def _flatten_tiers(
    role: str,
    tiers: dict[str, list[str]],
) -> dict[tuple[str, str, str], list[str]]:
    tier_map = _tier_map(
        tiers.get('foundational', []),
        tiers.get('intermediate', []),
        tiers.get('advanced', []),
    )
    output: dict[tuple[str, str, str], list[str]] = {}
    for (band, difficulty), questions in tier_map.items():
        allowed = DIFFICULTY_BY_BAND.get(band, ['medium'])
        if difficulty not in allowed:
            continue
        key = (role, band, difficulty)
        formatted = [
            _apply_experience_framing(role, band, q)
            for q in _format_role(role, questions)
        ]
        output[key] = formatted
    return output


def build_expanded_technical_questions() -> dict[tuple[str, str, str], list[str]]:
    merged: dict[tuple[str, str, str], list[str]] = {}
    for role in USER_APPROVED_JOB_ROLES:
        tiers = _ROLE_TECHNICAL_TIERS.get(role)
        if not tiers:
            continue
        for key, questions in _flatten_tiers(role, tiers).items():
            merged.setdefault(key, []).extend(questions)
    return merged


def build_expanded_personality_questions() -> dict[tuple[str, str, str], list[str]]:
    merged: dict[tuple[str, str, str], list[str]] = {}
    for role in USER_APPROVED_JOB_ROLES:
        tiers = _ROLE_PERSONALITY_TIERS.get(role, {})
        for key, questions in _flatten_tiers(role, tiers).items():
            merged.setdefault(key, []).extend(questions)
    return merged
