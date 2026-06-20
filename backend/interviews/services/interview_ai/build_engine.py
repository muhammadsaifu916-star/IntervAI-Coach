"""DEPRECATED one-off builder.

This script used to generate engine.py from engine_source.py. It is now STALE:
the live engine.py has been hand-edited well beyond engine_source.py (reference +
semantic scoring, completion ratio, empty-answer handling, the weighted final-score
formula, instant tab-switch hard fail, etc.). Running this would OVERWRITE engine.py
with the old, inferior engine and silently break scoring.

engine.py is now the source of truth. This builder is disabled on purpose. If you
ever need to regenerate, first port the current engine.py logic back into
engine_source.py, then remove this guard.
"""
import sys
from pathlib import Path

print(
    "build_engine.py is disabled: engine.py is the source of truth and running this "
    "would revert it to an older, broken version. See the module docstring.",
    file=sys.stderr,
)
sys.exit(1)

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "engine_source.py"
OUT = ROOT / "engine.py"

text = SRC.read_text(encoding="utf-8")

# Keep helper + inference code only (stop before verification section).
start = text.index("# ## 2. Load and clean datasets")
end = text.index("# ## 11. Verification cases")
core = text[start:end]

# Remove notebook cell markers and display imports.
for junk in ("# In[2]:\n", "# In[3]:\n", "# In[4]:\n", "# In[5]:\n", "# In[6]:\n",
             "# In[7]:\n", "# In[8]:\n", "# In[9]:\n", "# In[10]:\n", "# In[11]:\n",
             "from IPython.display import display\n"):
    core = core.replace(junk, "")

header = '''"""AI interview inference engine for Django backend integration."""
from __future__ import annotations

import json
import os
import random
import re
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

warnings.filterwarnings("ignore")
random.seed(42)
np.random.seed(42)

BASE_DIR = Path(__file__).resolve().parent
DATASET_DIR = BASE_DIR / "dataset"
MODEL_DIR = BASE_DIR / "trained_models"
OUTPUT_DIR = BASE_DIR / "output"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

'''

# Strip duplicate imports/config from core (section 2 onward).
core = core[core.index("technical_df = pd.read_csv"):]

training_block_end = core.index("MODELS = {")
training_block = core[:training_block_end]
runtime_block = core[training_block_end:]

runtime_block = runtime_block.replace(
    "MODELS = {",
    "_MODELS = None\n"
    "question_generation_df = None\n"
    "technical_feature_columns = None\n"
    "personality_feature_columns = None\n"
    "session_feature_columns = None\n"
    "question_generation_feature_columns = None\n\n"
    "def _model_files_ready():\n"
    "    names = [\n"
    "        'technical_score_model.joblib', 'technical_label_model.joblib',\n"
    "        'personality_score_model.joblib', 'personality_label_model.joblib',\n"
    "        'final_score_model.joblib', 'final_label_model.joblib',\n"
    "        'question_generation_model.joblib',\n"
    "    ]\n"
    "    return all((MODEL_DIR / n).exists() for n in names)\n\n"
    "def _load_dataframes():\n"
    "    global question_generation_df\n"
    "    technical_df = pd.read_csv(DATASET_DIR / 'technical_interview_dataset.csv')\n"
    "    personality_df = pd.read_csv(DATASET_DIR / 'personality_interview_dataset.csv')\n"
    "    session_df = pd.read_csv(DATASET_DIR / 'interview_session_dataset.csv')\n"
    "    question_generation_df = pd.read_csv(DATASET_DIR / 'interview_question_generation_dataset.csv')\n"
    "    personality_df = personality_df.drop_duplicates(subset=['answer_text'], keep='first').reset_index(drop=True)\n"
    "    technical_df['target_label'] = technical_df['target_score'].apply(label_from_score)\n"
    "    personality_df['target_label'] = personality_df['target_score'].apply(label_from_score)\n"
    "    session_df['decision'] = session_df['final_score'].apply(label_from_score)\n"
    "    question_generation_df['question_family_train'] = question_generation_df['question_family'].replace(\n"
    "        {'debugging': 'conceptual', 'optimization': 'conceptual'}\n"
    "    )\n"
    "    return technical_df, personality_df, session_df, question_generation_df\n\n"
    "def train_and_save_models():\n"
    "    global _MODELS, technical_feature_columns, personality_feature_columns\n"
    "    global session_feature_columns, question_generation_feature_columns, question_generation_df\n"
    "    technical_df, personality_df, session_df, question_generation_df = _load_dataframes()\n",
    1,
)

# Indent original eager training code inside train_and_save_models.
indented_training = "\n".join(
    ("    " + line if line.strip() else line) for line in training_block.splitlines()
)
# training_block started with technical_df load - already in _load_dataframes, skip first 14 lines
indented_training = "\n".join(indented_training.splitlines()[14:])

save_models_tail = '''
    for filename, model in _MODELS.items():
        joblib.dump(model, MODEL_DIR / f"{filename}.joblib")

    contract = {
        "technical_feature_columns": technical_feature_columns,
        "personality_feature_columns": personality_feature_columns,
        "session_feature_columns": session_feature_columns,
        "question_generation_feature_columns": question_generation_feature_columns,
        "pass_mark": PASS_MARK,
    }
    with open(MODEL_DIR / "model_contract.json", "w", encoding="utf-8") as f:
        json.dump(contract, f, indent=2)


def ensure_models_loaded():
    global _MODELS, technical_feature_columns, personality_feature_columns
    global session_feature_columns, question_generation_feature_columns, question_generation_df
    if _MODELS is not None:
        return
    if not _model_files_ready():
        train_and_save_models()
        return
    with open(MODEL_DIR / "model_contract.json", encoding="utf-8") as f:
        contract = json.load(f)
    technical_feature_columns = contract["technical_feature_columns"]
    personality_feature_columns = contract["personality_feature_columns"]
    session_feature_columns = contract["session_feature_columns"]
    question_generation_feature_columns = contract["question_generation_feature_columns"]
    _MODELS = {
        name: joblib.load(MODEL_DIR / f"{name}.joblib")
        for name in [
            "technical_score_model", "technical_label_model",
            "personality_score_model", "personality_label_model",
            "final_score_model", "final_label_model", "question_generation_model",
        ]
    }
    _load_dataframes()


def _models():
    ensure_models_loaded()
    return _MODELS

'''

runtime_block = runtime_block.replace("MODELS[", "_models()[")
runtime_block = runtime_block.replace(
    "MODELS = {\n    'technical_score_model': technical_score_model,",
    "    _MODELS = {\n        'technical_score_model': technical_score_model,",
)
runtime_block = runtime_block.replace(
    "    'question_generation_model': question_generation_model,\n}",
    "        'question_generation_model': question_generation_model,\n    }",
)

# Need helper functions from section 1 before dataset load
helpers_start = text.index("def banner(title):")
helpers_end = text.index("# ## 2. Load and clean datasets")
helpers = text[helpers_start:helpers_end]
for junk in ("# In[2]:\n", "from IPython.display import display\n"):
    helpers = helpers.replace(junk, "")
helpers = helpers.replace("project_root = os.getcwd()", "")
helpers = helpers.replace("dataset_dir = os.path.join(project_root, 'Dataset')", "")
helpers = helpers.replace(
    "model_dir = os.path.join(project_root, 'interview_module_assets', 'trained_models')",
    "",
)
helpers = helpers.replace(
    "output_dir = os.path.join(project_root, 'interview_module_assets', 'output')",
    "",
)
helpers = helpers.replace("os.makedirs(model_dir, exist_ok=True); os.makedirs(output_dir, exist_ok=True)", "")

# Also need taxonomy section (section 3) which is between dataset load and section 4
taxonomy_start = text.index("# ## 3. Taxonomy and preprocessing helpers")
taxonomy_end = text.index("# ## 4. Transcript feature extraction")
taxonomy = text[taxonomy_start:taxonomy_end]
for junk in ("# In[4]:\n",):
    taxonomy = taxonomy.replace(junk, "")
taxonomy = taxonomy.split("\n", 1)[1]  # drop header comment line

features_start = text.index("# ## 4. Transcript feature extraction")
features_end = text.index("# ## 5. Cooldown rules and dynamic feedback")
features = text[features_start:features_end].split("\n", 1)[1]

cooldown_start = text.index("# ## 5. Cooldown rules and dynamic feedback")
cooldown_end = text.index("# ## 6. Train technical models")
cooldown = text[cooldown_start:cooldown_end].split("\n", 1)[1]

engine = (
    header
    + helpers
    + "\n"
    + taxonomy
    + "\n"
    + features
    + "\n"
    + cooldown
    + "\n"
    + "def train_and_save_models():\n"
    + "    global _MODELS, technical_feature_columns, personality_feature_columns\n"
    + "    global session_feature_columns, question_generation_feature_columns, question_generation_df\n"
    + "    technical_df, personality_df, session_df, question_generation_df = _load_dataframes()\n"
    + indented_training
    + save_models_tail
    + runtime_block
)

OUT.write_text(engine, encoding="utf-8")
print(f"Wrote {OUT} ({len(engine)} chars)")
