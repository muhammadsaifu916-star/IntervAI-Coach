"""Rule-based answer quality checks used alongside ML scoring."""

from __future__ import annotations

import re

STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'to', 'of', 'in', 'on', 'for', 'with', 'is', 'are',
    'was', 'were', 'be', 'been', 'being', 'you', 'your', 'how', 'what', 'when', 'where',
    'why', 'would', 'could', 'should', 'do', 'does', 'did', 'i', 'me', 'my', 'we', 'our',
    'they', 'their', 'this', 'that', 'it', 'as', 'at', 'by', 'from', 'about', 'into',
    'through', 'during', 'before', 'after', 'above', 'below', 'can', 'will', 'shall',
    'have', 'has', 'had', 'not', 'only', 'also', 'than', 'then', 'them', 'these', 'those',
    'explain', 'describe', 'tell', 'walk', 'give', 'discuss', 'compare', 'design',
}

STAR_MARKERS = ['situation', 'task', 'action', 'result', 'learned', 'outcome', 'because', 'therefore']

SEMANTIC_SHORT_ANSWER_BYPASS = 68.0
SEMANTIC_STRONG_MATCH = 75.0

MIN_NEW_WORDS = {
    'fresher': {'technical': 12, 'personality': 20},
    'junior_professional': {'technical': 15, 'personality': 24},
    'mid_level_expert': {'technical': 18, 'personality': 28},
    'senior_professional': {'technical': 22, 'personality': 32},
    'industry_veteran': {'technical': 25, 'personality': 35},
}


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", str(text or '').lower())


def content_tokens(text: str) -> set[str]:
    return {w for w in tokenize(text) if w not in STOPWORDS and len(w) > 2}


def question_echo_ratio(answer: str, question: str) -> float:
    """Share of answer content tokens that also appear in the question (read-back)."""
    question_tokens = content_tokens(question)
    answer_tokens = content_tokens(answer)
    if not answer_tokens:
        return 1.0
    if not question_tokens:
        return 0.0
    repeated = answer_tokens & question_tokens
    return len(repeated) / len(answer_tokens)


def new_content_word_count(answer: str, question: str) -> int:
    return len(content_tokens(answer) - content_tokens(question))


def is_mostly_question_readback(answer: str, question: str) -> bool:
    answer = str(answer or '').strip()
    question = str(question or '').strip()
    if not answer:
        return True

    a_tokens = tokenize(answer)
    q_tokens = tokenize(question)
    if len(a_tokens) < 8:
        return True

    # Near-verbatim read-back of the prompt
    if answer.lower().strip() in question.lower() or question.lower().strip() in answer.lower():
        return True

    # Very high overlap with almost no new substance
    if question_echo_ratio(answer, question) >= 0.58 and new_content_word_count(answer, question) < 6:
        return True

    return question_echo_ratio(answer, question) >= 0.72


def min_new_words_required(experience_band: str, question_type: str) -> int:
    band = experience_band if experience_band in MIN_NEW_WORDS else 'junior_professional'
    qtype = 'personality' if question_type == 'personality' else 'technical'
    return MIN_NEW_WORDS[band][qtype]


def gate_answer_score(
    answer: str,
    question: str,
    question_type: str,
    experience_band: str,
    semantic_score: float | None = None,
) -> float | None:
    """
    Return a hard-capped score when the answer is empty, read-back, or too short.
    Return None when the answer should proceed to ML + substantive scoring.
    """
    answer = str(answer or '').strip()
    question = str(question or '').strip()
    if not answer:
        return 0.0

    if is_mostly_question_readback(answer, question):
        return 8.0

    new_words = new_content_word_count(answer, question)
    minimum = min_new_words_required(experience_band, question_type)

    if new_words < minimum:
        if semantic_score is not None and semantic_score >= SEMANTIC_SHORT_ANSWER_BYPASS:
            return None
        return float(min(18.0, max(5.0, new_words * 1.2)))

    if question_type == 'personality':
        lower = answer.lower()
        star_hits = sum(1 for marker in STAR_MARKERS if marker in lower)
        has_first_person = any(p in lower for p in [' i ', ' my ', ' we ', "i'd", "i've", "i'm"])
        if star_hits == 0 and not has_first_person and new_words < minimum + 8:
            if semantic_score is not None and semantic_score >= SEMANTIC_SHORT_ANSWER_BYPASS:
                return None
            return 22.0

    return None


def substantive_content_score(
    answer: str,
    question: str,
    question_type: str,
    experience_band: str,
    keyword_hits: int = 0,
    star_hits: int = 0,
    semantic_score: float | None = None,
) -> float:
    """Upper bound for ML score based on real answer substance (not question echo)."""
    new_words = new_content_word_count(answer, question)
    minimum = min_new_words_required(experience_band, question_type)
    if new_words < minimum:
        if semantic_score is not None and semantic_score >= SEMANTIC_STRONG_MATCH:
            return min(82.0, 38.0 + semantic_score * 0.45)
        return 18.0

    echo = question_echo_ratio(answer, question)
    base = 20.0 + min(22.0, new_words * 0.9) + keyword_hits * 8.0
    base -= echo * 35.0

    # Long rambling without domain terms should not score well.
    if keyword_hits == 0:
        base = min(base, 26.0 if question_type == 'technical' else 30.0)

    if question_type == 'personality':
        base += star_hits * 8.0
        if any(p in answer.lower() for p in [' i ', ' my ', ' we ']):
            base += 8.0

    if question_type == 'technical':
        lower = answer.lower()
        if any(k in lower for k in ['trade-off', 'complexity', 'edge case', 'because', 'therefore', 'example']):
            base += 10.0

    return max(12.0, min(85.0, base))


def lexical_diversity(text: str) -> float:
    """Unique-token ratio; low values suggest repetitive filler speech."""
    tokens = tokenize(text)
    if not tokens:
        return 0.0
    return len(set(tokens)) / len(tokens)


def reference_relevance_score_cap(
    reference_match_pct: float | None,
    keyword_hits: int,
    question_type: str,
) -> float:
    """Hard ceiling when an answer misses expected topic coverage."""
    ref = float(reference_match_pct or 0)
    qtype = 'personality' if question_type == 'personality' else 'technical'

    if qtype == 'technical':
        if ref < 8 and keyword_hits == 0:
            return 16.0
        if ref < 15:
            return 24.0
        if ref < 30:
            return 38.0
        if ref < 45:
            return 52.0
        return 100.0

    if ref < 12 and keyword_hits == 0:
        return 18.0
    if ref < 25:
        return 35.0
    if ref < 40:
        return 50.0
    return 100.0


def apply_answer_score_caps(
    score: float,
    *,
    transcript: str,
    reference_match: dict | None,
    keyword_hits: int,
    question_type: str,
    semantic_match: dict | None = None,
) -> float:
    """Apply relevance and repetition caps after ML/reference/semantic blending."""
    capped = float(score)
    sem = float((semantic_match or {}).get('semantic_score', 0) or 0)

    if reference_match is not None:
        ref_pct = float(reference_match.get('reference_match_pct', 0) or 0)
        if sem >= SEMANTIC_STRONG_MATCH and ref_pct < 35:
            capped = min(float(score), max(capped, sem * 0.9))
        else:
            capped = min(
                capped,
                reference_relevance_score_cap(ref_pct, keyword_hits, question_type),
            )
    elif question_type == 'technical' and keyword_hits == 0:
        capped = min(capped, 38.0)

    if sem >= SEMANTIC_STRONG_MATCH:
        capped = max(capped, min(float(score), sem * 0.88))

    diversity = lexical_diversity(transcript)
    if diversity < 0.32 and sem < SEMANTIC_SHORT_ANSWER_BYPASS:
        capped = min(capped, 18.0)
    elif diversity < 0.40 and reference_match and float(reference_match.get('reference_match_pct', 0) or 0) < 25:
        if sem < SEMANTIC_SHORT_ANSWER_BYPASS:
            capped = min(capped, 22.0)
    return round(max(0.0, min(100.0, capped)), 2)


def session_completion_multiplier(answered_count: int, total_questions: int) -> float:
    """Scale session delivery metrics by how many prompts were actually answered."""
    if total_questions <= 0 or answered_count <= 0:
        return 0.0
    ratio = answered_count / total_questions
    return round(0.12 + 0.88 * ratio, 4)
