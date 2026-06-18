"""Question-specific reference keywords for interview answer scoring."""

from __future__ import annotations

import re

from .role_interview_constants import (
    ROLE_INTERVIEW_SKILLS,
    ROLE_PERSONALITY_TRAITS,
    ROLE_REQUIRED_TOPIC_MARKERS,
    USER_APPROVED_JOB_ROLES,
)

REFERENCE_BLEND_WEIGHT = 0.45
MAX_REFERENCE_KEYWORDS = 24

TOPIC_REFERENCE_KEYWORDS: dict[str, tuple[str, ...]] = {
    'React': (
        'component', 'state', 'props', 'hook', 'render', 'usestate', 'useeffect',
        're-render', 'context', 'virtual dom', 'jsx', 'memo', 'controlled',
        'uncontrolled', 'accessibility', 'lazy', 'bundle', 'key', 'effect',
        'cleanup', 'subscription', 'form', 'parent', 'child', 'frontend',
        'code-splitting', 'virtualization', 'core web vitals', 'spa', 'hydration',
        'server components', 'closure', 'memory leak', 'data-table', 'hooks',
    ),
    'DBMS': (
        'index', 'query', 'sql', 'transaction', 'join', 'schema', 'normalization',
        'locking', 'table', 'database', 'primary key', 'foreign key', 'acid',
        'deadlock', 'partition', 'replic', 'view', 'trigger', 'aggregate',
        'window function', 'covering index', 'execution plan', 'migration',
        'stored procedure', 'column', 'row', 'backup', 'restore', 'postgres',
        'mysql', 'sharding', 'read replica', 'inventory', 'contention', 'workloads',
        'optimizing', 'report', 'maintenance', 'integrity', 'referential',
    ),
    'Django': (
        'model', 'view', 'orm', 'migration', 'middleware', 'serializer', 'rest',
        'authentication', 'queryset', 'admin', 'signal', 'template', 'url',
        'form', 'cache', 'celery', 'endpoint', 'permission', 'select_related',
        'prefetch', 'n+1', 'settings', 'wsgi', 'python', 'backend', 'redis',
        'idempotency', 'webhook', 'payment', 'rate limiting', 'async', 'worker',
    ),
    'DSA': (
        'complexity', 'algorithm', 'time', 'space', 'edge case', 'trade-off',
        'hash', 'tree', 'array', 'graph', 'binary', 'search', 'sort', 'stack',
        'queue', 'heap', 'recursion', 'dynamic programming', 'pointer', 'linked',
        'bfs', 'dfs', 'big-o', 'optimize', 'iterate', 'lru', 'cache', 'dijkstra',
        'bellman-ford', 'consistent hashing', 'top-k', 'streaming', 'cycle',
        'duplicate', 'merge', 'sorted', 'performance', 'regression',
    ),
    'Machine Learning': (
        'model', 'training', 'validation', 'overfitting', 'feature', 'precision',
        'recall', 'dataset', 'bias', 'cross-validation', 'hyperparameter', 'metric',
        'classification', 'regression', 'pipeline', 'experiment', 'baseline',
        'drift', 'label', 'inference', 'scikit', 'pandas', 'numpy', 'statistics',
        'leakage', 'imbalance', 'skew', 'serving', 'mlops', 'retrain', 'gpu',
        'visualization', 'hypothesis', 'production',
    ),
    'Artificial Intelligence': (
        'embedding', 'retrieval', 'prompt', 'llm', 'inference', 'rag',
        'hallucination', 'guardrail', 'token', 'fine-tune', 'transformer',
        'vector', 'agent', 'context window', 'semantic', 'generative', 'model',
        'evaluation', 'safety', 'latency', 'injection', 'quality', 'mitigation',
        'pipeline', 'architecture', 'monitoring',
    ),
    'DevOps': (
        'docker', 'pipeline', 'ci', 'cd', 'kubernetes', 'deploy', 'monitoring',
        'rollback', 'container', 'terraform', 'ansible', 'jenkins', 'github actions',
        'incident', 'alert', 'scaling', 'infrastructure', 'artifact', 'release',
        'canary', 'blue-green', 'observability', 'log', 'image', 'hardening',
        'multi-az', 'failover', 'cost', 'production', 'linux', 'cloud',
    ),
    'Networking': (
        'tcp', 'udp', 'latency', 'firewall', 'routing', 'dns', 'tls', 'packet',
        'subnet', 'vpn', 'load balancer', 'proxy', 'http', 'https', 'port',
        'bandwidth', 'ip', 'switch', 'router', 'encryption', 'certificate',
        'handshake', 'protocol', 'network', 'security', 'segmentation', 'zero trust',
        'lateral movement', 'smart contract', 'api',
    ),
    'OOP': (
        'inheritance', 'polymorphism', 'encapsulation', 'abstraction', 'class',
        'interface', 'object', 'method', 'override', 'overload', 'composition',
        'solid', 'java', 'junit', 'spring', 'exception', 'collection', 'bean',
        'thread', 'abstract class', 'spring boot', 'jpa', 'repository', 'service',
        'layer', 'testing', 'memory',
    ),
    'Software Engineering': (
        'requirement', 'design', 'testing', 'maintainability', 'architecture',
        'scalability', 'code review', 'git', 'debug', 'refactor', 'agile',
        'sprint', 'unit test', 'integration', 'api', 'documentation', 'release',
        'quality', 'pattern', 'dependency', 'modular', 'mobile', 'lifecycle',
        'production', 'security', 'performance', 'intermittent', 'bugs', 'qa',
        'flaky', 'triage', 'mobile app', 'offline', 'sync',
    ),
    'MERN Stack': (
        'mongo', 'express', 'react', 'node', 'api', 'jwt', 'routing',
        'middleware', 'mongoose', 'document', 'collection', 'rest', 'auth',
        'frontend', 'backend', 'full stack', 'json', 'endpoint', 'state',
        'cors', 'cookie', 'versioning', 'client', 'session', 'flows',
    ),
    'Operating Systems': (
        'process', 'thread', 'memory', 'scheduling', 'deadlock', 'mutex',
        'semaphore', 'paging', 'virtual memory', 'context switch', 'cpu',
        'kernel', 'file system', 'concurrency', 'race condition', 'lock',
        'ipc', 'interrupt', 'linux', 'systems', 'database administrator',
    ),
    'Behavioral': (
        'situation', 'task', 'action', 'result', 'learned', 'team', 'communicate',
        'because', 'outcome', 'stakeholder', 'example', 'challenge', 'resolved',
        'feedback', 'improved', 'collaborated', 'deadline', 'prioritized',
        'ownership', 'reflection', 'evaluation', 'practical', 'communicated',
        'teammate', 'delay', 'go-live', 'codebase', 'escalation', 'release',
        'dependency', 'incident', 'pressure', 'scenario', 'collaboration',
    ),
}

PERSONALITY_TRAIT_REFERENCE_KEYWORDS: dict[str, tuple[str, ...]] = {
    'Communication': (
        'explain', 'clarify', 'listen', 'audience', 'feedback', 'message',
        'stakeholder', 'present', 'translate', 'understand', 'concise',
        'communicated', 'clearly', 'non-technical', 'technical', 'writing',
    ),
    'Collaboration': (
        'team', 'align', 'support', 'shared', 'conflict', 'respect', 'coordinate',
        'pair', 'handoff', 'consensus', 'cross-functional', 'mentor', 'teammate',
        'collaboration', 'resolved', 'workshops',
    ),
    'Stress handling': (
        'pressure', 'deadline', 'prioritize', 'calm', 'focus', 'escalate',
        'urgent', 'recover', 'stabilize', 'incident', 'manage', 'stress',
        'delay', 'go-live', 'release', 'dependency', 'tight',
    ),
    'Leadership': (
        'lead', 'mentor', 'delegate', 'initiative', 'ownership', 'decision',
        'guide', 'motivate', 'accountable', 'vision', 'coach', 'reflection',
    ),
    'Adaptability': (
        'change', 'learn', 'adjust', 'flexible', 'pivot', 'new', 'uncertainty',
        'transition', 'evolve', 'resilient', 'requirements', 'scope',
    ),
    'Problem solving': (
        'analyze', 'root cause', 'solution', 'debug', 'investigate', 'hypothesis',
        'diagnose', 'fix', 'systematic', 'evidence', 'trade-off', 'scenario',
    ),
    'Time management': (
        'prioritize', 'schedule', 'deadline', 'plan', 'organize', 'backlog',
        'estimate', 'deliver', 'milestone', 'scope', 'efficient', 'late',
    ),
    'Integrity': (
        'honest', 'ethical', 'transparent', 'accountable', 'trust', 'compliance',
        'policy', 'report', 'responsible', 'confidential', 'secrets',
    ),
    'Openness to learning': (
        'learn', 'course', 'practice', 'mentor', 'feedback', 'improve', 'curious',
        'research', 'upskill', 'experiment', 'documentation', 'learning',
    ),
    'Attention to detail': (
        'detail', 'review', 'checklist', 'validate', 'accuracy', 'edge case',
        'verify', 'quality', 'mistake', 'thorough', 'precise', 'verification',
    ),
}

ROLE_REFERENCE_KEYWORDS: dict[str, tuple[str, ...]] = {
    'Data Scientist': (
        'data', 'model', 'feature', 'training', 'validation', 'sql', 'query',
        'statistics', 'experiment', 'visualization', 'hypothesis', 'pandas',
        'overfitting', 'precision', 'recall', 'pipeline', 'insight', 'metric',
        'leakage', 'imbalance', 'skew', 'notebook', 'eda', 'a/b test',
    ),
    'Java Developer': (
        'java', 'spring', 'junit', 'interface', 'abstract', 'exception', 'thread',
        'collection', 'arraylist', 'linkedlist', 'memory', 'bean', 'rest',
        'transaction', 'oop', 'class', 'service', 'repository', 'spring boot',
        'jpa', 'layer', 'testing', 'n+1', 'concurrency',
    ),
    'Python Developer': (
        'python', 'django', 'flask', 'pip', 'virtual environment', 'list', 'tuple',
        'celery', 'async', 'pytest', 'orm', 'api', 'decorator', 'csv', 'logging',
        'error handling', 'package', 'venv', 'idempotency', 'retries', 'typing',
    ),
    'React Developer': (
        'react', 'component', 'state', 'props', 'hook', 'jsx', 'render', 'useeffect',
        'usestate', 'context', 're-render', 'accessibility', 'form', 'effect',
        'frontend', 'lazy loading', 'virtualization', 'core web vitals', 'spa',
    ),
    'DevOps Engineer': (
        'docker', 'kubernetes', 'ci', 'cd', 'pipeline', 'terraform', 'monitoring',
        'rollback', 'deploy', 'container', 'linux', 'incident', 'alert', 'scaling',
        'infrastructure', 'release', 'observability', 'devops', 'image', 'hardening',
        'multi-az', 'failover', 'canary',
    ),
    'SQL Developer': (
        'sql', 'query', 'index', 'join', 'schema', 'table', 'normalization',
        'transaction', 'window function', 'stored procedure', 'deadlock', 'partition',
        'acid', 'view', 'trigger', 'aggregate', 'report', 'optimize', 'dbms',
        'workloads', 'optimizing', 'read replica', 'sharding', 'execution plan',
    ),
    'Business Analyst': (
        'requirement', 'stakeholder', 'metric', 'dashboard', 'report', 'sql',
        'process', 'workflow', 'gap', 'analysis', 'kpi', 'user story', 'scope',
        'acceptance', 'documentation', 'visualization', 'business', 'workshops',
        'criteria', 'writing', 'acceptance criteria',
    ),
    'Software Developer': (
        'design', 'testing', 'code review', 'git', 'algorithm', 'debug', 'api',
        'refactor', 'agile', 'unit test', 'architecture', 'maintainability',
        'complexity', 'pattern', 'release', 'production', 'security', 'intermittent',
        'bugs', 'performance',
    ),
    'Full Stack Developer': (
        'mongo', 'express', 'react', 'node', 'api', 'jwt', 'full stack',
        'frontend', 'backend', 'database', 'routing', 'middleware', 'auth',
        'rest', 'state', 'component', 'cors', 'cookie', 'versioning', 'mern',
    ),
    'Cloud Engineer': (
        'aws', 'azure', 'gcp', 'cloud', 'vpc', 'iam', 'ec2', 's3', 'lambda',
        'scaling', 'ha', 'disaster recovery', 'load balancer', 'kubernetes',
        'network', 'security group', 'terraform', 'monitoring', 'multi-az',
        'cost', 'failover', 'spikes',
    ),
    'Machine Learning Engineer': (
        'model', 'training', 'deployment', 'feature', 'pipeline', 'mlops',
        'inference', 'serving', 'monitoring', 'drift', 'retrain', 'gpu', 'batch',
        'validation', 'overfitting', 'embedding', 'production', 'machine learning',
        'skew', 'leakage', 'serving latency',
    ),
    'Security Engineer': (
        'security', 'vulnerability', 'owasp', 'firewall', 'encryption', 'threat',
        'access control', 'siem', 'incident', 'hardening', 'tls', 'authentication',
        'authorization', 'pentest', 'patch', 'risk', 'secrets', 'rotation',
        'public', 'zero trust',
    ),
    'Frontend Developer': (
        'html', 'css', 'javascript', 'semantic', 'accessibility', 'seo', 'responsive',
        'component', 'browser', 'dom', 'core web vitals', 'layout', 'performance',
        'react', 'state', 'props', 'render', 'frontend', 'mobile', 'usability',
    ),
    'Backend Developer': (
        'api', 'rest', 'database', 'caching', 'redis', 'authentication',
        'authorization', 'microservice', 'queue', 'scaling', 'orm', 'endpoint',
        'django', 'middleware', 'transaction', 'migration', 'backend', 'webhook',
        'idempotency', 'rate limiting', 'payment',
    ),
    'AI Engineer': (
        'llm', 'prompt', 'rag', 'embedding', 'retrieval', 'inference', 'fine-tune',
        'guardrail', 'hallucination', 'token', 'agent', 'vector', 'transformer',
        'evaluation', 'latency', 'model', 'pipeline', 'injection', 'quality',
        'mitigation', 'monitoring',
    ),
    'QA Engineer': (
        'test', 'testing', 'regression', 'automation', 'selenium', 'bug', 'defect',
        'testcase', 'coverage', 'manual', 'exploratory', 'quality', 'verify',
        'acceptance', 'ci', 'reproduce', 'flaky', 'triage', 'risk-based',
    ),
    'Database Administrator': (
        'backup', 'restore', 'replication', 'partition', 'postgres', 'mysql',
        'performance', 'tuning', 'maintenance', 'failover', 'recovery', 'storage',
        'index', 'query', 'deadlock', 'monitoring', 'dbms', 'migration',
        'administrator', 'verification', 'busy', 'systems', 'operating',
    ),
    'UI/UX  Developer': (
        'ux', 'ui', 'wireframe', 'prototype', 'figma', 'usability', 'accessibility',
        'design system', 'user research', 'persona', 'journey', 'contrast', 'layout',
        'component', 'responsive', 'feedback', 'iteration', 'consistency',
        'checkout', 'flow', 'review',
    ),
    'Mobile App Developer': (
        'mobile', 'ios', 'android', 'react native', 'flutter', 'offline', 'push',
        'notification', 'api', 'lifecycle', 'performance', 'store', 'screen',
        'navigation', 'battery', 'crash', 'app', 'sync', 'startup', 'conflicts',
    ),
    'Blockchain Developer': (
        'blockchain', 'smart contract', 'solidity', 'ethereum', 'wallet', 'consensus',
        'hash', 'decentral', 'gas', 'ledger', 'web3', 'cryptography', 'node',
        'transaction', 'immutable', 'reentrancy', 'optimization',
    ),
    'Cybersecurity Analyst': (
        'threat', 'malware', 'phishing', 'siem', 'log', 'incident', 'forensic',
        'vulnerability', 'patch', 'compliance', 'risk', 'monitor', 'detect',
        'firewall', 'access', 'investigate', 'cybersecurity', 'lateral movement',
        'triage', 'analyst',
    ),
}

# Role-specific supplements mined from interview CSV/catalog datasets.
ROLE_DATASET_KEYWORD_SUPPLEMENTS: dict[str, tuple[str, ...]] = {
    'Data Scientist': ('machine learning', 'dbms', 'experiment', 'communicated', 'pressure'),
    'Java Developer': ('dbms', 'oop', 'communicated', 'pressure', 'incident'),
    'Python Developer': ('django', 'dbms', 'communicated', 'resolved', 'behavioral'),
    'React Developer': ('software engineering', 'communicated', 'management', 'complex'),
    'DevOps Engineer': ('networking', 'operating systems', 'failures', 'security'),
    'SQL Developer': ('read', 'heavy', 'design', 'communicated', 'report'),
    'Business Analyst': ('dbms', 'communicated', 'clearly', 'pressure', 'scenario'),
    'Software Developer': ('dsa', 'oop', 'communicated', 'clearly', 'pressure'),
    'Full Stack Developer': ('mern stack', 'pressure', 'flows', 'communicated', 'across'),
    'Cloud Engineer': ('devops', 'networking', 'design', 'pressure', 'learning'),
    'Machine Learning Engineer': ('artificial intelligence', 'collaboration', 'communicated'),
    'Security Engineer': ('networking', 'api', 'without', 'systems', 'learning'),
    'Frontend Developer': ('react', 'bugs', 'review', 'learning', 'handling'),
    'Backend Developer': ('dbms', 'production', 'incident', 'learning', 'handling'),
    'AI Engineer': ('machine learning', 'software engineering', 'update', 'handling'),
    'QA Engineer': ('software engineering', 'dsa', 'api', 'engineering', 'handling'),
    'Database Administrator': ('networking', 'operating systems', 'communication', 'dbms'),
    'UI/UX  Developer': ('react', 'software engineering', 'scenario', 'handling'),
    'Mobile App Developer': ('software engineering', 'networking', 'stack', 'handling'),
    'Blockchain Developer': ('networking', 'dsa', 'communicated', 'scenario', 'handling'),
    'Cybersecurity Analyst': ('networking', 'operating systems', 'engineering', 'review'),
}


def _dedupe_keywords(items: tuple[str, ...] | list[str], limit: int | None = None) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = str(item).strip().lower()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        merged.append(cleaned)
        if limit is not None and len(merged) >= limit:
            break
    return tuple(merged)


def _enrich_role_reference_keywords() -> None:
    """Merge skill topics, required markers, and dataset supplements into every role."""
    for role in USER_APPROVED_JOB_ROLES:
        groups: list[str] = list(ROLE_REFERENCE_KEYWORDS.get(role, ()))
        for skill in ROLE_INTERVIEW_SKILLS.get(role, []):
            groups.extend(TOPIC_REFERENCE_KEYWORDS.get(skill, ()))
        for marker in ROLE_REQUIRED_TOPIC_MARKERS.get(role, ()):
            groups.append(marker)
        groups.extend(ROLE_DATASET_KEYWORD_SUPPLEMENTS.get(role, ()))
        for trait in ROLE_PERSONALITY_TRAITS.get(role, []):
            groups.extend(PERSONALITY_TRAIT_REFERENCE_KEYWORDS.get(trait, ()))
        groups.extend(TOPIC_REFERENCE_KEYWORDS['Behavioral'])
        ROLE_REFERENCE_KEYWORDS[role] = _dedupe_keywords(groups)


_enrich_role_reference_keywords()

# Ensure every approved role has explicit reference keywords.
for _role in USER_APPROVED_JOB_ROLES:
    ROLE_REFERENCE_KEYWORDS.setdefault(_role, TOPIC_REFERENCE_KEYWORDS['Software Engineering'])

QUESTION_HINT_STOPWORDS = {
    'would', 'could', 'should', 'explain', 'describe', 'tell', 'walk', 'share',
    'about', 'your', 'when', 'what', 'how', 'with', 'during', 'through', 'role',
    'developer', 'engineer', 'scientist', 'analyst', 'starting', 'career',
    'experience', 'professional', 'veteran', 'senior', 'junior', 'handle',
    'problem', 'constraints', 'trade', 'offs', 'validation', 'dashboard',
}


def parse_reference_keywords(raw: str | None) -> list[str]:
    if not raw:
        return []
    parts = re.split(r'[|,;]', str(raw))
    seen: set[str] = set()
    output: list[str] = []
    for part in parts:
        keyword = part.strip().lower()
        if keyword and keyword not in seen:
            seen.add(keyword)
            output.append(keyword)
    return output


def format_reference_keywords(keywords: list[str]) -> str:
    return '|'.join(keywords)


def _question_hint_tokens(question_text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9+\-]{2,}", str(question_text or '').lower())
    hints: list[str] = []
    for token in tokens:
        if token in QUESTION_HINT_STOPWORDS:
            continue
        if token not in hints:
            hints.append(token)
    return hints[:8]


def _merge_reference_keywords(*groups: tuple[str, ...] | list[str], limit: int = MAX_REFERENCE_KEYWORDS) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            cleaned = str(item).strip().lower()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            merged.append(cleaned)
            if len(merged) >= limit:
                return merged
    return merged


def _topic_keyword_groups(topic: str, focus_area: str, job_role: str) -> list[tuple[str, ...] | list[str]]:
    """Collect topic, role, and secondary-skill keyword groups in priority order."""
    if focus_area == 'personality':
        groups: list[tuple[str, ...] | list[str]] = []
        for trait in ROLE_PERSONALITY_TRAITS.get(job_role, []):
            trait_keywords = PERSONALITY_TRAIT_REFERENCE_KEYWORDS.get(trait)
            if trait_keywords:
                groups.append(trait_keywords)
        groups.append(TOPIC_REFERENCE_KEYWORDS['Behavioral'])
        role_keywords = ROLE_REFERENCE_KEYWORDS.get(job_role, ())
        if role_keywords:
            groups.append(role_keywords)
        return groups

    topic_key = topic or 'Software Engineering'
    primary = TOPIC_REFERENCE_KEYWORDS.get(topic_key, TOPIC_REFERENCE_KEYWORDS['Software Engineering'])
    groups = [primary]

    role_keywords = ROLE_REFERENCE_KEYWORDS.get(job_role, ())
    if role_keywords:
        groups.append(role_keywords)

    supplements = ROLE_DATASET_KEYWORD_SUPPLEMENTS.get(job_role, ())
    if supplements:
        groups.append(supplements)

    for skill in ROLE_INTERVIEW_SKILLS.get(job_role, []):
        if skill == topic_key:
            continue
        skill_keywords = TOPIC_REFERENCE_KEYWORDS.get(skill)
        if skill_keywords:
            groups.append(skill_keywords[:8])

    return groups


def build_reference_metadata(
    question_text: str,
    topic: str,
    focus_area: str,
    job_role: str = '',
) -> tuple[str, str]:
    """Build pipe-separated keywords and a short model-answer hint for CSV/storage."""
    keyword_groups = _topic_keyword_groups(topic, focus_area, job_role)
    hints = _question_hint_tokens(question_text)
    merged = _merge_reference_keywords(hints, *keyword_groups)

    if focus_area == 'personality':
        points = (
            f'Use STAR format with a real example relevant to {job_role or "your role"}: '
            'situation, task, action, result, and what you learned.'
        )
    else:
        topic_label = topic or 'Software Engineering'
        points = (
            f'Explain the core {topic_label} concepts for a {job_role or "candidate"}, '
            'give a concrete example, and mention trade-offs or edge cases where relevant.'
        )
    return format_reference_keywords(merged), points


def evaluate_reference_match(transcript: str, reference_keywords: str | None) -> dict | None:
    """Score how many expected keywords appear in the candidate transcript."""
    keywords = parse_reference_keywords(reference_keywords)
    if not keywords:
        return None

    lowered = str(transcript or '').lower()
    hit_keywords = [kw for kw in keywords if kw in lowered]
    missed_keywords = [kw for kw in keywords if kw not in lowered]
    total = len(keywords)
    ratio = len(hit_keywords) / total if total else 0.0
    reference_score = round(ratio * 100.0, 2)

    return {
        'reference_score': reference_score,
        'reference_keyword_hits': len(hit_keywords),
        'reference_keyword_total': total,
        'hit_keywords': hit_keywords,
        'missed_keywords': missed_keywords,
        'reference_match_pct': reference_score,
    }


def blend_with_reference_score(quality_score: float, reference_match: dict | None) -> float:
    """Blend ML/rule quality score with question-specific keyword relevance."""
    if not reference_match:
        return float(quality_score)
    ref_score = float(reference_match['reference_score'])
    blended = (float(quality_score) * (1.0 - REFERENCE_BLEND_WEIGHT)) + (
        ref_score * REFERENCE_BLEND_WEIGHT
    )
    if ref_score < 10:
        blended = min(blended, 20.0)
    elif ref_score < 20:
        blended = min(blended, 30.0)
    elif ref_score < 35:
        blended = min(blended, 42.0)
    return round(max(0.0, min(100.0, blended)), 2)
