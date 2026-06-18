"""Semantic similarity scoring for interview answers (supports short but correct replies)."""

from __future__ import annotations

from functools import lru_cache

from .reference_answer_scoring import TOPIC_REFERENCE_KEYWORDS, parse_reference_keywords

SEMANTIC_MODEL_NAME = 'sentence-transformers/all-MiniLM-L6-v2'
SEMANTIC_SHORT_ANSWER_BYPASS = 68.0
SEMANTIC_STRONG_MATCH = 75.0

QUALITY_BLEND_WEIGHT = 0.35
REFERENCE_BLEND_WEIGHT = 0.30
SEMANTIC_BLEND_WEIGHT = 0.35

TOPIC_MODEL_ANSWER_SNIPPETS: dict[str, str] = {
    'Django': (
        'Use Django ORM with select_related and prefetch_related to avoid N+1 queries, '
        'add Redis caching with sensible TTL and invalidation, and keep migrations and queryset access safe in production.'
    ),
    'DBMS': (
        'Choose appropriate indexes, analyze execution plans, write efficient SQL with joins and transactions, '
        'and keep schema changes and backups safe under load.'
    ),
    'React': (
        'Build UI with components, manage state and hooks carefully, avoid unnecessary re-renders, '
        'and handle props, effects, accessibility, and performance trade-offs.'
    ),
    'Artificial Intelligence': (
        'Explain retrieval, embeddings, prompts, inference, and guardrails clearly with a concrete example '
        'and mention latency, safety, or evaluation trade-offs.'
    ),
    'Machine Learning': (
        'Describe training, validation, features, metrics, and deployment concerns with a concrete example '
        'and mention overfitting, leakage, or class imbalance trade-offs.'
    ),
    'DevOps': (
        'Use CI/CD, containers, monitoring, and rollback strategies with clear steps for safe deployment '
        'and incident response.'
    ),
    'Software Engineering': (
        'Explain requirements, design, testing, and maintainability with a concrete example and trade-offs.'
    ),
    'Behavioral': (
        'Use STAR format with a real example: situation, task, action, result, and what you learned.'
    ),
}


@lru_cache(maxsize=1)
def _load_encoder():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None
    try:
        return SentenceTransformer(SEMANTIC_MODEL_NAME)
    except Exception:
        return None


def semantic_scoring_available() -> bool:
    return _load_encoder() is not None


def build_semantic_reference_texts(
    *,
    question_text: str,
    reference_points: str = '',
    reference_keywords: str = '',
    category: str = '',
    question_type: str = 'technical',
    job_role: str = '',
) -> list[str]:
    """Build one or more reference texts to compare against the candidate answer."""
    texts: list[str] = []
    question = str(question_text or '').strip()
    if question:
        texts.append(question)

    points = str(reference_points or '').strip()
    if points:
        texts.append(points)

    keywords = parse_reference_keywords(reference_keywords)
    topic = str(category or '').strip() or 'Software Engineering'
    qtype = 'personality' if question_type == 'personality' else 'technical'

    if qtype == 'personality':
        texts.append(TOPIC_MODEL_ANSWER_SNIPPETS['Behavioral'])
        if keywords:
            texts.append(
                f'A strong answer for a {job_role or "candidate"} should address: '
                f'{", ".join(keywords[:12])}.'
            )
    else:
        snippet = TOPIC_MODEL_ANSWER_SNIPPETS.get(topic)
        if not snippet:
            topic_keywords = TOPIC_REFERENCE_KEYWORDS.get(topic, ())
            if topic_keywords:
                snippet = (
                    f'A complete {topic} answer explains {", ".join(topic_keywords[:10])} '
                    'with a concrete example and trade-offs.'
                )
        if snippet:
            texts.append(f'Question: {question} Ideal answer: {snippet}')
        if keywords:
            texts.append(
                f'A complete answer should cover: {", ".join(keywords[:14])}. '
                'Include one example and mention trade-offs or edge cases.'
            )

    deduped: list[str] = []
    seen: set[str] = set()
    for text in texts:
        cleaned = ' '.join(str(text).split())
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def evaluate_semantic_match(
    transcript: str,
    *,
    question_text: str = '',
    reference_points: str = '',
    reference_keywords: str = '',
    category: str = '',
    question_type: str = 'technical',
    job_role: str = '',
) -> dict | None:
    """Return semantic similarity score (0-100) against model/reference texts."""
    answer = str(transcript or '').strip()
    if len(answer.split()) < 3:
        return None

    encoder = _load_encoder()
    if encoder is None:
        return None

    references = build_semantic_reference_texts(
        question_text=question_text,
        reference_points=reference_points,
        reference_keywords=reference_keywords,
        category=category,
        question_type=question_type,
        job_role=job_role,
    )
    if not references:
        return None

    try:
        import numpy as np

        answer_emb = encoder.encode([answer], normalize_embeddings=True)
        ref_emb = encoder.encode(references, normalize_embeddings=True)
        similarities = np.dot(ref_emb, answer_emb[0])
        best_idx = int(similarities.argmax())
        best_similarity = float(similarities[best_idx])
        semantic_score = round(max(0.0, min(100.0, best_similarity * 100.0)), 2)
        return {
            'semantic_score': semantic_score,
            'semantic_similarity': round(best_similarity, 4),
            'semantic_reference_index': best_idx,
            'semantic_model': SEMANTIC_MODEL_NAME,
        }
    except Exception:
        return None


def blend_answer_scores(
    quality_score: float,
    reference_match: dict | None,
    semantic_match: dict | None,
) -> float:
    """Blend ML/rule quality, keyword reference match, and semantic similarity."""
    ref_score = float(reference_match['reference_score']) if reference_match else float(quality_score)
    sem_score = float(semantic_match['semantic_score']) if semantic_match else ref_score

    if reference_match and semantic_match:
        blended = (
            float(quality_score) * QUALITY_BLEND_WEIGHT
            + ref_score * REFERENCE_BLEND_WEIGHT
            + sem_score * SEMANTIC_BLEND_WEIGHT
        )
    elif semantic_match:
        blended = float(quality_score) * 0.55 + sem_score * 0.45
    elif reference_match:
        blended = blend_with_reference_legacy(quality_score, reference_match)
    else:
        blended = float(quality_score)

    return round(max(0.0, min(100.0, blended)), 2)


def blend_with_reference_legacy(quality_score: float, reference_match: dict | None) -> float:
    from .reference_answer_scoring import REFERENCE_BLEND_WEIGHT

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
