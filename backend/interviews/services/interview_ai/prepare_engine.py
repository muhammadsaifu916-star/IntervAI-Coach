"""Prepare engine.py for Django: fix paths, lazy-load models, drop notebook verification."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
src = (ROOT / "engine_source.py").read_text(encoding="utf-8")

cut = src.index("\n\n# ## 11. Verification cases")
src = src[:cut]

src = src.replace("from IPython.display import display\n", "")
src = src.replace("from pprint import pprint\n", "")
src = src.replace("pd.set_option('display.max_columns', None)\n", "")
src = src.replace("display(df.head(2))", "pass")

src = src.replace(
    "project_root = os.getcwd()\n"
    "dataset_dir = os.path.join(project_root, 'Dataset')\n"
    "model_dir = os.path.join(project_root, 'interview_module_assets', 'trained_models')\n"
    "output_dir = os.path.join(project_root, 'interview_module_assets', 'output')\n"
    "os.makedirs(model_dir, exist_ok=True); os.makedirs(output_dir, exist_ok=True)\n",
    "from pathlib import Path\n\n"
    "BASE_DIR = Path(__file__).resolve().parent\n"
    "dataset_dir = str(BASE_DIR / 'dataset')\n"
    "model_dir = str(BASE_DIR / 'trained_models')\n"
    "output_dir = str(BASE_DIR / 'output')\n"
    "os.makedirs(model_dir, exist_ok=True)\n"
    "os.makedirs(output_dir, exist_ok=True)\n",
)

section2_start = src.index("technical_df = pd.read_csv")
section3_start = src.index("# ## 3. Taxonomy and preprocessing helpers")
section6_start = src.index("# ## 6. Train technical models")
runtime_start = src.index("\nMODELS = {")

prefix = src[:section2_start]
taxonomy_and_features = src[section3_start:section6_start]
training_code = src[section6_start:runtime_start]
runtime_code = src[runtime_start + len("\nMODELS = {"):]
runtime_code = runtime_code[runtime_code.index("'technical_score_model'"):]
runtime_code = runtime_code[runtime_code.index("}\n\n") + 3:]

# Defer dataframe-derived taxonomy globals to bootstrap.
taxonomy_and_features = taxonomy_and_features.replace(
    "CANONICAL_TECH_SKILLS = sorted(technical_df['skill_area'].dropna().astype(str).unique().tolist())\n",
    "CANONICAL_TECH_SKILLS = []\n",
)
taxonomy_and_features = taxonomy_and_features.replace(
    "CANONICAL_ROLES = [role for role in USER_APPROVED_JOB_ROLES if role in set(question_generation_df['role'].dropna().astype(str).unique())]\n",
    "CANONICAL_ROLES = []\n",
)
taxonomy_and_features = taxonomy_and_features.replace(
    "CANONICAL_TRAITS = sorted(personality_df['trait'].dropna().astype(str).unique().tolist())\n",
    "CANONICAL_TRAITS = []\n",
)
taxonomy_and_features = taxonomy_and_features.replace(
    "SKILL_NORMALIZATION_MAP = {s: s for s in CANONICAL_TECH_SKILLS}\n",
    "SKILL_NORMALIZATION_MAP = {}\n",
)
taxonomy_and_features = taxonomy_and_features.replace(
    "TRAIT_NORMALIZATION_MAP = {t: t for t in CANONICAL_TRAITS}\n",
    "TRAIT_NORMALIZATION_MAP = {}\n",
)

lazy_block = '''

_MODELS = None
question_generation_df = None
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
    global question_generation_df, CANONICAL_TECH_SKILLS, CANONICAL_ROLES, CANONICAL_TRAITS
    global SKILL_NORMALIZATION_MAP, TRAIT_NORMALIZATION_MAP
    technical_df = pd.read_csv(os.path.join(dataset_dir, 'technical_interview_dataset.csv'))
    personality_df = pd.read_csv(os.path.join(dataset_dir, 'personality_interview_dataset.csv'))
    session_df = pd.read_csv(os.path.join(dataset_dir, 'interview_session_dataset.csv'))
    question_generation_df = pd.read_csv(os.path.join(dataset_dir, 'interview_question_generation_dataset.csv'))
    personality_df = personality_df.drop_duplicates(subset=['answer_text'], keep='first').reset_index(drop=True)
    question_generation_df['question_family_train'] = question_generation_df['question_family'].replace(
        {'debugging': 'conceptual', 'optimization': 'conceptual'}
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
'''

indented_training = "\n".join(
    ("    " + line if line.strip() else line) for line in training_code.splitlines()
)

post_train = '''
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

'''

for fn in (
    "_score_single_answer",
    "generate_runtime_question",
    "run_full_interview_inference",
    "evaluate_interview_session",
    "generate_interview_questions",
    "start_interview_after_quiz",
    "run_backend_interview_pipeline",
):
    marker = f"def {fn}("
    idx = runtime_code.index(marker)
    close = runtime_code.index("):", idx) + 2
    if runtime_code[close:close + 5].strip().startswith('"""'):
        doc_end = runtime_code.index('"""', close + 3) + 3
        close = doc_end
    runtime_code = runtime_code[:close] + "\n    _require_models()\n" + runtime_code[close + 1:]

engine = (
    '"""AI interview engine for Django backend integration."""\n'
    + prefix
    + taxonomy_and_features
    + lazy_block
    + indented_training
    + post_train
    + runtime_code
)

(ROOT / "engine.py").write_text(engine, encoding="utf-8")
print("Wrote engine.py")
