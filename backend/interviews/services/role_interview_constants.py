"""Shared role, skill, and difficulty mappings for interview question selection."""

from __future__ import annotations

USER_APPROVED_JOB_ROLES = [
    'Data Scientist',
    'Java Developer',
    'Python Developer',
    'React Developer',
    'DevOps Engineer',
    'SQL Developer',
    'Business Analyst',
    'Software Developer',
    'Full Stack Developer',
    'Cloud Engineer',
    'Machine Learning Engineer',
    'Security Engineer',
    'Frontend Developer',
    'Backend Developer',
    'AI Engineer',
    'QA Engineer',
    'Database Administrator',
    'UI/UX  Developer',
    'Mobile App Developer',
    'Blockchain Developer',
    'Cybersecurity Analyst',
]

ROLE_SKILL_MAP: dict[str, list[str]] = {
    'Data Scientist': ['Machine Learning', 'DBMS', 'Software Engineering'],
    'Java Developer': ['OOP', 'DBMS', 'Software Engineering'],
    'Python Developer': ['Django', 'DSA', 'DBMS'],
    'React Developer': ['React', 'Software Engineering', 'DSA'],
    'DevOps Engineer': ['DevOps', 'Networking', 'Operating Systems'],
    'SQL Developer': ['DBMS', 'Software Engineering', 'DSA'],
    'Business Analyst': ['Software Engineering', 'DBMS', 'Software Engineering'],
    'Software Developer': ['Software Engineering', 'DSA', 'OOP'],
    'Full Stack Developer': ['MERN Stack', 'React', 'DBMS'],
    'Cloud Engineer': ['DevOps', 'Networking', 'Operating Systems'],
    'Machine Learning Engineer': ['Machine Learning', 'Artificial Intelligence', 'DSA'],
    'Security Engineer': ['Networking', 'Operating Systems', 'Software Engineering'],
    'Frontend Developer': ['React', 'Software Engineering', 'DSA'],
    'Backend Developer': ['Django', 'DBMS', 'DSA'],
    'AI Engineer': ['Artificial Intelligence', 'Machine Learning', 'Software Engineering'],
    'QA Engineer': ['Software Engineering', 'DBMS', 'DSA'],
    'Database Administrator': ['DBMS', 'Operating Systems', 'Networking'],
    'UI/UX  Developer': ['React', 'Software Engineering', 'Software Engineering'],
    'Mobile App Developer': ['Software Engineering', 'DSA', 'Networking'],
    'Blockchain Developer': ['DSA', 'Networking', 'Software Engineering'],
    'Cybersecurity Analyst': ['Networking', 'Operating Systems', 'Software Engineering'],
}

# Skills used only for interview question selection (strict — no cross-domain bleed).
ROLE_INTERVIEW_SKILLS: dict[str, list[str]] = {
    'Data Scientist': ['Machine Learning', 'DBMS'],
    'Java Developer': ['OOP', 'DBMS'],
    'Python Developer': ['Django', 'DBMS'],
    'React Developer': ['React'],
    'DevOps Engineer': ['DevOps', 'Networking', 'Operating Systems'],
    'SQL Developer': ['DBMS'],
    'Business Analyst': ['DBMS', 'Software Engineering'],
    'Software Developer': ['Software Engineering', 'DSA', 'OOP'],
    'Full Stack Developer': ['MERN Stack', 'React', 'DBMS'],
    'Cloud Engineer': ['DevOps', 'Networking', 'Operating Systems'],
    'Machine Learning Engineer': ['Machine Learning', 'Artificial Intelligence'],
    'Security Engineer': ['Networking', 'Operating Systems'],
    'Frontend Developer': ['React'],
    'Backend Developer': ['Django', 'DBMS'],
    'AI Engineer': ['Artificial Intelligence', 'Machine Learning'],
    'QA Engineer': ['Software Engineering'],
    'Database Administrator': ['DBMS', 'Operating Systems', 'Networking'],
    'UI/UX  Developer': ['React', 'Software Engineering'],
    'Mobile App Developer': ['Software Engineering', 'Networking'],
    'Blockchain Developer': ['Networking', 'DSA'],
    'Cybersecurity Analyst': ['Networking', 'Operating Systems'],
}

# Block clearly off-topic fragments from adapted skill questions.
ROLE_FORBIDDEN_FRAGMENTS: dict[str, tuple[str, ...]] = {
    'SQL Developer': (
        'linked list',
        'array and a linked',
        'binary search tree',
        'hash map versus binary',
        'merge two sorted arrays',
        'lru cache',
        'dijkstra',
        'consistent hashing',
        'react component',
        'virtual environment',
        'django orm',
        'docker',
        'kubernetes',
    ),
    'Database Administrator': (
        'linked list',
        'array and a linked',
        'react component',
        'virtual environment',
        'django',
    ),
    'React Developer': (
        'linked list',
        'sql query',
        'normalization',
        'django orm',
        'dockerfile',
    ),
    'Frontend Developer': (
        'linked list',
        'sql query',
        'django orm',
        'stored procedure',
    ),
    'Python Developer': (
        'react component',
        'linked list',
        'binary search tree',
    ),
}

ROLE_REQUIRED_TOPIC_MARKERS: dict[str, tuple[str, ...]] = {
    'SQL Developer': (
        'sql', 'query', 'index', 'join', 'schema', 'table', 'database',
        'migration', 'transaction', 'window function', 'normalization',
        'acid', 'deadlock', 'report', 'dbms', 'partition', 'replic',
        'locking', 'view', 'trigger', 'column', 'row', 'aggregate',
    ),
    'Database Administrator': (
        'sql', 'query', 'index', 'database', 'backup', 'replic', 'partition',
        'postgres', 'mysql', 'migration', 'transaction', 'deadlock', 'dbms',
    ),
}

ROLE_PERSONALITY_TRAITS: dict[str, list[str]] = {
    'Data Scientist': ['Communication', 'Problem solving', 'Collaboration'],
    'Java Developer': ['Collaboration', 'Problem solving', 'Stress handling'],
    'Python Developer': ['Communication', 'Collaboration', 'Problem solving'],
    'React Developer': ['Collaboration', 'Communication', 'Adaptability'],
    'DevOps Engineer': ['Stress handling', 'Collaboration', 'Leadership'],
    'SQL Developer': ['Attention to detail', 'Communication', 'Problem solving'],
    'Business Analyst': ['Communication', 'Collaboration', 'Time management'],
    'Software Developer': ['Openness to learning', 'Collaboration', 'Problem solving'],
    'Full Stack Developer': ['Collaboration', 'Stress handling', 'Time management'],
    'Cloud Engineer': ['Stress handling', 'Leadership', 'Collaboration'],
    'Machine Learning Engineer': ['Communication', 'Problem solving', 'Integrity'],
    'Security Engineer': ['Integrity', 'Stress handling', 'Attention to detail'],
    'Frontend Developer': ['Collaboration', 'Adaptability', 'Communication'],
    'Backend Developer': ['Stress handling', 'Collaboration', 'Problem solving'],
    'AI Engineer': ['Communication', 'Integrity', 'Problem solving'],
    'QA Engineer': ['Attention to detail', 'Collaboration', 'Communication'],
    'Database Administrator': ['Stress handling', 'Attention to detail', 'Integrity'],
    'UI/UX  Developer': ['Collaboration', 'Communication', 'Adaptability'],
    'Mobile App Developer': ['Adaptability', 'Collaboration', 'Problem solving'],
    'Blockchain Developer': ['Problem solving', 'Integrity', 'Attention to detail'],
    'Cybersecurity Analyst': ['Integrity', 'Stress handling', 'Communication'],
}

DIFFICULTY_BY_BAND: dict[str, list[str]] = {
    'fresher': ['easy', 'medium'],
    'junior_professional': ['easy', 'medium'],
    'mid_level_expert': ['medium', 'hard'],
    'senior_professional': ['medium', 'hard'],
    'industry_veteran': ['hard', 'medium'],
}

# Resume upload dropdown stores these exact values (years_experience on Resume model).
RESUME_EXPERIENCE_TIER_YEARS = (1.0, 3.0, 5.0)


def experience_band_from_years(years: float | int | str | None) -> str:
    """Map resume years_experience to interview band.

    Aligned with ResumeUpload.tsx values:
      1 -> fresher (Entry, 0-1 years)
      3 -> junior_professional (Mid, 1-3 years)
      5 -> mid_level_expert (Senior UI, 3+ years)
    """
    years = float(years or 0)
    if years <= 1:
        return 'fresher'
    if years <= 3:
        return 'junior_professional'
    if years < 6:
        return 'mid_level_expert'
    if years < 10:
        return 'senior_professional'
    return 'industry_veteran'


EXPERIENCE_BAND_ORDER = [
    'fresher',
    'junior_professional',
    'mid_level_expert',
    'senior_professional',
    'industry_veteran',
]
