from __future__ import annotations

import json
import logging
import re
import warnings
from pathlib import Path
from typing import Any, Dict, Optional

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)

import joblib
import numpy as np
import pdfplumber
import pytesseract
from PIL import Image

try:
    import fitz  # PyMuPDF, used by OCR fallback
except Exception:  # pragma: no cover
    fitz = None

try:
    import nltk
    from nltk.corpus import stopwords
    nltk.download("stopwords", quiet=True)
    STOP_WORDS = set(stopwords.words("english"))
except Exception:
    STOP_WORDS = set()
 
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
except Exception:
    nlp = None

try:
    import language_tool_python
except Exception:
    language_tool_python = None

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"


def _load_model_file(filename: str):
    path = MODEL_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Missing resume AI model file: {path}. "
            "Place vectorizer.pkl, best_model.pkl, and lr_model.pkl inside "
            "backend/resumes/services/resume_ai/models/."
        )
    return joblib.load(path)


# Loaded once when Django imports this module.
vectorizer = _load_model_file("vectorizer.pkl")
best_model = _load_model_file("best_model.pkl")
lr_for_explain = _load_model_file("lr_model.pkl")

def fix_pdf_artifacts(text):
    """
    Stage 1: Fix structural PDF extraction problems.
    
    This is applied to raw extracted text BEFORE any analysis.
    Preserves newlines and structure for section/bullet detection.
    """
    text = text.replace('\uf0b7', '\n• ')
    text = text.replace('\uf0b2', '\n• ')   
    text = text.replace('\u25cf', '\n• ')
    text = re.sub(r'([a-z]{3,})([A-Z])', r'\1 \2', text)
    
    text = re.sub(r'([A-Z]{2,})([A-Z][a-z])', r'\1 \2', text)
    
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
    text = re.sub(r'\u200b|\u200c|\u200d|\ufeff', '', text) 
    
    text = re.sub(r'[ \t]{2,}', ' ', text)
    
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


def clean_text(text):
    """
    Stage 2: Normalize text for TF-IDF / ML classifier input.
    Strips everything except letters and spaces, then lowercases.
    """
    text = fix_pdf_artifacts(text)
    text = re.sub(r'https?://\S+|www\.\S+', ' ', text)       # URLs
    text = re.sub(r'\S+@\S+\.\S+', ' ', text)                # emails
    text = re.sub(r'\+?\d[\d\s\-\.()]{7,}\d', ' ', text)     # phonesresumes
    text = re.sub(r'[^a-zA-Z\s]', ' ', text)                 # keep letters
    text = text.lower()
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def preprocess_text(text):
    """
    Stage 3: Deeper clean — removes stopwords for NLP similarity tasks.
    """
    text = clean_text(text)
    tokens = [w for w in text.split() if w not in STOP_WORDS and len(w) > 2]
    return ' '.join(tokens)




def _extract_pdf_link_uris(pdf_path):
    """
    Extract real hyperlink targets from PDF annotations.

    Some resume templates show generic visible text such as "LinkedIn" or
    "linkedin.com/in/username" while the real clickable URL is stored in a PDF
    annotation. Text extraction alone misses that real URL.
    """
    urls = []

    def _add(uri):
        if not uri:
            return
        uri = str(uri).strip().rstrip('.,);]}>')
        if not uri:
            return
        low = uri.lower()
        if low.startswith(('mailto:', 'tel:')):
            return
        if low.startswith(('http://', 'https://', 'www.')) and uri not in urls:
            urls.append(uri)

    if fitz is not None:
        try:
            doc = fitz.open(pdf_path)
            for page in doc:
                for link in page.get_links() or []:
                    _add(link.get('uri'))
            doc.close()
        except Exception:
            pass

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                for ann in getattr(page, 'annots', []) or []:
                    data = ann.get('data', ann)
                    uri = None
                    if isinstance(data, dict):
                        uri = data.get('URI') or data.get('uri')
                        action = data.get('A') or data.get('a')
                        if isinstance(action, dict):
                            uri = uri or action.get('URI') or action.get('uri')
                    _add(uri)
    except Exception:
        pass

    return urls

def extract_text(pdf_path):
    """
    Extracts and normalizes text from a PDF resume.

    v21 — gap-aware text extraction + PDF hyperlink annotation extraction.
    The annotation pass lets the pipeline read the real LinkedIn/GitHub URL
    when the visible PDF text is only a label or placeholder.

    Returns: cleaned str, or 'ERROR: ...' on failure.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages = [_extract_page_gap_aware(p) for p in pdf.pages]
        raw = '\n\n'.join(pages)

        # Put annotation URLs first so the real clickable link wins over
        # visible placeholders such as linkedin.com/in/username.
        link_uris = _extract_pdf_link_uris(pdf_path)
        if link_uris:
            raw = '\n'.join(link_uris) + '\n\n' + raw

        # OCR fallback for scanned PDFs
        if len(raw.strip()) < 100:
            print('      ⚠️  Little text extracted — trying OCR...')
            raw = _ocr_fallback(pdf_path)

        return fix_pdf_artifacts(raw)

    except FileNotFoundError:
        return f'ERROR: File not found — {pdf_path}'
    except Exception as e:
        return f'ERROR: {e}'



# common section headings — used to detect a genuine 2nd column (self-contained)
_COL_HEADINGS = ('summary','about me','about','objective','profile','who am i','who i am',
    'experience','work experience','professional experience','employment','education',
    'skills','technical skills','projects','project','personal projects','certifications',
    'achievements','key achievements','awards','interests','languages','references',
    'publications','volunteer','leadership','portfolio','contact','core competencies')

def _looks_heading(text):
    s = re.sub(r'[^a-z ]', ' ', text.lower()); s = re.sub(r'\s+', ' ', s).strip()
    if not s or len(s) > 32:
        return False
    return any(s == h or s.startswith(h + ' ') for h in _COL_HEADINGS)


def _extract_page_gap_aware(page, gap_threshold=25):
    """
    v20 — column-aware extraction.

    • Single-column resumes (and sidebar layouts where the section HEADINGS live
      in a narrow left rail) are read exactly as before — row by row — so grammar
      and scoring are completely unaffected.
    • TRUE two-column bodies (Enhancv/Canva templates where each column has its
      OWN heading, e.g. SUMMARY on the left and KEY ACHIEVEMENTS / PROJECTS on the
      right) are de-interleaved: the header stays on top, then the left column is
      read fully, then the right column. This stops side-by-side sections from
      being stitched together line-by-line.
    """
    words = page.extract_words(x_tolerance=2, y_tolerance=3, keep_blank_chars=False)
    if not words:
        return page.extract_text(x_tolerance=2) or ''

    rows = {}
    for w in words:
        rows.setdefault(round(w['top'] / 3) * 3, []).append(w)

    # group each row into segments, splitting at large horizontal gaps
    segs = []
    for y in sorted(rows):
        ws = sorted(rows[y], key=lambda w: w['x0']); grp = [ws[0]]
        for i in range(1, len(ws)):
            if ws[i]['x0'] - ws[i-1]['x1'] > gap_threshold:
                segs.append({'top': y, 'x0': min(w['x0'] for w in grp), 'x1': max(w['x1'] for w in grp),
                             'text': ' '.join(w['text'] for w in grp)}); grp = [ws[i]]
            else:
                grp.append(ws[i])
        segs.append({'top': y, 'x0': min(w['x0'] for w in grp), 'x1': max(w['x1'] for w in grp),
                     'text': ' '.join(w['text'] for w in grp)})

    def emit_rows(group):                       # original behaviour: each segment on its own line
        out = []
        for y in sorted(set(s['top'] for s in group)):
            for s in sorted([s for s in group if s['top'] == y], key=lambda s: s['x0']):
                out.append(s['text'])
        return out

    # estimate the gutter from the consistent left-edge of the 2nd segment in split rows
    rstarts = []
    for y in sorted(rows):
        rs = sorted([s for s in segs if s['top'] == y], key=lambda s: s['x0'])
        for a, b in zip(rs, rs[1:]):
            if b['x0'] - a['x1'] > gap_threshold:
                rstarts.append(b['x0'])

    split_x = None
    if rstarts:
        counts = {}
        for x in rstarts:
            k = round(x / 12) * 12
            counts[k] = counts.get(k, 0) + 1
        cx = max(counts, key=counts.get)
        if counts[cx] >= 3:
            near = [x for x in rstarts if abs(x - cx) <= 18]
            split_x = sum(near) / len(near) - gap_threshold / 2

    if split_x is None:
        return '\n'.join(emit_rows(segs))       # single column

    def spans(s):                               # full-width line crossing the gutter
        return s['x0'] < split_x - 50 and s['x1'] > split_x + 15

    left  = [s for s in segs if not spans(s) and (s['x0'] + s['x1']) / 2 <  split_x]
    right = [s for s in segs if not spans(s) and (s['x0'] + s['x1']) / 2 >= split_x]
    R = sum(len(s['text']) for s in right)

    # reorder ONLY when both columns carry their own heading + the right has real text
    both_have_headings = any(_looks_heading(s['text']) for s in left) and \
                         any(_looks_heading(s['text']) for s in right)
    if not (both_have_headings and R >= 150):
        return '\n'.join(emit_rows(segs))        # sidebar/date layouts -> unchanged

    mixed = [y for y in sorted(rows)
             if any(not spans(s) and (s['x0']+s['x1'])/2 <  split_x for s in segs if s['top'] == y)
             and any(not spans(s) and (s['x0']+s['x1'])/2 >= split_x for s in segs if s['top'] == y)]
    y_body = min(mixed) if mixed else min(rows)

    def lines_merged(group):                    # merge same-row pieces within one column
        byrow = {}
        for s in group:
            byrow.setdefault(s['top'], []).append(s)
        return [' '.join(x['text'] for x in sorted(byrow[y], key=lambda s: s['x0'])) for y in sorted(byrow)]

    header = [s for s in segs if s['top'] <  y_body]
    bodyL  = [s for s in segs if s['top'] >= y_body and (spans(s) or (s['x0']+s['x1'])/2 <  split_x)]
    bodyR  = [s for s in segs if s['top'] >= y_body and not spans(s) and (s['x0']+s['x1'])/2 >= split_x]
    return '\n'.join(lines_merged(header) + lines_merged(bodyL) + lines_merged(bodyR))

def _ocr_fallback(pdf_path):
    """OCR fallback using pytesseract on page images."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        texts = []
        for page in doc:
            pix  = page.get_pixmap(dpi=200)
            img  = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
            texts.append(pytesseract.image_to_string(img, lang='eng'))
        return '\n'.join(texts)
    except Exception:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                texts = [
                    pytesseract.image_to_string(
                        page.to_image(resolution=200).original, lang='eng'
                    )
                    for page in pdf.pages
                ]
            return '\n'.join(texts)
        except Exception as e2:
            return f'OCR failed: {e2}'




# ## 🏷️ Section 8 — Role Classification
# 
# `classify_resume()` returns:
# - **Predicted role** (the top-1 ML prediction)
# - **Top 3 roles** (for display purposes only)
# - **Top influencing keywords** (from LR coefficients)
# 
# > Confidence percentage is computed internally for quiz eligibility logic  
# > but is **NOT shown in the final output** to avoid user confusion.


_KEYWORD_STRONG_SIGNALS = {
    


'Cybersecurity Analyst': [
    'cyber security analyst', 'cybersecurity analyst', 'soc analyst',
    'information security analyst', 'security operations center analyst',
    'cyber threat analyst', 'malware analyst', 'incident response analyst',
],
 'Security Engineer': [
    'network security engineer', 'network security analyst',
    'network security specialist', 'firewall engineer',
    'network administrator', 'cisco network engineer', 'network engineer',
    'network infrastructure engineer',
    'information security engineer', 'cybersecurity engineer',
],



    'Cloud Engineer': [
        'cloud engineer', 'cloud architect', 'aws engineer', 'azure engineer',
        'gcp engineer', 'cloud infrastructure engineer',
        'aws solutions architect', 'azure solutions architect',
        'cloud solutions architect',
    ],

    'UI/UX Developer': [
        'ui/ux developer', 'ui developer','ui ux developer', 'ux designer',
        'ui/ux designer', 'user experience designer','frontend technologies','fron-tend technologies','product designer',
        'interaction designer', 'ux developer', 'ux researcher',
    ],

    'Blockchain Developer': [
        'blockchain developer', 'blockchain engineer', 'smart contract developer',
        'solidity developer', 'web3 developer', 'ethereum developer',
        'cryptocurrency developer', 'dapp developer',
    ],
    'Database Administrator': [
        'database administrator', 'dba', 'oracle dba', 'sql server dba',
        'mysql dba', 'database engineer', 'database manager',
        'database reliability engineer',
    ],
    'SQL Developer': [
        'sql developer', 'pl/sql developer', 'plsql developer',
        'sql server developer', 't-sql developer', 'oracle sql developer',
        'database developer',
    ],
    'QA Engineer': [
        'qa engineer', 'quality assurance engineer', 'test engineer',
        'software tester', 'automation test engineer', 'qa automation engineer',
        'sdet', 'software development engineer in test',
        'quality engineer', 'qa analyst',
    ],
    'Business Analyst': [
        'business analyst', 'business systems analyst', 'it business analyst',
        'functional analyst', 'business intelligence analyst',
        'systems analyst', 'ba analyst', 'business process analyst',
    ],
    'Java Developer': [
        'java developer', 'java engineer', 'j2ee developer',
        'java software engineer', 'java backend developer',
        'spring developer', 'java full stack developer',
    ],
    'Python Developer': [
        'python developer', 'python engineer', 'python software engineer',
        'python backend developer', 'django developer', 'flask developer',
        'fastapi developer',
    ],

    'Full Stack Developer': [
        'mern stack', 'mean stack', 'mern developer', 'mean developer',
        'full stack developer', 'fullstack developer', 'full-stack developer',
    ],

    
    'Mobile App Developer': [
        'mobile application developer', 'android developer', 'ios developer',
        'flutter developer', 'react native developer', 'swift developer',
        'kotlin developer', 'mobile app developer',
    ],
    'Data Scientist': [
        'data scientist', 'data science engineer', 'machine learning researcher',
        'ai researcher', 'nlp researcher',
    ],
    'AI Engineer': [
        'ai engineer', 'generative ai engineer', 'llm engineer',
        'artificial intelligence engineer',
    ],
    'DevOps Engineer': [
        'devops engineer', 'site reliability engineer', 'platform engineer',
        'infrastructure engineer',
    ],
    'Frontend Developer': [
        'front-end developer', 'frontend developer', 'front end developer',
        
    ],
    'Backend Developer': [
        'backend developer', 'back-end developer', 'back end developer',
        'server-side developer',
    ],
    'React Developer': [
        'react developer','react full stack developer', 'reactjs developer',
    ],
    'Machine Learning Engineer': [
        'machine learning engineer', 'ml engineer', 'mlops engineer',
    ],
    'Software Developer': [
        'software developer', 'software engineer', 'application developer',
        'software development engineer',
    ],
}

_KEYWORD_MODERATE_SIGNALS = {
    'Full Stack Developer':      ['mern', 'react', 'node', 'express', 'mongodb', 'angular', 'vue'],
    'Mobile App Developer':      ['swift', 'kotlin', 'flutter', 'react native', 'android', 'ios', 'xcode', 'firebase'],
    'Data Scientist':            ['pandas', 'numpy', 'scikit', 'tensorflow', 'pytorch', 'statistics', 'data analysis', 'jupyter'],
    'DevOps Engineer':           ['docker', 'kubernetes', 'jenkins', 'ansible', 'terraform', 'ci/cd', 'monitoring'],
    'Frontend Developer':        ['html', 'css', 'javascript', 'typescript', 'react', 'angular', 'vue', 'webpack', 'sass', 'ui developer'],
    'Backend Developer':         ['api', 'rest', 'microservices', 'postgresql', 'redis', 'kafka', 'spring boot', 'django', 'fastapi'],
    'AI Engineer':               ['llm', 'bert', 'transformer', 'fine-tuning', 'rag', 'langchain', 'openai'],
    'Machine Learning Engineer': ['mlops', 'model deployment', 'feature engineering', 'model training', 'xgboost', 'sklearn'],
    'React Developer':           ['react', 'react full stack developer','redux', 'next.js', 'jsx', 'hooks', 'react router'],
    'Java Developer':            ['java', 'spring', 'hibernate', 'maven', 'gradle', 'jvm', 'j2ee', 'junit', 'spring boot', 'tomcat'],
    'Python Developer':          ['python', 'django', 'flask', 'fastapi', 'pip', 'pytest', 'celery', 'sqlalchemy'],
    'SQL Developer':             ['sql', 'pl/sql', 'stored procedures', 'oracle', 't-sql', 'sql server', 'views', 'triggers', 'query optimization'],
    'Business Analyst':          ['requirements', 'stakeholders', 'business requirements', 'process mapping', 'user stories', 'gap analysis', 'uml', 'agile'],
    'Software Developer':        ['software development', 'agile', 'scrum', 'git', 'sdlc', 'oop', 'design patterns', 'unit testing'],
    'Cloud Engineer':            ['aws', 'azure', 'gcp', 'cloud', 'terraform', 'cloudformation', 'eks', 'aks', 'lambda', 's3'],
    'Security Engineer':         ['firewall', 'networking', 'cisco', 'ccna', 'vpn', 'ids', 'ips', 'network monitoring', 'packet analysis', 'wireshark'],
    'Cyber Security Analyst':    ['soc', 'siem', 'threat analysis', 'incident response', 'penetration testing', 'malware', 'vulnerability assessment', 'ethical hacking'],
    'QA Engineer':               ['selenium', 'test automation', 'junit', 'testng', 'cypress', 'jira', 'test cases', 'api testing', 'bug tracking'],
    'Database Administrator':    ['database administration', 'backup', 'recovery', 'performance tuning', 'oracle', 'sql server', 'replication', 'data migration'],
    'UI/UX Developer':           ['figma','UI Developer', 'adobe xd', 'sketch', 'prototyping', 'frontend technologies','front-end technologies','wireframing', 'user research', 'usability testing', 'design systems', 'ux'],
    'Blockchain Developer':      ['solidity', 'ethereum', 'smart contracts', 'web3', 'defi', 'nft', 'hyperledger', 'blockchain'],
}

def _best_strong_signal_match(text_region):
    
    best_role, best_signal = None, None
    best_pos, best_len = None, -1
    for role, signals in _KEYWORD_STRONG_SIGNALS.items():
        for signal in signals:
            m = re.search(r'\b' + re.escape(signal) + r'\b', text_region)
            if m:
                pos = m.start()
                if best_pos is None or pos < best_pos or (pos == best_pos and len(signal) > best_len):
                    best_role, best_signal = role, signal
                    best_pos, best_len = pos, len(signal)
    return best_role, best_signal


def _keyword_role_override(raw_text, confidence, ml_role):
    
    text   = raw_text.lower()
    header = text[:500]

    role, _ = _best_strong_signal_match(header)
    if role is not None:
        return role

    if confidence >= 65:
        return ml_role

    role, _ = _best_strong_signal_match(text)
    if role is not None:
        return role

    if confidence < 50:
        scores = {
            r: sum(1 for kw in kws if kw in text)
            for r, kws in _KEYWORD_MODERATE_SIGNALS.items()
        }
        best_role = max(scores, key=scores.get)
        if scores[best_role] >= 3:
            return best_role

    return ml_role
def classify_resume(raw_text):

    cleaned = clean_text(raw_text)
    vec     = vectorizer.transform([cleaned])

    predicted_role = best_model.predict(vec)[0]
    proba          = best_model.predict_proba(vec)[0]
    classes        = best_model.classes_

    _confidence_val = float(round(max(proba) * 100, 1))   # noqa: F841

    predicted_role = _keyword_role_override(raw_text, _confidence_val, predicted_role)

    top3_idx = np.argsort(proba)[::-1][:3]
    top3 = [
        {'role': classes[i], 'rank': rank + 1}
        for rank, i in enumerate(top3_idx)
    ]

    top_kws = []
    try:
        feat_names = vectorizer.get_feature_names_out()
        class_list = list(lr_for_explain.classes_)
        explain_role = best_model.predict(vec)[0]
        if explain_role in class_list:
            idx    = class_list.index(explain_role)
            coefs  = lr_for_explain.coef_[idx]
            nz     = vec.nonzero()[1]
            scored = sorted(
                [(feat_names[i], float(coefs[i] * vec[0, i])) for i in nz],
                key=lambda x: x[1], reverse=True
            )
            top_kws = [
                {'word': w, 'score': round(s, 3)}
                for w, s in scored[:10] if s > 0
            ]
    except Exception:
        pass

    return {
        'predicted_role':    predicted_role,
        'top_3_predictions': top3,
        'top_keywords':      top_kws,
    }




# ## 🔍 Section 9 — CV Validation
# 
# Two checks before any analysis:
# 
# 1. **Is it a CV?** — Must contain ≥2 resume section keywords  
# 2. **Is it a tech CV?** — Must contain ≥3 tech keywords  
# 
# If check 2 fails → return:  
# > *"This platform currently supports technical resumes only. Please upload a tech-related CV."*


CV_SECTION_KEYWORDS = [
    'experience', 'education', 'skills', 'projects', 'summary',
    'objective', 'certifications', 'internship', 'work history',
    'achievements', 'profile', 'about me', 'about', 'publications',
    'awards', 'languages', 'leadership', 'volunteer'
]

# TECH_KEYWORDS = [
#     # ── Programming Languages ──────────────────────────────────────────────
#     'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'golang',
#     'kotlin', 'swift', 'scala', 'php', 'ruby', 'dart', 'rust',

#     # ── Web / Frontend Frameworks ──────────────────────────────────────────
#     'html', 'css', 'react', 'angular', 'vue', 'node', 'express',
#     'django', 'flask', 'spring', 'laravel', 'next.js', 'graphql',
#     'webpack', 'tailwind', 'sass',

#     # ── AI / ML / Data ─────────────────────────────────────────────────────
#     'machine learning', 'deep learning', 'tensorflow', 'pytorch', 'keras',
#     'scikit', 'pandas', 'numpy', 'data science', 'nlp', 'neural network',
#     'llm', 'computer vision', 'jupyter', 'matplotlib','data analysis','AI/ML',

#     # ── Databases ──────────────────────────────────────────────────────────
#     'sql', 'mysql', 'postgresql', 'mongodb', 'redis', 'sqlite',
#     'database administration', 'nosql', 'elasticsearch', 'cassandra',

#     # ── DevOps / Cloud / Infrastructure ────────────────────────────────────
#     'docker', 'kubernetes', 'aws', 'azure', 'gcp', 'linux',
#     'git', 'ci/cd', 'jenkins', 'terraform', 'ansible', 'devops',
#     'github', 'gitlab', 'bitbucket', 'bash', 'shell scripting',

#     # ── Mobile ─────────────────────────────────────────────────────────────
#     'android development', 'ios development', 'flutter', 'react native',
#     'mobile app development', 'mobile application development',
#     'swift development', 'kotlin development',

#     # ── Security ───────────────────────────────────────────────────────────
#     'cybersecurity', 'penetration testing', 'ethical hacking',
#     'network security', 'network engineer', 'network infrastructure',
#     'firewall configuration', 'ids/ips', 'siem',
#     'vulnerability assessment', 'malware analysis', 'threat analysis',
#     'cisco', 'ccna', 'ccnp', 'tcp/ip', 'vpn configuration',

#     # ── UI/UX ──────────────────────────────────────────────────────────────
#     'ui/ux', 'ux designer', 'ui designer', 'ux developer', 'ui developer',
#     'figma', 'adobe xd', 'prototyping', 'wireframing', 'usability testing',

#     # ── Blockchain ─────────────────────────────────────────────────────────
#     'blockchain', 'solidity', 'smart contracts', 'web3', 'ethereum',

#     # ── Software Engineering Concepts ──────────────────────────────────────
#     # NOTE: only kept terms specific enough to indicate a tech background.
#     # Removed: 'software', 'engineer', 'engineering', 'application',
#     #          'development', 'optimization', 'integration', 'architecture',
#     #          'cloud', 'network', 'networking', 'mobile' — all too generic.
#     'computer science', 'coding', 'debugging', 'programmer', 'programming',
#     'api development', 'rest api', 'backend development', 'frontend development',
#     'full stack', 'software developer', 'software engineer',
#     'data structures', 'algorithms', 'oop', 'design patterns',
#     'agile methodology', 'scrum master', 'version control',
#     'tech stack', 'sdlc', 'microservices', 'repository',

#     'business analyst', 'business analysis', 'business systems analyst',
#     'requirements gathering', 'requirements analysis', 'business requirements',
#     'functional requirements', 'user stories', 'use cases', 'brd', 'frd',
#     'scrum', 'kanban', 'sprint planning', 'confluence', 'visio', 'lucidchart',
#     'uml', 'bpmn',
# ]

TECH_KEYWORDS = [
    # ── Programming Languages ──────────────────────────────────────────────
    'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'golang',
    'kotlin', 'swift', 'scala', 'php', 'ruby', 'dart', 'rust',

    # ── Web / Frontend Frameworks ──────────────────────────────────────────
    'html', 'css', 'react', 'angular', 'vue', 'node', 'express',
    'django', 'flask', 'spring', 'laravel', 'next.js', 'graphql',
    'webpack', 'tailwind', 'sass',

    # ── AI / ML / Data Science ─────────────────────────────────────────────
    'machine learning', 'deep learning', 'tensorflow', 'pytorch', 'keras',
    'scikit', 'pandas', 'numpy', 'data science', 'nlp', 'neural network',
    'ai', 'llm', 'computer vision', 'jupyter', 'matplotlib',

    # ── Databases ──────────────────────────────────────────────────────────
    'sql', 'mysql', 'postgresql', 'mongodb', 'redis', 'database', 'sqlite',

    # ── DevOps / Cloud / Infrastructure ────────────────────────────────────
    'docker', 'kubernetes', 'aws', 'azure', 'gcp', 'linux',
    'git', 'ci/cd', 'jenkins', 'terraform', 'devops',
    'github', 'gitlab', 'bitbucket',

    # ── Core Tech Identity Terms ───────────────────────────────────────────
    # NOTE: 'software', 'engineer', 'engineering', 'mobile', 'cloud' removed
    # — all appear naturally in non-tech CVs (accounting software, cloud kitchen, etc.)
    'developer', 'programmer', 'programming',
    'algorithm', 'api', 'backend', 'frontend', 'full stack',
    'android', 'ios', 'flutter', 'cybersecurity', 'blockchain',
    'computer science', 'coding', 'debugging', 'repository',

    # ── Networking / Security ─────────────────────────────────────────────
    # NOTE: 'network', 'networking', 'security', 'server', 'infrastructure',
    #       'troubleshooting', 'configuration', 'monitoring', 'protocols',
    #       'wireless' removed — all appear in non-tech roles.
    'network engineer', 'network security', 'network design',
    'network configuration', 'network monitoring', 'network infrastructure',
    'firewall', 'firewalls', 'router', 'routers',
    'switch', 'switches', 'tcp/ip', 'vpn', 'lan', 'wan', 'vlan',
    'cisco', 'ccna', 'ccnp', 'juniper', 'mikrotik',
    'system administration', 'sysadmin',
    'it support', 'it infrastructure',
    'information systems', 'information technology',
    'penetration testing', 'pen testing', 'ethical hacking',
    'siem', 'splunk', 'ids', 'ips', 'soc', 'incident response',
    'vulnerability assessment', 'malware analysis', 'threat analysis',
    'kali linux', 'wireshark', 'metasploit', 'burp suite', 'nmap',
    'owasp', 'ceh', 'cissp', 'comptia', 'security+',
    'dns', 'dhcp', 'encryption', 'cryptography', 'wifi', 'ethernet',

    # ── UI/UX Developer / Designer ────────────────────────────────────────
    # NOTE: 'designer', 'design', 'prototype', 'prototypes', 'accessibility'
    #       removed — used by non-tech fields (fashion, interior, manufacturing).
    'ui/ux', 'ux designer', 'ui designer', 'ux engineer',
    'ux developer', 'ui developer', 'product designer',
    'figma', 'sketch', 'adobe xd', 'invision', 'framer', 'zeplin', 'miro',
    'prototyping', 'wireframing', 'wireframe', 'wireframes',
    'mockup', 'mockups', 'user research', 'user testing',
    'user experience', 'user interface', 'interaction design',
    'visual design', 'usability', 'usability testing', 'usability heuristics',
    'responsive design', 'mobile design',
    'design system', 'design systems', 'information architecture',
    'user-centered design', 'user flows', 'journey mapping', 'personas',

    # ── QA Engineer / Tester ──────────────────────────────────────────────
    'qa', 'qa engineer', 'quality assurance', 'manual testing',
    'automation testing', 'test automation', 'automated testing',
    'selenium', 'cypress', 'playwright', 'puppeteer', 'appium',
    'test cases', 'test plans', 'test scripts', 'bug tracking',
    'bug reporting', 'defect tracking', 'jira', 'testrail', 'zephyr',
    'sdet', 'software testing', 'regression testing',
    'functional testing', 'integration testing', 'unit testing',
    'api testing', 'postman', 'rest assured', 'soapui',
    'load testing', 'performance testing', 'jmeter', 'testng', 'junit',
    'cucumber', 'bdd', 'tdd',

    # ── Database Administrator / SQL Developer ────────────────────────────
    'dba', 'database administrator', 'database engineer',
    'sql developer', 'pl/sql', 'plsql', 't-sql', 'tsql',
    'stored procedures', 'stored procedure', 'triggers', 'views',
    'indexes', 'indexing', 'query optimization', 'execution plan',
    'database design', 'schema design', 'normalization', 'denormalization',
    'oracle', 'sql server', 'mariadb', 'db2', 'sybase',
    'cassandra', 'dynamodb', 'firebase', 'elasticsearch', 'snowflake',
    'data warehouse', 'data warehousing', 'data modeling', 'erd',
    'backup and recovery', 'replication', 'data migration',
    'etl', 'data pipelines', 'informatica', 'talend', 'ssis',

    # ── Data Scientist / ML / AI Engineer ────────────────────────────────
    'data scientist', 'data analyst', 'data engineer',
    'ml engineer', 'mlops', 'ai engineer', 'machine learning engineer',
    'statistical analysis', 'regression', 'classification',
    'clustering', 'feature engineering', 'feature extraction',
    'model training', 'model deployment', 'model evaluation',
    'hyperparameter tuning', 'cross validation',
    'xgboost', 'lightgbm', 'catboost', 'random forest', 'svm',
    'cnn', 'rnn', 'lstm', 'gan', 'transformer', 'bert', 'gpt',
    'hugging face', 'huggingface', 'transformers', 'langchain', 'rag',
    'fine tuning', 'fine-tuning', 'prompt engineering', 'openai',
    'spark', 'pyspark', 'hadoop', 'airflow', 'kafka', 'kubeflow', 'mlflow',
    'tableau', 'power bi', 'powerbi', 'looker', 'seaborn', 'plotly',
    'r programming', 'data visualization',

    # ── Business Analyst ──────────────────────────────────────────────────
    # NOTE: 'stakeholders', 'agile', 'reporting', 'excel', 'pivot tables',
    #       'vlookup', 'dashboards', 'kpi', 'kpis', 'process mapping',
    #       'process improvement', 'gap analysis' removed — all appear
    #       heavily in accounting, finance, HR, and general management CVs.
    'business analyst', 'business analysis', 'business systems analyst',
    'requirements gathering', 'requirements analysis', 'business requirements',
    'functional requirements', 'user stories', 'use cases', 'brd', 'frd',
    'scrum', 'kanban', 'sprint planning', 'confluence', 'visio', 'lucidchart',
    'uml', 'bpmn',

    # ── DevOps / Cloud / SRE ──────────────────────────────────────────────
    'devops engineer', 'cloud engineer', 'sre',
    'site reliability', 'site reliability engineer', 'platform engineer',
    'ansible', 'puppet', 'chef', 'helm', 'argocd',
    'prometheus', 'grafana', 'datadog', 'new relic',
    'elk stack', 'logstash', 'kibana',
    'cloudformation', 'pulumi', 'serverless', 'lambda', 'ec2', 's3',
    'rds', 'eks', 'ecs', 'aks', 'gke', 'vpc',
    'github actions', 'gitlab ci', 'circleci', 'travis ci',
    'bash', 'shell scripting', 'powershell', 'yaml',
    'microservices', 'service mesh', 'istio', 'nginx', 'apache',
    'load balancing', 'auto scaling', 'high availability',

    # ── Frontend / React / Backend / Full Stack ───────────────────────────
    'jsx', 'tsx', 'redux', 'redux toolkit', 'mobx', 'zustand', 'recoil',
    'react hooks', 'react router', 'nuxt', 'svelte', 'remix',
    'astro', 'gatsby', 'vite', 'babel', 'rollup', 'parcel',
    'bootstrap', 'material ui', 'mui', 'chakra ui',
    'scss', 'less', 'styled components', 'emotion',
    'jquery', 'ajax', 'axios', 'es6', 'ecmascript',
    'nestjs', 'fastapi', 'koa', '.net', 'asp.net', 'entity framework',
    'rest api', 'restful', 'soap', 'grpc', 'websocket', 'webhooks',
    'oauth', 'jwt', 'sso', 'web development', 'web application', 'web app',
    'spa', 'pwa',

    # ── Mobile App Developer ──────────────────────────────────────────────
    'mobile app', 'mobile application', 'mobile developer',
    'react native', 'xamarin', 'ionic', 'cordova',
    'xcode', 'android studio', 'jetpack compose', 'swiftui',
    'kotlin multiplatform', 'objective-c',
    'play store', 'app store', 'mobile sdk',
    'push notifications', 'firebase',

    # ── Blockchain Developer ──────────────────────────────────────────────
    'solidity', 'ethereum', 'smart contract', 'smart contracts',
    'web3', 'web3.js', 'ethers.js', 'hardhat', 'truffle', 'ganache',
    'dapp', 'dapps', 'defi', 'nft', 'erc20', 'erc-20',
    'erc721', 'ipfs', 'metamask', 'cryptocurrency',
    'hyperledger', 'layer 2',

    # ── Software Engineering Concepts ─────────────────────────────────────
    # NOTE: 'system', 'systems', 'application', 'applications', 'development',
    #       'deployment', 'optimization', 'integration', 'architecture',
    #       'technical', 'technology', 'technologies', 'engineering',
    #       'implementation', 'maintenance', 'agile methodology' all removed
    #       — every non-tech CV contains these words.
    'sdlc', 'oop', 'design patterns',
    'data structures', 'scrum master', 'version control',
    'tech stack', 'gitlab', 'bitbucket',
]


def is_valid_cv(text):
    t = text.lower()
    return sum(1 for kw in CV_SECTION_KEYWORDS if kw in t) >= 2

# ── Non-tech domain signals — CVs with ≥ 3 hits in any domain are flagged ──

NON_TECH_ROLE_SIGNALS = {

    'medical_healthcare': [ 

        'physician', 'nurse', 'nursing',
        'patient care', 'patient management','patient safety', 'patient assessment',
        'clinical trial', 'clinical operations','diagnosis', 'treatment plan',
        'prescription', 'surgery','healthcare provider','medical doctor', 'pharmacist',
        'physiotherapist', 'radiologist','laboratory technician', 
        'medical records','electronic health records','hospital administration',
        'hospital management','icu', 'emergency room','ward', 'hospital',
        'vital signs', 'dosage',

    ],

     'hospitality_retail': [

        'hotel management', 'front desk', 'concierge', 'housekeeping',
        'food and beverage', 'restaurant management', 'chef', 'catering',
        'guest services', 'event planning', 'inventory management',
        'retail sales', 'customer checkout', 'store manager', 'merchandising',
    ],

    'human_resources': [
        'human resources', 'hr manager', 'talent acquisition',
        'employee relations', 'hr policies', 'performance appraisal',
        'compensation and benefits', 'labor law', 'workforce planning',
        'staff management', 'grievance handling', 'exit interviews',
        'job description', 'headcount', 'attrition', 'employee engagement',
        'hr executive', 'hr officer', 'hr specialist', 'hr generalist',
        'senior hr manager', 'hr business partner', 'hr director',
        'chief human resources officer', 'chro', 'people operations',
        'people manager', 'people partner',
    ],
    
    'accounting_finance': [
        'accountant', 'accounting', 'accounts payable', 'accounts receivable',
        'gaap', 'ledger', 'bookkeeping', 'auditing', 'tax preparation',
        'financial statements', 'balance sheet', 'income statement', 'quickbooks',
        'journal entries', 'month-end close', 'year-end close', 'reconciliation',
        'payroll', 'cpa', 'certified public accountant', 'variance analysis',
        'financial reporting', 'general ledger', 'accruals', 'amortization',
        'accounts reconciliation', 'fiscal year', 'revenue recognition',
    ],


'sales_marketing': [
    'sales representative', 'sales executive', 'sales manager',
    'account executive', 'business development executive',
    'business development manager', 'inside sales', 'field sales',
    'cold calling', 'warm calling', 'prospecting', 'lead generation',
    'lead qualification', 'pipeline management', 'deal closure',
    'sales quota', 'revenue target', 'sales forecasting',
    'negotiation', 'b2b sales', 'b2c sales','public relations', 'media relations', 'press release',
    'marketing campaign', 'digital marketing', 'traditional marketing',
    'brand management', 'brand strategy', 'brand awareness',
    'market research', 'competitor analysis', 'marketing strategy',
    'content creation', 'content marketing', 'copywriting',
    'social media marketing', 'social media management',
    'email marketing', 'newsletter campaigns',
    'influencer marketing', 'affiliate marketing',
    # split from here
    'go-to-market','pre-sales', 'sales enablement',
    'pipeline management', 'lead generation',
    'crm', 'salesforce', 'zoho crm',
    'cold calling', 'enterprise sales',

    ],

    'legal': [
        'attorney', 'lawyer', 'paralegal', 'legal counsel', 'litigation',
        'contract law', 'intellectual property', 'corporate law', 'bar exam',
        'legal research', 'court filing', 'deposition', 'arbitration',
        'legal drafting', 'case management', 'legal compliance',
        'advocate', 'junior associate', 'senior associate', 'legal advisor',
        'in-house counsel', 'solicitor', 'barrister', 'judge',
        'magistrate', 'legal officer', 'legal assistant',
        'civil litigation', 'criminal litigation', 'court proceedings',
        'trial preparation', 'cross examination', 'witness handling',
        'legal hearing', 'judgment drafting', 'pleading', 'motion filing',
        'appeal process',
        'mergers and acquisitions', 'm&a', 'corporate governance',
        'shareholder agreements', 'contract negotiation',
        'due diligence', 'regulatory compliance',
        'patent law', 'trademark law', 'copyright law','licensing agreements',
        'contract drafting', 'legal documentation',
        'agreement review', 'terms and conditions drafting',
        'nda', 'non disclosure agreement',
        'regulatory affairs', 'legal audit', 'risk compliance',
        'anti money laundering', 'aml compliance',
        'data protection law', 'gdpr compliance',
        'mediation', 'negotiation', 'conciliation',
        'dispute resolution', 'settlement agreement',

    ],

    'education_teaching': [
        'teacher', 'professor', 'lecturer', 'curriculum development',
        'lesson plan', 'classroom management', 'student assessment',
        'pedagogy', 'tutoring', 'academic performance', 'grading',
        'school administration', 'educational institution',
    ],

    'construction_civil': [
        'civil engineer', 'structural engineer', 'construction site',
        'blueprint', 'geotechnical', 'land surveying', 'quantity surveyor',
        'building permit', 'site inspection', 'concrete', 'rebar',
        'plumbing', 'electrical wiring', 'hvac', 'masonry',
    ],


}

# ── Specific tech signals that CONFIRM a real tech CV ────────────────────────
# Generic words like "software", "cloud", "development" are intentionally
# excluded — only tool/framework/language names that non-tech CVs never use.
STRONG_TECH_SIGNALS = [
    'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'golang',
    'kotlin', 'swift', 'dart', 'rust', 'php', 'ruby',
    'react', 'angular', 'vue', 'node.js', 'django', 'flask', 'spring',
    'fastapi', 'laravel', 'next.js', 'express',
    'machine learning', 'deep learning', 'tensorflow', 'pytorch', 'keras',
    'scikit', 'data science', 'neural network', 'nlp', 'computer vision',
    'docker', 'kubernetes', 'jenkins', 'terraform', 'ansible',
    'aws', 'azure', 'gcp', 'linux', 'ci/cd', 'devops',
    'mongodb', 'postgresql', 'mysql', 'redis', 'elasticsearch',
    'github', 'git', 'rest api', 'graphql', 'microservices',
    'flutter', 'android development', 'ios development', 'react native',
    'cybersecurity', 'penetration testing', 'blockchain', 'solidity',
    'selenium', 'junit', 'pytest', 'cypress'
]

def is_tech_cv(text):
    """Two-layer tech CV validator with length-aware threshold."""
    t = text.lower()

    # ── Layer 1: broad keyword count
    tech_count = sum(1 for kw in TECH_KEYWORDS if kw in t)
    if tech_count < 5:
        return False

    # ── Layer 2: non-tech domain check (length-aware) ──
    non_tech_domain_hits = {}
    for domain, signals in NON_TECH_ROLE_SIGNALS.items():
        hits = sum(1 for s in signals if s in t)
        if hits >= 3:
            non_tech_domain_hits[domain] = hits

    if not non_tech_domain_hits:
        return True  # Pure tech, pass immediately

    # ── Decide strong signal threshold based on resume length ──
    cleaned_len = len(fix_pdf_artifacts(text).strip())
    if cleaned_len < 300:
        # Short resume: require only 2 strong signals (more lenient)
        strong_threshold = 2
    elif cleaned_len < 600:
        # Medium resume: require 3 strong signals (default)
        strong_threshold = 3
    else:
        # Long resume: require 3+ strong signals (existing)
        strong_threshold = 3

    strong_tech_count = sum(1 for s in STRONG_TECH_SIGNALS if s in t)
    if strong_tech_count < strong_threshold:
        return False

    return True





# Compile patterns for CORE keywords (whole-word matching)
# ## Step 10 — Grammar & Spelling (v7: enhanced multi-layer detection)
# 
# **Four-layer detection (works even without Java/LanguageTool)**
# 
# 1. **Repeated-char scanner** — catches `Computerrr→Computer`, `Scienceee→Science`
# 2. **Spellchecker (pyspellchecker)** — catches suffix typos:`projecty→project`
# 3. **LanguageTool ENHANCED** — catches grammar, tense, capitalization, subject-verb agreement, punctuation
# 4. **Error-type classifier** — maps every issue to: `spelling | capitalization | grammar | tense | subject_verb_agreement | punctuation | sentence_structure`
# 
# **v7 enhancements over v6:**
# - ✅ Capitalization: `"i am going"` → `"I am going"`
# - ✅ Tense: `"He go to school yesterday"` → `"He went to school yesterday"`
# - ✅ Subject-verb agreement: `"They was playing"` → `"They were playing"`
# - ✅ Punctuation: `"hello how are you"` → `"Hello, how are you?"`
# - ✅ Structured output with `error_type` and `detected_errors[]`
# - ✅ All v6 spelling detection preserved (Layers 1 & 2 unchanged)
# 
# **CV section awareness** — lines are classified as HEADING / TITLE / DESCRIPTIVE. Only DESCRIPTIVE lines are checked.
# 
# **Output format**
# ```
# {
#   "original_text": "i want to become software engineer",
#   "corrected_text": "I want to become a software engineer",
#   "error_type": "capitalization",
#   "detected_errors": [
#     {"error_type": "capitalization", "original": "i", "corrected": "I", "explanation": "..."}
#   ],
#   "explanation": "..."
# }
# ```
# 


try:
    import language_tool_python as _lt_module
    # Ensure Java is findable in common server locations
    import os as _os
    _java_candidates = [
        r"C:\Program Files\Java\jdk-17\bin",   # Windows JDK 17
        r"C:\Program Files\Java\jdk-11\bin",   # Windows JDK 11
        r"C:\Program Files\Java\jre-11\bin",   # Windows JRE 11
        "/usr/bin",                             # Ubuntu/Debian (java symlink)
        "/usr/lib/jvm/default-java/bin",       # Ubuntu/Debian JDK
        "/usr/lib/jvm/java-17-openjdk-amd64/bin",  # Ubuntu JDK 17
        "/usr/lib/jvm/java-11-openjdk-amd64/bin",  # Ubuntu JDK 11
        "/usr/local/bin",                       # Homebrew / other Linux
    ]
    _path_env = _os.environ.get("PATH", "")
    for _jc in _java_candidates:
        if _jc not in _path_env and _os.path.isdir(_jc):
            _os.environ["PATH"] = _jc + _os.pathsep + _path_env
            break
    grammar_tool      = _lt_module.LanguageTool('en-US')
    GRAMMAR_AVAILABLE = True
    logger.info("LanguageTool initialised successfully.")
except Exception as e:
    grammar_tool      = None
    GRAMMAR_AVAILABLE = False
    logger.debug(f"LanguageTool unavailable, using fallback grammar checker: {e}")

# ── Spellchecker (Layer 2) ─────────────────────────────────────────────────
try:
    from spellchecker import SpellChecker
    _spell = SpellChecker()
    SPELLCHECK_AVAILABLE = True
except Exception:
    _spell = None
    SPELLCHECK_AVAILABLE = False

# ── Known tech terms — NEVER flag these ───────────────────────────────────
TECH_WHITELIST = frozenset({
    'react', 'reactjs', 'reactnative', 'angular', 'angularjs', 'vuejs', 'vue',
    'nextjs', 'nuxtjs', 'node.js','nodes','MySQL','Postgre SQL' ,'expressjs', 'django', 'flask', 'fastapi',
    'spring', 'springboot', 'laravel', 'symfony', 'rails',
    'tensorflow', 'pytorch', 'keras', 'sklearn', 'scikit', 'xgboost', 'lightgbm',
    'numpy', 'pandas', 'matplotlib', 'seaborn', 'plotly', 'scipy', 'statsmodels',
    'mongodb', 'postgresql', 'mysql', 'sqlite', 'redis', 'elasticsearch',
    'cassandra', 'firebase', 'dynamodb', 'supabase', 'prisma',
    'docker', 'kubernetes', 'terraform', 'ansible', 'jenkins', 'github',
    'gitlab', 'bitbucket', 'aws', 'azure', 'gcp', 'heroku', 'netlify',
    'javascript', 'typescript', 'golang', 'kotlin', 'flutter', 'dart',
    'graphql', 'restapi', 'grpc', 'websocket', 'microservices',
    'nlp', 'llm', 'gpt', 'bert', 'transformer', 'blockchain', 'solidity',
    'ucp', 'mit', 'stanford', 'coursera', 'udemy', 'hackerrank', 'leetcode',
    'linkedin', 'figma', 'postman', 'swagger', 'jira', 'confluence','Node.JS',
    'lstm', 'gan', 'cnn', 'rnn', 'mlp', 'svm', 'knn', 'eda',
    'api', 'apis', 'sdk', 'oop','Bitcoin', 'bitcoin','mvc', 'mvvm', 'crud', 'json', 'xml', 'yaml',
    'html', 'css', 'sass', 'scss', 'tailwind', 'bootstrap', 'jquery',
    'tsx', 'jsx', 'npm', 'yarn', 'pnpm', 'webpack', 'vite', 'babel',
    'framer', 'redux','tariq', 'vuex', 'pinia', 'recoil', 'zustand','Node.js','onsite','Node JS',
    'spacy', 'nltk', 'gensim', 'huggingface','Ethereum','ethereum','langchain', 'openai',
    'streamlit', 'gradio', 'tableau', 'powerbi', 'looker','Angular 4/2','jQuery',
    'mern', 'mean', 'lamp', 'ats','https','immersive',
    'employability', 'preprocessing', 'scalability', 'backend', 'frontend',
    'fullstack', 'dataset', 'datasets', 'resumes', 'skillset',
    'ui', 'ux', 'sql', 'nosql','Tariq', 'csv', 'pdf', 'ci', 'cd',
    'asyncio', 'asyncpg', 'aiohttp', 'aiomysql', 'uvicorn', 'gunicorn',
    'pydantic', 'sqlalchemy', 'alembic', 'celery', 'pytest', 'mypy',
    'postgre', 'postgres', 'mariadb', 'memcached', 'rabbitmq', 'kafka',
    'pyspark', 'airflow', 'dbt', 'snowflake', 'databricks',
    'opencv', 'yolov', 'onnx', 'mlflow', 'wandb', 'optuna',
    'eslint', 'prettier', 'vitest', 'jest', 'cypress', 'playwright',
    'nestjs', 'svelte', 'sveltekit', 'remix', 'astro', 'solidjs',
})


# ── Custom proper nouns (lowercased) ──────────────────────────────────────
CUSTOM_PROPER_NOUNS = frozenset({
    'intervai', 'interv', 
    'ucp', 'fast', 'comsats', 'nust', 'lums', 'itu', 'pu', 'ku', 'ued',
    'bise', 'fbise', 'fsc', 'ics', 'matric', 'icpc', 'punjab',
    'digitech', 'netsol', 'arbisoft', 'systems limited', 'tcs', 'ptcl',
    'infinity', 'edge', 'technologies', 'crane', 'craft',
    'leetcode', 'hackerrank', 'github', 'codeforces', 'codechef', 'kaggle',
    'coderush', 'taakra', 'procom','immersive' ,'softec', 'nascon', 'hultprize',
    'vis', 'speedup', 'codejam',
    'intervai', 'jarvis', 'nova', 'alexa', 'cortana', 'siri',
    'careercrafter', 'careercrafting', 'aibot', 'chatbot', 'helpbot',
    'fyp', 'cv', 'cvs', 'gpa', 'cgpa', 'mlsa', 'acm', 'ieee', 'usc',
    'mern', 'lamp', 'oop', 'pf', 'dsa', 'ds', 'ai', 'ml',
    'nlp', 'llm', 'crm', 'erp', 'saas', 'paas', 'iaas',
    'hse', 'spc', 'llc',
    'lahore', 'islamabad', 'karachi', 'rawalpindi', 'peshawar', 'faisalabad',
    'wikipedia', 'google', 'microsoft', 'amazon', 'facebook', 'meta',
})

# ── PDF merge-boundary words ───────────────────────────────────────────────
PDF_MERGE_SUFFIXES = [
    'and', 'or', 'of', 'in', 'at', 'on', 'to', 'the', 'for', 'by',
    'with', 'from', 'as', 'but', 'not', 'so', 'if', 'an', 'a',
    'is', 'it', 'its', 'be', 'was', 'are', 'has', 'had', 'have',
]
PDF_MERGE_PREFIXES = [
    'in', 'a', 'an', 'the', 'and', 'or', 'of', 'to', 'by', 'for',
    'with', 'from', 'as', 'at', 'on',
]

SKIP_CATEGORIES    = {
    'STYLE', 'TYPOGRAPHY', 'REDUNDANCY', 'COLLOQUIALISMS',
}

SKIP_RULE_PATTERNS = [
    'DASH', 'QUOTE', 'ELLIPSIS', 'WHITESPACE', 'WORD_REPEAT',
]

_RESUME_PUNCTUATION_SKIP_RULES = frozenset({
    'UNLIKELY_OPENING_PUNCTUATION',
    'MULTIPLICATION_SIGN',
    'EN_QUOTES',
    'CONSECUTIVE_SPACES',
})

_ALWAYS_ALLOW_RULES = frozenset({
    'UPPERCASE_SENTENCE_START',
    'I_LOWERCASE',
    'ENGLISH_WORD_REPEAT_BEGINNING_RULE',
    'HE_VERB_AGR',
    'PERS_PRONOUN_AGREEMENT',
    'DID_BASEFORM',
    'NON3PRS_VERB',
    'BEEN_PART_AGREEMENT',
    'SENT_START_CONJUNCTIVE_LINKING_ADVERB_COMMA',
    'COMMA_COMPOUND_SENTENCE',
    'COMMA_COMPOUND_SENTENCE_2',
    'MISSING_COMMA_AFTER_INTRODUCTORY_PHRASE',
})

# ── Sentence-start capitalization rules (suppressed on continuation lines) ─
_SENTENCE_START_CAP_RULES = frozenset({
    'UPPERCASE_SENTENCE_START',
    'SENTENCE_START_STYLE',
    'UPPERCASE_AFTER_COMMA',   # sometimes misfires on fragments
})

# Pre-compiled patterns
_REPEAT3_RE = re.compile(r'(.)\1{2,}')

# ── NEW: terminal punctuation detector ────────────────────────────────────
_TERMINAL_PUNCT = frozenset('.!?')

def _line_ends_sentence(line: str) -> bool:
    """
    Returns True if the line ends with terminal punctuation (.  !  ?),
    meaning the NEXT descriptive line is a fresh sentence (not a continuation).
    Lines ending with commas, colons, or nothing are treated as continuations.
    """
    stripped = line.rstrip()
    return bool(stripped) and stripped[-1] in _TERMINAL_PUNCT


# ── Column-merge artifact detector ────────────────────────────────────────
_MID_LINE_PERIOD_LC = re.compile(r'\.\s+[a-z]')

def _is_column_merge_line(line: str) -> bool:
    """
    Detects PDF column-merge artifacts: a period followed by a lowercase
    word mid-line means two sentence fragments from different layout columns
    (or achievement boxes) were concatenated by the PDF extractor.

    The whole line is treated as a continuation so neither the first word
    NOR the word after the mid-line period gets flagged for missing
    capitalisation.

    Example (Sophia Brown — 3-column Key Achievements layout):
        "exceeded company targets by 15%. analytics solution."
         ↑ col-1 fragment                 ↑ col-2 fragment (lowercase start)

    The previous line ended with "." so is_continuation was False, letting
    "exceeded" get incorrectly flagged. This helper catches it by inspecting
    the line itself rather than relying solely on the previous line's ending.
    """
    return bool(_MID_LINE_PERIOD_LC.search(line))


def _starts_as_participle_fragment(line: str) -> bool:
    """
    v19 — True when the line opens with a present-participle / gerund
    (e.g. 'cutting', 'achieving', 'leading') with no preceding subject.

    In a CV this is almost always a fragment from a right-column achievement
    description that landed between left-column bullets after PDF extraction.
    Such lines should be treated as continuations so the first word doesn't
    get flagged for missing capitalisation.

    Example (Alexander Jackson — Enhancv 2-column):
        "Mentored a team of junior developers to adopt best practices,"
        "cut down post-release bug fixes by 25%."   ← starts with verb,
                                                       NOT a new sentence.
    """
    s = line.lstrip()
    s_nb = _BULLET_RE.sub('', s).strip()
    if not s_nb:
        return False
    first = s_nb.split()[0]
    # -ing word, at least 5 chars (avoids 'sing', 'ring' false positives)
    return bool(re.match(r'^[A-Za-z]+ing$', first)) and len(first) >= 5


# ═══════════════════════════════════════════════════════════════════════════
# Error-type classifier (Layer 4)
# ═══════════════════════════════════════════════════════════════════════════
def _classify_error_type(rule, category, message=''):
    r = (rule or '').upper()
    c = (category or '').upper()
    m = (message or '').lower()

    # FIX 7: pronoun "i"→"I" is capitalization, not spelling
    # Must come BEFORE the TYPOS catch to prevent misclassification
    if 'pronoun' in m and ('"i"' in m or '“i”' in m):
        return 'capitalization'
    if 'I_LOWERCASE' in r or 'UPPERCASE_SENTENCE_START' in r:
        return 'capitalization'

    if r in ('REPEATED_CHARS_TYPO', 'SPELLCHECK') or c == 'TYPOS':
        return 'spelling'
    if c == 'CASING' or 'UPPERCASE' in r or 'LOWERCASE' in r or 'I_LOWERCASE' in r:
        return 'capitalization'
    if c == 'AGREEMENT' or 'AGR' in r or 'AGREEMENT' in r:
        return 'subject_verb_agreement'
    if any(kw in m for kw in ['subject', 'verb agreement', 'singular', 'plural']):
        return 'subject_verb_agreement'
    if 'TENSE' in r or 'PAST_' in r or 'PRESENT_' in r or 'DID_BASEFORM' in r:
        return 'tense'
    if any(kw in m for kw in ['past tense', 'present tense', 'tense', 'past participle']):
        return 'tense'
    if c == 'PUNCTUATION' or 'COMMA' in r or 'PERIOD' in r or 'SEMICOLON' in r:
        return 'punctuation'
    if 'FRAGMENT' in r or 'SENTENCE' in r or 'MISSING_VERB' in r:
        return 'sentence_structure'
    if any(kw in m for kw in ['sentence fragment', 'incomplete sentence', 'missing verb']):
        return 'sentence_structure'
    if c in ('GRAMMAR', 'MORPHOLOGY'):
        return 'grammar'
    return 'grammar'


# ───────────────────────────────────────────────────────────────────────────
# CV line classification
# ───────────────────────────────────────────────────────────────────────────
try:
    _SECTION_HEADERS = {h.upper().strip() for h in CV_SECTION_KEYWORDS}
except NameError:
    _SECTION_HEADERS = set()

_SECTION_HEADERS |= {
    'SUMMARY', 'OBJECTIVE', 'PROFILE', 'ABOUT', 'ABOUT ME', 'WHO AM I',
    'EXPERIENCE', 'WORK EXPERIENCE', 'PROFESSIONAL EXPERIENCE', 'EMPLOYMENT',
    'EDUCATION', 'ACADEMIC BACKGROUND', 'QUALIFICATIONS',
    'PROJECTS', 'PERSONAL PROJECTS', 'KEY PROJECTS',
    'SKILLS', 'TECHNICAL SKILLS', 'CORE SKILLS', 'SKILLS AND INTERESTS',
    'SKILLS AND CERTIFICATIONS',
    'CERTIFICATIONS', 'CERTIFICATES', 'AWARDS', 'ACHIEVEMENTS',
    'LEADERSHIP', 'LEADERSHIP ACTIVITIES', 'ACTIVITIES', 'VOLUNTEER',
    'INTERESTS', 'HOBBIES', 'LANGUAGES',
    'CONTACT', 'CONTACT INFO', 'PERSONAL INFO', 'PERSONAL INFORMATION',
    'REFERENCES', 'PUBLICATIONS', 'COURSEWORK', 'RELEVANT COURSEWORK',
    'KEY ACHIEVEMENTS',
    'ADDITIONAL INFO', 'ADDITIONAL INFORMATION', 'TOOLS',
}

_DATE_RE_1 = re.compile(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(19|20)\d{2}\b', re.I)
_DATE_RE_2 = re.compile(r'\b(19|20)\d{2}\s*[-–—]\s*(present|(19|20)\d{2})\b', re.I)
_DATE_RE_3 = re.compile(r'\b\d{4}\s*[-–—]\s*present\b', re.I)
_URL_RE    = re.compile(r'(linkedin|github|gitlab|gmail|outlook|yahoo)\.com', re.I)
_PHONE_RE  = re.compile(r'^\+?\d[\d\s\-\.()]{6,}')
_BULLET_RE = re.compile(r'^\s*[•●○◦▪►◆■\-\*]\s+')
_LABEL_PREFIX_RE = re.compile(r'^[A-Za-z][A-Za-z &]{2,30}\s*:')

_CONNECTORS = {
    'with', 'and', 'to', 'that', 'which', 'where', 'using', 'for', 'from', 'by',
    'of', 'on', 'in', 'as', 'but', 'because', 'while', 'when', 'if', 'than',
    'into', 'through', 'about', 'over', 'under',
}


def _classify_line(line):
    s = line.strip()
    if not s:
        return 'EMPTY'

    s_nb = _BULLET_RE.sub('', line).strip()
    has_bullet = (s_nb != s)
    if not s_nb:
        return 'EMPTY'

    words  = s_nb.split()
    nwords = len(words)

    # v19 — short orphan capitalised tokens like 'Spanish', 'Advanced', 'Native'
    # are column-fragment titles from the LANGUAGES / SKILLS sidebar, NOT
    # descriptive prose. Marking them TITLE prevents the grammar checker from
    # treating them as a stand-alone descriptive line.
    if nwords <= 2 and not has_bullet:
        if all(w[0].isupper() for w in words if w and w[0].isalpha()):
            if not re.search(r'[.!?]', s_nb):
                return 'TITLE'

    if s_nb.upper().rstrip(':.,').strip() in _SECTION_HEADERS:
        return 'HEADING'
    if s_nb.isupper() and nwords <= 5:
        return 'HEADING'
    if _LABEL_PREFIX_RE.match(s_nb):
        head = s_nb.split(':', 1)[0]
        if ' ' not in head or len(head.split()) <= 3:
            return 'HEADING'
    if ':' in s_nb and nwords <= 7 and not has_bullet:
        return 'HEADING'
    if _DATE_RE_1.search(s) or _DATE_RE_2.search(s) or _DATE_RE_3.search(s):
        return 'TITLE'
    if '@' in s_nb and nwords <= 6:
        return 'TITLE'
    if _PHONE_RE.match(s_nb):
        return 'TITLE'
    if _URL_RE.search(s_nb) and nwords <= 6:
        return 'TITLE'

    if has_bullet and nwords >= 3:
        return 'DESCRIPTIVE'
    if nwords >= 5:
        cap_ratio = sum(1 for w in words if w and (w[0].isupper() or w.isupper())) / nwords
        if cap_ratio < 0.4:
            return 'DESCRIPTIVE'
    if re.search(r'[.!?]', s_nb) and nwords >= 5:
        cap_ratio = sum(1 for w in words if w and (w[0].isupper() or w.isupper())) / nwords
        if cap_ratio > 0.7 and not any(w.lower() in _CONNECTORS for w in words):
            return 'TITLE'
        return 'DESCRIPTIVE'

    if not re.search(r'[.!?]', s_nb):
        cap_ratio = sum(1 for w in words if w and (w[0].isupper() or w.isupper())) / nwords
        if cap_ratio > 0.6:
            return 'TITLE'

    if nwords >= 8 and any(w.lower() in _CONNECTORS for w in words):
        return 'DESCRIPTIVE'

    if nwords >= 4:
        lower_ratio = sum(1 for w in words if w and w[0].islower()) / nwords
        if lower_ratio >= 0.6:
            return 'DESCRIPTIVE'
    if nwords <= 7:
        return 'TITLE'
    return 'DESCRIPTIVE'


# ───────────────────────────────────────────────────────────────────────────
# v21 — SECTION-AWARE grammar suppression
# ───────────────────────────────────────────────────────────────────────────
_NO_GRAMMAR_SECTION_ROOTS = (
    'CERTIF',        # Certification(s) / Certificates
    'AWARD',         # Awards / Awards & Recognition
    'ACHIEV',        # Achievements / Key Achievements
    'RECOGNI',       # Recognition(s)
    'HONOR', 'HONOUR',
    'ACCOMPLISH',
    'PUBLICATION',
)

_GRADE_SECTION_ROOTS = (
    'SUMMARY', 'OBJECTIVE', 'PROFILE', 'ABOUT',
    'EXPERIENCE', 'EMPLOYMENT', 'WORK HISTORY',
    'PROJECT', 'EDUCATION', 'RESPONSIBILIT',
)


def _detect_section_switch(line):
    """Return 'SKIP', 'GRADE', or None for a section header line."""
    s = _BULLET_RE.sub('', line).strip()
    if not s:
        return None
    core = s.rstrip(':').strip()
    words = core.split()
    if not words or len(words) > 6:
        return None
    norm = re.sub(r'[^A-Z& ]', '', core.upper())
    for root in _NO_GRAMMAR_SECTION_ROOTS:
        if root in norm:
            return 'SKIP'
    for root in _GRADE_SECTION_ROOTS:
        if root in norm:
            return 'GRADE'
    return None


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────
def _has_triple_repeat(word):
    return bool(_REPEAT3_RE.search(word.lower()))


def _collapse_repeats(word):
    return _REPEAT3_RE.sub(lambda mm: mm.group(1), word)


def _is_pdf_merge_artifact(word):
    w, wl = word.strip(), word.strip().lower()
    if len(w) < 5: return False
    if wl in TECH_WHITELIST or wl in CUSTOM_PROPER_NOUNS: return False
    if any(tech in wl for tech in TECH_WHITELIST if len(tech) >= 4): return True
    for suffix in PDF_MERGE_SUFFIXES:
        if wl.endswith(suffix) and len(wl) > len(suffix) + 2:
            root = wl[:-len(suffix)]
            if len(root) >= 3 and root.isalpha(): return True
    for prefix in PDF_MERGE_PREFIXES:
        if wl.startswith(prefix) and len(wl) > len(prefix) + 3:
            orig_rest = w[len(prefix):]
            if orig_rest and orig_rest[0].isupper() and len(orig_rest) >= 3:
                return True
    return False


def _is_structural_artifact(word, rule, category, suggestion):
    w, wl = word.strip(), word.strip().lower()
    if _has_triple_repeat(w): return False
    if w.isupper() and len(w) > 6 and ' ' not in w: return True
    if re.search(r'^[A-Z][a-z]+[A-Z]', w): return True
    vowel_ratio = sum(1 for c in wl if c in 'aeiou') / max(len(wl), 1)
    if len(w) >= 5 and vowel_ratio < 0.15: return True
    if suggestion and suggestion not in ('(see explanation)', ''):
        sug_norm  = re.sub(r'[\s\-]+', '', suggestion)
        word_norm = re.sub(r'[\s\-]+', '', w)
        if sug_norm == word_norm: return True
    if len(w) > 25 and ' ' not in w: return True
    return False


def _is_camelcase_fragment(check_text, match):
    try:
        offset, end = match.offset, match.offset + match.error_length
    except AttributeError:
        return False
    if 0 <= end < len(check_text):
        nxt = check_text[end]
        if nxt.isalpha() and nxt.isupper(): return True
    if offset > 0:
        prev = check_text[offset - 1]
        if prev.isalpha() and prev.islower():
            try:
                first = check_text[offset]
                if first.isalpha() and first.isupper(): return True
            except IndexError:
                pass
    return False


def _is_british_american_spelling(match):
    msg = (match.message or '').lower()
    return 'british english' in msg or 'american english' in msg


def _extract_proper_nouns(text):
    if not nlp: return set()
    doc = nlp(text[:3000])
    return {ent.text.lower() for ent in doc.ents
            if ent.label_ in ('PERSON', 'ORG', 'GPE', 'LOC', 'PRODUCT', 'EVENT')}


# ───────────────────────────────────────────────────────────────────────────
# Layer 1: Repeated-char typo scanner
# ───────────────────────────────────────────────────────────────────────────
def _find_repeated_char_typos(text, proper_nouns):
    typos = []
    seen  = set()
    LEFT_MAX, RIGHT_MAX = 12, 3

    for m in _REPEAT3_RE.finditer(text):
        start, end = m.start(), m.end()
        left = start
        while left > 0 and text[left - 1].isalpha() and (start - left) < LEFT_MAX:
            left -= 1
        rep_char = m.group(1).lower()
        right = end
        while (right < len(text)
               and text[right].isalpha()
               and text[right].islower()
               and text[right].lower() != rep_char
               and (right - end) < RIGHT_MAX):
            right += 1

        word = text[left:right]
        wl   = word.lower()
        if len(word) < 4 or word in seen:
            continue
        seen.add(word)

        if wl in proper_nouns or wl in TECH_WHITELIST or wl in CUSTOM_PROPER_NOUNS:
            continue
        if any(pn in wl for pn in CUSTOM_PROPER_NOUNS if len(pn) >= 4):
            continue

        suggestion = _collapse_repeats(word)
        if suggestion == word or suggestion.lower() == wl:
            continue

        typos.append({
            'error':       word,
            'suggestion':  suggestion,
            'rule':        'REPEATED_CHARS_TYPO',
            'category':    'TYPOS',
            'error_type':  'spelling',
            'explanation': f'Repeated character typo: "{word}" → "{suggestion}"',
            'context':     text[max(0, left - 20):min(len(text), right + 20)].strip()[:120],
            'offset':      left,
            'length':      right - left,
        })
    return typos


# ───────────────────────────────────────────────────────────────────────────
# Layer 2: Spellchecker
# ───────────────────────────────────────────────────────────────────────────
_SPELL_WHITELIST = TECH_WHITELIST | CUSTOM_PROPER_NOUNS | frozenset({
    'analysed', 'optimised', 'utilised', 'organised', 'recognised',
    'personalised', 'personalized', 'customised', 'summarised',
    'visualisation', 'modelling', 'colour', 'programme', 'behaviour',
    'honour', 'favourite', 'centre', 'standardised', 'specialised',
    'initialised', 'prioritised', 'minimised', 'maximised',
    'analytics', 'transformative', 'onboarding', 'runtime', 'actionable',
    'scalable', 'stakeholders', 'stakeholder', 'cross-functional',
    'spearheading', 'strategizing', 'mentored', 'mentoring',
    'facilitated', 'collaborated', 'collaborative', 'forecasting',
    'predictive', 'proactive', 'impactful', 'deliverables',
    'operationalize', 'streamline', 'streamlined', 'streamlining',
    'upskilling', 'reskilling', 'downsizing', 'offshoring','onsite',
    'ideation', 'synergy', 'synergies', 'incentivize', 'incentivized',
    'monetize', 'monetized', 'gamification', 'decentralized',
    'preprocessing', 'hyperparameter', 'hyperparameters', 'overfitting',
    'underfitting', 'tokenization', 'embeddings', 'vectorization',
    'backpropagation', 'regularization', 'normalization', 'featurization',
    'dimensionality', 'multivariate', 'univariate', 'multiclass',
    'multimodal', 'pretrained', 'Bitcoin','finetuned', 'finetuning','Node.js',
    'scalability', 'deployable', 'codebase', 'refactoring', 'refactored',
    'containerized', 'microservice', 'middleware', 'serverless',
    'backend', 'frontend', 'fullstack', 'dataset', 'datasets','https',
    'webapp', 'webapps','Tariq','runtime', 'runtimes',
    'skillset', 'skillsets', 'resumes', 'workflow', 'workflows',
    'chatbot', 'chatbots', 'leaderboard', 'leaderboards',
    'roadmap', 'roadmaps', 'changelog', 'webhook', 'webhooks',
    'employability', 'bitcoin','interviewee', 'mentorship', 'internee',
    'intermediary', 'bachelors', 'coursework', 'co-curricular',
    'extracurricular', 'valedictorian', 'bootcamp',
    'optimized', 'leveraging', 'enhancing', 'Node.JS','spearheaded', 'architected',
    'orchestrated', 'conceptualized', 'contextualized', 'operationalized',
    'evangelized', 'productionized', 'productionize', 'democratized',
    'containerize', 'containerizing', 'parameterized', 'deprioritized',
    'optimise', 'optimises', 'optimising', 'optimisation', 'optimisations',
    'realise', 'realises', 'realising', 'realisation', 'realisations',
    'recognise', 'recognises', 'recognising', 'recognisable',
    'organise', 'organises', 'organising', 'organisation', 'organisations',
    'analyse', 'analyses', 'analysing', 'analyser', 'analysers',
    'utilise', 'utilises', 'utilising', 'utilisation','Node JS','Angular 4/2','jQuery',
    'customise', 'customises', 'customising', 'customisation','JSON',
    'specialise', 'specialises', 'specialising', 'specialisation',
    'standardise', 'standardises', 'standardising', 'standardisation',
    'minimise', 'minimises', 'minimising', 'minimisation',
    'maximise', 'maximises', 'maximising', 'maximisation',
    'prioritise', 'prioritises', 'prioritising', 'prioritisation',
    'initialise', 'initialises', 'initialising', 'initialisation',
    'summarise', 'summarises', 'summarising',
    'personalise', 'personalises', 'personalising', 'personalisation',
    'monetise', 'monetises', 'monetising', 'monetisation',
    'incentivise', 'incentivises', 'incentivising', 'incentivisation',
    'synthesise', 'synthesises', 'synthesising',
    'synchronise', 'synchronises', 'synchronising', 'synchronisation',
    'centralise', 'centralises', 'centralising', 'centralisation',
    'modernise', 'modernises', 'modernising', 'modernisation',
    'visualise', 'visualises', 'visualising',
    'categorise', 'categorises', 'categorising', 'categorisation',
    'parameterise', 'parameterising', 'parameterisation',
    'characterise', 'characterising', 'characterisation',
    'familiarise', 'familiarising',
    'finalise', 'finalises', 'finalising',
    'mobilise', 'mobilises', 'mobilising', 'mobilisation',
    'digitise', 'digitises','tariq', 'digitising', 'digitisation',
    'tokenise', 'tokenises', 'tokenising', 'tokenisation',
    'normalise', 'normalises', 'normalising', 'normalisation',
    'regularise', 'regularising', 'regularisation',
    'generalise', 'generalises', 'generalising', 'generalisation',
    'modelled', 'modelling', 'cancelled', 'cancelling', 'travelled',
    'travelling', 'labelled', 'labelling', 'fulfilled', 'fulfilling',
    'enrolled', 'enrolling', 'enrolment','Ethereum','ethereum',
    'licence', 'licences', 'defence', 'offence', 'practise', 'practising',
    'enquiry', 'enquiries', 'whilst', 'amongst',
    'laude', 'summa', 'magna', 'cum', 'alma', 'mater', 'emeritus',
    'curriculum', 'vitae', 'curricula', 'alumnus', 'alumni', 'alumna',
    'alumnae', 'doctorate', 'baccalaureate',
    'customizable', 'customisable', 'configurable', 'configurability',
    'rollout', 'rollouts', 'rollback', 'rollbacks',
    'workflow', 'workflows', 'pipeline', 'pipelines',
    'codebase', 'codebases', 'subteam', 'subteams', 'toolkit', 'toolkits',
    'dashboard', 'dashboards', 'sandbox', 'sandboxes', 'sandboxed',
    'realtime', 'multi-tenant', 'multitenant', 'plug-and-play',
    'low-code', 'no-code', 'open-source', 'cross-platform',
    'use-case', 'use-cases', 'end-to-end', 'go-to-market',
    'agile', 'scrum', 'kanban', 'jira', 'confluence', 'figma',
    'async', 'asyncio', 'aiohttp', 'fastapi', 'starlette', 'uvicorn',
    'numpy', 'pandas', 'scikit', 'sklearn', 'matplotlib', 'seaborn',
    'pytorch', 'tensorflow', 'keras', 'xgboost', 'lightgbm', 'catboost',
    'huggingface', 'transformers', 'langchain', 'llamaindex',
    'openai', 'anthropic', 'gemini', 'mistral', 'cohere',
    'postgres', 'postgresql', 'postgre',  
    'mongodb', 'mongo', 'redis', 'memcached', 'elasticsearch', 'opensearch',
    'kafka', 'rabbitmq', 'celery', 'airflow', 'kubeflow', 'mlflow',
    'kubernetes', 'docker', 'helm', 'terraform', 'ansible', 'jenkins',
    'gitlab', 'bitbucket', 'github', 'githubs',
    'devops', 'mlops', 'finops', 'secops', 'gitops',
    'ci-cd', 'cicd', 'sso', 'oauth', 'jwt', 'graphql', 'restful',
    'crud', 'orm', 'cdn', 'cdns', 'dns', 'tls', 'ssl', 'tcp', 'udp',
    'lstm', 'lstms', 'rnn', 'rnns', 'cnn', 'cnns', 'gan', 'gans',
    'nlp', 'cnn', 'ann', 'ai-powered', 'ml-driven',
    'frontend', 'backend', 'fullstack', 'full-stack',
    'frontends', 'backends',
    'iOS', 'Android', 'macOS', 'watchOS', 'tvOS', 'iPadOS',
    'civillines', 'cantt', 'cantonment', 'gulberg', 'defence',
    'lahore', 'karachi', 'islamabad', 'rawalpindi', 'faisalabad',
    'multan', 'peshawar', 'quetta', 'hyderabad', 'sialkot',
    'gujranwala', 'bahawalpur', 'sargodha', 'mardan', 'sahiwal',
    'muzaffarabad', 'mirpur', 'gilgit', 'skardu', 'abbottabad',
    'mansehra', 'haripur', 'dadu', 'larkana', 'sukkur',
    'punjab', 'sindh', 'balochistan', 'kpk', 'pakistan', 'pakistani',
    'mentee', 'mentees', 'onboarded', 'offboarded', 'offboarding',
    'reskilled', 'upskilled', 'crowdsourced', 'crowdsourcing',
    'open-sourced', 'opensourced',
    'low-latency', 'high-availability', 'high-throughput', 'high-volume',
})

_WORD_RE = re.compile(r"\b([A-Za-z][a-z]{2,})\b")

_BRITISH_SUFFIX_RE = re.compile(
    r'^([a-z]{3,})(is|ise|ises|ised|ising|isation|isations|iser|isers)$'
)

def _is_british_variant(wl):
    """True if `wl` looks like a British -ise/-isation form whose American
    -ize/-ization equivalent is in the spellchecker dictionary."""
    if not (SPELLCHECK_AVAILABLE and _spell is not None):
        return False
    m = _BRITISH_SUFFIX_RE.match(wl)
    if not m:
        return False
    stem, suffix = m.group(1), m.group(2)
    american = stem + suffix.replace('is', 'iz', 1)
    # Known to the American spellchecker → it's a real word in US English
    return american not in _spell.unknown([american])


def _spellcheck_words(sentence, proper_nouns, already_flagged_words):
    if not SPELLCHECK_AVAILABLE or _spell is None:
        return []

    errors = []
    seen = set()

    for m in _WORD_RE.finditer(sentence):
        word = m.group(1)
        wl   = word.lower()

        if word in already_flagged_words:
            continue
        if wl in _SPELL_WHITELIST or wl in proper_nouns:
            continue
        if any(term in wl for term in TECH_WHITELIST if len(term) >= 4):
            continue
        # v19.1: British-spelling safety net — catches -ise/-isation forms
        # not already in the explicit whitelist.
        if _is_british_variant(wl):
            continue
        if len(word) <= 3:
            continue
        if wl in seen:
            continue
        seen.add(wl)

        if wl not in _spell.unknown([wl]):
            continue

        # ── v21: VALID-INFLECTION GUARD ───────────────────────────────────
        _INFLECTION_SUFFIXES = (
            'es', 's', 'ed', 'ing', 'ings', 'er', 'ers',
            ' ly', 'ly', 'ment', 'ments', 'tion', 'tions',
        )
        _valid_inflection = False
        for suf in _INFLECTION_SUFFIXES:
            if wl.endswith(suf) and len(wl) - len(suf) >= 4:
                stem = wl[:-len(suf)]
                candidates = {stem}
                if suf in ('s', 'es', 'ed', 'ing', 'ings'):
                    candidates.add(stem + 'e')
                if suf in ('ed', 'ing', 'ings', 'er', 'ers'):
                    candidates.add(stem[:-1] if stem else stem)
                if any(c and c not in _spell.unknown([c]) for c in candidates):
                    _valid_inflection = True
                    break
        if _valid_inflection:
            continue
            
        _VALID_TRIM_SUFFIXES = (
            's', 'es', 'ed', 'd', 'ly', 'er', 'ers', 'or', 'ors',
            'ing', 'ings', 'tion', 'tions', 'sion', 'sions',
            'ness', 'ment', 'ments', 'ity', 'ities',
            'al', 'als', 'able', 'ables', 'ible', 'ibles',
            'ful', 'less', 'ive', 'ives', 'ous', 'ish',
            'ist', 'ists', 'ism', 'isms',
        )
        correction = None
        min_trim_len = max(4, int(len(wl) * 0.6))
        for trim in range(1, 5):
            alt    = wl[:-trim]
            suffix = wl[-trim:]
            if len(alt) < min_trim_len:
                continue
            # v21 — single-char trim only for real suffixes or doubled-letter typos
            doubled = (trim == 1 and len(alt) >= 1 and suffix == alt[-1])
            suffix_ok = (suffix in _VALID_TRIM_SUFFIXES) or doubled
            if suffix_ok and alt not in _spell.unknown([alt]):
                correction = alt
                break
                
        if not correction:
            fallback = _spell.correction(wl)
            if fallback and fallback != wl:
                # Character overlap from the START of the word
                common_prefix = 0
                for c1, c2 in zip(wl, fallback):
                    if c1 == c2: common_prefix += 1
                    else:        break
                # Require ≥ 70% leading-char overlap and ≤ 2 char length diff.
                # This blocks 'customizable'→'customable' (only 7/12 prefix
                # match) and 'asyncio'→'Asunción' (only 1 char match).
                length_diff = abs(len(fallback) - len(wl))
                prefix_ok   = common_prefix >= max(4, int(len(wl) * 0.7))
                if prefix_ok and length_diff <= 2:
                    correction = fallback

        if not correction or correction == wl:
            continue

        if correction in _spell.unknown([correction]):
            continue

        # Defensive: re-verify the prefix overlap (handles trim case too)
        min_len = min(len(wl), len(correction))
        prefix_len = 0
        for i in range(min_len):
            if wl[i] == correction[i]:
                prefix_len += 1
            else:
                break
        # v20.1 — raised threshold: prefix must share ≥ 70 % of the shorter
        # word's length, with a minimum of 4 chars. This blocks edit-
        # distance noise reaching this point.
        if prefix_len < max(4, int(min_len * 0.7)):
            continue

        # Inflection / suffix guard for FALLBACK corrections that slipped
        # through. trim=1 corrections (typos like 'projecty'→'project') are
        # allowed — only reject when ≥ 2 chars differ AND those chars don't
        # form a valid morphological suffix.
        if wl.startswith(correction):
            diff = len(wl) - len(correction)
            suffix_trimmed = wl[len(correction):]
            if diff >= 2 and diff <= 4 and suffix_trimmed not in _VALID_TRIM_SUFFIXES:
                continue

        if word[0].isupper():
            correction = correction[0].upper() + correction[1:]
        if word.isupper():
            correction = correction.upper()

        errors.append({
            'error':       word,
            'suggestion':  correction,
            'rule':        'SPELLCHECK',
            'category':    'TYPOS',
            'error_type':  'spelling',
            'explanation': f'Spelling: "{word}" → "{correction}"',
            'context':     sentence[:120],
            'offset':      m.start(),
            'length':      len(word),
        })

    return errors


# ───────────────────────────────────────────────────────────────────────────
# Sentence-level helpers
# ───────────────────────────────────────────────────────────────────────────
def _apply_corrections(original, errors):
    valid = [e for e in errors
             if 'offset' in e and e.get('suggestion') not in ('(see explanation)', '', None)]
    valid.sort(key=lambda e: e['offset'], reverse=True)
    result = original
    used = []
    for e in valid:
        s  = e['offset']
        en = s + e.get('length', len(e['error']))
        if any(not (en <= us or s >= ue) for us, ue in used):
            continue
        used.append((s, en))
        result = result[:s] + e['suggestion'] + result[en:]
    return result


def _short_explanation(error):
    rule  = error.get('rule', '')
    cat   = error.get('category', '')
    etype = error.get('error_type', '')
    msg   = (error.get('explanation') or '').strip()

    if rule in ('REPEATED_CHARS_TYPO', 'SPELLCHECK'):
        return msg
    if etype == 'capitalization':
        short = msg.split('.')[0]
        return short[:80] if short else 'Capitalization error'
    if etype == 'subject_verb_agreement':
        short = msg.split('.')[0]
        return short[:80] if short else 'Subject-verb agreement error'
    if etype == 'tense':
        short = msg.split('.')[0]
        return short[:80] if short else 'Verb tense error'
    if etype == 'punctuation':
        short = msg.split('.')[0]
        return short[:80] if short else 'Punctuation issue'
    if etype == 'sentence_structure':
        short = msg.split('.')[0]
        return short[:80] if short else 'Sentence structure issue'
    if cat in ('GRAMMAR', 'AGREEMENT', 'MORPHOLOGY'):
        short = msg.split('.')[0]
        return short[:80] if short else f"{cat.title()} issue"
    short = msg.split('.')[0][:80] if msg else f"{cat.title() or 'Grammar'} issue"
    return short


# ───────────────────────────────────────────────────────────────────────────
# Layer 3b: Pure-Python grammar checker (NO Java required)
# ───────────────────────────────────────────────────────────────────────────
_LONE_I_RE = re.compile(r'(?<![a-zA-Z])i(?![a-zA-Z])')

_SVA_PATTERNS = [
    (re.compile(r'\b(they|we)\s+(was)\b', re.I),
     2, 'were', 'Subject-verb agreement: use "were" with "{subj}"'),
    (re.compile(r'\b(he|she|it)\s+(are)\b', re.I),
     2, 'is', 'Subject-verb agreement: use "is" with "{subj}"'),
    (re.compile(r'\b(he|she|it)\s+(have)\b(?!\s+to\b)', re.I),
     2, 'has', 'Subject-verb agreement: use "has" with "{subj}"'),
    (re.compile(r"\b(he|she|it)\s+(don'?t)\b", re.I),
     2, "doesn't", 'Subject-verb agreement: use "doesn\'t" with "{subj}"'),
    (re.compile(r'\b(I|you|we|they)\s+(has)\b', re.I),
     2, 'have', 'Subject-verb agreement: use "have" with "{subj}"'),
    (re.compile(r'\b(he|she|it)\s+(were)\b(?!\s+to\b)', re.I),
     2, 'was', 'Subject-verb agreement: use "was" with "{subj}"'),
    (re.compile(r'\b(I|you|we|they)\s+(was)\b', re.I),
     2, 'were', 'Subject-verb agreement: use "were" with "{subj}"'),
]

_3PS_VERBS = {
    'go': 'goes', 'do': 'does', 'come': 'comes', 'make': 'makes',
    'run': 'runs', 'take': 'takes', 'give': 'gives', 'know': 'knows',
    'think': 'thinks', 'see': 'sees', 'want': 'wants', 'get': 'gets',
    'say': 'says', 'find': 'finds', 'tell': 'tells', 'ask': 'asks',
    'work': 'works', 'seem': 'seems', 'feel': 'feels', 'try': 'tries',
    'leave': 'leaves', 'call': 'calls', 'need': 'needs', 'become': 'becomes',
    'keep': 'keeps', 'let': 'lets', 'begin': 'begins', 'show': 'shows',
    'hear': 'hears', 'play': 'plays', 'move': 'moves', 'live': 'lives',
    'happen': 'happens', 'write': 'writes', 'provide': 'provides',
    'sit': 'sits', 'stand': 'stands', 'lose': 'loses', 'pay': 'pays',
    'meet': 'meets', 'include': 'includes', 'continue': 'continues',
    'set': 'sets', 'learn': 'learns', 'change': 'changes',
    'lead': 'leads', 'understand': 'understands', 'watch': 'watches',
    'follow': 'follows', 'stop': 'stops', 'create': 'creates',
    'speak': 'speaks', 'read': 'reads', 'spend': 'spends',
    'grow': 'grows', 'open': 'opens', 'walk': 'walks', 'win': 'wins',
    'teach': 'teaches', 'offer': 'offers', 'remember': 'remembers',
    'love': 'loves', 'consider': 'considers', 'appear': 'appears',
    'buy': 'buys', 'serve': 'serves', 'die': 'dies', 'send': 'sends',
    'build': 'builds', 'stay': 'stays', 'fall': 'falls', 'reach': 'reaches',
    'kill': 'kills', 'remain': 'remains', 'suggest': 'suggests',
    'raise': 'raises', 'pass': 'passes', 'sell': 'sells', 'require': 'requires',
    'report': 'reports', 'decide': 'decides', 'pull': 'pulls',
    'develop': 'develops', 'use': 'uses', 'help': 'helps', 'like': 'likes',
}
_3PS_PATTERN = re.compile(
    r'\b(he|she|it)\s+(' + '|'.join(re.escape(v) for v in _3PS_VERBS) + r')\b',
    re.I
)

_MISSING_ARTICLE_PATTERNS = [
    (re.compile(r'\b(become|became|becoming|am|is|are|was|were|be)\s+(software engineer|data scientist|web developer|project manager|team lead|frontend developer|backend developer|full stack developer)\b', re.I),
     'a', 'Missing article: add "a" before "{noun}"'),
    (re.compile(r'\b(in|at|to|from)\s+(office|university|college|company|organization|school|team)\b(?!\s+of\b)', re.I),
     None, 'Missing article: add "an/a" before "{noun}"'),
]


def _python_grammar_check(sentence, proper_nouns, is_continuation=False):
    """
    Layer 3b: Pure-Python grammar checker — NO Java/LanguageTool required.

    is_continuation: when True, skip the sentence-start capitalization check
                     (section 2) because this line is a mid-sentence PDF fragment.
                     Note: standalone "i" (section 1) is still always checked.
    """
    errors = []
    seen_offsets = set()

    def _offset_used(start, length):
        rng = set(range(start, start + length))
        if rng & seen_offsets:
            return True
        seen_offsets.update(rng)
        return False

    # ── 1. Lowercase "i" as standalone pronoun ────────────────────────────
    # Always checked — "i" is wrong regardless of position in sentence.
    for m in _LONE_I_RE.finditer(sentence):
        pos = m.start()
        if _offset_used(pos, 1):
            continue
        errors.append({
            'error':       'i',
            'suggestion':  'I',
            'rule':        'I_LOWERCASE_PY',
            'category':    'CASING',
            'error_type':  'capitalization',
            'explanation': 'The pronoun "I" should always be capitalized.',
            'offset':      pos,
            'length':      1,
            'context':     sentence[:120],
        })

    # ── 2. Sentence-start capitalization ──────────────────────────────────
    # SKIPPED for continuation lines — the first word is mid-sentence, not
    # the start of a new sentence. PDF extraction split it across lines.
    if not is_continuation:
        stripped = sentence.lstrip()
        if stripped and stripped[0].isalpha() and stripped[0].islower():
            offset = len(sentence) - len(stripped)
            if not _offset_used(offset, 1):
                errors.append({
                    'error':       stripped[0],
                    'suggestion':  stripped[0].upper(),
                    'rule':        'UPPERCASE_SENTENCE_START_PY',
                    'category':    'CASING',
                    'error_type':  'capitalization',
                    'explanation': 'Sentences should start with a capital letter.',
                    'offset':      offset,
                    'length':      1,
                    'context':     sentence[:120],
                })

    # ── 3. Subject-verb agreement ─────────────────────────────────────────
    for pattern, verb_group, correction, expl_tmpl in _SVA_PATTERNS:
        for m in pattern.finditer(sentence):
            subj = m.group(1)
            verb = m.group(verb_group)
            start = m.start(verb_group)
            if _offset_used(start, len(verb)):
                continue
            corr = correction
            if verb[0].isupper():
                corr = correction[0].upper() + correction[1:]
            errors.append({
                'error':       verb,
                'suggestion':  corr,
                'rule':        'SUBJ_VERB_AGREEMENT_PY',
                'category':    'AGREEMENT',
                'error_type':  'subject_verb_agreement',
                'explanation': expl_tmpl.format(subj=subj),
                'offset':      start,
                'length':      len(verb),
                'context':     sentence[:120],
            })

    # ── 4. Third-person singular present tense ────────────────────────────
    for m in _3PS_PATTERN.finditer(sentence):
        subj = m.group(1)
        verb = m.group(2)
        verb_lower = verb.lower()
        if verb_lower not in _3PS_VERBS:
            continue
        start = m.start(2)
        if _offset_used(start, len(verb)):
            continue

        pre_text = sentence[:m.start()].lower().rstrip()
        skip = False
        for modal in ('can', 'could', 'will', 'would', 'shall', 'should',
                       'may', 'might', 'must', "didn't", "doesn't", "did",
                       "don't", 'to', "let's", 'let', 'not'):
            if pre_text.endswith(modal):
                skip = True
                break
        if skip:
            continue

        correction = _3PS_VERBS[verb_lower]
        if verb[0].isupper():
            correction = correction[0].upper() + correction[1:]
        errors.append({
            'error':       verb,
            'suggestion':  correction,
            'rule':        'THIRD_PERSON_SINGULAR_PY',
            'category':    'GRAMMAR',
            'error_type':  'tense',
            'explanation': f'Third-person singular: "{subj} {verb}" should be "{subj} {correction}".',
            'offset':      start,
            'length':      len(verb),
            'context':     sentence[:120],
        })

    # ── 5. Missing articles ───────────────────────────────────────────────
    for pattern, article, expl_tmpl in _MISSING_ARTICLE_PATTERNS:
        for m in pattern.finditer(sentence):
            preword = m.group(1)
            noun    = m.group(2)
            insert_pos = m.start(2)
            if _offset_used(insert_pos, 0):
                continue
            art = article if article else ('an' if noun[0].lower() in 'aeiou' else 'a')
            errors.append({
                'error':       noun,
                'suggestion':  f'{art} {noun}',
                'rule':        'MISSING_ARTICLE_PY',
                'category':    'GRAMMAR',
                'error_type':  'grammar',
                'explanation': expl_tmpl.format(noun=noun),
                'offset':      insert_pos,
                'length':      len(noun),
                'context':     sentence[:120],
            })

    # ── 6. Missing end punctuation ────────────────────────────────────────
    # NOTE: This check is intentionally DISABLED in the pure-Python fallback
    # (Layer 3b). CV bullet points almost never end with a period; LanguageTool
    # (Layer 3a) understands this and suppresses it. The Python engine does not,
    # causing hundreds of false-positive "missing period" errors on every resume.
    # This was the primary source of spurious grammar_count inflation when
    # LanguageTool was unavailable (e.g. no Java on the server).
    #
    # If you want to re-enable it, uncomment the block below — but expect a
    # significant increase in false-positives on resume bullet points.
    #
    # if not is_continuation:
    #     words = sentence.split()
    #     if (len(words) >= 6
    #         and sentence.rstrip()
    #         and sentence.rstrip()[-1] not in '.!?;:,)]\'"'
    #         and not sentence.rstrip().endswith('etc')
    #         ):
    #         ... (verb detection + error append)

    return errors




# ───────────────────────────────────────────────────────────────────────────
# v7-fixed — main check_grammar (4-layer with continuation-line fix)
# ───────────────────────────────────────────────────────────────────────────
def check_grammar(text):
    """
    v7-fixed — four-layer grammar checker.

    KEY FIX: PDF-split continuation lines no longer trigger false
    sentence-start capitalization errors.

    Logic:
      - Track whether the previous DESCRIPTIVE line ended with . ! ?
      - If it did NOT end with terminal punctuation, the current line is a
        continuation of that sentence → suppress sentence-start caps rules.
      - HEADING lines reset the tracker (new section = fresh sentence).
      - Standalone "i" is still always checked (correct in any position).

    Layers:
      1. Repeated-char scanner  (pure regex)
      2. Spellchecker           (pyspellchecker)
      3a. LanguageTool ENHANCED (needs Java)
      3b. Python grammar engine (pure Python fallback)
      4. Error-type classifier
    """
    text = fix_pdf_artifacts(text)

    proper_nouns  = _extract_proper_nouns(text)
    proper_nouns |= CUSTOM_PROPER_NOUNS

    issues = []

    # ── Continuation tracker ───────────────────────────────────────────────
    # True  = previous descriptive line ended the sentence → next is fresh
    # False = previous descriptive line did NOT end → next is a continuation
    prev_descriptive_ends_sentence = True   # assume clean start before first line

    in_skip_section = False   # v21 — True while inside awards/certs/achievements/etc.

    for line in text.split('\n'):
        switch = _detect_section_switch(line)   # v21 — runs on EVERY line
        if switch == 'SKIP':
            in_skip_section = True
        elif switch == 'GRADE':
            in_skip_section = False

        line_type = _classify_line(line)

        # Non-descriptive lines: update tracker and skip grammar check
        if line_type != 'DESCRIPTIVE':
            if line_type == 'HEADING':
                prev_descriptive_ends_sentence = True
            continue

        # v21 — skip grammar inside no-grammar sections
        if in_skip_section:
            prev_descriptive_ends_sentence = _line_ends_sentence(line)
            continue
        # ── This is a DESCRIPTIVE line ────────────────────────────────────
        # Strip bullet markers first so cleaned is available for both the
        # column-merge check and the grammar layers below.
        cleaned = _BULLET_RE.sub('', line).strip()
        if not cleaned or len(cleaned) < 8:
            # Still update the tracker even for very short lines
            prev_descriptive_ends_sentence = _line_ends_sentence(line)
            continue

        # is_continuation is True when EITHER:
        #   (a) the previous descriptive line did not end with . ! ?
        #       → this line is the tail of that sentence (normal line-wrap)
        #   (b) this line itself contains ". [lowercase]" mid-line
        #       → PDF column-merge artifact; two fragments concatenated
        #       → e.g. "exceeded company targets by 15%. analytics solution."
        is_continuation = (
            not prev_descriptive_ends_sentence
            or _is_column_merge_line(cleaned)
            # v19 — lines beginning with a participle (cutting, achieving, ...)
            # are almost always right-column fragments interleaved by PDF
            # extraction, not real new sentences.
            or _starts_as_participle_fragment(cleaned)
            # v19 — in a CV, no real sentence ever starts with a lowercase
            # letter, so any lowercase line-start must be a continuation /
            # fragment, not a new sentence (so don't flag it for caps).
            or (cleaned[0].isalpha() and cleaned[0].islower())
        )

        # Update tracker for the NEXT iteration using this line's ending
        prev_descriptive_ends_sentence = _line_ends_sentence(line)

        # ── Layer 1: Repeated-char typos ──────────────────────────────────
        line_errors = _find_repeated_char_typos(cleaned, proper_nouns)
        seen_words  = {e['error'] for e in line_errors}

        # ── Layer 2: Spellchecker ─────────────────────────────────────────
        spell_errors = _spellcheck_words(cleaned, proper_nouns, seen_words)
        line_errors.extend(spell_errors)
        seen_words.update(e['error'] for e in spell_errors)

        # ── Layer 3a: LanguageTool ────────────────────────────────────────
        if GRAMMAR_AVAILABLE:
            try:
                matches = grammar_tool.check(cleaned)
            except Exception:
                matches = []

            for m in matches:
                flagged    = m.matched_text.strip()
                flo        = flagged.lower()
                category   = m.category
                rule       = m.rule_id
                suggestion = m.replacements[0] if m.replacements else '(see explanation)'
                message    = m.message or ''

                # ── CONTINUATION-LINE FIX (LanguageTool path) ────────────
                # If this line continues the previous sentence, suppress any
                # rule that only fires because the first word isn't capitalised.
                # We check offset == 0 to confirm it's flagging the line-start.
                if is_continuation and m.offset == 0:
                    if rule in _SENTENCE_START_CAP_RULES:
                        continue
                    # Also catch generic CASING errors on the very first char
                    if (category == 'CASING'
                            and m.error_length <= 2
                            and flo == flagged):          # only-lowercase mismatch
                        continue

                if flagged in seen_words:                                          continue
                if flo in proper_nouns:                                            continue
                if any(pn in flo for pn in proper_nouns if len(pn) > 2):           continue
                if flo in TECH_WHITELIST:                                          continue
                if any(tech in flo for tech in TECH_WHITELIST if len(tech) >= 4): continue
                
                if _is_pdf_merge_artifact(flagged):                                continue
                if _is_structural_artifact(flagged, rule, category, suggestion):   continue
                if _is_camelcase_fragment(cleaned, m):                             continue
                if _is_british_american_spelling(m):                               continue
                if len(flagged) < 1:                                               continue

                force_allow = rule in _ALWAYS_ALLOW_RULES

                if not force_allow:
                    if category in SKIP_CATEGORIES:                                continue
                    if any(p in rule for p in SKIP_RULE_PATTERNS):                 continue
                    if rule in _RESUME_PUNCTUATION_SKIP_RULES:                     continue
                    if flagged.isupper() and len(flagged) <= 6:                    continue
                    if rule in ('EN_A_VS_AN', 'A_VS_AN') or 'a_vs_an' in rule.lower(): continue
                    if suggestion and suggestion.lower().strip() == flo.strip():   continue
                    is_core = category in ('GRAMMAR', 'AGREEMENT', 'MORPHOLOGY', 'CASING', 'PUNCTUATION')
                    if not is_core:
                        if not m.replacements:                                     continue
                        if m.replacements[0].lower() == flo:                       continue
                    if category == 'TYPOS' and len(flagged) <= 5:                  continue

                if flo in {e['error'].lower() for e in line_errors}:               continue

                error_type = _classify_error_type(rule, category, message)

                line_errors.append({
                    'error':       flagged,
                    'suggestion':  suggestion,
                    'rule':        rule,
                    'category':    category,
                    'error_type':  error_type,
                    'explanation': message,
                    'offset':      m.offset,
                    'length':      m.error_length,
                    'context':     cleaned[:120],
                })

        # ── Layer 3b: Python grammar fallback ─────────────────────────────
        if not GRAMMAR_AVAILABLE:
            py_errors = _python_grammar_check(
                cleaned,
                proper_nouns,
                is_continuation=is_continuation,   # ← pass the flag
            )
            for pe in py_errors:
                pe_word = pe['error'].lower()
                if pe_word in {e['error'].lower() for e in line_errors}:
                    continue
                if pe_word in TECH_WHITELIST or pe_word in proper_nouns:
                    continue
                line_errors.append(pe)

        if not line_errors:
            continue

        corrected = _apply_corrections(cleaned, line_errors)
        if corrected == cleaned:
            continue

        # ── Build output ──────────────────────────────────────────────────
        detected_errors = []
        seen_exp = set()
        parts = []
        for e in line_errors:
            etype = e.get('error_type', _classify_error_type(
                e.get('rule', ''), e.get('category', ''), e.get('explanation', '')
            ))
            exp = _short_explanation(e)
            detected_errors.append({
                'error_type':    etype,
                'original':      e['error'],
                'corrected':     e.get('suggestion', ''),
                'explanation':   exp,
            })
            if exp and exp not in seen_exp:
                seen_exp.add(exp)
                parts.append(exp)

        explanation = ' | '.join(parts[:6])

        type_counts = {}
        for de in detected_errors:
            t = de['error_type']
            type_counts[t] = type_counts.get(t, 0) + 1
        dominant_type = max(type_counts, key=type_counts.get) if type_counts else 'grammar'

        first = line_errors[0]
        issues.append({
            'original':        cleaned,
            'corrected':       corrected,
            'explanation':     explanation,
            'error_type':      dominant_type,
            'detected_errors': detected_errors,
            'original_text':   cleaned,
            'corrected_text':  corrected,
            'error':           first['error'],
            'suggestion':      first['suggestion'],
            'rule':            first.get('rule', ''),
            'category':        first.get('category', ''),
            'context':         cleaned[:120],
        })

    return len(issues), issues[:15]




# only for dependency(ignore)

# import os

# os.environ["JAVA_HOME"] = r"D:\bin"
# os.environ["PATH"] += os.pathsep + r"D:\bin"



# import os
# only for dependency(ignore)

# os.environ["JAVA_HOME"] = r"D:\bin"
# os.environ["PATH"] += os.pathsep + r"D:\bin"
# os.environ["LANGUAGE_TOOL_JAR"] = r"D:\bin"



# import tempfile, os
# only for dependency(ignore)

# print("TEMP:", tempfile.gettempdir())
# print("JAVA_HOME:", os.environ.get("JAVA_HOME"))


# ## 📊 Section 11 — 9-Dimension Weighted Scoring Engine (v3)
# 
# ### Scoring Weights
# 
# | # | Dimension | Weight | Max Points |
# |---|---|---|---|
# | 1 | Grammar & Spelling | 15% | 15 |
# | 2 | Section Completeness | 20% | 20 |
# | 3 | Bullet Points | 10% | 10 |
# | 4 | Action Verbs | 10% | 10 |
# | 5 | Professional Tone | 10% | 10 |
# | 6 | Readability | 10% | 10 |
# | 7 | Technical Skills | 10% | 10 |
# | 8 | Projects Quality | 10% | 10 |
# | 9 | Quantified Achievements | 5% | 5 |
# 
# ### Key v3 Fixes
# - **Bullet detection**: Two-layer hybrid approach — real chars + implied bullets (for Canva/design PDFs)
# - **Section detection**: Must appear as a header line (not buried in body text)
# - **Section scoring**: Missing critical sections (Experience, Skills, Education) get hard deductions
# 
# ### Score → Grade Map
# | Score | Grade |
# |---|---|
# | 95–100 | Exceptional |
# | 85–94 | Excellent |
# | 70–84 | Good |
# | 50–69 | Satisfactory |
# | <50 | Weak |


# ── Action verbs ──────────────────────────────────────────────────────────────
STRONG_VERBS = [
    'led', 'built', 'developed', 'designed', 'managed', 'created',
    'implemented', 'launched', 'improved', 'optimized', 'delivered',
    'architected', 'automated', 'engineered', 'deployed', 'integrated',
    'established', 'increased', 'reduced', 'achieved', 'collaborated',
    'mentored', 'streamlined', 'migrated', 'configured', 'tested',
    'analyzed', 'researched', 'presented', 'coordinated', 'supervised',
    'spearheaded', 'revamped', 'accelerated', 'transformed', 'facilitated',
    'generated', 'secured', 'scaled', 'refactored', 'resolved',
    'maintained', 'contributed'
]

# ── Leadership verbs (used by Senior tier scoring + improvement plan) ─────────
LEADERSHIP_VERBS = ['led', 'managed', 'mentored', 'architected', 'spearheaded']

# ── Cloud / DevOps / Architecture skills (Senior tier technical-skills bonus) ─
CLOUD_DEVOPS_ARCH_SKILLS = [
    'docker', 'kubernetes', 'aws', 'azure', 'gcp', 'terraform', 'ci/cd',
    'jenkins', 'ansible', 'microservices', 'architecture', 'system design',
    'cloud', 'devops',
]

# ── Section definitions ────────────────────────────────────────────────────────
CRITICAL_SECTIONS = {
    'Education':   ['education', 'academic', 'degree', 'university', 'college',
                    'bachelors', 'bachelor', 'masters', 'master', 'bsc', 'msc',
                    'b.sc', 'm.sc', 'b.tech', 'intermediate'],
    'Experience':  ['experience', 'work history', 'employment', 'internship',
                    'intern ', 'position', 'worked at', 'role'],
    'Skills':      ['skills', 'technical skills', 'technologies', 'competencies',
                    'expertise', 'proficiencies', 'languages'],
}
IMPORTANT_SECTIONS = {
    'Summary':        ['summary', 'objective', 'about me', 'about', 'profile',
                       'professional summary', 'career objective'],
    'Projects':       ['projects', 'project', 'portfolio'],
    'Certifications': ['certification', 'certificate', 'certified', 'credential'],
    'Achievements':   ['achievement', 'award', 'honor', 'recognition',
                       'accomplishment', 'winner', 'competition', 'hackathon'],
}

ROLE_TECH_SKILLS = {
    'Data Scientist':            ['python','pandas','numpy','scikit','sql','visualization','statistics','r','spark','tensorflow'],
    'Machine Learning Engineer': ['tensorflow','pytorch','keras','scikit','python','mlops','docker','api','feature engineering','deployment'],
    'Python Developer':          ['python','django','flask','rest api','sql','celery','redis','fastapi','unittest','git'],
    'Java Developer':            ['java','spring','hibernate','maven','junit','sql','microservices','rest api','docker','git'],
    'React Developer':           ['react','javascript','html','css','typescript','redux','next','git','rest api','jest'],
    'Full Stack Developer':      ['react','node','javascript','python','sql','mongodb','rest api','html','css','docker'],
    'Backend Developer':         ['python','node','java','sql','rest api','docker','microservices','redis','postgresql','kafka'],
    'Frontend Developer':        ['html','css','javascript','react','typescript','responsive','figma','git','webpack','sass'],
    'DevOps Engineer':           ['docker','kubernetes','ci/cd','linux','aws','terraform','jenkins','ansible','bash','monitoring'],
    'Cloud Engineer':            ['aws','azure','gcp','linux','terraform','networking','iam','serverless','kubernetes','cost'],
    'AI Engineer':               ['python','tensorflow','pytorch','llm','bert','transformers','nlp','api','docker','mlops'],
    'Cybersecurity Analyst':    ['network security','linux','penetration testing','firewalls','siem','kali','vulnerability','incident'],
    'Mobile App Developer':      ['flutter','dart','android','ios','kotlin','swift','firebase','rest api','mobile','state management'],
    'UI/UX Developer':           ['figma','wireframing','prototyping','user research','design systems','adobe xd','usability','accessibility'],
    'Database Administrator':    ['sql','mysql','postgresql','query optimization','schema','indexing','backup','replication','stored procedures'],
    'Software Developer':        ['python','java','javascript','git','sql','api','algorithms','data structures','testing','agile'],
    'QA Engineer':               ['manual testing','test cases','selenium','bug reporting','test automation','cypress','jira','api testing','postman','regression'],
    'ETL Developer':             ['etl','sql','data pipelines','python','informatica','talend','spark','airflow','data warehousing','transformation'],
    'DotNet Developer':          ['.net','c#','asp.net','sql','visual studio','entity framework','azure','rest api','unit testing','docker'],
    'Blockchain Developer':     ['solidity','ethereum','smart contracts','web3','hardhat','truffle','nft','defi','cryptography','ipfs'],
    'Site Reliability Engineer': ['linux','kubernetes','monitoring','ci/cd','automation','prometheus','grafana','sre','incident management','chaos engineering'],
    'Security Engineer':         ['networking','security','firewall','linux','tcp/ip','vpn','ids/ips','siem','penetration testing','cisco'],
    'SQL Developer':             ['sql','stored procedures','database design','mysql','postgresql','query optimization','indexing','views','triggers','data warehousing'],
    'Business Analyst':          ['business analysis','requirements gathering','sql','excel','power bi', 'tableau', 'jira','agile','stakeholder management','data analysis'],
}



# ── Section detection ─────────────────────────────────────────────────────────
def detect_sections(text):
    """
    Headers must appear as standalone/near-standalone lines to avoid
    body-text phrases being counted as section headers.
    """
    lines      = text.split('\n')
    text_lower = text.lower()
    p_crit, m_crit, p_imp, m_imp = [], [], [], []

    def _found_as_header(keywords):
        for line in lines:
            s = line.strip().lower()
            if s and len(s) <= 50 and any(kw in s for kw in keywords):
                return True
        return any(kw in text_lower for kw in keywords)  # fallback

    for sec, kws in CRITICAL_SECTIONS.items():
        (p_crit if _found_as_header(kws) else m_crit).append(sec)
    for sec, kws in IMPORTANT_SECTIONS.items():
        (p_imp if _found_as_header(kws) else m_imp).append(sec)

    return p_crit, m_crit, p_imp, m_imp

# ── Bug 4 fix: additive bullet count ──────────────────────────────────────────
def count_bullets(text):
    """
    Two-layer bullet detection.

    Bug 4 fixed: real_count is now TRUE + AMBIG + NUMBERED (additive),
    not max(true, ambig+numbered).
    """
    lines = text.split('\n')

    TRUE_BULLETS = [
        '•', '●', '▪', '○', '▶', '▸', '✓', '✔', '‣','•',
        '\uf0b7', '\uf0b2',
        '\u25aa', '\u25cf', '\u2023', '\u25b6',
        '\u2713', '\u2714', '\u2022','\u2699'
    ]

  

    AMBIG_BULLETS = ('-', '*', '–')

    true_bullet_count = sum(text.count(ch) for ch in TRUE_BULLETS)

    ambig_lines       = [
        l for l in lines
        if l.strip() and l.strip()[0] in AMBIG_BULLETS and len(l.strip()) > 4
    ]
    numbered_lines    = [
        l for l in lines if re.match(r'^\s*\d{1,2}[.)\s]\s+\S', l)
    ]

    real_count    = true_bullet_count + len(ambig_lines) + len(numbered_lines)

    implied_count = 0
    if real_count < 3:
        implied_count = _count_implied_bullets(text, lines)

    final = max(real_count, implied_count)
    return final, real_count, implied_count


def _count_implied_bullets(text, lines):
    """Counts list-like lines in graphical-bullet sections (Canva-style PDFs)."""
    LIST_SECTION_SIGNALS = [
        'skills', 'certifications', 'achievements', 'awards',
        'languages', 'interests', 'technical skills', 'competencies',
        'tools', 'publications', 'leadership'
    ]
    ALL_SECTION_SIGNALS = [
        'education', 'experience', 'projects', 'summary', 'objective', 'about'
    ] + LIST_SECTION_SIGNALS

    def _is_header(s):
        sl = s.lower().strip()
        return (len(s) <= 55 and any(sig in sl for sig in ALL_SECTION_SIGNALS)) or (s.isupper() and len(s) <= 40)

    def _is_meta(s):
        return bool(
            re.match(r'^\d{4}', s) or re.match(r'^[\+\(]?\d', s)
            or 'http' in s.lower() or '@' in s
            or (s.isupper() and len(s) <= 50)
        )

    in_list_section = False
    candidate_runs  = []
    current_run     = []

    for line in lines:
        s = line.strip()
        if not s:
            if len(current_run) >= 2:
                candidate_runs.extend(current_run)
            current_run = []
            continue
        sl = s.lower()
        if _is_header(s):
            in_list_section = any(sig in sl for sig in LIST_SECTION_SIGNALS)
            if len(current_run) >= 2:
                candidate_runs.extend(current_run)
            current_run = []
            continue
        if not in_list_section or _is_meta(s):
            continue
        if 5 <= len(s) <= 120 and (s[0].isupper() or s[0].isdigit()):
            current_run.append(s)
        else:
            if len(current_run) >= 2:
                candidate_runs.extend(current_run)
            current_run = []

    if len(current_run) >= 2:
        candidate_runs.extend(current_run)
    return len(candidate_runs)







_ROLE_BANK_ALIASES = {
    'cyber security analyst': 'Cybersecurity Analyst',
}

def _score_tech_skills(text, predicted_role, tier=None):
    """
    Score technical skill richness against role-specific skill bank.

    Tier-aware thresholds (v15):
        Entry  → ratio ≥ 0.25 → full marks
        Mid    → ratio ≥ 0.45 → full marks
        Senior → ratio ≥ 0.65 → full marks
                 + must include ≥ 1 cloud/DevOps/architecture skill
                 if missing → deduct 2 extra points (cap 0)
        None   → current default behavior (ratio ≥ 0.7 → full marks)
    """
    tl      = text.lower()
    _pl     = predicted_role.strip().lower()
    matched = _ROLE_BANK_ALIASES.get(_pl)
    if matched is None or matched not in ROLE_TECH_SKILLS:
        matched = 'Software Developer'
        for key in ROLE_TECH_SKILLS:
            if key.lower() in _pl or _pl in key.lower():
                matched = key
                break
    bank  = ROLE_TECH_SKILLS[matched]
    
    found = [s for s in bank if s in tl]
    ratio = len(found) / max(len(bank), 1)

    if tier == 'Entry':
        if   ratio >= 0.25: score = 10
        elif ratio >= 0.15: score = 7
        elif ratio >= 0.05: score = 4
        else:               score = 1
        note = f'Entry-tier bar: {len(found)}/{len(bank)} skills for {matched} (ratio {ratio:.2f}).'

    elif tier == 'Mid':
        if   ratio >= 0.45: score = 10
        elif ratio >= 0.25: score = 7
        elif ratio >= 0.15: score = 4
        else:               score = 1
        note = f'Mid-tier bar: {len(found)}/{len(bank)} skills for {matched} (ratio {ratio:.2f}).'

    elif tier == 'Senior':
        if   ratio >= 0.65: score = 10
        elif ratio >= 0.45: score = 7
        elif ratio >= 0.25: score = 4
        else:               score = 1
        # Senior bonus check: must have ≥ 1 cloud/DevOps/architecture skill
        has_cloud = any(s in tl for s in CLOUD_DEVOPS_ARCH_SKILLS)
        if not has_cloud:
            score = max(0, score - 2)
            note = (f'Senior-tier bar: {len(found)}/{len(bank)} skills for {matched} '
                    f'(ratio {ratio:.2f}). Missing cloud/DevOps/architecture skills (-2).')
        else:
            note = (f'Senior-tier bar: {len(found)}/{len(bank)} skills for {matched} '
                    f'(ratio {ratio:.2f}). Cloud/DevOps presence detected.')

    else:  # tier is None — current default behavior
        if   ratio >= 0.7:  score, note = 10, f'Strong tech skills ({len(found)}/{len(bank)} for {matched}).'
        elif ratio >= 0.45: score, note = 7,  f'Good tech skills ({len(found)}/{len(bank)} for {matched}).'
        elif ratio >= 0.25: score, note = 4,  f'Some tech skills ({len(found)}/{len(bank)} for {matched}). Add more.'
        else:               score, note = 1,  f'Weak tech skills ({len(found)}/{len(bank)} for {matched}). Major gap.'

    return score, note, found


def _score_projects(text):
    """Score project quality: GitHub link, descriptions, tech stack."""
    tl, score, notes = text.lower(), 0, []
    if 'github.com' in tl: score += 4; notes.append('GitHub link present')
    else:                               notes.append('No GitHub link')
    if any(w in tl for w in ['project','built','developed','created','implemented']):
        score += 3; notes.append('Projects described')
    else:
        notes.append('No project descriptions')
    tech_hits = sum(1 for t in TECH_WHITELIST if t in tl)
    if   tech_hits >= 5: score += 3; notes.append('Tech stack mentioned')
    elif tech_hits >= 2: score += 1
    return min(score, 10), '; '.join(notes) + '.'


def _count_quantified_achievements(text):
    """Count quantified metrics: %, $, user counts, etc."""
    patterns = [
        r'\d+\s*%',
        r'\$\s*\d+',
        r'\d+[kKmMbB]\b',
        r'(increased|reduced|improved|decreased|boosted|grew)\s+by\s+\d+',
        r'\d+x\s*(faster|improvement|speed|better)',
        r'\d+\s+(users|clients|engineers|students|employees)',
        r'\d+\+\s*(projects|services|systems|features)',
        r'cgpa[:\s]+[\d\.]+',
    ]
    return len(re.findall('|'.join(patterns), text.lower()))


def _grammar_score(grammar_count):
    """Map grammar error count → score out of 15."""
    if grammar_count == 0:  return 15
    if grammar_count <= 2:  return 12
    if grammar_count <= 4:  return 8
    return 4


def analyze_resume(raw_text, predicted_role='Software Developer', grammar_count=0, tier=None):
    """
    Evaluates resume quality across 9 weighted dimensions.

    v15 — Now tier-aware. The same CV scores differently for Entry / Mid / Senior.

    Args:
        raw_text       (str): Extracted & preprocessed resume text
        predicted_role (str): ML-predicted tech role
        grammar_count  (int): Real grammar error count from check_grammar()
        tier           (str|None): Experience tier — 'Entry', 'Mid', 'Senior', or None.
                                   None = default scoring (fully backward compatible).

    Returns:
        (dict of 9 dimension results, list of missing section names)
    """
    tl    = raw_text.lower()
    lines = raw_text.split('\n')

    # CamelCase-aware word count
    _wc   = re.sub(r'([a-z]{2,})([A-Z])', r'\1 \2', raw_text)
    _wc   = re.sub(r'([A-Z]{2,})([A-Z][a-z])', r'\1 \2', _wc)
    words = len(_wc.split())

    results = {}

    # ── 1. Sections Completeness (max 20) ─────────────────────────────────────
    p_crit, m_crit, p_imp, m_imp = detect_sections(raw_text)
    all_missing = m_crit + m_imp
    crit_score  = len(p_crit) * 5
    imp_score   = min(len(p_imp) * 1.25, 5)
    sec_score   = round(min(crit_score + imp_score, 20))

    # Tier-aware Summary handling
    summary_missing = 'Summary' in m_imp
    if tier == 'Entry' and summary_missing:
        # Entry: Summary is optional — refund the 1.25 deduction so it doesn't hurt
        sec_score = round(min(sec_score + 1.25, 20))
    elif tier == 'Senior' and summary_missing:
        # Senior: Summary is CRITICAL — additional hard deduct of 5 points
        sec_score = max(0, sec_score - 5)

    sec_note    = (
        f'{len(p_crit)}/3 critical + {len(p_imp)}/4 important sections found.'
        + (f' Missing critical: {", ".join(m_crit)}.' if m_crit else '')
        + (f' Missing: {", ".join(m_imp)}.' if m_imp else '')
    )
    if tier == 'Senior' and summary_missing:
        sec_note += ' Senior tier: missing Summary penalized -5.'
    elif tier == 'Entry' and summary_missing:
        sec_note += ' Entry tier: Summary not required.'

    results['sections_completeness'] = {
        'score': sec_score, 'max': 20, 'note': sec_note,
        'detail': 'Critical: Education, Experience, Skills. Important: Summary, Projects, Certs, Achievements.'
    }

    # ── 2. Grammar & Spelling (max 15) ────────────────────────────────────────
    gram = _grammar_score(grammar_count)
    results['grammar_spelling'] = {
        'score': gram, 'max': 15,
        'note':  f'{grammar_count} real grammar issue(s). Score: {gram}/15.',
        'detail': 'Each confirmed grammar mistake deducts points.'
    }

    # ── 3. Bullet Points (max 10) ─────────────────────────────────────────────
    total_b, real_b, implied_b = count_bullets(raw_text)

    if total_b >= 8:
        bul_score, bul_note = 10, 'Excellent use of bullet points for readability and ATS scanning.'
    elif total_b >= 5:
        bul_score, bul_note = 7, 'Good bullet structure. Additional concise bullets could improve readability further.'
    elif total_b >= 2:
        bul_score, bul_note = 4, 'Limited bullet usage detected. Use more bullet points for clearer presentation.'
    else:
        bul_score, bul_note = 0, 'No structured bullet formatting detected. Add bullet points for experience, projects, and skills.'

    results['bullet_points'] = {
        'score': bul_score,
        'max': 10,
        'note': bul_note,
        'detail': 'Bullet formatting improves readability, recruiter scanning speed, and ATS parsing.',
        'bullet_count': total_b
    }

    # ── 4. Action Verbs (max 10) — tier-aware ─────────────────────────────────
    found_verbs = [v for v in STRONG_VERBS if v in tl]
    vc          = len(found_verbs)

    if tier == 'Entry':
        # Full marks at ≥ 3 verbs
        if   vc >= 3: verb_score = 10
        elif vc >= 2: verb_score = 7
        elif vc >= 1: verb_score = 4
        else:         verb_score = 0
        verb_note = f'Entry-tier bar: {vc} action verb(s) found.'

    elif tier == 'Mid':
        # Full marks at ≥ 5 verbs
        if   vc >= 5: verb_score = 10
        elif vc >= 3: verb_score = 7
        elif vc >= 1: verb_score = 4
        else:         verb_score = 0
        verb_note = f'Mid-tier bar: {vc} action verb(s) found.'

    elif tier == 'Senior':
        # Full marks at ≥ 8 verbs
        if   vc >= 8: verb_score = 10
        elif vc >= 5: verb_score = 7
        elif vc >= 3: verb_score = 4
        elif vc >= 1: verb_score = 1
        else:         verb_score = 0
        # Senior must contain at least 1 leadership verb
        has_lead = any(lv in tl for lv in LEADERSHIP_VERBS)
        if not has_lead:
            verb_score = max(0, verb_score - 2)
            verb_note  = (f'Senior-tier bar: {vc} action verb(s). '
                          f'No leadership verb (led/managed/mentored/architected/spearheaded) detected (-2).')
        else:
            verb_note  = f'Senior-tier bar: {vc} action verb(s). Leadership verb present.'

    else:  # tier is None — current default behavior
        if   vc >= 8: verb_score, verb_note = 10, f'Excellent action verbs ({vc}: {", ".join(found_verbs[:5])}...).'
        elif vc >= 5: verb_score, verb_note = 7,  f'Good action verbs ({vc}: {", ".join(found_verbs[:4])}).'
        elif vc >= 2: verb_score, verb_note = 4,  f'Only {vc} action verbs. Use: Led, Built, Optimized, Deployed.'
        else:         verb_score, verb_note = 0,  'No strong action verbs. Start bullets with: Developed, Led, Implemented.'

    results['action_verbs'] = {
        'score': verb_score, 'max': 10, 'note': verb_note,
        'detail': 'Strong verbs make experience descriptions impactful and ATS-friendly.',
        'found': found_verbs
    }

    # ── 5. Professional Tone (max 10) — tier-aware ────────────────────────────
    informal_pats = [
        r'\bi am\b', r'\bi have\b', r'\bi was\b', r'\bi will\b',
        r'\bmy name is\b', r'\bhire me\b', r'\bplease hire\b',
        r'\bi think\b', r'\bi believe\b', r'\bi can\b', r'\bi want\b',
    ]
    informal_hits = sum(len(re.findall(p, tl)) for p in informal_pats)

    if tier == 'Entry':
        # Up to 3 informal hits before penalty starts
        if   informal_hits <= 3: tone_score = 10
        elif informal_hits <= 5: tone_score = 7
        elif informal_hits <= 8: tone_score = 4
        else:                    tone_score = 1
        tone_note = f'Entry-tier tone: {informal_hits} informal phrase(s).'

    elif tier == 'Mid':
        # Up to 2 informal hits
        if   informal_hits <= 2: tone_score = 10
        elif informal_hits <= 4: tone_score = 7
        elif informal_hits <= 6: tone_score = 4
        else:                    tone_score = 1
        tone_note = f'Mid-tier tone: {informal_hits} informal phrase(s).'

    elif tier == 'Senior':
        # Up to 1 informal hit — strict
        if   informal_hits <= 1: tone_score = 10
        elif informal_hits <= 3: tone_score = 7
        elif informal_hits <= 5: tone_score = 4
        else:                    tone_score = 1
        tone_note = f'Senior-tier tone: {informal_hits} informal phrase(s). Strict tone expected.'

    else:  # tier is None — current default behavior
        if   informal_hits == 0: tone_score, tone_note = 10, 'Professional tone throughout.'
        elif informal_hits <= 2: tone_score, tone_note = 7,  f'{informal_hits} first-person phrase(s). Avoid "I am", "I have".'
        elif informal_hits <= 5: tone_score, tone_note = 4,  f'{informal_hits} informal phrases. Remove first-person language.'
        else:                    tone_score, tone_note = 1,  f'{informal_hits} informal phrases. Major rewrite needed.'

    results['professional_tone'] = {
        'score': tone_score, 'max': 10, 'note': tone_note,
        'detail': 'Use implied-subject style: "Developed X" not "I developed X".'
    }

    # ── 6. Readability (max 10) — tier-aware word-count ranges ────────────────
    if tier == 'Entry':
        # Optimal 150–500 words
        if   150 <= words <= 500: read_score, read_note = 10, f'Ideal Entry length ({words} words).'
        elif 100 <= words <  150: read_score, read_note = 6,  f'Short ({words} words). Aim for 150–500.'
        elif words > 500:         read_score, read_note = 5,  f'Long ({words} words). Trim toward 500.'
        else:                     read_score, read_note = 2,  f'Very sparse ({words} words). Add much more content.'

    elif tier == 'Mid':
        # Optimal 250–700 words (current default)
        if   250 <= words <= 700: read_score, read_note = 10, f'Ideal Mid length ({words} words).'
        elif 150 <= words <  250: read_score, read_note = 6,  f'Short ({words} words). Add project/experience detail.'
        elif words > 700:         read_score, read_note = 5,  f'Long ({words} words). Trim to ~700.'
        else:                     read_score, read_note = 2,  f'Very sparse ({words} words). Add much more content.'

    elif tier == 'Senior':
        # Optimal 400–900 words
        if   400 <= words <= 900: read_score, read_note = 10, f'Ideal Senior length ({words} words).'
        elif 250 <= words <  400: read_score, read_note = 6,  f'Short for Senior ({words} words). Aim for 400–900.'
        elif words > 900:         read_score, read_note = 5,  f'Long ({words} words). Trim toward 900.'
        else:                     read_score, read_note = 2,  f'Very sparse for Senior ({words} words). Major expansion needed.'

    else:  # tier is None — current default behavior
        if   250 <= words <= 700: read_score, read_note = 10, f'Ideal length ({words} words).'
        elif 150 <= words <  250: read_score, read_note = 6,  f'Short ({words} words). Add project/experience detail.'
        elif words > 700:         read_score, read_note = 5,  f'Long ({words} words). Trim to ~700 for one page.'
        else:                     read_score, read_note = 2,  f'Very sparse ({words} words). Add much more content.'

    results['readability'] = {
        'score': read_score, 'max': 10, 'note': read_note,
        'detail': 'Recruiters scan in ~7 sec. Dense, structured content wins.'
    }

    # ── 7. Technical Skills (max 10) — tier-aware ─────────────────────────────
    tech_score, tech_note, found_skills = _score_tech_skills(raw_text, predicted_role, tier=tier)
    results['technical_skills'] = {
        'score': tech_score, 'max': 10, 'note': tech_note,
        'detail': f'Evaluated against skill bank for: {predicted_role}.',
        'found': found_skills
    }

    # ── 8. Projects Quality (max 10) ──────────────────────────────────────────
    proj_score, proj_note = _score_projects(raw_text)
    results['projects_quality'] = {
        'score': proj_score, 'max': 10, 'note': proj_note,
        'detail': 'Projects need GitHub links, tech stack, and measurable outcomes.'
    }

    # ── 9. Quantified Achievements (max 5) — tier-aware ───────────────────────
    qc = _count_quantified_achievements(raw_text)

    if tier == 'Entry':
        # Need ≥ 1 metric for full marks
        if   qc >= 1: quant_score, quant_note = 5, f'Entry-tier bar met: {qc} quantified metric(s) found.'
        else:         quant_score, quant_note = 0, 'No quantified achievements detected. Add at least one metric.'

    elif tier == 'Mid':
        # Current default behavior: ≥ 4 full, ≥ 2 partial, = 1 minimal
        if   qc >= 4: quant_score, quant_note = 5, f'Mid-tier: excellent use of {qc} quantified achievements.'
        elif qc >= 2: quant_score, quant_note = 3, f'Mid-tier: {qc} metric(s) found — add more for full marks.'
        elif qc == 1: quant_score, quant_note = 1, 'Mid-tier: only 1 metric — add several more.'
        else:         quant_score, quant_note = 0, 'No quantified achievements detected.'

    elif tier == 'Senior':
        # Need ≥ 4 metrics for full marks — high bar
        if   qc >= 4: quant_score, quant_note = 5, f'Senior-tier bar met: {qc} quantified metric(s) demonstrate impact.'
        elif qc == 3: quant_score, quant_note = 3, f'Senior-tier: {qc} metric(s) — close, but seniors should show more business impact.'
        elif qc == 2: quant_score, quant_note = 1, 'Senior-tier: only 2 metrics — well below expectation for senior roles.'
        elif qc == 1: quant_score, quant_note = 0, 'Senior-tier: only 1 metric — senior CVs must quantify impact extensively.'
        else:         quant_score, quant_note = 0, 'Senior-tier: no quantified achievements — critical gap for senior roles.'

    else:  # tier is None — current default behavior
        if   qc >= 4: quant_score, quant_note = 5, 'Excellent use of quantified achievements and measurable impact.'
        elif qc >= 2: quant_score, quant_note = 3, 'Good use of metrics to support achievements and project outcomes.'
        elif qc == 1: quant_score, quant_note = 1, 'Limited measurable impact shown. Add more metrics to strengthen credibility.'
        else:         quant_score, quant_note = 0, 'No quantified achievements detected. Include percentages, accuracy scores, user counts, or performance improvements.'

    results['quantified_achievements'] = {
        'score': quant_score,
        'max': 5,
        'note': quant_note,
        'detail': 'Quantified achievements help recruiters understand real impact and performance.'
    }

    return results, all_missing


def calculate_score(quality_results):
    """
    Sums dimension scores → final 0–100 score.

    Pure, side-effect-free sum. No more in-place dict mutation.
    """
    return min(int(sum(d['score'] for d in quality_results.values())), 100)


def get_grade(score):
    if score >= 95: return 'Exceptional'
    if score >= 85: return 'Excellent'
    if score >= 70: return 'Good'
    if score >= 50: return 'Satisfactory'
    return 'Weak'


def quiz_eligible(score):
    """Resume Quality ≥ 70 → eligible. Simple, no confidence involved."""
    if score >= 70:
        return True,  f'Score {score}/100 meets the 70-point threshold. ✅ Eligible!'
    return False, f'Score {score}/100 is below 70. Improve your resume first.'


# ## 💪 Section 12 — Strengths & Weaknesses
# 
# Auto-generated from the 9 dimension scores:
# - **Strength** = dimension score ≥ 75% of its maximum
# - **Weakness** = dimension score < 50% of its maximum


DIMENSION_META = {
    'grammar_spelling':         {'label': 'Grammar & Spelling',        'strength': 'Clean, error-free writing',                            'weakness': 'Grammar/spelling errors'},
    'sections_completeness':    {'label': 'Resume Completeness',       'strength': 'All key sections present',                             'weakness': 'Missing important resume sections'},
    'bullet_points':            {'label': 'Bullet Formatting',         'strength': 'Well-structured bullet points for fast scanning',       'weakness': 'Insufficient bullet points'},
    'action_verbs':             {'label': 'Action Verbs',              'strength': 'Strong action verbs make experience dynamic',           'weakness': 'Weak action verbs'},
    'professional_tone':        {'label': 'Professional Tone',         'strength': 'Professional tone maintained throughout',               'weakness': 'First-person / informal language detected'},
    'readability':              {'label': 'Length & Readability',       'strength': 'Ideal length — concise and scannable',                 'weakness': 'Resume length is too short'},
    'technical_skills':         {'label': 'Technical Skill Coverage',   'strength': 'Strong technical skills for detected role',            'weakness': 'Technical skills insufficient for target role'},
    'projects_quality':         {'label': 'Projects Quality',           'strength': 'Well-described projects with GitHub links',            'weakness': 'Projects lack detail, GitHub links, or tech stack info'},
    'quantified_achievements':  {'label': 'Quantified Achievements',   'strength': 'Excellent use of metrics and numbers',                  'weakness': 'Achievements not quantified — add metrics and numbers'},
}


def detect_strengths_weaknesses(quality_results):
    """
    Strength threshold : >= 75% of dimension max
    Weakness threshold : <  50% of dimension max

    Returns:
        strengths  : list[str]  — human-readable strength labels
        weaknesses : list[str]  — human-readable weakness labels
        weak_dims  : list[str]  — dimension keys that scored < 50%
                                  (used by targeted improvement plan logic)
    """
    strengths  = []
    weaknesses = []
    weak_dims  = []
    for key, data in quality_results.items():
        ratio = data['score'] / max(data.get('max', 10), 1)
        meta  = DIMENSION_META.get(key, {})
        if ratio >= 0.75:
            strengths.append(meta.get('strength', key))
        elif ratio < 0.50:
            weaknesses.append(meta.get('weakness', key))
            weak_dims.append(key)
    return strengths, weaknesses, weak_dims




# ## 💡 Section 13 — Role-Based Improvement Plan (v12: Score-Aware Targeted Mode)
# 
# **v12 Improvement Plan Generation Rules:**
# 
# | Condition | Action |
# |---|---|
# | Score < 70 | **Full plan** — all 4 categories, all checks, comprehensive recommendations |
# | Score ≥ 70 + weaknesses detected | **Targeted plan** — only suggestions for specific weak dimensions |
# | Score ≥ 70 + no weaknesses | **No plan** — resume is sufficiently optimized |
# 
# **Key principles:**
# - Weakness analysis module has **higher priority** than overall score
# - Never generates suggestions for areas already meeting professional standards
# - No generic filler recommendations in targeted mode
# - All recommendations are specific, action-oriented, ATS-aware, and role-relevant
# 
# **4 categories** (populated only when relevant checks trigger):
# 
# 1. **Skill Gap Analysis** — missing must-have and good-to-have skills with impact + recommendation
# 2. **Technical Enhancement** — project quality, GitHub presence, quantified achievements
# 3. **Experience & Impact Upgrade** — bullet points, action verbs, measurable outcomes
# 4. **Communication & Clarity** — professional tone, readability, grammar
# 
# Each item follows the format:
# ```
# ▸ <Gap/Issue identified>
#   Impact: <Why this matters to recruiters>
#   Recommendation: <Specific, actionable fix>
# ```
# 


ROLE_REQUIREMENTS = {
    'Data Scientist':              {'must': ['python','pandas','sql','visualization','statistics'],    'good': ['tensorflow','pytorch','spark','tableau','r'],                    'tip': 'Quantify model accuracy gains and business impact of your analyses.'},
    'Machine Learning Engineer': {'must': ['python','tensorflow','pytorch','docker','api'],           'good': ['mlops','airflow','kubernetes','feature engineering','kubeflow'],   'tip': 'Describe model accuracy (e.g. F1=0.94) and production deployment details.'},
    'Python Developer':          {'must': ['python','django','flask','rest api','sql'],               'good': ['celery','redis','fastapi','docker','unittest'],                   'tip': 'Show API throughput, uptime %, or lines of test coverage.'},
    'Java Developer':            {'must': ['java','spring','sql','rest api','git'],                  'good': ['microservices','docker','junit','maven','kafka'],                 'tip': 'Mention transaction throughput and test coverage percentage.'},
    'React Developer':           {'must': ['react','javascript','html','css','git'],                 'good': ['typescript','redux','next.js','jest','rest api'],                'tip': 'Link live apps. Mention Core Web Vitals or Lighthouse score improvements.'},
    'Full Stack Developer':      {'must': ['react','node','javascript','sql','rest api'],            'good': ['docker','typescript','mongodb','aws','testing'],                 'tip': 'Describe full features built end-to-end with user impact metrics.'},
    'Backend Developer':         {'must': ['python','node','sql','rest api','docker'],               'good': ['redis','kafka','microservices','postgresql','kubernetes'],        'tip': 'Mention API response times, request volumes, and DB optimization wins.'},
    'Frontend Developer':        {'must': ['html','css','javascript','react','git'],                 'good': ['typescript','figma','webpack','responsive','accessibility'],     'tip': 'Link portfolio. Mention page load improvements or accessibility scores.'},
    'DevOps Engineer':           {'must': ['docker','kubernetes','ci/cd','linux','aws'],             'good': ['terraform','jenkins','ansible','prometheus','grafana'],           'tip': 'Describe infra scale -- server count, deployment frequency, uptime SLAs.'},
    'Cloud Engineer':            {'must': ['aws','azure','linux','terraform','networking'],          'good': ['gcp','kubernetes','iam','serverless','cost optimization'],        'tip': 'Mention cloud certifications and cost savings achieved (e.g. 30% reduction).'},
    'AI Engineer':               {'must': ['python','tensorflow','pytorch','nlp','docker'],          'good': ['llm','transformers','bert','mlops','rag'],                        'tip': 'Describe model accuracy, inference latency, and production scale.'},
    'Cybersecurity Analyst':     {'must': ['linux','penetration testing','firewalls','siem'],        'good': ['kali','ethical hacking','soc','incident response','ceh'],        'tip': 'Mention certifications (CEH, CISSP). Quantify vulnerabilities found.'},
    'Mobile App Developer':      {'must': ['flutter','dart','android','ios','firebase'],             'good': ['rest api','state management','push notifications','kotlin'],      'tip': 'Link Play Store / App Store apps. Mention downloads and ratings.'},
    'UI/UX Developer':           {'must': ['figma','wireframing','prototyping','user research'],    'good': ['adobe xd','usability testing','accessibility','design systems'],  'tip': 'Link Figma portfolio. Show before/after designs and user testing results.'},
    'Database Administrator':    {'must': ['sql','mysql','postgresql','query optimization'],         'good': ['mongodb','redis','indexing','backup','replication'],              'tip': 'Mention DB size managed and measured performance improvements.'},
    'Software Developer':        {'must': ['python','java','git','sql','algorithms'],               'good': ['docker','api','testing','agile','code review'],                  'tip': 'Add GitHub links. Mention code quality, test coverage, or team contributions.'},
    'QA Engineer':               {'must': ['manual testing','test cases','bug reporting','selenium'],'good': ['cypress','jira','api testing','postman','automation'],           'tip': 'Mention number of test cases, bugs found, and coverage achieved.'},
    'ETL Developer':             {'must': ['etl','sql','data pipelines','python'],                  'good': ['spark','airflow','talend','informatica','data warehousing'],      'tip': 'Describe data volumes processed and pipeline performance wins.'},
    'DotNet Developer':          {'must': ['.net','c#','asp.net','sql','visual studio'],            'good': ['azure','docker','entity framework','rest api','unit testing'],   'tip': 'Mention enterprise systems built and deployment environments.'},
    'Blockchain Developer':      {'must': ['solidity','ethereum','smart contracts','web3'],          'good': ['hardhat','nft','defi','ipfs','layer2'],                           'tip': 'Link deployed contracts. Mention TVL or transaction volume.'},
    'Site Reliability Engineer': {'must': ['linux','kubernetes','monitoring','ci/cd','automation'],  'good': ['prometheus','grafana','chaos engineering','sre','incident'],     'tip': 'Mention SLA/SLO targets met and incident reduction metrics.'},
    'Security Engineer': {'must': ['networking','security','firewall','linux','tcp/ip'],     'good': ['vpn','ids/ips','siem','penetration testing','cisco'],             'tip': 'Mention certifications (CCNA, Security+). Describe network scale secured.'},
     'Business Analyst': {
    'must': ['business analysis', 'sql', 'excel', 'requirements', 'power bi'],
    'good': ['tableau', 'jira', 'agile', 'data analysis', 'stakeholder management'],
    'tip': 'Quantify business impact, process improvements, cost savings, or efficiency gains from your recommendations.'
},

'SQL Developer': {
    'must': ['sql', 'stored procedures', 'database design', 'mysql', 'query optimization'],
    'good': ['postgresql', 'etl', 'data warehousing', 'indexing', 'performance tuning'],
    'tip': 'Highlight query performance improvements, database size handled, and complex SQL solutions delivered.'
},


}


def _match_role(predicted_role):
    """Fuzzy match predicted role to ROLE_REQUIREMENTS key (v22: alias-aware)."""
    if predicted_role in ROLE_REQUIREMENTS:
        return predicted_role
    pl = predicted_role.strip().lower()
    # v22 FIX: resolve known spelling mismatches first (same map as Section 11)
    alias = _ROLE_BANK_ALIASES.get(pl)
    if alias and alias in ROLE_REQUIREMENTS:
        return alias
    candidates = [k for k in ROLE_REQUIREMENTS if k.lower() in pl or pl in k.lower()]
    return max(candidates, key=len) if candidates else 'Software Developer'

# -- Opt 1: pre-compile regex patterns at module load time ------------------
def _make_skill_pattern(skill):
    esc   = re.escape(skill)
    start = r'\b'     if skill[0].isalnum()  or skill[0]  == '_' else r'(?<!\w)'
    end   = r'\b'     if skill[-1].isalnum() or skill[-1] == '_' else r'(?!\w)'
    return re.compile(start + esc + end, re.IGNORECASE)


ROLE_SKILL_PATTERNS = {
    role: {
        skill: _make_skill_pattern(skill)
        for skill in reqs['must'] + reqs['good']
    }
    for role, reqs in ROLE_REQUIREMENTS.items()
}
_total_patterns = sum(len(v) for v in ROLE_SKILL_PATTERNS.values())


# -- SKILL_CONTEXT: per-role, per-skill contextual explanations ---------------
SKILL_CONTEXT = {
    'Data Scientist': {
        'python':        'Foundation of data science workflows including data manipulation, modeling, and visualization.',
        'pandas':        'Core library for data manipulation. Demonstrate with dataset sizes and transformations performed.',
        'sql':           'Required for data querying and extraction from relational databases.',
        'visualization': 'Expected competency for presenting insights through matplotlib, seaborn, Tableau, or Power BI.',
        'statistics':    'Non-negotiable for DS roles. Cite hypothesis testing, regression analysis, or A/B testing methodologies.',
    },
    'Machine Learning Engineer': {
        'python':     'Required baseline language for ML development and model serving.',
        'tensorflow': 'Industry-standard deep learning framework for production model training.',
        'pytorch':    'Increasingly preferred for research and production fine-tuning workflows.',
        'docker':     'Required for ML model containerization and reproducible deployment.',
        'api':        'ML engineers must serve models via REST APIs with documented latency targets.',
    },
    'Python Developer': {
        'python':    'Primary language. Specify version (3.10+) and key libraries used.',
        'django':    'Dominant Python web framework. Describe ORM usage, REST API endpoints, or DRF integration.',
        'flask':     'Lightweight framework for microservices and REST API prototypes.',
        'rest api':  'All backend roles require REST API experience. Describe endpoints, HTTP methods, and auth strategy.',
        'sql':       'Backend developers need SQL proficiency. Name the RDBMS and describe query optimization work.',
    },
    'Java Developer': {
        'java':      'Core language. Specify version (11, 17, 21) and advanced features used.',
        'spring':    'Spring Boot is the dominant Java framework. Describe REST controllers and Spring Security.',
        'sql':       'Java backends are database-heavy. Mention JPA/Hibernate or raw SQL optimization.',
        'rest api':  'REST APIs are standard. Describe endpoint design and OpenAPI/Swagger documentation.',
        'git':       'Version control is non-negotiable. Mention branching strategy and CI integration.',
    },
    'React Developer': {
        'react':      'List React version and key hooks (useState, useEffect, custom hooks).',
        'javascript': 'Core language. Mention ES6+ features: destructuring, async/await, modules.',
        'html':       'Core web skill. Mention semantic HTML5 elements and accessibility practices.',
        'css':        'Specify preprocessors (Sass) or utility frameworks (Tailwind, Bootstrap) used.',
        'git':        'Expected on every dev role. Mention collaborative PR workflow.',
    },
    'Full Stack Developer': {
        'react':      'Mention hooks, state management (Redux, Zustand), and SSR experience.',
        'node':       'Add Node.js version. Describe Express, Fastify, or NestJS usage.',
        'javascript': 'Core language. Specify TypeScript proficiency if applicable.',
        'sql':        'Full stack devs need database experience. Name the database and describe schema design.',
        'rest api':   'Describe APIs built: auth strategy, versioning, and documentation approach.',
    },
    'Backend Developer': {
        'python':    'Add version and frameworks (Django, Flask, FastAPI) with specific use cases.',
        'node':      'Mention Express or NestJS and async patterns (Promises, async/await).',
        'sql':       'Core skill. Name RDBMS and mention indexing, transactions, or query optimization.',
        'rest api':  'Describe REST API design: HTTP conventions, auth (JWT/OAuth), and versioning.',
        'docker':    'Containerization is expected. Mention Dockerfiles or container registries.',
    },
    'Frontend Developer': {
        'html':       'Specify HTML5. Mention semantic markup and accessibility (ARIA, WCAG).',
        'css':        'Mention Flexbox/Grid, responsive design, and preprocessors (Sass, Less).',
        'javascript': 'Core language. Mention ES6+, async patterns, and browser APIs used.',
        'react':      'Most frontend roles require React. Describe projects and hooks used.',
        'git':        'Expected on any dev role. Mention PR workflow and CI/CD experience.',
    },
    'DevOps Engineer': {
        'docker':     'Describe container builds, multi-stage Dockerfiles, or Compose setups.',
        'kubernetes': 'Mention clusters managed, Helm charts, or autoscaling configurations.',
        'ci/cd':      'Describe pipeline tool (Jenkins, GitHub Actions) and automation scope.',
        'linux':      'Mention distributions, shell scripting, and system administration tasks.',
        'aws':        'List specific AWS services (EC2, ECS, Lambda, S3) and certifications.',
    },
    'Cloud Engineer': {
        'aws':        'List specific services (EC2, S3, Lambda, RDS, VPC) and certifications.',
        'azure':      'List specific services (AKS, App Service, Azure DevOps) and certifications.',
        'linux':      'Core to cloud engineering. Mention distributions and scripting experience.',
        'terraform':  'IaC tool. Describe environments provisioned and state management approach.',
        'networking': 'Mention VPCs, subnets, security groups, load balancers, or DNS configuration.',
    },
    'AI Engineer': {
        'python':     'Primary language with AI libraries (transformers, LangChain, FastAPI).',
        'tensorflow': 'Describe model types trained: CNNs, RNNs, or fine-tuned pre-trained models.',
        'pytorch':    'Note whether used for research prototyping or production fine-tuning.',
        'nlp':        'Describe NLP tasks: classification, NER, summarization, or RAG pipelines.',
        'docker':     'AI models are deployed as containers. Describe containerization workflow.',
    },
    'Cyber Security Analyst': {
        'linux':               'Mention distros (Kali, Ubuntu) and CLI tools for security analysis.',
        'penetration testing': 'Mention methodology (OWASP, PTES) and tools (Burp Suite, Metasploit).',
        'firewalls':           'Describe firewall platforms configured (pfSense, Cisco ASA, AWS SGs).',
        'siem':                'Name the SIEM platform (Splunk, QRadar, ELK) and describe alert rules.',
    },
    'Mobile App Developer': {
        'flutter':  'Describe widgets, state management (Riverpod, BLoC, Provider) used.',
        'dart':     'Mention async patterns (Future, Stream) and null safety usage.',
        'android':  'Mention Jetpack components or Kotlin if used alongside Flutter.',
        'ios':      'Mention Swift interop or App Store publishing experience.',
        'firebase': 'Describe Firebase services: Auth, Firestore, Cloud Messaging, Analytics.',
    },
    'UI/UX Developer': {
        'figma':        'Link portfolio. Describe component libraries or design systems built.',
        'wireframing':  'Mention fidelity level (low-fi / hi-fi) and tools used.',
        'prototyping':  'Describe interactive prototypes and user feedback generated.',
        'user research':'Describe methods: interviews, usability tests, surveys, card sorting.',
    },
    'Database Administrator': {
        'sql':               'Core skill. Mention query optimization, execution plans, or stored procedures.',
        'mysql':             'Describe replication, partitioning, or backup configurations.',
        'postgresql':        'Mention vacuuming, JSONB, CTEs, or performance monitoring usage.',
        'query optimization':'Describe specific wins: added indexes, rewrote N+1 queries.',
    },
    'Software Developer': {
        'python':     'Add version and key libraries. Note application domain (web, data, scripting).',
        'java':       'Add version. Describe OOP design patterns applied in projects.',
        'git':        'Mention branching strategy and platform (GitHub, GitLab, Azure DevOps).',
        'sql':        'Name the RDBMS and describe schema design or query optimization.',
        'algorithms': 'Mention competitive programming or algorithm-heavy features built.',
    },
    'QA Engineer': {
        'manual testing': 'Describe test types: functional, regression, exploratory, UAT.',
        'test cases':     'Mention count and management tool (TestRail, Zephyr, Excel).',
        'bug reporting':  'Describe bug lifecycle workflow and tracker (Jira, Bugzilla).',
        'selenium':       'Describe language binding (Python/Java) and framework used.',
    },
    'ETL Developer': {
        'etl':          'Describe extract-transform-load pipelines built and data volumes.',
        'sql':          'Describe transformations, stored procedures, or complex joins.',
        'data pipelines':'Describe architecture: batch vs streaming, scheduling, error handling.',
        'python':       'Add ETL libraries used (pandas, PySpark, Airflow operators).',
    },
    'DotNet Developer': {
        '.net':         'Add version (6, 7, 8) and specify Core, Framework, or MAUI.',
        'c#':           'Mention version and advanced features: LINQ, async/await, generics.',
        'asp.net':      'Describe controllers, middleware, and REST API patterns.',
        'sql':          'Name the database (SQL Server, Azure SQL) and describe ORM usage.',
        'visual studio':'Mention debugging, profiling, or extension usage.',
    },
    'Blockchain Developer': {
        'solidity':        'Add version. Describe contract types: ERC-20, ERC-721, or custom.',
        'ethereum':        'Mention network: mainnet, testnet (Goerli, Sepolia), or L2.',
        'smart contracts': 'Describe contract functionality: minting, governance, staking.',
        'web3':            'Add library (ethers.js, web3.js) and describe dApp patterns.',
    },
    'Site Reliability Engineer': {
        'linux':      'Mention kernel tuning, systemd, or performance profiling.',
        'kubernetes': 'Describe cluster size, workloads, and tools (Helm, ArgoCD).',
        'monitoring': 'Name monitoring stack (Prometheus, Grafana, Datadog) and alerts.',
        'ci/cd':      'Describe pipeline gates: tests, security scans, canary deploys.',
        'automation': 'Mention scripting (Bash, Python) and automation scope.',
    },
    'Security Engineer': {
        'networking': 'Describe topology: routing protocols, VLANs, or WAN optimization.',
        'security':   'Add frameworks (NIST, ISO 27001) and security tools used.',
        'firewall':   'Name platforms (Palo Alto, Fortinet, Cisco ASA, pfSense).',
        'linux':      'Mention tools: Wireshark, tcpdump, netstat.',
        'tcp/ip':     'Describe protocol-level debugging and packet analysis.',
    },
    'Business Analyst': {
    'business analysis': 'Core skill. Describe requirements gathering, stakeholder communication, and process improvement initiatives.',
    'sql':               'Used for data extraction and analysis. Mention joins, aggregations, and reporting queries.',
    'excel':             'Describe advanced Excel usage including PivotTables, Power Query, and dashboards.',
    'requirements':      'Explain experience creating BRDs, FRDs, user stories, or use cases.',
    'power bi':          'Mention dashboard creation, KPI tracking, and business reporting solutions.',
},

'SQL Developer': {
    'sql':               'Primary skill. Mention complex joins, CTEs, window functions, and query optimization.',
    'stored procedures': 'Describe procedure development, parameterization, and performance tuning.',
    'database design':   'Mention normalization, ER diagrams, constraints, and schema design.',
    'mysql':             'Describe indexing, transactions, views, and query performance improvements.',
    'query optimization':'Provide examples of reducing execution time through indexing and query rewriting.',
},
}


# ── Tier-aware language helpers (v15) ────────────────────────────────────────
def _tier_prefix(tier):
    """Return the tier-specific prefix to prepend to relevant recommendations."""
    if tier == 'Entry':
        return 'As an early-career candidate: '
    if tier == 'Senior':
        return 'At senior level, recruiters expect: '
    return ''


def _apply_tier(text, tier):
    """Prepend the tier prefix to a recommendation string, idempotently."""
    pref = _tier_prefix(tier)
    if not pref:
        return text
    if text.startswith(pref):
        return text
    # Lowercase the first letter of the original so the joined sentence flows naturally
    first = text[:1].lower() + text[1:] if text else text
    return pref + first


def generate_improvement_plan(raw_text, predicted_role, quality_results, missing_sections,
                              targeted_dims=None, tier=None):
    """
    v15 — Score-aware + tier-aware improvement plan.

    Parameters:
        targeted_dims : list[str] or None
            If None  -> FULL improvement plan (all 4 categories).
            If list  -> TARGETED mode: only suggestions for those weak dimensions.
        tier          : 'Entry' | 'Mid' | 'Senior' | None
            Adds tier-specific prefix language to relevant suggestions and
            triggers the Senior-only leadership-evidence check.

    Returns a dict with 4 categories.
    """
    tl       = raw_text.lower()
    role     = _match_role(predicted_role)
    reqs     = ROLE_REQUIREMENTS[role]
    patterns = ROLE_SKILL_PATTERNS[role]
    skill_ctx = SKILL_CONTEXT.get(role, {})

    plan = {
        'skill_gap':     [],
        'technical':     [],
        'experience':    [],
        'communication': [],
    }

    _DIM_TO_CHECKS = {
        'technical_skills':        {'skill_gap', 'experience_techskills'},
        'quantified_achievements': {'technical_quant'},
        'projects_quality':        {'technical_projects', 'technical_github'},
        'bullet_points':           {'experience_bullets'},
        'action_verbs':            {'experience_verbs'},
        'readability':             {'experience_readability'},
        'professional_tone':       {'communication_tone'},
        'grammar_spelling':        {'communication_grammar'},
        'sections_completeness':   {'technical_sections'},
    }

    targeted = targeted_dims is not None
    if targeted:
        _active = set()
        for dim in targeted_dims:
            _active |= _DIM_TO_CHECKS.get(dim, set())
    else:
        _active = None

    def _should(check_name):
        return _active is None or check_name in _active

    # ======================================================================
    # CATEGORY 1 — Skill Gap Analysis
    # ======================================================================
    if _should('skill_gap'):
        miss_must = [s for s in reqs['must'] if not patterns[s].search(tl)]
        for skill in miss_must:
            ctx = skill_ctx.get(skill, f"Add '{skill}' to Skills section and demonstrate usage in a project.")
            plan['skill_gap'].append({
                'gap':            f"{skill.title()} proficiency not detected in resume.",
                'impact':         f"May reduce competitiveness for {role} positions where {skill} is a core requirement.",
                'recommendation': _apply_tier(ctx, tier),
            })

        miss_good = [s for s in reqs['good'] if not patterns[s].search(tl)]
        if miss_good[:3]:
            plan['skill_gap'].append({
                'gap':            f"Missing complementary skills: {', '.join(miss_good[:3])}.",
                'impact':         f"These skills differentiate strong {role} candidates in competitive hiring pools.",
                'recommendation': _apply_tier(
                    f"Add at least one of these to your Skills section and reference it in a project or experience bullet.",
                    tier,
                ),
            })

        if not targeted:
            plan['skill_gap'].append({
                'gap':            f"{role}-specific presentation gap.",
                'impact':         "Recruiters scan for role-aligned language and metrics within 6 seconds.",
                'recommendation': _apply_tier(reqs['tip'], tier),
            })

    # ======================================================================
    # CATEGORY 2 — Technical Enhancement
    # ======================================================================
    if _should('technical_sections'):
        section_recs = {
            'Projects': {
                'area':           "Projects section is missing.",
                'impact':         "Recruiters evaluate hands-on capability through project descriptions. Absence significantly weakens candidacy.",
                'recommendation': _apply_tier(
                    "Add a Projects section with GitHub links, tech stack used, and one measurable outcome per project "
                    "(e.g. 'Reduced API latency by 40%').",
                    tier,
                ),
            },
            'Certifications': {
                'area':           "Certifications section is missing.",
                'impact':         "Industry certifications (AWS, Google, Coursera) provide immediate ATS credibility and signal validated competency.",
                'recommendation': "Add relevant certifications. Prioritize cloud platform certs, language proficiency certs, or role-specific credentials.",
            },
            'Summary': {
                'area':           "Professional Summary is missing.",
                'impact':         (
                    "Senior roles treat a strong Summary as critical — it anchors recruiter scanning."
                    if tier == 'Senior'
                    else "First section recruiters read. Absence means the resume relies entirely on content scanning, reducing pass-through rate."
                ),
                'recommendation': _apply_tier(
                    "Add a 2-3 line Professional Summary at the top: state your role title, top 3 technical skills, "
                    "and years of relevant experience.",
                    tier,
                ),
            },
            'Achievements': {
                'area':           "Achievements section is missing.",
                'impact':         "Achievements (hackathon wins, awards, recognitions) differentiate candidates with similar skill profiles.",
                'recommendation': "Add an Achievements section: include competition placements, academic awards, or professional recognitions with dates.",
            },
        }
        for sec in missing_sections:
            rec = section_recs.get(sec)
            if rec:
                # Entry tier: skip the Summary recommendation (it's optional for Entry)
                if tier == 'Entry' and sec == 'Summary':
                    continue
                plan['technical'].append(rec)

    if _should('technical_projects'):
        proj_data = quality_results.get('projects_quality', {})
        if proj_data.get('score', 10) / max(proj_data.get('max', 10), 1) < 0.5:
            plan['technical'].append({
                'area':           "Project descriptions lack production-level complexity.",
                'impact':         "Weak project descriptions fail to demonstrate implementation depth and real-world problem solving.",
                'recommendation': _apply_tier(
                    "Describe each project with: what it does, the tech stack, and one measurable outcome. Add GitHub links. "
                    "Build at least one end-to-end project with authentication, database integration, and deployment.",
                    tier,
                ),
            })

    if _should('technical_quant'):
        quant_data = quality_results.get('quantified_achievements', {})
        if quant_data.get('score', 10) / max(quant_data.get('max', 10), 1) < 0.5:
            plan['technical'].append({
                'area':           "Resume lacks quantified achievements.",
                'impact':         "Bullet points without metrics appear generic. Recruiters prioritize measurable impact over task descriptions.",
                'recommendation': _apply_tier(
                    "Add numbers to bullet points: percentages ('reduced load time by 35%'), user counts ('served 10K active users'), "
                    "or cost impact ('cut infrastructure cost by $2K/month').",
                    tier,
                ),
            })

    if _should('technical_github'):
        if 'github.com' not in tl:
            plan['technical'].append({
                'area':           "GitHub profile link is missing.",
                'impact':         "GitHub is the primary portfolio platform for technical roles. Its absence limits recruiter ability to verify coding activity.",
                'recommendation': _apply_tier(
                    "Add your GitHub profile URL to the contact section. Ensure pinned repositories showcase relevant, well-documented projects.",
                    tier,
                ),
            })
    if not targeted:
        if 'linkedin' not in tl:
            plan['technical'].append({
                'area':           "LinkedIn profile link is missing.",
                'impact':         "LinkedIn is the standard professional networking platform. Recruiters use it for background verification and outreach.",
                'recommendation': "Add your LinkedIn URL to the contact section. Ensure your LinkedIn headline and experience match your resume.",
            })

    # ======================================================================
    # CATEGORY 3 — Experience & Impact Upgrade
    # ======================================================================
    if _should('experience_bullets'):
        bp_data = quality_results.get('bullet_points', {})
        if bp_data.get('score', 10) / max(bp_data.get('max', 10), 1) < 0.5:
            bc = bp_data.get('bullet_count', bp_data.get('score', 0))
            plan['experience'].append({
                'area':           f"Resume contains only {bc} bullet point(s).",
                'impact':         "Recruiters expect 8+ structured bullet points. Low bullet count suggests insufficient detail in experience descriptions.",
                'recommendation': "Add bullet points to Experience and Projects sections. Each bullet should start with an action verb and describe a specific contribution or outcome.",
            })

    if _should('experience_verbs'):
        av_data = quality_results.get('action_verbs', {})
        if av_data.get('score', 10) / max(av_data.get('max', 10), 1) < 0.5:
            found = av_data.get('found', [])
            vc = len(found)
            have = f" (current: {', '.join(found[:3])})" if found else ''
            plan['experience'].append({
                'area':           f"Only {vc} strong action verb(s) detected{have}.",
                'impact':         "Weak openers like 'worked on' or 'helped with' reduce perceived ownership and leadership capability.",
                'recommendation': _apply_tier(
                    "Rewrite bullet points using impact-driven verbs: Led, Built, Designed, Optimized, Deployed, Refactored, Architected, Automated.",
                    tier,
                ),
            })

    if _should('experience_techskills'):
        ts_data = quality_results.get('technical_skills', {})
        if ts_data.get('score', 10) / max(ts_data.get('max', 10), 1) < 0.5:
            plan['experience'].append({
                'area':           f"Technical skills coverage is below expected standard for {role}.",
                'impact':         "ATS systems and recruiters filter candidates based on skill keyword density.",
                'recommendation': _apply_tier(
                    f"Add more {role}-specific skills to your Skills section. Prioritize the missing items identified in the Skill Gap Analysis above.",
                    tier,
                ),
            })

    if _should('experience_readability'):
        rd_data = quality_results.get('readability', {})
        if rd_data.get('score', 10) / max(rd_data.get('max', 10), 1) < 0.5:
            note = rd_data.get('note', '')
            m_hit = re.search(r'(\d+) words', note)
            wc = int(m_hit.group(1)) if m_hit else 0
            if 0 < wc < 250:
                plan['experience'].append({
                    'area':           f"Resume is very short ({wc} words).",
                    'impact':         "Extremely short resumes signal insufficient experience detail and reduce recruiter engagement.",
                    'recommendation': "Expand experience descriptions (2-3 bullets per role), add a Projects section, and elaborate on technologies and methodologies used.",
                })
            elif wc > 0:
                plan['experience'].append({
                    'area':           f"Resume length ({wc} words) is outside optimal range.",
                    'impact':         "Resumes outside the optimal word range receive lower ATS scores and recruiter attention.",
                    'recommendation': "Target the appropriate length for your experience tier: trim redundant phrases, condense older roles to 1-2 bullets, and remove soft-skill filler language.",
                })

    # ── Senior-only mandatory check: leadership indicators ────────────────────
    # Runs regardless of targeted mode if tier is Senior.
    if tier == 'Senior':
        has_leadership = any(lv in tl for lv in ['led', 'managed', 'mentored', 'architected', 'spearheaded'])
        if not has_leadership:
            plan['experience'].append({
                'area':           "No leadership indicators found.",
                'impact':         "Senior roles require demonstrating team ownership — recruiters expect evidence of leadership, mentoring, or architectural decisions.",
                'recommendation': (
                    "Senior roles require demonstrating team ownership — rewrite bullets to show what you led, not just what "
                    "you did (e.g. 'Led a team of 5 engineers to deliver X')."
                ),
            })

    # ======================================================================
    # CATEGORY 4 — Communication & Clarity
    # ======================================================================
    if _should('communication_tone'):
        pt_data = quality_results.get('professional_tone', {})
        if pt_data.get('score', 10) / max(pt_data.get('max', 10), 1) < 0.5:
            note = pt_data.get('note', '')
            m_hit = re.search(r'(\d+) (first-person|informal)', note)
            count = int(m_hit.group(1)) if m_hit else 'Several'
            plan['communication'].append({
                'issue':          f"{count} first-person or informal phrase(s) detected.",
                'impact':         "First-person language ('I developed', 'I am') and informal phrasing reduce professional credibility.",
                'recommendation': "Use implied-subject style throughout: write 'Developed X' not 'I developed X'. Remove all instances of 'I am', 'I have', 'I want to', 'hire me'.",
            })

    if _should('communication_grammar'):
        gr_data = quality_results.get('grammar_spelling', {})
        gr_score = gr_data.get('score', 10)
        gr_max   = gr_data.get('max', 10)
        if gr_score / max(gr_max, 1) < 0.5:
            plan['communication'].append({
                'issue':          "Multiple grammar or spelling issues detected in descriptive content.",
                'impact':         "Grammar errors in a resume signal lack of attention to detail, which is a disqualifying factor for many recruiters.",
                'recommendation': "Review all bullet points for spelling, subject-verb agreement, and sentence structure. Use consistent tense (past for completed work, present for ongoing).",
            })

    if not targeted and not plan['communication']:
        if any(plan[k] for k in ('skill_gap', 'technical', 'experience')):
            plan['communication'].append({
                'issue':          "Maintain consistent professional language standards.",
                'impact':         "Uniform formatting, consistent tense, and precise technical terminology improve recruiter confidence.",
                'recommendation': "Use concise, action-oriented sentences. Maintain consistent technical terminology. Ensure each bullet point communicates a single, clear contribution.",
            })

    # ── Deduplication ────────────────────────────────────────────────────────
    for key in plan:
        seen = set()
        deduped = []
        for item in plan[key]:
            sig = str(item)
            if sig not in seen:
                seen.add(sig)
                deduped.append(item)
        plan[key] = deduped

    if targeted:
        plan = {k: v for k, v in plan.items() if v}

    return plan




# ## 🧭 Section 13.5 — Role Mismatch Detection & Experience Tier  (v15)
# 
# Adds the two new user-facing inputs — `target_role` and `years_of_experience` — that flow into the pipeline and change how the CV is scored.
# 
# - **`normalize_user_role()`** — fuzzy-matches a free-text role against the 21 supported roles.
# - **`get_role_group()`** — maps a role (canonical or ML-predicted) to one of 12 role groups.
# - **`resolve_experience_tier()`** — maps years → `Entry` / `Mid` / `Senior` (matches the quiz module).
# - **`assess_role_alignment()`** — compares target vs ML group → `full_match` / `partial_mismatch` (-20) / `full_mismatch` (-40) / `auto`.
# 


SUPPORTED_ROLES = [
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
    'Cybersecurity Analyst',
    'QA Engineer',
    'Database Administrator',
    'UI/UX Developer',
    'Blockchain Developer',
    'Mobile App Developer',
]


# Common abbreviations / free-text spellings → canonical supported role.
# Checked before fuzzy matching so e.g. "ml engineer" doesn't accidentally
# fall through token-overlap and resolve to the wrong "* Engineer".
ROLE_ALIASES = {
    'ml':                    'Machine Learning Engineer',
    'ml engineer':           'Machine Learning Engineer',
    'mle':                   'Machine Learning Engineer',
    'machine learning':      'Machine Learning Engineer',
    'ai/ml engineer':        'Machine Learning Engineer',
    'ai':                    'AI Engineer',
    'ai/ml':                 'AI Engineer',
    'ml/ai':                 'AI Engineer',
    'data science':          'Data Scientist',
    'data analyst':          'Business Analyst',
    'ba':                    'Business Analyst',
    'swe':                   'Software Developer',
    'sde':                   'Software Developer',
    'software engineer':     'Software Developer',
    'fullstack':             'Full Stack Developer',
    'full-stack':            'Full Stack Developer',
    'full stack':            'Full Stack Developer',
    'front end':             'Frontend Developer',
    'front-end':             'Frontend Developer',
    'back end':              'Backend Developer',
    'back-end':              'Backend Developer',
    'devops':                'DevOps Engineer',
    'sre':                   'DevOps Engineer',
    'cloud':                 'Cloud Engineer',
    'ui/ux':                 'UI/UX Developer',
    'ux':                    'UI/UX Developer',
    'ui':                    'UI/UX Developer',
    'ui/ux designer':        'UI/UX Developer',
    'cyber security':        'Cybersecurity Analyst',
    'cybersecurity':         'Cybersecurity Analyst',
    'cybersecurity analyst': 'Cybersecurity Analyst',
    'infosec':               'Security Engineer',
    'security':              'Security Engineer',
    'qa':                    'QA Engineer',
    'tester':                'QA Engineer',
    'dba':                   'Database Administrator',
    'mobile':                'Mobile App Developer',
    'android':               'Mobile App Developer',
    'ios':                   'Mobile App Developer',
    'blockchain':            'Blockchain Developer',
    'web3':                  'Blockchain Developer',
}

# Tokens too generic to anchor a match on their own.
_GENERIC_ROLE_TOKENS = {'engineer', 'developer', 'analyst', 'administrator', 'app'}


def normalize_user_role(user_input):

    if not user_input or not isinstance(user_input, str):
        return None

    needle = user_input.strip().lower()
    if not needle:
        return None

    # 1) Exact canonical match.
    for role in SUPPORTED_ROLES:
        if needle == role.lower():
            return role

    # 2) Known abbreviation / alias.
    if needle in ROLE_ALIASES:
        return ROLE_ALIASES[needle]

    # 3) Substring containment either direction.
    candidates = []
    for role in SUPPORTED_ROLES:
        r_lower = role.lower()
        if needle in r_lower or r_lower in needle:
            candidates.append(role)
    if candidates:
        candidates.sort(key=len, reverse=True)
        return candidates[0]

    # 4) Token overlap — but ignore matches that rest only on a generic word
    #    like "engineer"/"developer", which would otherwise resolve almost
    #    anything to an arbitrary role.
    needle_tokens = set(needle.replace('/', ' ').split())
    meaningful_needle = needle_tokens - _GENERIC_ROLE_TOKENS
    best, best_score = None, 0
    for role in SUPPORTED_ROLES:
        r_tokens = set(role.lower().replace('/', ' ').split())
        overlap = needle_tokens & r_tokens
        meaningful_overlap = overlap - _GENERIC_ROLE_TOKENS
        # Require at least one non-generic word in common.
        if not meaningful_overlap:
            continue
        score = len(overlap)
        if score > best_score:
            best_score = score
            best = role

    if best is not None and best_score >= max(1, len(needle_tokens) // 2):
        return best
    return None


ROLE_GROUPS = {
    'data_ai': ['Data Scientist', 'Machine Learning Engineer', 'AI Engineer'],
    'business': ['Business Analyst'],
    'database': ['SQL Developer', 'Database Administrator'],
    'web_frontend': ['React Developer', 'Frontend Developer'],
    'design': ['UI/UX Developer'],
    'web_backend': ['Python Developer', 'Java Developer', 'Backend Developer'],
    'fullstack': ['Full Stack Developer', 'Software Developer'],
    'mobile': ['Mobile App Developer'],
    'devops_cloud': ['DevOps Engineer', 'Cloud Engineer'],
    'security': ['Security Engineer', 'Cyber Security Analyst'],
    'blockchain': ['Blockchain Developer'],
    'qa': ['QA Engineer'],
}


# ----------------------------------------------------------------------------
#  Role families — broader "field" buckets used to decide HOW different two
#  roles are. Two roles in the same group are an exact match; two roles in the
#  same family (but different group) are a *related* mismatch (e.g. Frontend vs
#  Full Stack); roles in different families are a *hard* mismatch (e.g. a Data
#  Science CV submitted for a Cyber Security role).
# ----------------------------------------------------------------------------


ROLE_GROUPS = {
    'data_ai': ['Data Scientist', 'Machine Learning Engineer', 'AI Engineer'],
    'business': ['Business Analyst'],
    'database': ['SQL Developer', 'Database Administrator'],
    'web_frontend': ['React Developer', 'Frontend Developer'],
    'design': ['UI/UX Developer'],
    'web_backend': ['Python Developer', 'Java Developer', 'Backend Developer'],
    'fullstack': ['Full Stack Developer'],
    'software_generic':  ['Software Developer'],
    'mobile': ['Mobile App Developer'],
    'devops_cloud': ['DevOps Engineer', 'Cloud Engineer'],
    'security': ['Security Engineer', 'Cyber Security Analyst'],
    'blockchain': ['Blockchain Developer'],
    'qa': ['QA Engineer'],
}


# ----------------------------------------------------------------------------
#  Role families — broader "field" buckets used to decide HOW different two
#  roles are. Two roles in the same group are an exact match; two roles in the
#  same family (but different group) are a *related* mismatch (e.g. Frontend vs
#  Full Stack); roles in different families are a *hard* mismatch (e.g. a Data
#  Science CV submitted for a Cyber Security role).
# ----------------------------------------------------------------------------


ROLE_FAMILIES = {
    'software_engineering': {
        'web_frontend',
        'software_generic',
        'web_backend',
        'fullstack',
        'mobile',
    },
    'qa_testing': {          
        'qa',               
    },

    'blockchain': {          
        'blockchain',        
    },

    'data_and_analytics': {
        'data_ai',
    },
    'business_operations': { 
        'business',
    },

    'design': {
        'design',
    },

    'infrastructure': {
        'devops_cloud',
        'security',
        'database',

    },
}


# ----------------------------------------------------------------------------
#  Mismatch policy — tune scoring consequences here in ONE place.
#
#    penalty     : points subtracted from the base score.
#    force_zero  : if True, the final score is forced to 0 regardless of the
#                  CV's quality (a "you uploaded the wrong kind of CV" block).
#
#  Policy: ANY role mismatch is penalised but never zeroed. A *related*
#  mismatch (same broad field, just not tailored) takes a soft penalty; a
#  *hard* mismatch (different field entirely) takes a heavier penalty. The
#  resume is still scored normally on its merits in both cases.
#  Set 'force_zero' = True on either tier if you ever want that mismatch to
#  score 0 again. To make every mismatch cost the same, set both penalties
#  to the same number (e.g. 25).
# ----------------------------------------------------------------------------
ROLE_MISMATCH_CONFIG = {
    'related_mismatch': {'penalty': 25,  'force_zero': False},
    'hard_mismatch':    {'penalty': 40,  'force_zero': False},
}


ML_ROLE_TO_SUPPORTED = {
    'data science':              'Data Scientist',
    'data scientist':            'Data Scientist',
    'machine learning engineer': 'Machine Learning Engineer',
    'python developer':          'Python Developer',
    'java developer':            'Java Developer',
    'react developer':           'React Developer',
    'full stack developer':      'Full Stack Developer',
    'backend developer':         'Backend Developer',
    'frontend developer':        'Frontend Developer',
    'devops':                    'DevOps Engineer',
    'devops engineer':           'DevOps Engineer',
    'cloud engineer':            'Cloud Engineer',
    'ai engineer':               'AI Engineer',
    'cybersecurity analyst':     'Cyber Security Analyst',
    'cyber security analyst':    'Cyber Security Analyst',
    'mobile developer':          'Mobile App Developer',
    'mobile app developer':      'Mobile App Developer',
    'ui/ux designer':            'UI/UX Developer',
    'ui/ux developer':           'UI/UX Developer',
    'database administrator':    'Database Administrator',
    'software developer':        'Software Developer',
    'qa engineer':               'QA Engineer',
    'blockchain':                'Blockchain Developer',
    'blockchain developer':      'Blockchain Developer',
    'network security engineer': 'Security Engineer',   
    'network security':          'Security Engineer',   
    'security engineer':         'Security Engineer',   
    'etl developer':             'Database Administrator',
    'dotnet developer':          'Backend Developer',
    'site reliability engineer': 'DevOps Engineer',

    # --- Generalist / senior engineering titles the ML model can emit. ---
    # These ARE software roles, so map them to the closest supported group.
    # Without these they fell through to 'unknown' and a strong, on-topic CV
    # could be wrongly flagged as a hard role mismatch.
    'engineering manager':       'Software Developer',
    'principal engineer':        'Software Developer',
    'technical lead':            'Software Developer',
    'system administrator':      'DevOps Engineer',
    'product manager':           'Business Analyst',
    # 'Digital Media' and 'Technical Writer' are intentionally NOT mapped:
    # they are genuinely outside the supported technical roles, so they
    # correctly resolve to 'unknown' (→ hard mismatch against a tech target).
}


def get_role_group(role):

    if not role or not isinstance(role, str):
        return 'unknown'

    role_lower = role.strip().lower()

    canonical = ML_ROLE_TO_SUPPORTED.get(role_lower)

    if canonical is None:
        for sr in SUPPORTED_ROLES:
            if role_lower == sr.lower():
                canonical = sr
                break

    if canonical is None:
        for sr in SUPPORTED_ROLES:
            sr_low = sr.lower()
            if role_lower in sr_low or sr_low in role_lower:
                canonical = sr
                break

    if canonical is None:
        return 'unknown'

    
    for group_key, roles_in_group in ROLE_GROUPS.items():
        if canonical in roles_in_group:
            return group_key
    return 'unknown'


def get_role_family(group):
    """Map a role *group* (from get_role_group) to its broader family."""
    if not group or group == 'unknown':
        return 'unknown'
    for family, groups in ROLE_FAMILIES.items():
        if group in groups:
            return family
    return 'unknown'


def resolve_experience_tier(years_of_experience):
    """
    Map years_of_experience → tier string (must match quiz module exactly).

        None       → None     (no tier; default scoring applies)
        < 0        → ValueError
        0 to 1     → 'Entry'  (quiz: easy)
        1.x to 3   → 'Mid'    (quiz: medium)
        > 3        → 'Senior' (quiz: hard)
    """
    if years_of_experience is None:
        return None
    if not isinstance(years_of_experience, (int, float)):
        raise ValueError(f"years_of_experience must be a number, got {type(years_of_experience).__name__}.")
    if years_of_experience < 0:
        raise ValueError("Experience cannot be negative.")
    if years_of_experience <= 1:
        return 'Entry'
    if years_of_experience <= 3:
        return 'Mid'
    return 'Senior'


def assess_role_alignment(target_role_canonical, ml_predicted_role):
    """..."""
    if target_role_canonical is None:
        return {
            'alignment':     'auto',
            'penalty':       0,
            'force_zero':    False,
            'message':       'ℹ️ No target role provided — scored against the AI-detected role.',
            'detected_role': ml_predicted_role,
            'target_role':   None,
        }

    target_group  = get_role_group(target_role_canonical)
    ml_group      = get_role_group(ml_predicted_role)

    # Exact group match
    if target_group != 'unknown' and target_group == ml_group:
        return {
            'alignment':     'full_match',
            'penalty':       0,
            'force_zero':    False,
            'message':       f"✅ Your resume matches the selected role '{target_role_canonical}'.",
            'detected_role': ml_predicted_role,
            'target_role':   target_role_canonical,
        }

    # ===== MOVED HERE: Check for generic "Software Developer" BEFORE family logic =====
    target_lower = target_role_canonical.lower()
    ml_lower = ml_predicted_role.lower()
    
    if target_lower == 'software developer' or ml_lower == 'software developer':
        target_family = get_role_family(target_group)
        ml_family = get_role_family(ml_group)
        # If either is generic Software Developer AND they're in same family, full match
        if target_family != 'unknown' and target_family == ml_family:
            return {
                'alignment':     'full_match',
                'penalty':       0,
                'force_zero':    False,
                'message':       f"✅ Your resume matches the selected role '{target_role_canonical}'.",
                'detected_role': ml_predicted_role,
                'target_role':   target_role_canonical, 
            }
    # ===== END GENERIC CHECK =====

    target_family = get_role_family(target_group)
    ml_family     = get_role_family(ml_group)

    # Same broad field, different specialisation → soft penalty, no block.
    if (target_family != 'unknown'
            and target_family == ml_family):
        cfg = ROLE_MISMATCH_CONFIG['related_mismatch']
        return {
            'alignment':     'related_mismatch',
            'penalty':       cfg['penalty'],
            'force_zero':    cfg['force_zero'],
            'message':       (f"⚠️ Your resume looks like a '{ml_predicted_role}' resume, but you "
                              f"selected '{target_role_canonical}'. They are in the same field, so "
                              f"tailor your resume to the selected role to score higher."),
            'detected_role': ml_predicted_role,
            'target_role':   target_role_canonical,
        }

    # Different field entirely (or non-tech / unrecognised) → hard mismatch.
    cfg = ROLE_MISMATCH_CONFIG['hard_mismatch']
    return {
        'alignment':     'hard_mismatch',
        'penalty':       cfg['penalty'],
        'force_zero':    cfg['force_zero'],
        'message':       (f"❌ Your resume looks like a '{ml_predicted_role}' resume, but you selected "
                          f"'{target_role_canonical}'. These are different fields, so a scoring penalty "
                          f"applies. Upload a resume tailored to '{target_role_canonical}', or re-upload "
                          f"and select '{ml_predicted_role}', to score higher."),
        'detected_role': ml_predicted_role,
        'target_role':   target_role_canonical,
    }






# ============================================================================
#  Section 13.6 — Skills & Social Links Extraction
# ============================================================================
_NON_SKILL = {'developer','engineer','programmer','programming','software','coding','debugging',
    'github','repository','computer science','algorithm','backend','frontend','full stack','mobile'}

_EXTRA_HEADINGS = ['work experience','professional experience','personal projects','academic projects',
    'professional summary','career summary','summary of qualifications','core competencies',
    'technical skills','programming languages','contact','links','social','interests','hobbies',
    'references','declaration','personal details','volunteer','leadership',
    'who am i','who i am','key achievements','experience and projects']

_HEADER_VOCAB = set(
    CV_SECTION_KEYWORDS
    + [k for ks in CRITICAL_SECTIONS.values() for k in ks]
    + [k for ks in IMPORTANT_SECTIONS.values() for k in ks]
    + _EXTRA_HEADINGS)


def _norm(s):
    s = re.sub(r'[^a-z0-9 ]', ' ', s.strip().lower())
    return re.sub(r'\s+', ' ', s).strip()


def _is_heading(line, phrases):
    s = _norm(line)
    if not s or len(s) > 45:
        return False
    for p in phrases:
        if s == p:
            return True
        if s.startswith(p + ' ') and re.fullmatch(r'[\d ]{0,12}', s[len(p):].strip()):
            return True
    return False


def _section_lines(raw_text, target_phrases):
    """Raw lines under the FIRST matching heading, until the next heading."""
    lines, out, capturing, blanks = raw_text.split('\n'), [], False, 0
    for line in lines:
        if not capturing:
            if _is_heading(line, target_phrases):
                capturing = True
            continue
        if _is_heading(line, _HEADER_VOCAB):
            break
        if not line.strip():
            blanks += 1
            if blanks >= 3:
                break
            continue
        blanks = 0
        out.append(line.strip())
    return out

def extract_technical_skills(raw_text):
    """Extract skills from TECH_KEYWORDS dictionary + actual Skills section in the CV."""
    tl = raw_text.lower()
    found = []

    for kw in TECH_KEYWORDS:
        if kw in _NON_SKILL:
            continue
        if re.search(r'(?<![a-z+#.])' + re.escape(kw) + r'(?![a-z+#])', tl):
            found.append(kw)

    _SKILLS_H = IMPORTANT_SECTIONS.get('Skills', ['skills']) + [
        'technical skills', 'programming languages', 'core competencies'
    ]
    for ln in _section_lines(raw_text, _SKILLS_H):
        for tok in re.split(r'[,|•·/]|\s{2,}', ln):
            tok = tok.strip(' .-–—').strip()
            if (2 <= len(tok) <= 30
                    and tok.lower() not in _NON_SKILL
                    and ':' not in tok
                    and not re.search(
                        r'\((native|fluent|conversational|proficient|basic|intermediate|advanced)\)',
                        tok, re.I)):
                found.append(tok.lower())

    pretty = {
        'ai': 'AI', 'nlp': 'NLP', 'sql': 'SQL', 'html': 'HTML', 'css': 'CSS',
        'aws': 'AWS', 'gcp': 'GCP', 'llm': 'LLM', 'ci/cd': 'CI/CD',
        'ios': 'iOS', 'php': 'PHP', 'c++': 'C++', 'c#': 'C#', 'api': 'API'
    }
    out, seen = [], set()
    for kw in found:
        label = pretty.get(kw, kw.title() if (' ' in kw or kw.islower()) else kw)
        if label.lower() not in seen:
            seen.add(label.lower())
            out.append(label)

    return out

def _normalise_public_url(url):
    if not url:
        return None
    url = str(url).strip().strip('<>[](){}').rstrip('.,);]}>')
    if not url:
        return None
    if url.lower().startswith('www.'):
        url = 'https://' + url
    elif not re.match(r'https?://', url, re.I):
        url = 'https://' + url
    return url


def _is_placeholder_profile_url(url):
    if not url:
        return True
    u = url.lower().strip().rstrip('/')
    bad_bits = (
        '/username', '/yourusername', '/your-username', '/your_username',
        '/your_name', '/your-name', '/yourname', '/name', '/profile',
        '/example', '/sample', '/user', '/handle', '/linkedin', '/github',
    )
    return any(u.endswith(bit) for bit in bad_bits)


def extract_social_links(raw_text):
    """
    Website / LinkedIn / GitHub extraction.

    Handles normal visible URLs, label-style entries, and ignores common
    placeholders like linkedin.com/in/username when a real URL is also present.
    """

    t = re.sub(r'\[([^\]]*)\]\(([^)]*)\)', r' \1 \2 ', raw_text)
    _JUNK = ('enhancv.com', 'canva.com', 'overleaf.com', 'novoresume', 'zety.com', 'resume.io')

    def _all(pattern):
        return [m.group(0).rstrip('.,);]}>') for m in re.finditer(pattern, t, re.I)]

    github_candidates = _all(r'(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9_.\-]+')
    linkedin_candidates = _all(r'(?:https?://)?(?:(?:[a-z]{2,3}|www)\.)?linkedin\.com/(?:in|pub)/[A-Za-z0-9_.\-/]+')

    m = re.search(r'github\s*[:\-]\s*([A-Za-z0-9_.\-]{3,})', t, re.I)
    if m and '.' not in m.group(1):
        github_candidates.append('github.com/' + m.group(1))

    m = re.search(r'(?:linked\s*in|linkedin)\s*[:\-]\s*([A-Za-z0-9_.\-]{4,})', t, re.I)
    if m and '.' not in m.group(1):
        linkedin_candidates.append('linkedin.com/in/' + m.group(1))

    def choose(candidates):
        for c in candidates:
            normal = _normalise_public_url(c)
            if normal and not _is_placeholder_profile_url(normal):
                return normal
        return None

    github = choose(github_candidates)
    linkedin = choose(linkedin_candidates)

    website = None
    for u in re.findall(r'(?:https?://|www\.)[A-Za-z0-9._\-]+\.[A-Za-z]{2,}(?:/[^\s)\]}>]*)?', t, re.I):
        ul = u.lower()
        if 'github.com' in ul or 'linkedin.com' in ul or any(j in ul for j in _JUNK):
            continue
        website = _normalise_public_url(u)
        break

    if not any([github, linkedin, website]):
        return None
    return {'website': website, 'linkedin': linkedin, 'github': github}




# ## 🚀 Section 14 — Main Pipeline: `run_pipeline()`
# 
# Single entry point. Takes only a PDF path. Returns clean JSON.
# 
# ```python
# result = run_pipeline('my_resume.pdf')
# ```


def run_pipeline(resume_file_path, target_role=None, years_of_experience=None, verbose=False):

    # Step logs are noise in the Django request log. Keep them off stdout by
    # default; pass verbose=True to restore terminal output for debugging.
    # The user-facing version of these steps is returned as 'analysis_log'.
    import builtins
    def print(*args, **kwargs):  # noqa: A001  (intentional local shadow)
        if verbose:
            builtins.print(*args, **kwargs)

    SEP = '=' * 62
    print(f'\n{SEP}')
    print('  🤖 AI Resume Intelligence Engine v15 — Starting')
    print(SEP)

    tier = resolve_experience_tier(years_of_experience)
    if tier is not None:
        print(f'      ▶ Experience: {years_of_experience} year(s) → {tier} tier')

    
    normalized_target_role = None
    if target_role is not None:
        normalized_target_role = normalize_user_role(target_role)
        if normalized_target_role is None:
            print(f"      ⚠️  Target role '{target_role}' did not match any supported role.")
            print(f"         Falling back to ML-detected role for scoring.")
        else:
            print(f'      ▶ Target role: {normalized_target_role}')


    print('\n[1/8] 📄 Extracting text...')
    raw_text = extract_text(resume_file_path)
    if raw_text.startswith('ERROR'):
        return {'status': 'error', 'message': raw_text}
    if len(raw_text.strip()) < 50:
        return {'status': 'error', 'message': 'Insufficient text. PDF may be image-only.'}
    print(f'      ✅ {len(raw_text)} characters extracted')

    
    print('\n[2/8] 🔍 Validating document...')

    # Check 1: Is there enough content to evaluate?
    if len(fix_pdf_artifacts(raw_text).strip()) < 200:
        return {
            'status': 'rejected',
            'reason': 'Resume content is too short to analyze properly.',
            'hint':   'Please upload a text-based resume with at least 200 characters of content.'
        }

    # Check 2: Does it look like a CV at all?
    if not is_valid_cv(raw_text):
        return {
            'status': 'rejected',
            'reason': 'Document does not appear to be a CV/Resume.',
            'hint':   'Upload a PDF with sections like: Experience, Education, Skills, Projects.'
        }

    # Check 3: Is it a TECH CV?
    if not is_tech_cv(raw_text):
        extra = ''
        if normalized_target_role:
            extra = (f" You are targeting '{normalized_target_role}', but the document does "
                    f"not contain enough technical signals for any tech role.")
        return {
            'status': 'rejected',
            'reason': 'This platform currently supports technical resumes only. Please upload a tech-related CV.' + extra,
            'hint':   'Supported roles: Software Engineer, Data Scientist, DevOps, Cloud, AI/ML, and more.'
        }

    print('      ✅ Valid tech resume')

    print('\n[3/8] 🏷️  Predicting technical role (ML)...')
    clf               = classify_resume(raw_text)
    ml_predicted_role = clf['predicted_role']
    print(f'      ✅ ML predicted: {ml_predicted_role}')

    role_for_scoring = ml_predicted_role

    
    alignment_result = assess_role_alignment(normalized_target_role, ml_predicted_role)
    role_alignment   = alignment_result['alignment']
    role_penalty     = alignment_result['penalty']
    role_message     = alignment_result['message']
    role_force_zero  = alignment_result.get('force_zero', False)
    if role_alignment != 'auto':
        print(f"      ▶ Role alignment: {role_alignment.replace('_', ' ')}"
              + (' (score forced to 0 — wrong field)' if role_force_zero else f' (penalty -{role_penalty})'))

    
    print('\n[4/8] 📝 Checking grammar...')
    g_count, g_examples = check_grammar(raw_text)
    print(f'      ✅ {g_count} real grammar issue(s)')

    
    print('\n[5/8] 📊 9-dimension quality scoring' + (f' ({tier} tier)' if tier else '') + '...')
    quality, missing_secs = analyze_resume(
        raw_text,
        role_for_scoring,
        grammar_count=g_count,
        tier=tier,
    )
    base_score  = calculate_score(quality)
    if role_force_zero:
        final_score = 0
    else:
        final_score = max(0, base_score - role_penalty)
    grade       = get_grade(final_score)
    if role_force_zero:
        print(f'      ⛔ Base: {base_score}/100  →  Role mismatch  →  Final: 0/100 — {grade}')
    elif role_penalty > 0:
        print(f'      ✅ Base: {base_score}/100  →  Penalty: -{role_penalty}  →  Final: {final_score}/100 — {grade}')
    else:
        print(f'      ✅ Score: {final_score}/100 — {grade}')
        
    print('\n[6/8] 💪 Strengths & weaknesses...')
    strengths, weaknesses, weak_dims = detect_strengths_weaknesses(quality)
    print(f'      ✅ {len(strengths)} strengths · {len(weaknesses)} weaknesses')

    print('\n[7/8] 🔧 Generating improvement plan...')
    if final_score < 70:
        plan = generate_improvement_plan(
            raw_text, role_for_scoring, quality, missing_secs,
            targeted_dims=None, tier=tier,
        )
        plan_items = sum(len(v) for v in plan.values()) if isinstance(plan, dict) else len(plan)
        print(f'      ✅ Full improvement plan generated ({plan_items} suggestions)')
    elif weaknesses:
        plan = generate_improvement_plan(
            raw_text, role_for_scoring, quality, missing_secs,
            targeted_dims=weak_dims, tier=tier,
        )
        plan_items = sum(len(v) for v in plan.values()) if isinstance(plan, dict) else len(plan)
        print(f'      ✅ Targeted improvement plan ({plan_items} suggestions for {len(weak_dims)} weak area(s))')
    else:
        plan = {}
        print('      ✅ No improvement plan needed — no critical weaknesses detected')

    print('\n[8/8] 🎯 Quiz eligibility...')
    eligible, eli_reason = quiz_eligible(final_score)
    print(f'      {"✅" if eligible else "❌"} Eligible: {"Yes" if eligible else "No"}')

    if role_force_zero:
        # Wrong field entirely — the headline message is the mismatch explanation.
        msg = role_message
    elif final_score >= 70:
        msg = f'🎉 Score {final_score}/100 ({grade}). Eligible for the adaptive quiz!'
    elif final_score >= 50:
        msg = f'📈 Score {final_score}/100 ({grade}). Improve to 70+ to unlock the quiz.'
    else:
        msg = f'⚠️  Score {final_score}/100 ({grade}). Significant improvements needed.'

    print(f'\n{SEP}')
    print(f'  {"⛔" if role_force_zero else "✅"} Complete — {final_score}/100 — {grade}')
    print(f'{SEP}\n')

    # User-facing version of the per-step progress that used to only print to
    # the server terminal. The feedback page renders this list.
    _plan_count = sum(len(v) for v in plan.values()) if isinstance(plan, dict) else len(plan or [])
    if role_force_zero:
        _score_detail = f'Base {base_score}/100 → final 0/100 ({grade}) — score zeroed because the resume does not match the selected role.'
    elif role_penalty:
        _score_detail = f'Base {base_score}/100 → role penalty −{role_penalty} → final {final_score}/100 ({grade}).'
    else:
        _score_detail = f'Final score {final_score}/100 ({grade}).'

    analysis_log = [
        {'step': 'Text extraction',        'detail': f'{len(raw_text)} characters read from the PDF.'},
        {'step': 'Document validation',    'detail': 'Recognised as a valid technical resume.'},
        {'step': 'AI role prediction',     'detail': f'Detected role: {ml_predicted_role}.'},
    ]
    if role_alignment != 'auto':
        analysis_log.append({'step': 'Role alignment', 'detail': role_message})
    if tier:
        analysis_log.append({'step': 'Experience tier', 'detail': f'{years_of_experience} year(s) → {tier} tier.'})
    analysis_log += [
        {'step': 'Grammar check',          'detail': f'{g_count} grammar/spelling issue(s) found.'},
        {'step': 'Quality scoring',        'detail': _score_detail},
        {'step': 'Strengths & weaknesses', 'detail': f'{len(strengths)} strength(s) and {len(weaknesses)} weakness(es) identified.'},
        {'step': 'Improvement plan',       'detail': (f'{_plan_count} suggestion(s) generated.' if _plan_count else 'No critical improvements needed.')},
        {'step': 'Quiz eligibility',       'detail': eli_reason},
    ]

    # TO
    profile = {
        'technical_skills_list': extract_technical_skills(raw_text),
        'social_links':          extract_social_links(raw_text),
    }
    return {
        'status':              'success',
        'analysis_log':        analysis_log,

        
        'target_role':         normalized_target_role or ml_predicted_role,
        'ml_predicted_role':   ml_predicted_role,
        'input_role':          'provided' if (target_role and normalized_target_role) else 'ml_predicted',
        'role_alignment':      role_alignment,
        'role_penalty':        role_penalty,
        'role_match_message':  role_message,
        'role_mismatch_block': role_force_zero,
        # Echo what the user typed vs what the model detected so the UI can
        # show "you selected X, your resume looks like Y".
        'selected_role':       normalized_target_role,
        'selected_role_raw':   target_role,

    
        'years_of_experience': years_of_experience,
        'experience_tier':     tier,

        
        'detected_role':       ml_predicted_role,  
        'top_3_roles':         [p['role'] for p in clf.get('top_3_predictions', [])],
        'top_keywords':        clf.get('top_keywords', []),

        
        'base_score':          base_score,
        'resume_score':        final_score,         
        'grade':               grade,

        'quiz_eligible':       eligible,
        'eligibility_reason':  eli_reason,
        'grammar_count':       g_count,
        'grammar_issues':      g_examples,
        'missing_sections':    missing_secs,
        'quality_analysis':    quality,
        'strengths':           strengths,
        'weaknesses':          weaknesses,
        'improvement_plan':    plan,
        'message':             msg,
        'technical_skills_list': profile['technical_skills_list'],
        'social_links':          profile['social_links'],
    }
    






class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that safely converts NumPy values for API responses."""

    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def to_json_safe(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert pipeline output into plain JSON-safe Python values."""
    return json.loads(json.dumps(data, cls=NumpyEncoder, ensure_ascii=False))


def analyze_resume_file(
    file_path: str,
    target_role: Optional[str] = None,
    years_of_experience: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Django-friendly wrapper.

    Use this from resumes/services/resume_analyzer.py or directly from your upload view.
    It raises ValueError for rejected/error resumes and returns only the fields your app needs.
    """
    result = run_pipeline(
        file_path,
        target_role=target_role,
        years_of_experience=years_of_experience,
    )

    if result.get("status") == "error":
        raise ValueError(result.get("message", "Resume analysis failed."))

    if result.get("status") == "rejected":
        raise ValueError(result.get("reason", "Resume rejected."))

    analysis = {
        "score": result.get("resume_score", 0),
        "grade": result.get("grade"),
        "detected_role": result.get("detected_role"),
        "target_role": result.get("target_role"),
        "ml_predicted_role": result.get("ml_predicted_role"),
        "role_alignment": result.get("role_alignment"),
        "role_penalty": result.get("role_penalty", 0),
        "role_match_message": result.get("role_match_message"),
        "quiz_eligible": result.get("quiz_eligible", False),
        "eligibility_reason": result.get("eligibility_reason", ""),
        "grammar_count": result.get("grammar_count", 0),
        "grammar_issues": result.get("grammar_issues", []),
        "missing_sections": result.get("missing_sections", []),
        "quality_analysis": result.get("quality_analysis", {}),
        "strengths": result.get("strengths", []),
        "weaknesses": result.get("weaknesses", []),
        "improvement_plan": result.get("improvement_plan", {}),
        "technical_skills_list": result.get("technical_skills_list", []),
        "social_links": result.get("social_links"),
        "message": result.get("message", ""),
        "full_result": result,
    }
    return to_json_safe(analysis)
