from django.test import TestCase

from interviews.services.interview_engine import evaluate_session
from interviews.services.role_interview_constants import experience_band_from_years
from interviews.services.semantic_answer_scoring import (
    build_semantic_reference_texts,
    evaluate_semantic_match,
    semantic_scoring_available,
)


class SemanticAnswerScoringTests(TestCase):
    def test_build_semantic_reference_texts_includes_topic_snippet(self):
        texts = build_semantic_reference_texts(
            question_text='Explain Django ORM optimization with select_related.',
            reference_points='Explain ORM concepts with an example.',
            reference_keywords='select_related|prefetch_related|queryset|orm|cache',
            category='Django',
            question_type='technical',
            job_role='Python Developer',
        )
        joined = ' '.join(texts).lower()
        self.assertIn('select_related', joined)
        self.assertIn('django', joined)

    def test_short_correct_answer_scores_higher_than_nonsense_when_semantic_enabled(self):
        if not semantic_scoring_available():
            self.skipTest('sentence-transformers model unavailable')

        question = 'How would you optimize Django ORM queries to avoid N+1 problems?'
        keywords = 'select_related|prefetch_related|queryset|orm|n+1|cache|redis|migration'
        points = 'Explain ORM optimization with select_related/prefetch_related and a concrete example.'
        session_meta = {
            'job_role': 'Python Developer',
            'experience_years': 4.0,
            'experience_band': experience_band_from_years(4.0),
            'attentiveness_score': 85,
            'eye_contact_score': 85,
            'tab_switches': 0,
            'window_blur_events': 0,
            'screenshot_attempted': 0,
            'device_detected': 0,
            'gaze_off_over_20s': 0,
            'camera_available': 1,
            'mic_available': 1,
            'english_only_violation': 0,
        }
        short_good = evaluate_session(
            answers=[{
                'question_type': 'technical',
                'category': 'Django',
                'question_text': question,
                'transcript': 'Use select_related and prefetch_related to avoid N+1 queryset queries.',
                'reference_keywords': keywords,
                'reference_points': points,
                'job_role': 'Python Developer',
            }],
            session_meta=session_meta,
        )
        nonsense = evaluate_session(
            answers=[{
                'question_type': 'technical',
                'category': 'Django',
                'question_text': question,
                'transcript': (
                    'Well basically things happen and people talk every day without explaining anything useful.'
                ),
                'reference_keywords': keywords,
                'reference_points': points,
                'job_role': 'Python Developer',
            }],
            session_meta=session_meta,
        )
        good_score = short_good['per_question_scores'][0]['score']
        bad_score = nonsense['per_question_scores'][0]['score']
        self.assertGreater(good_score, 45.0)
        self.assertLess(bad_score, 25.0)
        self.assertGreater(good_score, bad_score)
        self.assertIsNotNone(short_good['per_question_scores'][0].get('semantic_score'))

    def test_evaluate_semantic_match_returns_score(self):
        if not semantic_scoring_available():
            self.skipTest('sentence-transformers model unavailable')
        result = evaluate_semantic_match(
            'Use select_related and prefetch_related to avoid N+1 ORM queries.',
            question_text='Explain Django ORM optimization.',
            reference_points='Mention select_related, prefetch_related, and N+1.',
            reference_keywords='select_related|prefetch_related|queryset|orm|n+1',
            category='Django',
            question_type='technical',
            job_role='Python Developer',
        )
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result['semantic_score'], 55.0)
