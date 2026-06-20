import os, json, random, secrets, warnings
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
warnings.filterwarnings('ignore')
random.seed(42); np.random.seed(42)
PASS_MARK = 70
LOW_ACCURACY_LIMIT = 0.8
HIGH_ACCURACY_LIMIT = 0.9

# ── Proctoring policy ────────────────────────────────────────────────────────
# "Focus" violations (looking away, brief tab/window blur) are noisy and prone to
# false positives (an OS notification, a permission prompt, an accidental Escape).
# They are handled in tiers: each one applies a score penalty, and only a sustained
# pattern (>= the limit) triggers a hard fail. "Integrity" violations (no camera/mic,
# screenshots, external devices, non-English answers, explicit security termination)
# remain instant hard fails.
FOCUS_VIOLATION_HARD_FAIL_LIMIT  = 3   # combined tab + blur + gaze events that hard-fail
FOCUS_VIOLATION_PENALTY_PER_EVENT = 8  # score penalty per minor focus event below the limit
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
dataset_dir = str(BASE_DIR / 'dataset')
model_dir = str(BASE_DIR / 'trained_models')
output_dir = str(BASE_DIR / 'output')
os.makedirs(model_dir, exist_ok=True)
os.makedirs(output_dir, exist_ok=True)

def banner(title):
    print('\n' + '=' * 80); print(title); print('=' * 80)

def rmse(y, p):
    return float(np.sqrt(mean_squared_error(y, p)))

def clamp_score(v):
    return float(max(0, min(100, float(v))))

def label_from_score(score):
    return 'pass' if float(score) >= PASS_MARK else 'fail'

def show_accuracy_guard(name, y_true, y_pred):
    acc = accuracy_score(y_true, y_pred)
    print(f'{name} accuracy: {acc:.3f}')
    if acc >= HIGH_ACCURACY_LIMIT: print('within band')
    elif acc < LOW_ACCURACY_LIMIT: print('WARNING: below')
    else: print('OK: in range.')
    print(classification_report(y_true, y_pred, zero_division=0)); print(confusion_matrix(y_true, y_pred))
    return acc


# ## 2. Load and clean datasets

# In[3]:


# ## 3. Taxonomy and preprocessing helpers

# In[4]:


EXPERIENCE_BAND_TO_YEAR_RANGE = {'fresher': (0.0, 0.9), 'junior_professional': (1.0, 2.9), 'mid_level_expert': (3.0, 5.9), 'senior_professional': (6.0, 9.9), 'industry_veteran': (10.0, 15.0)}
CANONICAL_TECH_SKILLS = []
USER_APPROVED_JOB_ROLES = ['Data Scientist', 'Java Developer', 'Python Developer', 'React Developer', 'DevOps Engineer', 'SQL Developer', 'Business Analyst', 'Software Developer', 'Full Stack Developer', 'Cloud Engineer', 'Machine Learning Engineer', 'Security Engineer', 'Frontend Developer', 'Backend Developer', 'AI Engineer', 'QA Engineer', 'Database Administrator', 'UI/UX  Developer', 'Mobile App Developer', 'Blockchain Developer', 'Cybersecurity Analyst']
CANONICAL_ROLES = []
CANONICAL_TRAITS = []
ROLE_NORMALIZATION_MAP = {
    'Software Engineer': 'Software Developer',
    'AI/ML Engineer': 'AI Engineer',
    'ML Engineer': 'Machine Learning Engineer',
    'Block Chain Developer': 'Blockchain Developer',
    'Blockchain Developer': 'Blockchain Developer',
    'Cyber Security Analyst': 'Cybersecurity Analyst',
    'Cybersecurity Analyst': 'Cybersecurity Analyst',
    'UI/UX Designer': 'UI/UX  Developer',
    'UI/UX Developer': 'UI/UX  Developer',
    'UI/UX  Developer': 'UI/UX  Developer',
}
SKILL_NORMALIZATION_MAP = {}
SKILL_NORMALIZATION_MAP.update({'SQL': 'DBMS', 'Statistics': 'Machine Learning', 'Python': 'Django', 'JavaScript': 'React', 'Spring Boot': 'OOP', 'Selenium': 'Software Engineering', 'Testing': 'Software Engineering', 'Cyber Security': 'Networking'})
TRAIT_NORMALIZATION_MAP = {}

def normalize_role(role):
    role = str(role).strip()
    if not role:
        return 'Software Developer'
    mapped = ROLE_NORMALIZATION_MAP.get(role)
    if mapped:
        return mapped
    lowered = role.lower()
    for key, value in ROLE_NORMALIZATION_MAP.items():
        if key.lower() == lowered:
            return value
    for approved_role in USER_APPROVED_JOB_ROLES:
        if approved_role.lower() == lowered:
            return approved_role
    if role in CANONICAL_ROLES:
        return role
    return 'Software Developer'

def normalize_skill(skill):
    skill = str(skill).strip()
    return SKILL_NORMALIZATION_MAP.get(skill, skill if skill in CANONICAL_TECH_SKILLS else 'Software Engineering')

def normalize_trait(trait):
    trait = str(trait).strip()
    return TRAIT_NORMALIZATION_MAP.get(trait, trait if trait in CANONICAL_TRAITS else 'Communication')

def align_row(row, ordered_columns):
    return pd.DataFrame([{col: row.get(col, 0) for col in ordered_columns}])

def create_text_preprocessor(text_col, numeric_cols, categorical_cols, max_features=500):
    return ColumnTransformer([('text', TfidfVectorizer(max_features=max_features, ngram_range=(1, 2), min_df=2), text_col), ('num', StandardScaler(), numeric_cols), ('cat', OneHotEncoder(handle_unknown='ignore'), categorical_cols)])

def create_tabular_preprocessor(numeric_cols, categorical_cols):
    return ColumnTransformer([('num', StandardScaler(), numeric_cols), ('cat', OneHotEncoder(handle_unknown='ignore'), categorical_cols)])


# ## 4. Transcript feature extraction
# 
# These helper functions convert backend speech-to-text transcripts into numeric features such as clarity, relevance, correctness, keyword hits, grammar, confidence, empathy, structure, and ownership. In the real website, the backend sends transcripts and monitoring scores; this module evaluates the interview from those values.
# 

# In[5]:


import re
from ..answer_quality import (
    apply_answer_score_caps,
    gate_answer_score,
    session_completion_multiplier,
    substantive_content_score,
    content_tokens,
    question_echo_ratio,
)
from ..interview_feedback import generate_improvement_plan, generate_progress_report
from ..reference_answer_scoring import evaluate_reference_match
from ..semantic_answer_scoring import blend_answer_scores, evaluate_semantic_match
from ..question_quality import normalize_for_dedupe
from ..question_selector import select_interview_question, selection_mode_label
from ..role_interview_constants import ROLE_INTERVIEW_SKILLS, experience_band_from_years
SKILL_KEYWORDS = {
    'DSA': ['complexity', 'algorithm', 'hash', 'tree', 'graph', 'binary', 'search', 'sort', 'edge case', 'trade-off'],
    'DBMS': ['index', 'query', 'transaction', 'normalization', 'join', 'sql', 'schema', 'locking'],
    'Django': ['model', 'view', 'orm', 'migration', 'middleware', 'serializer', 'rest', 'authentication', 'queryset', 'select_related', 'prefetch', 'cache', 'redis', 'celery'],
    'React': ['component', 'state', 'props', 'hook', 'render', 'virtual dom', 'context', 'memo'],
    'MERN Stack': ['mongo', 'express', 'react', 'node', 'api', 'jwt', 'routing'],
    'Machine Learning': ['model', 'training', 'validation', 'overfitting', 'feature', 'bias', 'precision', 'recall'],
    'Artificial Intelligence': ['prompt', 'retrieval', 'embedding', 'llm', 'inference', 'guardrail', 'hallucination'],
    'Operating Systems': ['process', 'thread', 'memory', 'scheduling', 'deadlock', 'mutex', 'paging'],
    'Networking': ['tcp', 'udp', 'latency', 'firewall', 'routing', 'packet', 'tls', 'dns'],
    'DevOps': ['docker', 'ci', 'cd', 'pipeline', 'kubernetes', 'monitoring', 'rollback', 'deploy'],
    'Software Engineering': ['requirement', 'design', 'testing', 'maintainability', 'architecture', 'scalability'],
    'OOP': ['inheritance', 'polymorphism', 'encapsulation', 'abstraction', 'class', 'interface'],
}
PERSONALITY_KEYWORDS = {
    'Communication': ['star', 'clarify', 'explain', 'listen', 'update', 'audience', 'feedback'],
    'Collaboration': ['team', 'align', 'support', 'shared', 'conflict', 'respect', 'coordinate'],
    'Stress handling': ['pressure', 'deadline', 'prioritize', 'calm', 'focus', 'escalate'],
    'Leadership': ['lead', 'mentor', 'delegate', 'initiative', 'ownership', 'decision'],
    'Adaptability': ['change', 'learn', 'adjust', 'new', 'flexible', 'pivot'],
    'Problem solving': ['analyze', 'root cause', 'solution', 'debug', 'investigate', 'hypothesis'],
    'Time management': ['prioritize', 'schedule', 'deadline', 'plan', 'organize', 'backlog'],
    'Integrity': ['honest', 'ethical', 'transparent', 'accountable', 'trust'],
}
FILLER_WORDS = {'um', 'uh', 'like', 'you know', 'basically', 'actually', 'sort of', 'kind of'}
STAR_MARKERS = ['situation', 'task', 'action', 'result', 'learned', 'outcome', 'because', 'therefore']

def _tokenize(text):
    return re.findall(r"[a-zA-Z']+", str(text).lower())

def _count_keyword_hits(text, keywords):
    lowered = str(text).lower()
    return sum(1 for kw in keywords if kw in lowered)

def _filler_ratio(text):
    words = _tokenize(text)
    if not words: return 0.0
    return round(sum(1 for w in words if w in FILLER_WORDS) / max(len(words), 1), 3)

def _grammar_heuristic(text):
    words = _tokenize(text)
    if len(words) < 8: return 45.0
    score = 70.0
    if re.search(r'\b(is|are|was|were|have|has|had)\b', text.lower()): score += 8
    if re.search(r'[.!?]', text): score += 6
    if len(words) >= 25: score += 8
    score -= min(20, sum(1 for w in words if len(w) > 12) * 2)
    return clamp_score(score)

def _confidence_heuristic(text):
    words = _tokenize(text)
    if not words:
        return 0.0
    score = 42.0
    score -= sum(8 for phrase in ['not sure', 'maybe', 'i think', 'i guess', "don't know"] if phrase in text.lower())
    score += sum(6 for phrase in ['i would', 'i implemented', 'i designed', 'because', 'therefore'] if phrase in text.lower())
    score += min(8, len(words) // 8)
    return clamp_score(score)

def _communication_heuristic(text):
    words = _tokenize(text)
    if not words:
        return 0.0
    score = 38.0
    if any(marker in text.lower() for marker in STAR_MARKERS):
        score += 12
    if len(words) >= 20:
        score += 5
    if len(words) >= 45:
        score += 4
    if _filler_ratio(text) > 0.2:
        score -= 12
    return clamp_score(score)

def extract_technical_features(answer_text, skill_area, question_text='', experience_band='fresher'):
    text = str(answer_text or '').strip()
    words = _tokenize(text)
    skill = normalize_skill(skill_area or 'Software Engineering')
    keywords = SKILL_KEYWORDS.get(skill, SKILL_KEYWORDS['Software Engineering'])
    keyword_hits = _count_keyword_hits(text, keywords)
    new_content = len(content_tokens(text) - content_tokens(question_text))
    echo = question_echo_ratio(text, question_text)
    relevance_base = 30 + new_content * 5 + keyword_hits * 6 - echo * 45
    return {
        'answer_text': text, 'word_count': len(words), 'keyword_hits': keyword_hits,
        'clarity_score': clamp_score(45 + min(35, len(words) // 2) + (8 if '.' in text else 0) - _filler_ratio(text) * 40),
        'relevance_score': clamp_score(relevance_base),
        'correctness_score': clamp_score(35 + keyword_hits * 8 + min(25, new_content * 2) + (10 if any(k in text.lower() for k in ['trade-off', 'complexity', 'edge case']) else 0)),
        'skill_area': skill, 'experience_band': experience_band,
    }

def extract_personality_features(answer_text, trait, experience_band='fresher', question_text=''):
    text = str(answer_text or '').strip()
    trait_name = normalize_trait(trait or 'Communication')
    keywords = PERSONALITY_KEYWORDS.get(trait_name, PERSONALITY_KEYWORDS['Communication'])
    keyword_hits = _count_keyword_hits(text, keywords)
    star_hits = sum(1 for m in STAR_MARKERS if m in text.lower())
    echo = question_echo_ratio(text, question_text)
    empathy = 45 + keyword_hits * 5 + star_hits * 4 - echo * 30
    structure = 40 + star_hits * 10 + (12 if 'first' in text.lower() and 'then' in text.lower() else 0) - echo * 20
    return {
        'answer_text': text,
        'empathy_score': clamp_score(empathy),
        'structure_score': clamp_score(structure),
        'positivity_score': clamp_score(50 + (8 if any(w in text.lower() for w in ['learned', 'improved', 'successful']) else 0)),
        'ownership_score': clamp_score(45 + (10 if any(w in text.lower() for w in ['i led', 'i owned', 'my responsibility', 'i took']) else 0)),
        'trait': trait_name, 'experience_band': experience_band,
    }

def extract_session_text_metrics(transcripts, avg_answer_seconds=None, total_questions=None):
    """Convert backend speech-to-text answers into session-level communication metrics.

    The backend provides the transcript text. This module extracts the answer quality
    scores from that text and also keeps monitoring scores from the backend separate.
    Communication and confidence are scaled by interview completion — skipping most
    questions cannot produce high delivery scores.
    """
    valid_transcripts = [str(t or '').strip() for t in transcripts if str(t or '').strip()]
    joined = ' '.join(valid_transcripts).strip()
    word_counts = [len(_tokenize(t)) for t in valid_transcripts]
    avg_answer_seconds_provided = avg_answer_seconds is not None
    if avg_answer_seconds is None:
        avg_answer_seconds = 60.0 if valid_transcripts else 0.0

    total = int(total_questions or len(transcripts) or 0)
    completion_multiplier = session_completion_multiplier(len(valid_transcripts), total)
    raw_comm = _communication_heuristic(joined) if joined else 0.0
    raw_conf = _confidence_heuristic(joined) if joined else 0.0

    return {
        'communication_score': clamp_score(raw_comm * completion_multiplier),
        'confidence_score': clamp_score(raw_conf * completion_multiplier),
        'filler_ratio': _filler_ratio(joined),
        'avg_answer_length': round(float(np.mean(word_counts)), 2) if word_counts else 0.0,
        'avg_answer_seconds': float(avg_answer_seconds),
        'avg_answer_seconds_source': 'provided' if avg_answer_seconds_provided else 'default',
        'questions_answered': len(valid_transcripts),
        'questions_total': total,
        'completion_ratio': round(len(valid_transcripts) / total, 3) if total else 0.0,
    }


# ## 5. Cooldown rules and dynamic feedback

# In[6]:


def backend_style_cooldown_days(final_score, decision, hard_fail_triggered=False, interview_expired=False):
    if interview_expired:
        return 3
    if str(decision).lower() == 'pass':
        return 0
    if hard_fail_triggered:
        return 3
    if float(final_score) < 50:
        return 3
    if 50 <= float(final_score) < PASS_MARK:
        return 1
    return 0

def _focus_event_count(session_input):
    """Combined count of low-severity 'focus' violations.

    Tab switches are intentionally excluded: they are treated as an instant
    integrity hard fail in apply_hard_fail_rules(), not a tiered focus event.
    """
    return (
        int(session_input.get('window_blur_events', 0))
        + int(session_input.get('gaze_off_over_20s', 0))
    )

def focus_violation_penalty(session_input):
    """Graduated score penalty for focus events that stay below the hard-fail limit."""
    events = _focus_event_count(session_input)
    if events >= FOCUS_VIOLATION_HARD_FAIL_LIMIT:
        return 0.0  # this becomes a hard fail elsewhere; no separate penalty needed
    return float(events * FOCUS_VIOLATION_PENALTY_PER_EVENT)

def apply_hard_fail_rules(session_input):
    """Two-tier proctoring.

    Integrity violations fail instantly. Focus violations (blur/gaze) only fail
    once their combined count reaches FOCUS_VIOLATION_HARD_FAIL_LIMIT; below that they
    are penalised via focus_violation_penalty() instead of ending the attempt.
    A single tab switch is treated as an integrity violation and fails instantly.
    """
    # An explicit client-side security termination is always a hard fail.
    if bool(session_input.get('terminated_by_violation', False)):
        return (True, 'Interview was ended early due to a security violation')

    integrity_checks = [
        ('camera_available',       lambda v: int(v) != 1, 'Camera access was unavailable during the interview.'),
        ('mic_available',          lambda v: int(v) != 1, 'Microphone access was unavailable during the interview.'),
        ('tab_switches',           lambda v: int(v) > 0,  'The interview tab was switched away from, which is not allowed.'),
        ('screenshot_attempted',   lambda v: int(v) > 0,  'A screenshot attempt was detected during the interview.'),
        ('device_detected',        lambda v: int(v) > 0,  'An external device was detected during the interview.'),
        ('english_only_violation', lambda v: int(v) > 0,  'A response violated the English-only rule.'),
    ]
    for field, rule, reason in integrity_checks:
        default = 1 if field in ('camera_available', 'mic_available') else 0
        if rule(session_input.get(field, default)):
            return (True, reason)

    focus_events = _focus_event_count(session_input)
    if focus_events >= FOCUS_VIOLATION_HARD_FAIL_LIMIT:
        return (True, f'Focus was repeatedly lost during the interview ({focus_events} events). '
                      f'Stay on the interview screen and keep your face toward the camera.')

    return (False, 'No hard-fail rule triggered.')

GENERIC_QUESTION_PATTERN = re.compile(
    r'^How would you handle a .* problem (for|during|in|inside)',
    re.IGNORECASE,
)


def _is_generic_template_question(text: str) -> bool:
    return bool(GENERIC_QUESTION_PATTERN.match(str(text or '').strip()))


def _empty_session_result(session_meta, interview_expired=False, reason='No answers were provided.'):
    """Return a zero-score result when the candidate did not answer."""
    monitoring = {
        'attentiveness_score': float(session_meta.get('attentiveness_score', 0) or 0),
        'eye_contact_score': float(session_meta.get('eye_contact_score', 0) or 0),
        'tab_switches': int(session_meta.get('tab_switches', 0) or 0),
        'window_blur_events': int(session_meta.get('window_blur_events', 0) or 0),
        'screenshot_attempted': int(session_meta.get('screenshot_attempted', 0) or 0),
        'device_detected': int(session_meta.get('device_detected', 0) or 0),
        'gaze_off_over_20s': int(session_meta.get('gaze_off_over_20s', 0) or 0),
        'camera_available': int(session_meta.get('camera_available', 1) or 1),
        'mic_available': int(session_meta.get('mic_available', 1) or 1),
        'english_only_violation': int(session_meta.get('english_only_violation', 0) or 0),
        'terminated_by_violation': bool(session_meta.get('terminated_by_violation', False)),
    }
    hard_fail, fail_reason = apply_hard_fail_rules({**session_meta, **monitoring})
    if not hard_fail and interview_expired:
        fail_reason = 'Interview time expired before all answers were completed.'
    elif not hard_fail:
        fail_reason = reason
    cooldown_days = backend_style_cooldown_days(0, 'fail', hard_fail, interview_expired)
    years = float(session_meta.get('experience_years', session_meta.get('years_experience', 0)) or 0)
    band = session_meta.get('experience_band') or experience_band_from_years(years)
    job_role = normalize_role(session_meta.get('job_role', 'Software Developer'))
    result = {
        'technical_score': 0.0,
        'personality_score': 0.0,
        'communication_score': 0.0,
        'confidence_score': 0.0,
        'attentiveness_score': monitoring['attentiveness_score'],
        'eye_contact_score': monitoring['eye_contact_score'],
        'filler_ratio': 0.0,
        'avg_answer_length': 0.0,
        'avg_answer_seconds': float(session_meta.get('avg_answer_seconds', 0) or 0),
        'avg_answer_seconds_source': session_meta.get('avg_answer_seconds_source', 'provided'),
        'final_score': 0.0,
        'score': 0.0,
        'final_decision': 'fail',
        'decision': 'fail',
        'passed': False,
        'hard_fail_triggered': bool(hard_fail),
        'fail_reason': fail_reason,
        'cooldown_days': cooldown_days,
        'target_role': job_role,
        'job_role': job_role,
        'experience_years': years,
        'years_experience': years,
        'experience_band': band,
        'technical_skill_area': normalize_skill(session_meta.get('target_skill_area', 'Software Engineering')),
        'personality_trait': normalize_trait(session_meta.get('personality_trait', 'Communication')),
        'per_question_scores': [],
        'interview_expired': bool(interview_expired),
        'model_reference_score': 0.0,
        **monitoring,
    }
    result['progress_report'] = generate_progress_report(result)
    result['improvement_plan'] = generate_improvement_plan(result)
    result['full_report_text'] = (
        f"Interview Result: FAIL | Final Score: 0 | Technical: 0 | Personality: 0 | "
        f"Cooldown: {cooldown_days} day(s). {result['improvement_plan']}"
    )
    return result

def _score_status(score):
    from ..interview_feedback import score_status
    return score_status(score)


_MODELS = None
question_generation_df = None
technical_question_df = None      # real technical questions (skill_area, experience_band, question)
personality_question_df = None    # real personality questions (trait, experience_band, question)
MODELS = None
technical_feature_columns = None
personality_feature_columns = None
session_feature_columns = None
question_generation_feature_columns = None


def _model_files_ready():
    names = [
        'technical_score_model.joblib', 'technical_label_model.joblib',
        'personality_score_model.joblib', 'personality_label_model.joblib',
        'final_score_model.joblib', 'final_label_model.joblib',
        'question_generation_model.joblib',
    ]
    return all(os.path.exists(os.path.join(model_dir, n)) for n in names)


def _bootstrap_dataframes():
    global question_generation_df, technical_question_df, personality_question_df
    global CANONICAL_TECH_SKILLS, CANONICAL_ROLES, CANONICAL_TRAITS
    global SKILL_NORMALIZATION_MAP, TRAIT_NORMALIZATION_MAP
    technical_df = pd.read_csv(os.path.join(dataset_dir, 'technical_interview_dataset.csv'))
    personality_df = pd.read_csv(os.path.join(dataset_dir, 'personality_interview_dataset.csv'))
    session_df = pd.read_csv(os.path.join(dataset_dir, 'interview_session_dataset.csv'))
    question_generation_df = pd.read_csv(os.path.join(dataset_dir, 'interview_question_generation_dataset.csv'))
    personality_df = personality_df.drop_duplicates(subset=['answer_text'], keep='first').reset_index(drop=True)
    question_generation_df['question_family_train'] = question_generation_df['question_family'].replace(
        {'debugging': 'conceptual', 'optimization': 'conceptual'}
    )
    # Real, candidate-facing question banks. The generation dataset's `question_text`
    # is an LLM meta-prompt ("ask a question about X … Question id N") and must NOT be
    # shown to candidates; the actual questions live in the technical/personality
    # answer datasets under the `question` column.
    technical_question_df = (
        technical_df[['skill_area', 'experience_band', 'question']]
        .dropna(subset=['question'])
        .drop_duplicates(subset=['question'])
        .reset_index(drop=True)
    )
    personality_question_df = (
        personality_df[['trait', 'experience_band', 'question']]
        .dropna(subset=['question'])
        .drop_duplicates(subset=['question'])
        .reset_index(drop=True)
    )
    CANONICAL_TECH_SKILLS = sorted(technical_df['skill_area'].dropna().astype(str).unique().tolist())
    CANONICAL_ROLES = [
        role for role in USER_APPROVED_JOB_ROLES
        if role in set(question_generation_df['role'].dropna().astype(str).unique())
    ]
    CANONICAL_TRAITS = sorted(personality_df['trait'].dropna().astype(str).unique().tolist())
    SKILL_NORMALIZATION_MAP = {s: s for s in CANONICAL_TECH_SKILLS}
    SKILL_NORMALIZATION_MAP.update({
        'SQL': 'DBMS', 'Statistics': 'Machine Learning', 'Python': 'Django',
        'JavaScript': 'React', 'Spring Boot': 'OOP', 'Selenium': 'Software Engineering',
        'Testing': 'Software Engineering', 'Cyber Security': 'Networking',
    })
    TRAIT_NORMALIZATION_MAP = {t: t for t in CANONICAL_TRAITS}
    return technical_df, personality_df, session_df, question_generation_df


def train_and_save_models():
    global MODELS, _MODELS
    technical_df, personality_df, session_df, question_generation_df = _bootstrap_dataframes()
    technical_df['target_label'] = technical_df['target_score'].apply(label_from_score)
    personality_df['target_label'] = personality_df['target_score'].apply(label_from_score)
    session_df['decision'] = session_df['final_score'].apply(label_from_score)
    # ## 6. Train technical models

    # In[7]:


    banner('TECHNICAL MODELS')
    technical_text_col = 'answer_text'
    technical_numeric_features = ['word_count', 'keyword_hits', 'clarity_score', 'relevance_score', 'correctness_score']
    technical_categorical_features = ['skill_area', 'experience_band']
    technical_feature_columns = [technical_text_col] + technical_numeric_features + technical_categorical_features
    X = technical_df[technical_feature_columns]; y_reg = technical_df['target_score'].astype(float); y_cls = technical_df['target_label'].astype(str)
    X_train, X_test, y_reg_train, y_reg_test, y_cls_train, y_cls_test = train_test_split(X, y_reg, y_cls, test_size=0.2, random_state=42, stratify=y_cls)
    technical_score_model = Pipeline([('preprocessor', create_text_preprocessor(technical_text_col, technical_numeric_features, technical_categorical_features)), ('model', Ridge(alpha=7.0))])
    technical_label_model = Pipeline([('preprocessor', create_text_preprocessor(technical_text_col, technical_numeric_features, technical_categorical_features)), ('model', LogisticRegression(max_iter=1200, C=0.8, class_weight='balanced'))])
    technical_score_model.fit(X_train, y_reg_train); technical_label_model.fit(X_train, y_cls_train)
    technical_accuracy = show_accuracy_guard('Technical label model', y_cls_test, technical_label_model.predict(X_test))


    # ## 7. Train personality models

    # In[8]:


    banner('PERSONALITY MODELS')
    personality_text_col = 'answer_text'
    personality_numeric_features = ['empathy_score', 'structure_score', 'positivity_score', 'ownership_score']
    personality_categorical_features = ['trait', 'experience_band']
    personality_feature_columns = [personality_text_col] + personality_numeric_features + personality_categorical_features
    X = personality_df[personality_feature_columns]; y_reg = personality_df['target_score'].astype(float); y_cls = personality_df['target_label'].astype(str)
    X_train, X_test, y_reg_train, y_reg_test, y_cls_train, y_cls_test = train_test_split(X, y_reg, y_cls, test_size=0.2, random_state=42, stratify=y_cls)
    personality_score_model = Pipeline([('preprocessor', create_text_preprocessor(personality_text_col, personality_numeric_features, personality_categorical_features)), ('model', Ridge(alpha=9.0))])
    personality_label_model = Pipeline([('preprocessor', create_text_preprocessor(personality_text_col, personality_numeric_features, personality_categorical_features)), ('model', LogisticRegression(max_iter=1200, C=0.15, class_weight='balanced'))])
    personality_score_model.fit(X_train, y_reg_train); personality_label_model.fit(X_train, y_cls_train)
    personality_accuracy = show_accuracy_guard('Personality label model', y_cls_test, personality_label_model.predict(X_test))


    # ## 8. Train final interview decision models

    # In[9]:


    banner('FINAL INTERVIEW MODELS')
    session_numeric_features = ['experience_years', 'technical_score', 'personality_score', 'communication_score', 'attentiveness_score', 'eye_contact_score', 'filler_ratio', 'avg_answer_seconds', 'grammar_score', 'confidence_score', 'tab_switches', 'window_blur_events', 'screenshot_attempted', 'device_detected', 'gaze_off_over_20s', 'camera_available', 'mic_available', 'english_only_violation']
    session_categorical_features = ['experience_band']
    session_feature_columns = session_numeric_features + session_categorical_features
    X = session_df[session_feature_columns]; y_reg = session_df['final_score'].astype(float); y_cls = session_df['decision'].astype(str)
    X_train, X_test, y_reg_train, y_reg_test, y_cls_train, y_cls_test = train_test_split(X, y_reg, y_cls, test_size=0.2, random_state=42, stratify=y_cls)
    final_score_model = Pipeline([('preprocessor', create_tabular_preprocessor(session_numeric_features, session_categorical_features)), ('model', RandomForestRegressor(n_estimators=140, max_depth=5, min_samples_leaf=12, random_state=42, n_jobs=-1))])
    final_label_model = Pipeline([('preprocessor', create_tabular_preprocessor(session_numeric_features, session_categorical_features)), ('model', RandomForestClassifier(n_estimators=140, max_depth=5, min_samples_leaf=12, random_state=42, n_jobs=-1, class_weight='balanced'))])
    final_score_model.fit(X_train, y_reg_train); final_label_model.fit(X_train, y_cls_train)
    final_accuracy = show_accuracy_guard('Final decision model', y_cls_test, final_label_model.predict(X_test))


    # ## 9. Train question-selection model

    # In[10]:


    banner('QUESTION SELECTION MODEL')
    question_generation_numeric_features = ['years_experience']
    question_generation_categorical_features = ['role', 'experience_band', 'focus_area', 'skill_topic', 'difficulty_level']
    question_generation_feature_columns = question_generation_numeric_features + question_generation_categorical_features
    X = question_generation_df[question_generation_feature_columns]; y = question_generation_df['question_family_train'].astype(str)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    question_generation_model = Pipeline([('preprocessor', create_tabular_preprocessor(question_generation_numeric_features, question_generation_categorical_features)), ('model', LogisticRegression(max_iter=1200, C=0.7, class_weight='balanced'))])
    question_generation_model.fit(X_train, y_train)
    question_accuracy = accuracy_score(y_test, question_generation_model.predict(X_test))
    print('Question family accuracy:', round(question_accuracy, 3)); print(classification_report(y_test, question_generation_model.predict(X_test), zero_division=0))


    # ## 10. Backend integration functions

    # In[11]:

    MODELS = {
        'technical_score_model': technical_score_model,
        'technical_label_model': technical_label_model,
        'personality_score_model': personality_score_model,
        'personality_label_model': personality_label_model,
        'final_score_model': final_score_model,
        'final_label_model': final_label_model,
        'question_generation_model': question_generation_model,
    }
    _MODELS = MODELS
    for filename, model in MODELS.items():
        joblib.dump(model, os.path.join(model_dir, f'{filename}.joblib'))
    contract = {
        'technical_feature_columns': technical_feature_columns,
        'personality_feature_columns': personality_feature_columns,
        'session_feature_columns': session_feature_columns,
        'question_generation_feature_columns': question_generation_feature_columns,
        'pass_mark': PASS_MARK,
    }
    with open(os.path.join(model_dir, 'model_contract.json'), 'w', encoding='utf-8') as f:
        json.dump(contract, f, indent=2)


def ensure_models_loaded():
    global MODELS, _MODELS
    global technical_feature_columns, personality_feature_columns
    global session_feature_columns, question_generation_feature_columns
    if _MODELS is not None:
        MODELS = _MODELS
        if not CANONICAL_TECH_SKILLS:
            _bootstrap_dataframes()
        return
    if _model_files_ready():
        with open(os.path.join(model_dir, 'model_contract.json'), encoding='utf-8') as f:
            contract = json.load(f)
        technical_feature_columns = contract['technical_feature_columns']
        personality_feature_columns = contract['personality_feature_columns']
        session_feature_columns = contract['session_feature_columns']
        question_generation_feature_columns = contract['question_generation_feature_columns']
        _MODELS = {
            name: joblib.load(os.path.join(model_dir, f'{name}.joblib'))
            for name in [
                'technical_score_model', 'technical_label_model',
                'personality_score_model', 'personality_label_model',
                'final_score_model', 'final_label_model', 'question_generation_model',
            ]
        }
        MODELS = _MODELS
        _bootstrap_dataframes()
        return
    train_and_save_models()


def _require_models():
    ensure_models_loaded()

def _merge_scoring_meta(reference_match, semantic_match):
    meta = {}
    if reference_match:
        meta.update(reference_match)
    if semantic_match:
        meta.update(semantic_match)
    return meta or None


def _score_single_answer(answer, experience_band):
    _require_models()
    qtype = answer.get('question_type', 'technical')
    transcript = str(answer.get('transcript', '') or answer.get('answer_text', '')).strip()
    question_text = str(answer.get('question_text', '') or '')
    reference_keywords = answer.get('reference_keywords') or ''
    reference_points = answer.get('reference_points') or ''
    category = answer.get('category', 'Software Engineering')
    if not transcript:
        return 0.0, None

    semantic_match = evaluate_semantic_match(
        transcript,
        question_text=question_text,
        reference_points=reference_points,
        reference_keywords=reference_keywords,
        category=category,
        question_type=qtype,
        job_role=answer.get('job_role', ''),
    )
    semantic_score = float(semantic_match['semantic_score']) if semantic_match else None
    reference_match = evaluate_reference_match(transcript, reference_keywords)

    gated = gate_answer_score(
        transcript,
        question_text,
        qtype,
        experience_band,
        semantic_score=semantic_score,
    )
    if gated is not None:
        if semantic_score is not None and semantic_score >= 68.0:
            gated = None
        else:
            return clamp_score(gated), _merge_scoring_meta(reference_match, semantic_match)

    if qtype == 'technical':
        features = extract_technical_features(
            transcript,
            category,
            question_text,
            experience_band,
        )
        ml_score = clamp_score(
            MODELS['technical_score_model'].predict(align_row(features, technical_feature_columns))[0]
        )
        cap = substantive_content_score(
            transcript,
            question_text,
            'technical',
            experience_band,
            keyword_hits=features.get('keyword_hits', 0),
            semantic_score=semantic_score,
        )
        quality_score = clamp_score(min(ml_score, cap))
        keyword_hits = int(features.get('keyword_hits', 0) or 0)
    else:
        trait = normalize_trait(category or 'Communication')
        if qtype == 'personality' and trait not in (CANONICAL_TRAITS or []) and trait not in TRAIT_NORMALIZATION_MAP:
            trait = 'Communication'
        features = extract_personality_features(transcript, trait, experience_band, question_text)
        ml_score = clamp_score(
            MODELS['personality_score_model'].predict(align_row(features, personality_feature_columns))[0]
        )
        star_hits = sum(1 for marker in STAR_MARKERS if marker in transcript.lower())
        keyword_hits = _count_keyword_hits(transcript, PERSONALITY_KEYWORDS.get(trait, []))
        cap = substantive_content_score(
            transcript,
            question_text,
            'personality',
            experience_band,
            keyword_hits=keyword_hits,
            star_hits=star_hits,
            semantic_score=semantic_score,
        )
        quality_score = clamp_score(min(ml_score, cap))

    final_score = blend_answer_scores(quality_score, reference_match, semantic_match)
    final_score = apply_answer_score_caps(
        final_score,
        transcript=transcript,
        reference_match=reference_match,
        keyword_hits=keyword_hits,
        question_type=qtype,
        semantic_match=semantic_match,
    )
    return final_score, _merge_scoring_meta(reference_match, semantic_match)

def _pick_real_question(
    focus_area,
    skill_or_trait,
    band,
    rng,
    exclude=None,
    difficulty='medium',
    job_role=None,
    years_experience=0.0,
    predicted_family=None,
    primary_skill=None,
    slot_index=0,
):
    """Select a question strictly by job role and experience (no unrelated topics)."""
    role = normalize_role(job_role) if job_role else 'Software Developer'
    skill = primary_skill or normalize_skill(skill_or_trait or 'Software Engineering')
    question_text, category, source, reference_keywords, reference_points = select_interview_question(
        focus_area=focus_area,
        job_role=role,
        years_experience=float(years_experience or 0),
        experience_band=band,
        difficulty=difficulty,
        primary_skill=skill,
        rng=rng,
        exclude=exclude or set(),
        predicted_family=predicted_family,
        slot_index=slot_index,
    )
    return question_text, category, source, reference_keywords, reference_points


def generate_runtime_question(request_input, seed=None, exclude_questions=None):
    _require_models()
    normalized = {'role': normalize_role(request_input.get('role', 'Software Developer')), 'experience_band': request_input.get('experience_band', experience_band_from_years(request_input.get('years_experience', 0))), 'years_experience': float(request_input.get('years_experience', 0)), 'focus_area': str(request_input.get('focus_area', 'technical')), 'skill_topic': str(request_input.get('skill_topic', 'Software Engineering')), 'difficulty_level': str(request_input.get('difficulty_level', 'medium'))}
    requested_skill = normalize_skill(normalized['skill_topic']) if normalized['focus_area'] == 'technical' else normalize_trait(normalized['skill_topic'])
    # Local sklearn model predicts question family; candidate-facing text is built in-process.
    predicted_family = str(MODELS['question_generation_model'].predict(align_row(normalized, question_generation_feature_columns))[0])

    question_text, category, generation_source, reference_keywords, reference_points = _pick_real_question(
        normalized['focus_area'], requested_skill, normalized['experience_band'],
        rng=seed, exclude=exclude_questions, difficulty=normalized['difficulty_level'],
        job_role=normalized['role'],
        years_experience=normalized['years_experience'],
        predicted_family=predicted_family,
        primary_skill=normalized.get('primary_skill') or requested_skill,
        slot_index=int(normalized.get('slot_index', 0)),
    )

    qtype = 'technical' if normalized['focus_area'] == 'technical' else 'personality'
    return {
        'question_text': question_text,
        'question_type': qtype,
        'category': category,
        'predicted_question_family': predicted_family,
        'difficulty_level': normalized['difficulty_level'],
        'generation_source': generation_source,
        'reference_keywords': reference_keywords,
        'reference_points': reference_points,
    }

def run_full_interview_inference(technical_input, personality_input, session_input, interview_expired=False):
    _require_models()
    years = float(session_input.get('experience_years', 0))
    band = session_input.get('experience_band', experience_band_from_years(years))
    technical_payload = dict(technical_input)
    personality_payload = dict(personality_input)
    if not technical_payload.get('clarity_score'):
        technical_payload.update(extract_technical_features(technical_payload.get('answer_text', ''), technical_payload.get('skill_area', 'Software Engineering'), technical_payload.get('question_text', ''), band))
    technical_payload['skill_area'] = normalize_skill(technical_payload.get('skill_area', 'Software Engineering'))
    technical_payload.setdefault('experience_band', band)
    if not personality_payload.get('empathy_score'):
        personality_payload.update(extract_personality_features(personality_payload.get('answer_text', ''), personality_payload.get('trait', 'Communication'), band))
    personality_payload['trait'] = normalize_trait(personality_payload.get('trait', 'Communication'))
    personality_payload.setdefault('experience_band', band)
    technical_score = clamp_score(MODELS['technical_score_model'].predict(align_row(technical_payload, technical_feature_columns))[0])
    personality_score = clamp_score(MODELS['personality_score_model'].predict(align_row(personality_payload, personality_feature_columns))[0])
    enriched = dict(session_input)
    enriched.update({'experience_band': band, 'technical_score': technical_score, 'personality_score': personality_score})
    defaults = {'communication_score': 70, 'attentiveness_score': 70, 'eye_contact_score': 70, 'filler_ratio': 0.1, 'avg_answer_seconds': 60, 'grammar_score': 70, 'confidence_score': 70, 'tab_switches': 0, 'window_blur_events': 0, 'screenshot_attempted': 0, 'device_detected': 0, 'gaze_off_over_20s': 0, 'camera_available': 1, 'mic_available': 1, 'english_only_violation': 0, 'target_role': 'Software Developer', 'target_skill_area': technical_payload['skill_area']}
    for k, v in defaults.items(): enriched.setdefault(k, v)
    enriched['target_role'] = normalize_role(enriched.get('target_role', 'Software Developer'))
    enriched['target_skill_area'] = normalize_skill(enriched.get('target_skill_area', technical_payload['skill_area']))
    final_score = clamp_score(MODELS['final_score_model'].predict(align_row(enriched, session_feature_columns))[0])
    final_decision = str(MODELS['final_label_model'].predict(align_row(enriched, session_feature_columns))[0])
    hard_fail, fail_reason = apply_hard_fail_rules(enriched)
    if hard_fail: final_decision, final_score = 'fail', min(final_score, 45.0)
    elif final_score < PASS_MARK: final_decision = 'fail'
    cooldown_days = backend_style_cooldown_days(final_score, final_decision, hard_fail, interview_expired)
    result = {'technical_score': round(technical_score, 2), 'personality_score': round(personality_score, 2), 'technical_skill_area': technical_payload['skill_area'], 'personality_trait': personality_payload['trait'], 'communication_score': float(enriched['communication_score']), 'attentiveness_score': float(enriched['attentiveness_score']), 'eye_contact_score': float(enriched['eye_contact_score']), 'filler_ratio': float(enriched['filler_ratio']), 'confidence_score': float(enriched['confidence_score']), 'tab_switches': int(enriched['tab_switches']), 'window_blur_events': int(enriched['window_blur_events']), 'screenshot_attempted': int(enriched['screenshot_attempted']), 'device_detected': int(enriched['device_detected']), 'gaze_off_over_20s': int(enriched['gaze_off_over_20s']), 'camera_available': int(enriched['camera_available']), 'mic_available': int(enriched['mic_available']), 'english_only_violation': int(enriched['english_only_violation']), 'final_score': round(final_score, 2), 'final_decision': final_decision, 'decision': final_decision, 'passed': final_decision == 'pass', 'hard_fail_triggered': bool(hard_fail), 'fail_reason': fail_reason, 'cooldown_days': cooldown_days, 'target_role': enriched['target_role'], 'target_skill_area': enriched['target_skill_area'], 'experience_years': years, 'experience_band': band}
    result['progress_report'] = generate_progress_report(result)
    result['improvement_plan'] = generate_improvement_plan(result)
    result['full_report_text'] = f"Interview Result: {result['decision'].upper()} | Final Score: {result['final_score']} | Technical: {result['technical_score']} | Personality: {result['personality_score']} | Cooldown: {result['cooldown_days']} day(s). {result['improvement_plan']}"
    return result

def evaluate_interview_session(answers, session_meta, interview_expired=False):
    _require_models()
    """Primary Django backend entry point for submit_interview."""
    years = float(session_meta.get('experience_years', 0))
    band = session_meta.get('experience_band', experience_band_from_years(years))
    job_role = normalize_role(session_meta.get('job_role', 'Software Developer'))

    transcripts = [
        str(ans.get('transcript', '') or ans.get('answer_text', '')).strip()
        for ans in answers
    ]
    if not any(transcripts):
        empty_meta = dict(session_meta)
        empty_meta.setdefault('job_role', job_role)
        empty_meta.setdefault('experience_years', years)
        empty_meta.setdefault('experience_band', band)
        return _empty_session_result(
            empty_meta,
            interview_expired=interview_expired,
            reason='No answers were provided for any interview question.',
        )

    technical_scores, personality_scores, per_question = [], [], []
    for ans in answers:
        transcript = str(ans.get('transcript', '') or ans.get('answer_text', '')).strip()
        score, scoring_meta = _score_single_answer(ans, band)
        qtype = ans.get('question_type', 'technical')
        item = {
            'question_type': qtype,
            'category': ans.get('category', ''),
            'question_text': ans.get('question_text', ''),
            'transcript': transcript,
            'score': round(score, 2),
        }
        if scoring_meta:
            item.update({
                'reference_match_pct': scoring_meta.get('reference_match_pct'),
                'reference_keyword_hits': scoring_meta.get('reference_keyword_hits'),
                'reference_keyword_total': scoring_meta.get('reference_keyword_total'),
                'hit_keywords': scoring_meta.get('hit_keywords', []),
                'missed_keywords': scoring_meta.get('missed_keywords', []),
                'semantic_score': scoring_meta.get('semantic_score'),
                'semantic_similarity': scoring_meta.get('semantic_similarity'),
            })
        per_question.append(item)
        (technical_scores if qtype == 'technical' else personality_scores).append(score)
    technical_avg = round(sum(technical_scores) / len(technical_scores), 2) if technical_scores else 0.0
    personality_avg = round(sum(personality_scores) / len(personality_scores), 2) if personality_scores else 0.0
    text_metrics = extract_session_text_metrics(
        transcripts,
        session_meta.get('avg_answer_seconds'),
        total_questions=len(answers),
    )
    answered_count = int(text_metrics.get('questions_answered', 0) or 0)
    completion_ratio = float(text_metrics.get('completion_ratio', 0) or 0)
    primary_skill = normalize_skill(next((a.get('category') for a in answers if a.get('question_type') == 'technical'), 'Software Engineering'))
    primary_trait = normalize_trait(next((a.get('category') for a in answers if a.get('question_type') == 'personality'), 'Communication'))
    session_input = {'experience_years': years, 'experience_band': band, 'technical_score': technical_avg, 'personality_score': personality_avg, 'target_role': job_role, 'target_skill_area': primary_skill, 'attentiveness_score': session_meta.get('attentiveness_score', 70), 'eye_contact_score': session_meta.get('eye_contact_score', 70), 'tab_switches': session_meta.get('tab_switches', 0), 'window_blur_events': session_meta.get('window_blur_events', 0), 'screenshot_attempted': session_meta.get('screenshot_attempted', 0), 'device_detected': session_meta.get('device_detected', 0), 'gaze_off_over_20s': session_meta.get('gaze_off_over_20s', 0), 'camera_available': session_meta.get('camera_available', 1), 'mic_available': session_meta.get('mic_available', 1), 'english_only_violation': session_meta.get('english_only_violation', 0), 'terminated_by_violation': bool(session_meta.get('terminated_by_violation', False)), **text_metrics}
    tech_answer = next((a for a in answers if a.get('question_type') == 'technical'), {'transcript': '', 'category': primary_skill})
    pers_answer = next((a for a in answers if a.get('question_type') == 'personality'), {'transcript': '', 'category': primary_trait})
    result = run_full_interview_inference(extract_technical_features(tech_answer.get('transcript', ''), tech_answer.get('category', primary_skill), tech_answer.get('question_text', ''), band), extract_personality_features(pers_answer.get('transcript', ''), pers_answer.get('category', primary_trait), band), session_input, interview_expired)
    result['technical_score'], result['personality_score'] = technical_avg, personality_avg
    result['communication_score'] = round(float(session_input['communication_score']), 2)
    result['confidence_score'] = round(float(session_input['confidence_score']), 2)
    result['filler_ratio'] = round(float(session_input['filler_ratio']), 3)
    result['avg_answer_length'] = text_metrics.get('avg_answer_length', 0.0)
    result['avg_answer_seconds'] = text_metrics.get('avg_answer_seconds', 0.0)
    result['avg_answer_seconds_source'] = text_metrics.get('avg_answer_seconds_source', 'default')

    # Final interview score combines the module-calculated answer scores with
    # backend-provided attentiveness/eye-contact monitoring scores.
    # The trained RandomForest score is kept for reference/auditing, but the
    # transparent weighted formula below is the decision driver.
    result['model_reference_score'] = result.get('final_score')
    if not result['hard_fail_triggered']:
        monitoring_scale = 0.35 + 0.65 * completion_ratio
        attentiveness = float(session_input['attentiveness_score']) * monitoring_scale
        eye_contact = float(session_input['eye_contact_score']) * monitoring_scale
        weighted_score = (
            technical_avg * 0.35
            + personality_avg * 0.25
            + float(session_input['communication_score']) * 0.15
            + float(session_input['confidence_score']) * 0.10
            + attentiveness * 0.075
            + eye_contact * 0.075
        )
        filler_penalty = min(10.0, float(session_input['filler_ratio']) * 25.0)
        focus_penalty = focus_violation_penalty(session_input)
        incomplete_penalty = round((1.0 - completion_ratio) * 22.0, 2) if completion_ratio < 1.0 else 0.0
        overall = round(
            clamp_score(weighted_score - filler_penalty - focus_penalty - incomplete_penalty),
            2,
        )
        # An expired interview can never pass, regardless of the answers given.
        passed = (overall >= PASS_MARK) and not interview_expired
        decision = 'pass' if passed else 'fail'
        result.update({
            'final_score': overall,
            'final_decision': decision,
            'decision': decision,
            'passed': passed,
            'cooldown_days': backend_style_cooldown_days(
                overall, decision, False, interview_expired
            ),
        })
        if interview_expired and not passed:
            result['fail_reason'] = 'Interview time expired before all answers were completed.'
        elif focus_penalty > 0:
            result['focus_penalty_applied'] = round(focus_penalty, 1)
        if incomplete_penalty > 0:
            result['incomplete_penalty_applied'] = incomplete_penalty
            result['questions_answered'] = answered_count
            result['questions_total'] = len(answers)
            result['completion_ratio'] = completion_ratio
    result['interview_expired'] = bool(interview_expired)
    result['job_role'] = job_role
    result['target_role'] = job_role
    result['experience_band'] = band
    result['experience_years'] = years
    result['years_experience'] = years
    role_skills = ROLE_INTERVIEW_SKILLS.get(job_role, [])
    if role_skills:
        result['technical_skill_area'] = normalize_skill(role_skills[0])
        result['target_skill_area'] = result['technical_skill_area']
    result['progress_report'] = generate_progress_report(result)
    result['improvement_plan'] = generate_improvement_plan(result)
    result['full_report_text'] = f"Interview Result: {result['decision'].upper()} | Final Score: {result['final_score']} | Technical: {result['technical_score']} | Personality: {result['personality_score']} | Cooldown: {result['cooldown_days']} day(s). {result['improvement_plan']}"
    result['per_question_scores'] = per_question
    return result


def generate_interview_questions(
    job_role,
    experience_years=0.0,
    num_questions=6,
    seed=None,
    exclude_questions=None,
):
    _require_models()
    """Select interview questions for a candidate using role and experience.

    This function is called by the backend only after the candidate passes the quiz.
    It returns both technical and personality questions.
    Previously used question texts can be passed via exclude_questions so repeat
    attempts for the same role do not show the same prompts again.
    """

    if seed is None:
        seed = secrets.randbelow(2**31)

    band = experience_band_from_years(experience_years)
    role = normalize_role(job_role)
    total_questions = max(2, int(num_questions))
    technical_count = max(1, total_questions // 2)
    personality_count = total_questions - technical_count

    role_skills = ROLE_INTERVIEW_SKILLS.get(role, ['Software Engineering'])
    primary_skill = normalize_skill(role_skills[0])
    difficulty_by_band = {
        'fresher': ['easy', 'medium'],
        'junior_professional': ['easy', 'medium'],
        'mid_level_expert': ['medium', 'hard'],
        'senior_professional': ['medium', 'hard'],
        'industry_veteran': ['hard', 'medium'],
    }
    difficulties = difficulty_by_band.get(band, ['medium'])
    rng = np.random.default_rng(seed)
    used_questions = set()
    for q in (exclude_questions or []):
        text = str(q).strip()
        if text:
            used_questions.add(text)
            used_questions.add(normalize_for_dedupe(text))
    diff_order = rng.permutation(len(difficulties)) if difficulties else np.array([])

    questions = []
    for index in range(technical_count):
        role_skills = ROLE_INTERVIEW_SKILLS.get(role, ['Software Engineering'])
        slot_skill = normalize_skill(role_skills[index % len(role_skills)])
        for attempt in range(20):
            question = generate_runtime_question(
                {
                    'role': role,
                    'experience_band': band,
                    'years_experience': experience_years,
                    'focus_area': 'technical',
                    'skill_topic': slot_skill,
                    'primary_skill': slot_skill,
                    'difficulty_level': difficulties[int(diff_order[index % len(difficulties)])],
                    'slot_index': index + attempt,
                },
                seed=int(rng.integers(0, 100000)),
                exclude_questions=used_questions,
            )
            text = str(question['question_text']).strip()
            text_key = normalize_for_dedupe(text)
            if text in used_questions or text_key in used_questions:
                continue
            used_questions.add(text)
            used_questions.add(text_key)
            question['question_text'] = text
            question['role'] = role
            question['experience_years'] = float(experience_years)
            question['experience_band'] = band
            question['order'] = len(questions)
            questions.append(question)
            break

    for index in range(personality_count):
        for attempt in range(20):
            question = generate_runtime_question(
                {
                    'role': role,
                    'experience_band': band,
                    'years_experience': experience_years,
                    'focus_area': 'personality',
                    'skill_topic': role,
                    'primary_skill': primary_skill,
                    'difficulty_level': difficulties[int(diff_order[index % len(difficulties)])],
                    'slot_index': technical_count + index + attempt,
                },
                seed=int(rng.integers(100000, 200000)),
                exclude_questions=used_questions,
            )
            text = str(question['question_text']).strip()
            text_key = normalize_for_dedupe(text)
            if text in used_questions or text_key in used_questions:
                continue
            used_questions.add(text)
            used_questions.add(text_key)
            question['question_text'] = text
            question['question_type'] = 'personality'
            question['role'] = role
            question['experience_years'] = float(experience_years)
            question['experience_band'] = band
            question['order'] = len(questions)
            questions.append(question)
            break

    technical_questions = [q for q in questions if q['question_type'] == 'technical']
    personality_questions = [q for q in questions if q['question_type'] == 'personality']

    # Interleave technical and personality questions so the interview feels natural.
    ordered_questions = []
    max_len = max(len(technical_questions), len(personality_questions))
    for idx in range(max_len):
        if idx < len(technical_questions):
            ordered_questions.append(technical_questions[idx])
        if idx < len(personality_questions):
            ordered_questions.append(personality_questions[idx])

    for idx, question in enumerate(ordered_questions[:total_questions]):
        question['order'] = idx
    return ordered_questions[:total_questions]


def start_interview_after_quiz(
    quiz_passed,
    job_role,
    experience_years,
    num_questions=6,
    seed=None,
    exclude_questions=None,
):
    _require_models()
    """Backend entry point before starting an interview.

    Quiz is used only as an interview gate. If the quiz is failed, no interview questions
    are generated and the candidate cannot start the interview.
    """

    if not bool(quiz_passed):
        return {
            'can_start_interview': False,
            'stage': 'blocked_by_quiz',
            'message': 'Candidate did not pass the quiz, so the AI interview cannot start.',
            'job_role': normalize_role(job_role),
            'experience_years': float(experience_years),
            'questions': [],
        }

    questions = generate_interview_questions(
        job_role=job_role,
        experience_years=experience_years,
        num_questions=num_questions,
        seed=seed,
        exclude_questions=exclude_questions,
    )
    return {
        'can_start_interview': True,
        'stage': 'questions_generated',
        'message': 'Quiz passed. Interview questions generated successfully.',
        'job_role': normalize_role(job_role),
        'experience_years': float(experience_years),
        'experience_band': experience_band_from_years(experience_years),
        'question_selection_mode': selection_mode_label(),
        'questions': questions,
    }


def run_backend_interview_pipeline(backend_payload):
    _require_models()
    """Complete backend-style flow used for testing and Django integration.

    Expected backend payload:
    - quiz_passed: bool
    - job_role: str
    - experience_years: float
    - num_questions: int
    - answers: list of question dictionaries with backend speech-to-text transcript
    - monitoring: dict containing attentiveness/proctoring scores and hard-fail flags
    """

    start_payload = start_interview_after_quiz(
        quiz_passed=backend_payload.get('quiz_passed', False),
        job_role=backend_payload.get('job_role', 'Software Developer'),
        experience_years=backend_payload.get('experience_years', 0.0),
        num_questions=backend_payload.get('num_questions', 6),
        seed=backend_payload.get('seed', 42),
    )

    if not start_payload['can_start_interview']:
        return {
            **start_payload,
            'interview_result': None,
        }

    answers = backend_payload.get('answers') or []
    if not answers:
        return {
            **start_payload,
            'stage': 'waiting_for_answers',
            'message': 'Questions generated. Waiting for backend speech-to-text transcripts.',
            'interview_result': None,
        }

    monitoring = backend_payload.get('monitoring', {}) or {}
    session_meta = {
        'job_role': start_payload['job_role'],
        'experience_years': start_payload['experience_years'],
        'experience_band': start_payload['experience_band'],
        'attentiveness_score': monitoring.get('attentiveness_score', 70),
        'eye_contact_score': monitoring.get('eye_contact_score', 70),
        'tab_switches': monitoring.get('tab_switches', 0),
        'window_blur_events': monitoring.get('window_blur_events', 0),
        'screenshot_attempted': monitoring.get('screenshot_attempted', 0),
        'device_detected': monitoring.get('device_detected', 0),
        'gaze_off_over_20s': monitoring.get('gaze_off_over_20s', 0),
        'camera_available': monitoring.get('camera_available', 1),
        'mic_available': monitoring.get('mic_available', 1),
        'english_only_violation': monitoring.get('english_only_violation', 0),
        'avg_answer_seconds': monitoring.get('avg_answer_seconds'),
    }
    interview_result = evaluate_interview_session(
        answers=answers,
        session_meta=session_meta,
        interview_expired=backend_payload.get('interview_expired', False),
    )
    return {
        **start_payload,
        'stage': 'completed',
        'interview_result': interview_result,
    }

