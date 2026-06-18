#!/usr/bin/env python
# coding: utf-8

# # AI Interview Module
# 
# This notebook trains the AI interview models and saves `.joblib` assets.
# 
# **Backend entry points:**
# 
# - `start_interview_after_quiz(quiz_passed, job_role, experience_years, num_questions=6)` → used before interview starts.
# - `evaluate_interview_session(answers, session_meta)` → used after backend sends speech-to-text transcripts and monitoring scores.
# - `run_backend_interview_pipeline(backend_payload)` → complete one-call backend flow for testing/integration.

# ## 1. Imports and configuration

# In[2]:


import os, json, random, warnings
from pprint import pprint
import joblib
import numpy as np
import pandas as pd
from IPython.display import display
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
pd.set_option('display.max_columns', None)
PASS_MARK = 70
LOW_ACCURACY_LIMIT = 0.8
HIGH_ACCURACY_LIMIT = 0.9
project_root = os.getcwd()
dataset_dir = os.path.join(project_root, 'Dataset')
model_dir = os.path.join(project_root, 'interview_module_assets', 'trained_models')
output_dir = os.path.join(project_root, 'interview_module_assets', 'output')
os.makedirs(model_dir, exist_ok=True); os.makedirs(output_dir, exist_ok=True)

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


technical_df = pd.read_csv(os.path.join(dataset_dir, 'technical_interview_dataset.csv'))
personality_df = pd.read_csv(os.path.join(dataset_dir, 'personality_interview_dataset.csv'))
session_df = pd.read_csv(os.path.join(dataset_dir, 'interview_session_dataset.csv'))
question_generation_df = pd.read_csv(os.path.join(dataset_dir, 'interview_question_generation_dataset.csv'))
before = len(personality_df)
personality_df = personality_df.drop_duplicates(subset=['answer_text'], keep='first').reset_index(drop=True)
print(f'Personality duplicates removed: {before - len(personality_df)}')
personality_df.to_csv(os.path.join(dataset_dir, 'personality_interview_dataset.csv'), index=False)
technical_df['target_label'] = technical_df['target_score'].apply(label_from_score)
personality_df['target_label'] = personality_df['target_score'].apply(label_from_score)
session_df['decision'] = session_df['final_score'].apply(label_from_score)
question_generation_df['question_family_train'] = question_generation_df['question_family'].replace({'debugging': 'conceptual', 'optimization': 'conceptual'})
banner('DATA QUALITY')
for name, df in [('technical', technical_df), ('personality', personality_df), ('session', session_df), ('question_generation', question_generation_df)]:
    print(name, df.shape); display(df.head(2))


# ## 3. Taxonomy and preprocessing helpers

# In[4]:


EXPERIENCE_BAND_TO_YEAR_RANGE = {'fresher': (0.0, 0.9), 'junior_professional': (1.0, 2.9), 'mid_level_expert': (3.0, 5.9), 'senior_professional': (6.0, 9.9), 'industry_veteran': (10.0, 15.0)}
CANONICAL_TECH_SKILLS = sorted(technical_df['skill_area'].dropna().astype(str).unique().tolist())
USER_APPROVED_JOB_ROLES = ['Data Scientist', 'Java Developer', 'Python Developer', 'React Developer', 'DevOps Engineer', 'SQL Developer', 'Business Analyst', 'Software Developer', 'Full Stack Developer', 'Cloud Engineer', 'Machine Learning Engineer', 'Security Engineer', 'Frontend Developer', 'Backend Developer', 'AI Engineer', 'QA Engineer', 'Database Administrator', 'UI/UX  Developer', 'Mobile App Developer', 'Blockchain Developer', 'Cybersecurity Analyst']
CANONICAL_ROLES = [role for role in USER_APPROVED_JOB_ROLES if role in set(question_generation_df['role'].dropna().astype(str).unique())]
CANONICAL_TRAITS = sorted(personality_df['trait'].dropna().astype(str).unique().tolist())
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
SKILL_NORMALIZATION_MAP = {s: s for s in CANONICAL_TECH_SKILLS}
SKILL_NORMALIZATION_MAP.update({'SQL': 'DBMS', 'Statistics': 'Machine Learning', 'Python': 'Django', 'JavaScript': 'React', 'Spring Boot': 'OOP', 'Selenium': 'Software Engineering', 'Testing': 'Software Engineering', 'Cyber Security': 'Networking'})
TRAIT_NORMALIZATION_MAP = {t: t for t in CANONICAL_TRAITS}

def normalize_role(role):
    role = str(role).strip()
    return ROLE_NORMALIZATION_MAP.get(role, role if role in CANONICAL_ROLES else 'Software Developer')

def normalize_skill(skill):
    skill = str(skill).strip()
    return SKILL_NORMALIZATION_MAP.get(skill, skill if skill in CANONICAL_TECH_SKILLS else 'Software Engineering')

def normalize_trait(trait):
    trait = str(trait).strip()
    return TRAIT_NORMALIZATION_MAP.get(trait, trait if trait in CANONICAL_TRAITS else 'Communication')

def experience_band_from_years(years):
    """Map resume years_experience (ResumeUpload: 1, 3, 5) to interview band."""
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
SKILL_KEYWORDS = {
    'DSA': ['complexity', 'algorithm', 'hash', 'tree', 'graph', 'binary', 'search', 'sort', 'edge case', 'trade-off'],
    'DBMS': ['index', 'query', 'transaction', 'normalization', 'join', 'sql', 'schema', 'locking'],
    'Django': ['model', 'view', 'orm', 'migration', 'middleware', 'serializer', 'rest', 'authentication'],
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
    if not words: return 35.0
    score = 62.0
    score -= sum(8 for phrase in ['not sure', 'maybe', 'i think', 'i guess', "don't know"] if phrase in text.lower())
    score += sum(5 for phrase in ['i would', 'i implemented', 'i designed', 'because', 'therefore'] if phrase in text.lower())
    score += min(15, len(words) // 4)
    return clamp_score(score)

def _communication_heuristic(text):
    words = _tokenize(text)
    if not words: return 40.0
    score = 55.0
    if any(marker in text.lower() for marker in STAR_MARKERS): score += 12
    if len(words) >= 20: score += 10
    if len(words) >= 45: score += 8
    if _filler_ratio(text) > 0.2: score -= 12
    return clamp_score(score)

def extract_technical_features(answer_text, skill_area, question_text='', experience_band='fresher'):
    text = str(answer_text or '').strip()
    words = _tokenize(text)
    skill = normalize_skill(skill_area or 'Software Engineering')
    keywords = SKILL_KEYWORDS.get(skill, SKILL_KEYWORDS['Software Engineering'])
    keyword_hits = _count_keyword_hits(text, keywords)
    overlap = len(set(_tokenize(question_text)) & set(words))
    return {
        'answer_text': text, 'word_count': len(words), 'keyword_hits': keyword_hits,
        'clarity_score': clamp_score(45 + min(35, len(words) // 2) + (8 if '.' in text else 0) - _filler_ratio(text) * 40),
        'relevance_score': clamp_score(40 + overlap * 4 + keyword_hits * 6 + min(20, len(words) // 3)),
        'correctness_score': clamp_score(35 + keyword_hits * 8 + min(25, len(words) // 2) + (10 if any(k in text.lower() for k in ['trade-off', 'complexity', 'edge case']) else 0)),
        'skill_area': skill, 'experience_band': experience_band,
    }

def extract_personality_features(answer_text, trait, experience_band='fresher'):
    text = str(answer_text or '').strip()
    trait_name = normalize_trait(trait or 'Communication')
    keywords = PERSONALITY_KEYWORDS.get(trait_name, PERSONALITY_KEYWORDS['Communication'])
    keyword_hits = _count_keyword_hits(text, keywords)
    star_hits = sum(1 for m in STAR_MARKERS if m in text.lower())
    return {
        'answer_text': text,
        'empathy_score': clamp_score(45 + keyword_hits * 5 + star_hits * 4),
        'structure_score': clamp_score(40 + star_hits * 10 + (12 if 'first' in text.lower() and 'then' in text.lower() else 0)),
        'positivity_score': clamp_score(50 + (8 if any(w in text.lower() for w in ['learned', 'improved', 'successful']) else 0)),
        'ownership_score': clamp_score(45 + (10 if any(w in text.lower() for w in ['i led', 'i owned', 'my responsibility', 'i took']) else 0)),
        'trait': trait_name, 'experience_band': experience_band,
    }

def extract_session_text_metrics(transcripts, avg_answer_seconds=None):
    """Convert backend speech-to-text answers into session-level communication metrics.

    The backend provides the transcript text. This module extracts the answer quality
    scores from that text and also keeps monitoring scores from the backend separate.
    """
    valid_transcripts = [str(t or '').strip() for t in transcripts if str(t or '').strip()]
    joined = ' '.join(valid_transcripts).strip()
    word_counts = [len(_tokenize(t)) for t in valid_transcripts]
    if avg_answer_seconds is None:
        avg_answer_seconds = 60.0 if valid_transcripts else 0.0
    return {
        'communication_score': _communication_heuristic(joined),
        'grammar_score': _grammar_heuristic(joined),
        'confidence_score': _confidence_heuristic(joined),
        'filler_ratio': _filler_ratio(joined),
        'avg_answer_length': round(float(np.mean(word_counts)), 2) if word_counts else 0.0,
        'avg_answer_seconds': float(avg_answer_seconds),
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

def apply_hard_fail_rules(session_input):
    checks = [('camera_available', lambda v: int(v) != 1, 'Camera access was unavailable during the interview.'), ('mic_available', lambda v: int(v) != 1, 'Microphone access was unavailable during the interview.'), ('tab_switches', lambda v: int(v) > 0, 'Interview failed because the candidate switched tabs.'), ('window_blur_events', lambda v: int(v) > 0, 'Interview failed because the interview window lost focus.'), ('screenshot_attempted', lambda v: int(v) > 0, 'Interview failed because a screenshot attempt was detected.'), ('device_detected', lambda v: int(v) > 0, 'Interview failed because an external device was detected.'), ('gaze_off_over_20s', lambda v: int(v) > 0, 'Interview failed because attentiveness was lost for over 20 seconds.'), ('english_only_violation', lambda v: int(v) > 0, 'Interview failed because the response violated the English-only rule.')]
    for field, rule, reason in checks:
        if rule(session_input.get(field, 0 if field not in ['camera_available', 'mic_available'] else 1)):
            return (True, reason)
    return (False, 'No hard-fail rule triggered.')

def _score_status(score):
    score = float(score)
    if score < 45:
        return 'critical'
    if score < 60:
        return 'weak'
    if score < 70:
        return 'borderline'
    if score >= 80:
        return 'strong'
    return 'acceptable'

def _unique_keep_order(items):
    seen, output = (set(), [])
    for item in items:
        if item and item not in seen:
            seen.add(item)
            output.append(item)
    return output

def _candidate_specific_recommendations(result, weak_details):
    """Generate dynamic recommendations from the candidate's actual weak scores and violations."""
    recommendations = []
    technical_skill = result.get('technical_skill_area') or result.get('target_skill_area', 'technical concepts')
    personality_trait = result.get('personality_trait', 'Communication')
    role = result.get('target_role', 'the target role')
    if result.get('hard_fail_triggered'):
        violation_actions = {'tab_switches': 'Do not switch tabs during the next attempt; keep all notes closed and stay on the interview screen.', 'window_blur_events': 'Keep the browser/interview window focused and disable pop-ups or notifications before starting.', 'screenshot_attempted': 'Do not take screenshots during the interview because it is treated as an integrity violation.', 'device_detected': 'Remove external devices or secondary screens before starting the interview.', 'gaze_off_over_20s': 'Practice answering while looking toward the camera and keep your face visible throughout the attempt.', 'english_only_violation': 'Answer fully in English and avoid switching languages during technical and personality answers.', 'camera_available': 'Check camera permission and lighting before starting the next interview.', 'mic_available': 'Check microphone permission and record a short test answer before starting the next interview.'}
        for field, action in violation_actions.items():
            if field in ['camera_available', 'mic_available']:
                if int(result.get(field, 1)) != 1:
                    recommendations.append(action)
            elif int(result.get(field, 0)) > 0:
                recommendations.append(action)
        if not recommendations:
            recommendations.append(result.get('fail_reason', 'Resolve the monitoring violation before the next attempt.'))
    for item in weak_details:
        area = item['area']
        score = item['score']
        status = item['status']
        if area == 'Technical performance':
            if status == 'critical':
                recommendations.append(f'Your {technical_skill} technical score is very low ({score:.0f}/100). Relearn the core concepts, then practice 8-10 role-specific {role} questions with complexity, examples, and edge cases.')
            else:
                recommendations.append(f'Improve {technical_skill} answers by adding the exact concept, a small example, time/space complexity where relevant, and one trade-off.')
        elif area == 'Personality performance':
            recommendations.append(f'Your behavioral/{personality_trait} answers need more structure. Use STAR format and include situation, task, action, result, and what you learned.')
        elif area == 'Communication':
            recommendations.append(f'Communication score is {score:.0f}/100. Give answers in 3 parts: direct answer, short explanation, and example; avoid long unclear sentences.')
        elif area == 'Grammar':
            recommendations.append(f'Grammar score is {score:.0f}/100. Practice simple English interview sentences, correct tense mistakes, and reread answers aloud before mock attempts.')
        elif area == 'Confidence':
            recommendations.append(f'Confidence score is {score:.0f}/100. Record 3 mock answers daily and focus on steady voice, fewer pauses, and clear opening lines.')
        elif area == 'Attentiveness':
            recommendations.append(f'Attentiveness score is {score:.0f}/100. Sit in a quiet place, remove distractions, and keep your face centered on camera.')
        elif area == 'Eye contact':
            recommendations.append(f'Eye-contact score is {score:.0f}/100. Practice looking at the camera while speaking, not at keyboard/phone/side screen.')
        elif area == 'Verbal fluency':
            recommendations.append(f"Filler-word ratio is high ({float(result.get('filler_ratio', 0)):.2f}). Pause silently instead of using fillers and keep answers under 60-90 seconds.")
        elif area == 'Answer timing':
            recommendations.append(f"Average answer time is {float(result.get('avg_answer_seconds', 0)):.0f} seconds. Keep each answer focused with a beginning, middle, and end.")
    if not recommendations and result.get('final_decision') == 'fail':
        recommendations.append('Practice a full mock interview and improve the lowest scoring areas before reattempting.')
    elif not recommendations:
        recommendations.append('Maintain current preparation and keep practicing role-specific questions before real interviews.')
    return _unique_keep_order(recommendations)[:8]

def generate_progress_report(result):
    strong, weak_details = ([], [])
    metric_map = {'Technical performance': result.get('technical_score', 0), 'Personality performance': result.get('personality_score', 0), 'Communication': result.get('communication_score', 0), 'Attentiveness': result.get('attentiveness_score', 0), 'Eye contact': result.get('eye_contact_score', 0), 'Grammar': result.get('grammar_score', 0), 'Confidence': result.get('confidence_score', 0)}
    for area, raw_score in metric_map.items():
        score = float(raw_score)
        status = _score_status(score)
        if status == 'strong':
            strong.append(area)
        if status in ['critical', 'weak']:
            weak_details.append({'area': area, 'score': round(score, 2), 'status': status})
    filler_ratio = float(result.get('filler_ratio', 0))
    if filler_ratio > 0.18:
        weak_details.append({'area': 'Verbal fluency', 'score': round((1 - filler_ratio) * 100, 2), 'status': 'critical' if filler_ratio > 0.28 else 'weak'})
    avg_answer_seconds = float(result.get('avg_answer_seconds', 60))
    if avg_answer_seconds < 20 or avg_answer_seconds > 150:
        weak_details.append({'area': 'Answer timing', 'score': round(avg_answer_seconds, 2), 'status': 'weak'})
    priority = {'critical': 0, 'weak': 1, 'borderline': 2, 'acceptable': 3, 'strong': 4}
    weak_details = sorted(weak_details, key=lambda x: (priority.get(x['status'], 9), x['score']))
    weak_points = [item['area'] for item in weak_details]
    recommendations = _candidate_specific_recommendations(result, weak_details)
    return {'overall_summary': 'The candidate passed the interview.' if result.get('final_decision') == 'pass' else 'The candidate did not meet the interview threshold.', 'strong_points': sorted(set(strong)) or ['Consistent participation'], 'weak_points': _unique_keep_order(weak_points), 'weak_details': weak_details, 'recommendations': recommendations, 'cooldown_days': int(result.get('cooldown_days', 0))}

def generate_improvement_plan(result):
    """Create a fully candidate-specific backend-ready improvement plan."""
    report = result.get('progress_report') or generate_progress_report(result)
    decision = result.get('final_decision', result.get('decision', 'fail'))
    score = float(result.get('final_score', 0))
    cooldown = int(result.get('cooldown_days', 0))
    role = result.get('target_role', 'the target role')
    skill = result.get('technical_skill_area') or result.get('target_skill_area', 'technical concepts')
    recommendations = report.get('recommendations', [])
    weak_details = report.get('weak_details', [])
    if decision == 'pass':
        strengths = ', '.join(report.get('strong_points', []))
        return f'Candidate passed the interview with a final score of {score:.2f}. Main strengths: {strengths}. Next step: keep practicing {role} questions, maintain structured answers, and revise {skill} concepts so the performance remains stable in the backend-integrated interview flow.'
    intro_parts = [f'Candidate failed the interview with a final score of {score:.2f}.', f'Cooldown before reattempt: {cooldown} day(s).']
    if result.get('hard_fail_triggered'):
        intro_parts.append(f"Main failure reason: {result.get('fail_reason')}.")
    if weak_details:
        priority_text = '; '.join([f"{item['area']} ({item['score']:.0f}/100, {item['status']})" for item in weak_details[:5]])
    else:
        priority_text = 'general interview readiness and answer quality'
    plan_steps = []
    weak_areas = {item['area'] for item in weak_details}
    if 'Technical performance' in weak_areas:
        plan_steps.append(f'revise {skill} concepts and solve role-specific {role} questions with examples, edge cases, and trade-offs')
    if 'Personality performance' in weak_areas:
        plan_steps.append('prepare 5 STAR-format behavioral answers covering teamwork, conflict, ownership, stress handling, and learning')
    if 'Communication' in weak_areas or 'Grammar' in weak_areas:
        plan_steps.append('record short English answers, remove grammar mistakes, and keep each answer clear in 3 parts')
    if 'Confidence' in weak_areas or 'Verbal fluency' in weak_areas:
        plan_steps.append('practice aloud daily, reduce filler words, and use short pauses instead of saying um/uh repeatedly')
    if 'Attentiveness' in weak_areas or 'Eye contact' in weak_areas or result.get('hard_fail_triggered'):
        plan_steps.append('set up a quiet room, test camera/microphone, keep face visible, and avoid tab switching or looking away')
    if not plan_steps:
        plan_steps.append('complete two full mock interviews and focus on the lowest scoring metrics from the report')
    rec_text = ' '.join(recommendations) if recommendations else 'Practice weak areas before reattempting.'
    return ' '.join(intro_parts) + f' Priority improvement areas: {priority_text}. ' + 'Personalized improvement plan: ' + '; '.join(plan_steps) + f'. Specific recommendations: {rec_text}'


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

def _score_single_answer(answer, experience_band):
    qtype = answer.get('question_type', 'technical')
    transcript = str(answer.get('transcript', '') or answer.get('answer_text', ''))
    if qtype == 'technical':
        features = extract_technical_features(transcript, answer.get('category', 'Software Engineering'), answer.get('question_text', ''), experience_band)
        return clamp_score(MODELS['technical_score_model'].predict(align_row(features, technical_feature_columns))[0])
    features = extract_personality_features(transcript, answer.get('category', 'Communication'), experience_band)
    return clamp_score(MODELS['personality_score_model'].predict(align_row(features, personality_feature_columns))[0])

def generate_runtime_question(request_input, seed=None):
    normalized = {'role': normalize_role(request_input.get('role', 'Software Developer')), 'experience_band': request_input.get('experience_band', experience_band_from_years(request_input.get('years_experience', 0))), 'years_experience': float(request_input.get('years_experience', 0)), 'focus_area': str(request_input.get('focus_area', 'technical')), 'skill_topic': str(request_input.get('skill_topic', 'Software Engineering')), 'difficulty_level': str(request_input.get('difficulty_level', 'medium'))}
    requested_skill = normalize_skill(normalized['skill_topic']) if normalized['focus_area'] == 'technical' else 'Communication'
    predicted_family = str(MODELS['question_generation_model'].predict(align_row(normalized, question_generation_feature_columns))[0])
    df = question_generation_df.copy()
    filters = [df['role'].eq(normalized['role']), df['experience_band'].eq(normalized['experience_band']), df['focus_area'].eq(normalized['focus_area']), df['difficulty_level'].eq(normalized['difficulty_level'])]
    candidate = df[np.logical_and.reduce(filters)].copy()
    if not candidate.empty and normalized['focus_area'] == 'technical':
        skill_candidate = candidate[candidate['skill_area'].eq(requested_skill)]
        if not skill_candidate.empty: candidate = skill_candidate
    if not candidate.empty:
        family_candidate = candidate[candidate['question_family'].isin(['conceptual', 'debugging', 'optimization'])] if predicted_family == 'conceptual' else candidate[candidate['question_family'].eq(predicted_family)]
        if not family_candidate.empty: candidate = family_candidate
    if candidate.empty: candidate = df[(df['role'].eq(normalized['role'])) & (df['difficulty_level'].eq(normalized['difficulty_level']))].copy()
    if candidate.empty: candidate = df[df['difficulty_level'].eq(normalized['difficulty_level'])].copy()
    if candidate.empty: candidate = df.copy()
    selected = candidate.sample(1, random_state=seed).iloc[0] if seed is not None else candidate.sample(1).iloc[0]
    qtype = 'technical' if selected['focus_area'] == 'technical' else 'personality'
    return {'question_text': str(selected['question_text']), 'question_type': qtype, 'category': str(selected.get('skill_area') if qtype == 'technical' else selected.get('skill_topic', 'Communication')), 'predicted_question_family': predicted_family, 'difficulty_level': str(selected['difficulty_level'])}

def run_full_interview_inference(technical_input, personality_input, session_input, interview_expired=False):
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
    result = {'technical_score': round(technical_score, 2), 'personality_score': round(personality_score, 2), 'technical_skill_area': technical_payload['skill_area'], 'personality_trait': personality_payload['trait'], 'communication_score': float(enriched['communication_score']), 'attentiveness_score': float(enriched['attentiveness_score']), 'eye_contact_score': float(enriched['eye_contact_score']), 'filler_ratio': float(enriched['filler_ratio']), 'grammar_score': float(enriched['grammar_score']), 'confidence_score': float(enriched['confidence_score']), 'tab_switches': int(enriched['tab_switches']), 'window_blur_events': int(enriched['window_blur_events']), 'screenshot_attempted': int(enriched['screenshot_attempted']), 'device_detected': int(enriched['device_detected']), 'gaze_off_over_20s': int(enriched['gaze_off_over_20s']), 'camera_available': int(enriched['camera_available']), 'mic_available': int(enriched['mic_available']), 'english_only_violation': int(enriched['english_only_violation']), 'final_score': round(final_score, 2), 'final_decision': final_decision, 'decision': final_decision, 'passed': final_decision == 'pass', 'hard_fail_triggered': bool(hard_fail), 'fail_reason': fail_reason, 'cooldown_days': cooldown_days, 'target_role': enriched['target_role'], 'target_skill_area': enriched['target_skill_area'], 'experience_years': years, 'experience_band': band}
    result['progress_report'] = generate_progress_report(result)
    result['improvement_plan'] = generate_improvement_plan(result)
    result['full_report_text'] = f"Interview Result: {result['decision'].upper()} | Final Score: {result['final_score']} | Technical: {result['technical_score']} | Personality: {result['personality_score']} | Cooldown: {result['cooldown_days']} day(s). {result['improvement_plan']}"
    return result

def evaluate_interview_session(answers, session_meta, interview_expired=False):
    """Primary Django backend entry point for submit_interview."""
    years = float(session_meta.get('experience_years', 0))
    band = session_meta.get('experience_band', experience_band_from_years(years))
    job_role = normalize_role(session_meta.get('job_role', 'Software Developer'))
    technical_scores, personality_scores, per_question, transcripts = [], [], [], []
    for ans in answers:
        transcript = str(ans.get('transcript', '') or ans.get('answer_text', ''))
        transcripts.append(transcript)
        score = _score_single_answer(ans, band)
        qtype = ans.get('question_type', 'technical')
        per_question.append({'question_type': qtype, 'category': ans.get('category', ''), 'question_text': ans.get('question_text', ''), 'transcript': transcript, 'score': round(score, 2)})
        (technical_scores if qtype == 'technical' else personality_scores).append(score)
    technical_avg = round(sum(technical_scores) / len(technical_scores), 2) if technical_scores else 0.0
    personality_avg = round(sum(personality_scores) / len(personality_scores), 2) if personality_scores else 0.0
    text_metrics = extract_session_text_metrics(transcripts, session_meta.get('avg_answer_seconds'))
    primary_skill = normalize_skill(next((a.get('category') for a in answers if a.get('question_type') == 'technical'), 'Software Engineering'))
    primary_trait = normalize_trait(next((a.get('category') for a in answers if a.get('question_type') == 'personality'), 'Communication'))
    session_input = {'experience_years': years, 'experience_band': band, 'technical_score': technical_avg, 'personality_score': personality_avg, 'target_role': job_role, 'target_skill_area': primary_skill, 'attentiveness_score': session_meta.get('attentiveness_score', 70), 'eye_contact_score': session_meta.get('eye_contact_score', 70), 'tab_switches': session_meta.get('tab_switches', 0), 'window_blur_events': session_meta.get('window_blur_events', 0), 'screenshot_attempted': session_meta.get('screenshot_attempted', 0), 'device_detected': session_meta.get('device_detected', 0), 'gaze_off_over_20s': session_meta.get('gaze_off_over_20s', 0), 'camera_available': session_meta.get('camera_available', 1), 'mic_available': session_meta.get('mic_available', 1), 'english_only_violation': session_meta.get('english_only_violation', 0), **text_metrics}
    tech_answer = next((a for a in answers if a.get('question_type') == 'technical'), {'transcript': '', 'category': primary_skill})
    pers_answer = next((a for a in answers if a.get('question_type') == 'personality'), {'transcript': '', 'category': primary_trait})
    result = run_full_interview_inference(extract_technical_features(tech_answer.get('transcript', ''), tech_answer.get('category', primary_skill), tech_answer.get('question_text', ''), band), extract_personality_features(pers_answer.get('transcript', ''), pers_answer.get('category', primary_trait), band), session_input, interview_expired)
    result['technical_score'], result['personality_score'] = technical_avg, personality_avg
    result['communication_score'] = round(float(session_input['communication_score']), 2)
    result['grammar_score'] = round(float(session_input['grammar_score']), 2)
    result['confidence_score'] = round(float(session_input['confidence_score']), 2)
    result['filler_ratio'] = round(float(session_input['filler_ratio']), 3)
    result['avg_answer_length'] = text_metrics.get('avg_answer_length', 0.0)
    result['avg_answer_seconds'] = text_metrics.get('avg_answer_seconds', 0.0)

    # Final interview score combines the module-calculated answer scores with
    # backend-provided attentiveness/eye-contact monitoring scores.
    if not result['hard_fail_triggered']:
        weighted_score = (
            technical_avg * 0.30
            + personality_avg * 0.20
            + float(session_input['communication_score']) * 0.15
            + float(session_input['grammar_score']) * 0.10
            + float(session_input['confidence_score']) * 0.10
            + float(session_input['attentiveness_score']) * 0.075
            + float(session_input['eye_contact_score']) * 0.075
        )
        filler_penalty = min(10.0, float(session_input['filler_ratio']) * 25.0)
        overall = round(clamp_score(weighted_score - filler_penalty), 2)
        passed = overall >= PASS_MARK
        result.update({
            'final_score': overall,
            'final_decision': 'pass' if passed else 'fail',
            'decision': 'pass' if passed else 'fail',
            'passed': passed,
            'cooldown_days': backend_style_cooldown_days(
                overall, 'pass' if passed else 'fail', False, interview_expired
            ),
        })
    result['progress_report'] = generate_progress_report(result)
    result['improvement_plan'] = generate_improvement_plan(result)
    result['full_report_text'] = f"Interview Result: {result['decision'].upper()} | Final Score: {result['final_score']} | Technical: {result['technical_score']} | Personality: {result['personality_score']} | Cooldown: {result['cooldown_days']} day(s). {result['improvement_plan']}"
    result['per_question_scores'] = per_question
    return result


def generate_interview_questions(job_role, experience_years=0.0, num_questions=6, seed=42):
    """Select interview questions for a candidate using role and experience.

    This function is called by the backend only after the candidate passes the quiz.
    It returns both technical and personality questions.
    """

    band = experience_band_from_years(experience_years)
    role = normalize_role(job_role)
    total_questions = max(2, int(num_questions))
    technical_count = max(1, total_questions // 2)
    personality_count = total_questions - technical_count

    role_skill_map = {
        'Data Scientist': ['Machine Learning', 'DBMS', 'Software Engineering'],
        'Java Developer': ['OOP', 'DBMS', 'Software Engineering'],
        'Python Developer': ['Django', 'DSA', 'DBMS'],
        'React Developer': ['React', 'Software Engineering', 'DSA'],
        'DevOps Engineer': ['DevOps', 'Networking', 'Operating Systems'],
        'SQL Developer': ['DBMS', 'Software Engineering', 'DSA'],
        'Business Analyst': ['Software Engineering', 'DBMS', 'Communication'],
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
        'UI/UX  Developer': ['React', 'Software Engineering', 'Communication'],
        'Mobile App Developer': ['Software Engineering', 'DSA', 'Networking'],
        'Blockchain Developer': ['DSA', 'Networking', 'Software Engineering'],
        'Cybersecurity Analyst': ['Networking', 'Operating Systems', 'Software Engineering'],
    }
    difficulty_by_band = {
        'fresher': ['easy', 'medium'],
        'junior_professional': ['easy', 'medium'],
        'mid_level_expert': ['medium', 'hard'],
        'senior_professional': ['medium', 'hard'],
        'industry_veteran': ['hard', 'medium'],
    }
    technical_skills = [normalize_skill(s) for s in role_skill_map.get(role, ['Software Engineering', 'DSA', 'DBMS'])]
    personality_traits = ['Communication', 'Collaboration', 'Problem solving', 'Stress handling', 'Leadership']
    difficulties = difficulty_by_band.get(band, ['medium'])
    rng = np.random.default_rng(seed)

    questions = []
    for index in range(technical_count):
        question = generate_runtime_question(
            {
                'role': role,
                'experience_band': band,
                'years_experience': experience_years,
                'focus_area': 'technical',
                'skill_topic': technical_skills[index % len(technical_skills)],
                'difficulty_level': difficulties[index % len(difficulties)],
            },
            seed=int(rng.integers(0, 100000)),
        )
        question['role'] = role
        question['experience_years'] = float(experience_years)
        question['experience_band'] = band
        question['order'] = len(questions)
        questions.append(question)

    for index in range(personality_count):
        question = generate_runtime_question(
            {
                'role': role,
                'experience_band': band,
                'years_experience': experience_years,
                'focus_area': 'personality',
                'skill_topic': personality_traits[index % len(personality_traits)],
                'difficulty_level': 'medium',
            },
            seed=int(rng.integers(100000, 200000)),
        )
        question['question_type'] = 'personality'
        question['role'] = role
        question['experience_years'] = float(experience_years)
        question['experience_band'] = band
        question['order'] = len(questions)
        questions.append(question)

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


def start_interview_after_quiz(quiz_passed, job_role, experience_years, num_questions=6, seed=42):
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
    )
    return {
        'can_start_interview': True,
        'stage': 'questions_generated',
        'message': 'Quiz passed. Interview questions generated successfully.',
        'job_role': normalize_role(job_role),
        'experience_years': float(experience_years),
        'experience_band': experience_band_from_years(experience_years),
        'questions': questions,
    }


def run_backend_interview_pipeline(backend_payload):
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



# ## 11. Verification cases

# In[12]:


def attach_transcripts_to_questions(questions, quality='good'):
    """Simulate backend speech-to-text by attaching transcripts to generated questions."""

    transcript_templates = {
        'good_technical': (
            'I explain the concept clearly using correct technical terms. I discuss the practical use case, '
            'steps, constraints, edge cases, complexity, testing, scalability, and trade-offs. I also mention '
            'role-specific keywords like API, database, query, architecture, model, index, transaction, and optimization.'
        ),
        'good_personality': (
            'Situation: the team had unclear requirements. Task: I had to align everyone. Action: I listened, '
            'clarified priorities, communicated updates, supported the team, and took ownership. Result: we delivered '
            'successfully and improved our process.'
        ),
        'medium_technical': (
            'I know the basic concept and can explain the main steps. I can give a simple example, but I need more '
            'practice with deeper trade-offs, edge cases, and optimization.'
        ),
        'medium_personality': (
            'I worked with my team and communicated when needed. I handled the task, but my answer could be more '
            'structured and more specific.'
        ),
        'weak_technical': 'I am not sure. I know a little, but I cannot explain the details clearly.',
        'weak_personality': 'I tried to do it. The answer is short and not structured.',
    }

    answered = []
    for question in questions:
        question_type = question.get('question_type', 'technical')
        transcript_key = f'{quality}_{question_type}'
        answered.append({
            **question,
            'transcript': transcript_templates.get(transcript_key, transcript_templates['medium_technical']),
        })
    return answered


# 1) Quiz failed: backend must block interview and no questions should be generated.
quiz_blocked_payload = run_backend_interview_pipeline(
    {
        'quiz_passed': False,
        'job_role': 'Backend Developer',
        'experience_years': 3.0,
        'num_questions': 6,
    }
)
assert quiz_blocked_payload['can_start_interview'] is False
assert quiz_blocked_payload['stage'] == 'blocked_by_quiz'
assert quiz_blocked_payload['questions'] == []
assert quiz_blocked_payload['interview_result'] is None


# 2) Quiz passed: module must generate technical and personality questions by role + experience.
start_payload = start_interview_after_quiz(
    quiz_passed=True,
    job_role='Backend Developer',
    experience_years=4.5,
    num_questions=6,
    seed=42,
)
assert start_payload['can_start_interview'] is True
assert len(start_payload['questions']) == 6
assert any(q['question_type'] == 'technical' for q in start_payload['questions'])
assert any(q['question_type'] == 'personality' for q in start_payload['questions'])
assert all(q['role'] == 'Backend Developer' for q in start_payload['questions'])


# 3) Good candidate: backend speech-to-text transcripts + monitoring scores should produce pass.
good_answers = attach_transcripts_to_questions(start_payload['questions'], quality='good')
good_backend_payload = {
    'quiz_passed': True,
    'job_role': 'Backend Developer',
    'experience_years': 4.5,
    'num_questions': 6,
    'seed': 42,
    'answers': good_answers,
    'monitoring': {
        'attentiveness_score': 88,
        'eye_contact_score': 84,
        'tab_switches': 0,
        'window_blur_events': 0,
        'screenshot_attempted': 0,
        'device_detected': 0,
        'gaze_off_over_20s': 0,
        'camera_available': 1,
        'mic_available': 1,
        'english_only_violation': 0,
    },
}
good_pipeline_result = run_backend_interview_pipeline(good_backend_payload)
pass_result = good_pipeline_result['interview_result']
assert good_pipeline_result['stage'] == 'completed'
assert pass_result['decision'] == 'pass'
assert len(pass_result['per_question_scores']) == 6
assert isinstance(pass_result['improvement_plan'], str) and len(pass_result['improvement_plan']) > 50


# 4) Weak candidate: weak transcripts and weak monitoring should fail with feedback.
weak_answers = attach_transcripts_to_questions(start_payload['questions'], quality='weak')
weak_payload = {
    **good_backend_payload,
    'answers': weak_answers,
    'monitoring': {
        **good_backend_payload['monitoring'],
        'attentiveness_score': 52,
        'eye_contact_score': 50,
    },
}
weak_result = run_backend_interview_pipeline(weak_payload)['interview_result']
assert weak_result['decision'] == 'fail'
assert len(weak_result['progress_report']['weak_points']) > 0
assert len(weak_result['progress_report']['recommendations']) > 0
assert len(weak_result['improvement_plan']) > 50


# 5) Hard fail: tab switch must override normal score and apply 3-day cooldown.
tab_fail_payload = {
    **good_backend_payload,
    'monitoring': {
        **good_backend_payload['monitoring'],
        'tab_switches': 1,
    },
}
tab_fail_result = run_backend_interview_pipeline(tab_fail_payload)['interview_result']
assert tab_fail_result['hard_fail_triggered'] is True
assert tab_fail_result['decision'] == 'fail'
assert tab_fail_result['cooldown_days'] == 3


verification_summary = pd.DataFrame(
    [
        {
            'case': 'Quiz failed gate',
            'can_start': quiz_blocked_payload['can_start_interview'],
            'decision': 'blocked',
            'final_score': None,
            'cooldown': None,
        },
        {
            'case': 'Quiz passed + generated questions + good transcripts',
            'can_start': True,
            'decision': pass_result['decision'],
            'final_score': pass_result['final_score'],
            'cooldown': pass_result['cooldown_days'],
        },
        {
            'case': 'Weak transcripts + weak attentiveness',
            'can_start': True,
            'decision': weak_result['decision'],
            'final_score': weak_result['final_score'],
            'cooldown': weak_result['cooldown_days'],
        },
        {
            'case': 'Tab switch hard fail',
            'can_start': True,
            'decision': tab_fail_result['decision'],
            'final_score': tab_fail_result['final_score'],
            'cooldown': tab_fail_result['cooldown_days'],
        },
    ]
)
display(verification_summary)
print('Final backend interview flow verification passed.')


# ## 12. Scorecard validation with generated questions
# 
# The backend sends quiz status, job role, years of experience, speech-to-text answers, and attentiveness monitoring scores. The notebook generates questions from the dataset/model flow, evaluates the answer text, combines backend monitoring scores, and displays a final candidate score table with report, recommendations, and improvement plan.

# In[14]:


def build_candidate_scorecard_row(case_name, pipeline_output):
    """Create the final score row that the backend can store/display."""
    result = pipeline_output.get('interview_result') or {}
    return {
        'case_name': case_name,
        'job_role': pipeline_output.get('job_role'),
        'experience_years': pipeline_output.get('experience_years'),
        'technical_score': result.get('technical_score'),
        'personality_score': result.get('personality_score'),
        'communication_score': result.get('communication_score'),
        'attentiveness_score': result.get('attentiveness_score'),
        'eye_contact_score': result.get('eye_contact_score'),
        'filler_ratio': result.get('filler_ratio'),
        'avg_answer_length': result.get('avg_answer_length'),
        'grammar_score': result.get('grammar_score'),
        'confidence_score': result.get('confidence_score'),
        'tab_switches': result.get('tab_switches'),
        'window_blur_events': result.get('window_blur_events'),
        'screenshot_attempted': result.get('screenshot_attempted'),
        'device_detected': result.get('device_detected'),
        'gaze_off_over_20s': result.get('gaze_off_over_20s'),
        'camera_available': result.get('camera_available'),
        'mic_available': result.get('mic_available'),
        'english_only_violation': result.get('english_only_violation'),
        'final_score': result.get('final_score'),
        'decision': result.get('decision'),
        'cooldown_days': result.get('cooldown_days'),
        'weak_areas': ', '.join(result.get('progress_report', {}).get('weak_points', [])),
        'recommendations': ' | '.join(result.get('progress_report', {}).get('recommendations', [])),
        'improvement_plan': result.get('improvement_plan'),
        'full_report_text': result.get('full_report_text'),
    }


def make_transcript(question, quality):
    """Simulate backend speech-to-text text for manual validation cases."""
    qtype = question.get('question_type', 'technical')
    category = question.get('category', 'Software Engineering')
    if quality == 'excellent' and qtype == 'technical':
        return (
            f"I will explain {category} clearly. First I define the concept, then I describe the implementation steps, "
            "then I discuss edge cases, complexity, scalability, testing, and trade-offs. For example, in a backend system "
            "I would validate inputs, design the API or database query, handle errors, monitor performance, and optimize indexes "
            "or algorithms when the data grows. This shows correctness, practical understanding, and maintainability."
        )
    if quality == 'excellent' and qtype == 'personality':
        return (
            "Situation: my team had a deadline with unclear requirements. Task: I needed to keep delivery on track. "
            "Action: I listened to stakeholders, clarified priorities, communicated updates, supported team members, "
            "and took ownership of blockers. Result: we delivered successfully, reduced confusion, and improved our process."
        )
    if quality == 'medium' and qtype == 'technical':
        return (
            f"I understand the basic idea of {category}. I can explain the main purpose and give a simple example. "
            "However, my answer needs more depth about edge cases, complexity, optimization, and trade-offs."
        )
    if quality == 'medium' and qtype == 'personality':
        return (
            "I worked with my team and communicated when needed. I completed my task and helped others, "
            "but I should explain the situation, action, and result more clearly."
        )
    if quality == 'weak' and qtype == 'technical':
        return "I am not sure. I know a little about this topic but I cannot explain the details, example, or correctness clearly."
    if quality == 'weak' and qtype == 'personality':
        return "I tried to do it. It was okay. I do not have a clear example and my answer is short."
    if quality == 'filler_heavy':
        return "um uh like I think basically I am not sure, like maybe it works, you know, kind of, sort of, I guess."
    return "I can answer this with a basic explanation."


def build_backend_payload_for_case(case):
    """Build a realistic backend payload for the full interview pipeline."""
    start = start_interview_after_quiz(
        quiz_passed=case.get('quiz_passed', True),
        job_role=case.get('job_role', 'Backend Developer'),
        experience_years=case.get('experience_years', 3.0),
        num_questions=case.get('num_questions', 6),
        seed=case.get('seed', 42),
    )
    answers = []
    if start['can_start_interview']:
        for question in start['questions']:
            answers.append({
                **question,
                'transcript': make_transcript(question, case.get('answer_quality', 'medium')),
            })
    return {
        'quiz_passed': case.get('quiz_passed', True),
        'job_role': case.get('job_role', 'Backend Developer'),
        'experience_years': case.get('experience_years', 3.0),
        'num_questions': case.get('num_questions', 6),
        'seed': case.get('seed', 42),
        'answers': answers,
        'monitoring': case.get('monitoring', {}),
        'interview_expired': case.get('interview_expired', False),
    }


backend_validation_cases = [
    {
        'case_name': 'Strong backend developer with clean monitoring',
        'job_role': 'Backend Developer',
        'experience_years': 4.0,
        'answer_quality': 'excellent',
        'monitoring': {
            'attentiveness_score': 92, 'eye_contact_score': 88, 'tab_switches': 0,
            'window_blur_events': 0, 'screenshot_attempted': 0, 'device_detected': 0,
            'gaze_off_over_20s': 0, 'camera_available': 1, 'mic_available': 1,
            'english_only_violation': 0, 'avg_answer_seconds': 75,
        },
        'expected_decision': 'pass',
    },
    {
        'case_name': 'Medium candidate with acceptable text but low monitoring',
        'job_role': 'React Developer',
        'experience_years': 2.0,
        'answer_quality': 'medium',
        'monitoring': {
            'attentiveness_score': 58, 'eye_contact_score': 55, 'tab_switches': 0,
            'window_blur_events': 0, 'screenshot_attempted': 0, 'device_detected': 0,
            'gaze_off_over_20s': 0, 'camera_available': 1, 'mic_available': 1,
            'english_only_violation': 0, 'avg_answer_seconds': 50,
        },
        'expected_decision': 'fail',
    },
    {
        'case_name': 'Weak candidate with poor answers',
        'job_role': 'Data Scientist',
        'experience_years': 1.0,
        'answer_quality': 'weak',
        'monitoring': {
            'attentiveness_score': 64, 'eye_contact_score': 61, 'tab_switches': 0,
            'window_blur_events': 0, 'screenshot_attempted': 0, 'device_detected': 0,
            'gaze_off_over_20s': 0, 'camera_available': 1, 'mic_available': 1,
            'english_only_violation': 0, 'avg_answer_seconds': 25,
        },
        'expected_decision': 'fail',
    },
    {
        'case_name': 'Filler-heavy candidate',
        'job_role': 'QA Engineer',
        'experience_years': 0.5,
        'answer_quality': 'filler_heavy',
        'monitoring': {
            'attentiveness_score': 72, 'eye_contact_score': 68, 'tab_switches': 0,
            'window_blur_events': 0, 'screenshot_attempted': 0, 'device_detected': 0,
            'gaze_off_over_20s': 0, 'camera_available': 1, 'mic_available': 1,
            'english_only_violation': 0, 'avg_answer_seconds': 35,
        },
        'expected_decision': 'fail',
    },
    {
        'case_name': 'Hard fail because of tab switch',
        'job_role': 'AI Engineer',
        'experience_years': 5.0,
        'answer_quality': 'excellent',
        'monitoring': {
            'attentiveness_score': 90, 'eye_contact_score': 87, 'tab_switches': 1,
            'window_blur_events': 0, 'screenshot_attempted': 0, 'device_detected': 0,
            'gaze_off_over_20s': 0, 'camera_available': 1, 'mic_available': 1,
            'english_only_violation': 0, 'avg_answer_seconds': 70,
        },
        'expected_decision': 'fail',
        'expected_cooldown': 3,
    },
]

validation_outputs = []
scorecard_rows = []

for case in backend_validation_cases:
    payload = build_backend_payload_for_case(case)
    output = run_backend_interview_pipeline(payload)
    result = output['interview_result']
    assert output['stage'] == 'completed', f"{case['case_name']} did not complete."
    assert result['decision'] == case['expected_decision'], (
        f"{case['case_name']} expected {case['expected_decision']} but got {result['decision']}"
    )
    if 'expected_cooldown' in case:
        assert result['cooldown_days'] == case['expected_cooldown']
    assert isinstance(result['full_report_text'], str) and len(result['full_report_text']) > 80
    assert isinstance(result['improvement_plan'], str) and len(result['improvement_plan']) > 50
    if result['decision'] == 'fail':
        assert len(result['progress_report']['recommendations']) > 0
        assert len(result['progress_report']['weak_points']) > 0 or result['hard_fail_triggered']
    validation_outputs.append(output)
    scorecard_rows.append(build_candidate_scorecard_row(case['case_name'], output))

candidate_scorecard_df = pd.DataFrame(scorecard_rows)
selected_score_columns = [
    'case_name', 'job_role', 'experience_years', 'technical_score', 'personality_score',
    'communication_score', 'attentiveness_score', 'eye_contact_score', 'filler_ratio',
    'avg_answer_length', 'grammar_score', 'confidence_score', 'tab_switches',
    'window_blur_events', 'screenshot_attempted', 'device_detected', 'gaze_off_over_20s',
    'camera_available', 'mic_available', 'english_only_violation', 'final_score',
    'decision', 'cooldown_days', 'weak_areas'
]

banner('BACKEND FULL-FLOW MANUAL VALIDATION')
print('All backend-style candidate cases passed.')
display(candidate_scorecard_df[selected_score_columns])

print('\nSample dynamic reports and improvement plans:')
for row in scorecard_rows:
    print('\n' + '-' * 90)
    print(row['case_name'])
    print('Decision:', row['decision'], '| Final score:', row['final_score'], '| Cooldown:', row['cooldown_days'])
    print('Recommendations:', row['recommendations'])
    print('Improvement plan:', row['improvement_plan'])


# ## 12. Save models, contract, and sample output

# In[15]:


for filename, model in MODELS.items():
    joblib.dump(model, os.path.join(model_dir, f'{filename}.joblib'))

model_contract = {
    'technical_feature_columns': technical_feature_columns,
    'personality_feature_columns': personality_feature_columns,
    'session_feature_columns': session_feature_columns,
    'question_generation_feature_columns': question_generation_feature_columns,
    'pass_mark': PASS_MARK,
    'cooldown_logic': {
        'pass': 0,
        'fail_score_below_50': 3,
        'fail_score_50_to_69': 1,
        'hard_fail': 3,
        'expired_interview': 3,
    },
    'accuracy': {
        'technical': float(technical_accuracy),
        'personality': float(personality_accuracy),
        'final': float(final_accuracy),
        'question_family': float(question_accuracy),
    },
    'backend_integration': {
        'quiz_gate': 'start_interview_after_quiz(quiz_passed, job_role, experience_years, num_questions=6)',
        'start_interview': 'generate_interview_questions(job_role, experience_years, num_questions=6)',
        'submit_interview': 'evaluate_interview_session(answers, session_meta)',
        'full_pipeline': 'run_backend_interview_pipeline(backend_payload)',
        'answer_schema': {
            'question_type': 'technical|personality',
            'category': 'skill or trait',
            'question_text': 'string',
            'transcript': 'backend speech-to-text transcript',
        },
        'session_meta_schema': {
            'job_role': 'string',
            'experience_years': 'float',
            'attentiveness_score': 'float from backend monitoring',
            'eye_contact_score': 'float from backend monitoring',
            'tab_switches': 'int',
            'window_blur_events': 'int',
            'screenshot_attempted': 'int',
            'device_detected': 'int',
            'gaze_off_over_20s': 'int',
            'camera_available': 'int',
            'mic_available': 'int',
            'english_only_violation': 'int',
        },
    },
}

with open(os.path.join(model_dir, 'model_contract.json'), 'w', encoding='utf-8') as f:
    json.dump(model_contract, f, indent=2)

sample_output = {
    'quiz_blocked': quiz_blocked_payload,
    'generated_questions': start_payload['questions'],
    'pass_session': pass_result,
    'weak_session': weak_result,
    'tab_fail_session': tab_fail_result,
}
with open(os.path.join(output_dir, 'sample_interview_module_output.json'), 'w', encoding='utf-8') as f:
    json.dump(sample_output, f, indent=2, default=str)

print('Saved models, backend contract, and sample interview outputs.')
print('Accuracies:', model_contract['accuracy'])


# In[ ]:




