from django.test import TestCase

from interviews.services.answer_quality import (
    apply_answer_score_caps,
    lexical_diversity,
    session_completion_multiplier,
)
from interviews.services.interview_engine import evaluate_session
from interviews.services.role_interview_constants import experience_band_from_years


class AnswerQualityTests(TestCase):
    def test_nonsense_rambling_scores_low(self):
        question = 'Explain Django ORM query optimization with select_related and prefetch_related.'
        nonsense = (
            'Well basically you know I think things are things and stuff happens sometimes and '
            'people talk about many topics every day and life goes on and we continue speaking '
            'about random ideas without really explaining anything useful in a structured way.'
        )
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
        result = evaluate_session(
            answers=[{
                'question_type': 'technical',
                'category': 'Django',
                'question_text': question,
                'transcript': nonsense,
            }],
            session_meta=session_meta,
        )
        score = result['per_question_scores'][0]['score']
        self.assertLess(score, 25.0, msg=f'Expected low nonsense score, got {score}')

    def test_one_of_six_answers_keeps_communication_and_confidence_low(self):
        session_meta = {
            'job_role': 'Python Developer',
            'experience_years': 4.0,
            'experience_band': experience_band_from_years(4.0),
            'attentiveness_score': 90,
            'eye_contact_score': 90,
            'tab_switches': 0,
            'window_blur_events': 0,
            'screenshot_attempted': 0,
            'device_detected': 0,
            'gaze_off_over_20s': 0,
            'camera_available': 1,
            'mic_available': 1,
            'english_only_violation': 0,
        }
        answers = [
            {
                'question_type': 'technical',
                'category': 'Django',
                'question_text': 'Explain caching in Django.',
                'transcript': (
                    'Well basically things happen and people talk and life continues and we keep '
                    'speaking without giving any clear structured explanation or useful detail.'
                ),
            },
            {'question_type': 'technical', 'category': 'DBMS', 'question_text': 'Indexing?', 'transcript': ''},
            {'question_type': 'technical', 'category': 'Django', 'question_text': 'Signals?', 'transcript': ''},
            {'question_type': 'personality', 'category': 'Communication', 'question_text': 'Conflict?', 'transcript': ''},
            {'question_type': 'personality', 'category': 'Collaboration', 'question_text': 'Teamwork?', 'transcript': ''},
            {'question_type': 'personality', 'category': 'Leadership', 'question_text': 'Lead?', 'transcript': ''},
        ]
        result = evaluate_session(answers=answers, session_meta=session_meta)
        self.assertLess(result['communication_score'], 35.0)
        self.assertLess(result['confidence_score'], 35.0)
        self.assertLess(result['final_score'], 45.0)
        self.assertFalse(result['passed'])

    def test_completion_multiplier_scales_with_answered_questions(self):
        self.assertEqual(session_completion_multiplier(0, 6), 0.0)
        self.assertAlmostEqual(session_completion_multiplier(1, 6), 0.12 + 0.88 / 6, places=3)
        self.assertEqual(session_completion_multiplier(6, 6), 1.0)

    def test_apply_answer_score_caps_limits_off_topic_answer(self):
        capped = apply_answer_score_caps(
            55.0,
            transcript='random words without technical meaning repeated again and again',
            reference_match={'reference_match_pct': 5.0},
            keyword_hits=0,
            question_type='technical',
        )
        self.assertLessEqual(capped, 24.0)

    def test_lexical_diversity_detects_repetition(self):
        self.assertLess(lexical_diversity('foo bar foo bar foo bar foo bar foo bar'), 0.5)
