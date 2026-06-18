from django.test import TestCase

from interviews.services.interview_feedback import generate_improvement_plan, generate_progress_report
from interviews.services.interview_engine import evaluate_session
from interviews.services.role_interview_constants import experience_band_from_years


class InterviewFeedbackTests(TestCase):
    def test_failed_report_is_candidate_facing_and_role_specific(self):
        result = {
            'final_decision': 'fail',
            'final_score': 58.0,
            'technical_score': 52.0,
            'personality_score': 61.0,
            'communication_score': 55.0,
            'confidence_score': 50.0,
            'attentiveness_score': 70.0,
            'eye_contact_score': 68.0,
            'filler_ratio': 0.1,
            'cooldown_days': 3,
            'job_role': 'Python Developer',
            'experience_band': 'junior_professional',
            'personality_trait': 'Communication',
        }
        report = generate_progress_report(result)
        plan = generate_improvement_plan(result, report)

        self.assertIn('You scored', report['overall_summary'])
        self.assertIn('Python Developer', report['overall_summary'])
        self.assertIn('Python Developer', ' '.join(report['recommendations']))
        self.assertIn('Django', ' '.join(report['recommendations']))
        self.assertNotIn('The candidate', report['overall_summary'])
        self.assertIn('Study plan', plan)
        self.assertIn('mid-level', plan.lower())

    def test_five_years_uses_senior_level_label_not_junior(self):
        result = {
            'final_decision': 'fail',
            'final_score': 62.0,
            'technical_score': 58.0,
            'personality_score': 65.0,
            'communication_score': 60.0,
            'confidence_score': 58.0,
            'attentiveness_score': 70.0,
            'eye_contact_score': 68.0,
            'filler_ratio': 0.1,
            'cooldown_days': 2,
            'job_role': 'Python Developer',
            'years_experience': 5.0,
            'experience_band': experience_band_from_years(5.0),
            'personality_trait': 'Communication',
        }
        report = generate_progress_report(result)
        plan = generate_improvement_plan(result, report)
        combined = f'{report["overall_summary"]} {plan}'.lower()
        self.assertIn('senior-level (3+ years)', combined)
        self.assertNotIn('junior (1', combined)
        self.assertNotIn('junior (1–3', combined)

    def test_pass_report_highlights_strengths(self):
        result = {
            'final_decision': 'pass',
            'final_score': 82.0,
            'technical_score': 85.0,
            'personality_score': 80.0,
            'communication_score': 78.0,
            'confidence_score': 76.0,
            'attentiveness_score': 88.0,
            'eye_contact_score': 86.0,
            'filler_ratio': 0.05,
            'cooldown_days': 0,
            'job_role': 'React Developer',
            'experience_band': 'fresher',
            'personality_trait': 'Collaboration',
        }
        report = generate_progress_report(result)
        plan = generate_improvement_plan(result, report)

        self.assertIn('You passed', report['overall_summary'])
        self.assertIn('React Developer', report['overall_summary'])
        self.assertIn('React Developer', plan)
        self.assertTrue(report['recommendations'])

    def test_evaluate_session_feedback_uses_session_role(self):
        session_meta = {
            'job_role': 'SQL Developer',
            'experience_years': 5.0,
            'experience_band': experience_band_from_years(5.0),
            'attentiveness_score': 55,
            'eye_contact_score': 55,
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
                'category': 'DBMS',
                'question_text': 'Explain indexing strategy.',
                'transcript': 'indexes speed reads',
            },
            {
                'question_type': 'personality',
                'category': 'Communication',
                'question_text': 'Tell me about conflict.',
                'transcript': 'I talked to my teammate',
            },
        ]
        result = evaluate_session(answers=answers, session_meta=session_meta)
        joined = ' '.join(result['progress_report']['recommendations'])
        self.assertIn('SQL Developer', joined)
        self.assertIn('DBMS', joined)
        self.assertIn('You scored', result['progress_report']['overall_summary'])
