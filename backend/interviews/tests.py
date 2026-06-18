from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from quizzes.models import QuizSession
from resumes.models import Resume
from interviews.models import InterviewSession, InterviewQuestion
from interviews.services.interview_engine import evaluate_session, prepare_interview_start
from interviews.services.attentiveness_monitoring import compute_monitoring_scores, merge_monitoring_state
from interviews.services.interview_ai.engine import experience_band_from_years, generate_interview_questions
from interviews.services.question_quality import normalize_for_dedupe

User = get_user_model()


class InterviewModuleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='candidate1',
            email='candidate1@example.com',
            password='testpass123',
        )
        Resume.objects.create(
            user=self.user,
            job_role='Python Developer',
            years_experience=4.0,
            file=SimpleUploadedFile('resume.pdf', b'fake resume content', content_type='application/pdf'),
            score=80,
        )
        QuizSession.objects.create(
            user=self.user,
            job_role='Python Developer',
            score=85,
            passed=True,
            submitted_at=timezone.now(),
        )

    def test_prepare_interview_start_after_quiz(self):
        payload = prepare_interview_start(
            quiz_passed=True,
            job_role='Python Developer',
            years_experience=4.0,
            num_questions=6,
        )
        self.assertTrue(payload['can_start_interview'])
        self.assertEqual(len(payload['questions']), 6)
        types = {q['question_type'] for q in payload['questions']}
        self.assertIn('technical', types)
        self.assertIn('personality', types)

    def test_question_echo_scores_low(self):
        q_technical = (
            'Design an LRU cache with O(1) get and put. Explain the data structures and edge cases.'
        )
        q_personality = (
            'Tell me about a time you had to explain a technical idea to someone without a technical background.'
        )
        session_meta = {
            'job_role': 'Python Developer',
            'experience_years': 4.0,
            'experience_band': experience_band_from_years(4.0),
            'attentiveness_score': 90,
            'eye_contact_score': 88,
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
                'category': 'DSA',
                'question_text': q_technical,
                'transcript': q_technical,
            },
            {
                'question_type': 'personality',
                'category': 'Communication',
                'question_text': q_personality,
                'transcript': q_personality,
            },
        ]
        result = evaluate_session(answers=answers, session_meta=session_meta)
        for item in result['per_question_scores']:
            self.assertLess(
                item['score'],
                25,
                msg=f"Read-back answer scored too high: {item['score']} for {item['question_type']}",
            )
        self.assertFalse(result['passed'])

    def test_react_developer_retake_has_no_overlap(self):
        first = generate_interview_questions(
            job_role='React Developer',
            experience_years=3.0,
            num_questions=6,
            seed=101,
        )
        first_keys = {normalize_for_dedupe(q['question_text']) for q in first}
        first_texts = {q['question_text'] for q in first}

        second = generate_interview_questions(
            job_role='React Developer',
            experience_years=3.0,
            num_questions=6,
            seed=202,
            exclude_questions=first_keys | first_texts,
        )
        second_keys = {normalize_for_dedupe(q['question_text']) for q in second}
        self.assertEqual(first_keys & second_keys, set())

    def test_three_attempts_same_role_and_years_stay_unique(self):
        role = 'Python Developer'
        years = 5.0
        exclude: set[str] = set()
        all_keys: set[str] = set()
        for attempt in range(3):
            batch = generate_interview_questions(
                job_role=role,
                experience_years=years,
                num_questions=6,
                seed=1000 + attempt,
                exclude_questions=exclude,
            )
            batch_keys = {normalize_for_dedupe(q['question_text']) for q in batch}
            overlap = batch_keys & all_keys
            self.assertEqual(overlap, set(), msg=f'Attempt {attempt + 1} repeated prior questions')
            all_keys.update(batch_keys)
            for question in batch:
                exclude.add(question['question_text'])
                exclude.add(normalize_for_dedupe(question['question_text']))

    def test_substantive_technical_answer_outscores_readback(self):
        q_technical = (
            'As a Python Developer with several years of experience, design a caching strategy '
            'for a Django view that aggregates data from three services with different SLAs.'
        )
        good_answer = (
            'I would introduce Redis in front of the Django view with cache keys scoped by tenant '
            'and endpoint. Each downstream service has a different SLA, so I would use shorter TTL '
            'for fast-changing data and longer TTL for stable aggregates. I would invalidate cache '
            'on write events, add a circuit breaker when a dependency fails, and monitor hit rate '
            'and stale reads in production. The trade-off is freshness versus latency, so I would '
            'document acceptable staleness with product owners before rollout.'
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
        readback = evaluate_session(
            answers=[{
                'question_type': 'technical',
                'category': 'Django',
                'question_text': q_technical,
                'transcript': q_technical,
            }],
            session_meta=session_meta,
        )
        substantive = evaluate_session(
            answers=[{
                'question_type': 'technical',
                'category': 'Django',
                'question_text': q_technical,
                'transcript': good_answer,
            }],
            session_meta=session_meta,
        )
        readback_score = readback['per_question_scores'][0]['score']
        substantive_score = substantive['per_question_scores'][0]['score']
        self.assertLess(readback_score, 25)
        self.assertGreater(substantive_score, readback_score)
        self.assertGreater(substantive_score, 40)

    def test_role_aligned_questions_for_python_developer(self):
        payload = prepare_interview_start(
            quiz_passed=True,
            job_role='Python Developer',
            years_experience=4.0,
            num_questions=6,
            seed=42,
        )
        self.assertTrue(payload['can_start_interview'])
        for question in payload['questions']:
            self.assertEqual(question['role'], 'Python Developer')
            self.assertEqual(question['experience_band'], 'mid_level_expert')
            self.assertEqual(question['experience_years'], 4.0)
            self.assertIn('python developer', question['question_text'].lower())

    def test_sql_developer_never_gets_dsa_questions(self):
        forbidden = (
            'linked list',
            'array and a linked',
            'binary search tree',
            'merge two sorted arrays',
            'hash map versus binary',
        )
        for seed in range(30):
            payload = prepare_interview_start(
                quiz_passed=True,
                job_role='SQL Developer',
                years_experience=2.0,
                num_questions=6,
                seed=seed,
            )
            for question in payload['questions']:
                if question['question_type'] != 'technical':
                    continue
                lower = question['question_text'].lower()
                for fragment in forbidden:
                    self.assertNotIn(
                        fragment,
                        lower,
                        msg=f'SQL Developer got off-topic question: {question["question_text"]}',
                    )

    def test_generated_questions_match_job_role_not_other_roles(self):
        payload = prepare_interview_start(
            quiz_passed=True,
            job_role='Data Scientist',
            years_experience=1.5,
            num_questions=6,
            seed=55,
        )
        self.assertTrue(payload['can_start_interview'])
        for question in payload['questions']:
            text = question['question_text'].lower()
            self.assertIn('data scientist', text)
            self.assertNotIn('python developer', text)
            self.assertNotIn('java developer', text)

    def test_no_duplicates_when_catalog_exhausted(self):
        from interviews.services.role_question_catalog import (
            PERSONALITY_CATALOG,
            TECHNICAL_CATALOG,
            collect_role_scoped_candidates,
        )

        role = 'Python Developer'
        band = 'mid_level_expert'
        exclude: set[str] = set()
        for bank in (TECHNICAL_CATALOG, PERSONALITY_CATALOG):
            for focus_band in ('fresher', 'junior_professional', band, 'senior_professional'):
                exclude.update(
                    collect_role_scoped_candidates(
                        bank, role, focus_band, 'easy', set()
                    )
                )
                exclude.update(
                    collect_role_scoped_candidates(
                        bank, role, focus_band, 'medium', set()
                    )
                )
                exclude.update(
                    collect_role_scoped_candidates(
                        bank, role, focus_band, 'hard', set()
                    )
                )

        payload = prepare_interview_start(
            quiz_passed=True,
            job_role=role,
            years_experience=4.0,
            num_questions=6,
            seed=999,
            exclude_questions=exclude,
        )
        texts = [q['question_text'] for q in payload['questions']]
        self.assertEqual(len(texts), len(set(texts)))

    def test_second_attempt_avoids_previous_questions(self):
        first = generate_interview_questions(
            job_role='Python Developer',
            experience_years=4.0,
            num_questions=6,
            seed=101,
        )
        first_texts = {q['question_text'] for q in first}
        self.assertEqual(len(first_texts), 6)

        second = generate_interview_questions(
            job_role='Python Developer',
            experience_years=4.0,
            num_questions=6,
            seed=202,
            exclude_questions=first_texts,
        )
        second_texts = {q['question_text'] for q in second}
        overlap = first_texts & second_texts
        self.assertEqual(
            overlap,
            set(),
            msg=f'Second interview reused questions: {overlap}',
        )

    def test_empty_answers_score_zero(self):
        session_meta = {
            'job_role': 'Python Developer',
            'experience_years': 4.0,
            'experience_band': experience_band_from_years(4.0),
            'attentiveness_score': 90,
            'eye_contact_score': 88,
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
                'question_text': 'Explain Django ORM optimization.',
                'transcript': '',
            },
            {
                'question_type': 'personality',
                'category': 'Communication',
                'question_text': 'Tell me about a conflict.',
                'transcript': '   ',
            },
        ]
        result = evaluate_session(answers=answers, session_meta=session_meta)
        self.assertEqual(result['final_score'], 0)
        self.assertFalse(result['passed'])
        self.assertEqual(result['technical_score'], 0)
        self.assertEqual(result['personality_score'], 0)

    def test_react_recommendations_use_session_job_role(self):
        session_meta = {
            'job_role': 'React Developer',
            'experience_years': 2.0,
            'experience_band': experience_band_from_years(2.0),
            'attentiveness_score': 50,
            'eye_contact_score': 50,
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
                'category': 'React',
                'question_text': 'Explain props versus state in React.',
                'transcript': 'props are inputs from parent',
            },
            {
                'question_type': 'technical',
                'category': 'DSA',
                'question_text': 'Explain two-sum.',
                'transcript': 'hash map',
            },
            {
                'question_type': 'technical',
                'category': 'Software Engineering',
                'question_text': 'Describe component testing.',
                'transcript': 'react testing library',
            },
            {
                'question_type': 'personality',
                'category': 'Communication',
                'question_text': 'Tell me about a conflict.',
                'transcript': 'I communicated clearly',
            },
            {
                'question_type': 'personality',
                'category': 'Collaboration',
                'question_text': 'Describe teamwork.',
                'transcript': 'we paired on a feature',
            },
            {
                'question_type': 'personality',
                'category': 'Adaptability',
                'question_text': 'Describe change.',
                'transcript': 'I adapted to new requirements',
            },
        ]
        result = evaluate_session(answers=answers, session_meta=session_meta)
        self.assertEqual(result['target_role'], 'React Developer')
        recommendations = result['progress_report']['recommendations']
        joined = ' '.join(recommendations)
        self.assertIn('React Developer', joined)
        self.assertNotIn('Software Developer', joined)
        self.assertIn('React', joined)

    def test_normalize_role_is_case_insensitive(self):
        from interviews.services.interview_ai.engine import normalize_role, ensure_models_loaded

        ensure_models_loaded()
        self.assertEqual(normalize_role('react developer'), 'React Developer')
        self.assertEqual(normalize_role('REACT DEVELOPER'), 'React Developer')

    def test_data_scientist_senior_years_avoid_fresher_phrasing(self):
        payload = prepare_interview_start(
            quiz_passed=True,
            job_role='Data Scientist',
            years_experience=5.0,
            num_questions=6,
            seed=20260608,
        )
        self.assertTrue(payload['can_start_interview'])
        self.assertEqual(payload.get('experience_band'), 'mid_level_expert')
        for question in payload['questions']:
            lower = question['question_text'].lower()
            self.assertNotIn('starting your career', lower, msg=question['question_text'])

    def test_resume_form_values_map_to_interview_bands(self):
        """ResumeUpload.tsx stores 1, 3, 5 — interview must use matching bands."""
        from interviews.services.role_interview_constants import RESUME_EXPERIENCE_TIER_YEARS

        self.assertEqual(RESUME_EXPERIENCE_TIER_YEARS, (1.0, 3.0, 5.0))
        self.assertEqual(experience_band_from_years(1.0), 'fresher')
        self.assertEqual(experience_band_from_years(3.0), 'junior_professional')
        self.assertEqual(experience_band_from_years(5.0), 'mid_level_expert')

        for years, expected_band in (
            (1.0, 'fresher'),
            (3.0, 'junior_professional'),
            (5.0, 'mid_level_expert'),
        ):
            payload = prepare_interview_start(
                quiz_passed=True,
                job_role='React Developer',
                years_experience=years,
                num_questions=6,
                seed=int(years * 100),
            )
            self.assertEqual(payload.get('experience_band'), expected_band)
            mid_markers = ('with 3–5 years of experience', 'with 3-5 years of experience')
            for question in payload['questions']:
                self.assertEqual(question['experience_band'], expected_band)
                if expected_band == 'junior_professional':
                    lower = question['question_text'].lower()
                    for marker in mid_markers:
                        self.assertNotIn(marker, lower, msg=question['question_text'])

    def test_resume_mid_level_years_use_junior_band_not_mid(self):
        """Resume '1+ to 3 years' stores 2–3y; must not get mid-level (3–5y) phrasing."""
        self.assertEqual(experience_band_from_years(3.0), 'junior_professional')
        self.assertEqual(experience_band_from_years(2.0), 'junior_professional')
        payload = prepare_interview_start(
            quiz_passed=True,
            job_role='React Developer',
            years_experience=3.0,
            num_questions=6,
            seed=20260609,
        )
        self.assertEqual(payload.get('experience_band'), 'junior_professional')
        mid_markers = ('with 3–5 years of experience', 'with 3-5 years of experience')
        for question in payload['questions']:
            self.assertEqual(question['experience_band'], 'junior_professional')
            lower = question['question_text'].lower()
            for marker in mid_markers:
                self.assertNotIn(marker, lower, msg=question['question_text'])
            self.assertNotIn('as a senior professional', lower)
            self.assertNotIn('as an industry veteran', lower)

    def test_monitoring_backend_scores(self):
        state = merge_monitoring_state(None, {
            'samples': [
                {'attentive': True, 'eye_contact': True},
                {'attentive': False, 'eye_contact': False},
                {'attentive': True, 'eye_contact': True},
                {'attentive': True, 'eye_contact': False},
            ],
        })
        scores = compute_monitoring_scores(state)
        self.assertEqual(scores['attentiveness_score'], 75.0)
        self.assertEqual(scores['eye_contact_score'], 50.0)

    def _auth_client(self, user):
        client = APIClient()
        token = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')
        return client

    def test_start_interview_api_requires_quiz(self):
        user = User.objects.create_user(
            username='noquiz',
            email='noquiz@example.com',
            password='testpass123',
        )
        client = self._auth_client(user)
        response = client.post('/api/interviews/start/')
        self.assertEqual(response.status_code, 403)

    def test_start_interview_api_success(self):
        client = self._auth_client(self.user)
        response = client.post('/api/interviews/start/')
        self.assertIn(response.status_code, (200, 201))
        data = response.json()
        self.assertIn('session_id', data)
        self.assertIn('job_role', data)
        self.assertIn('years_experience', data)
        session = InterviewSession.objects.get(id=data['session_id'])
        self.assertEqual(session.years_experience, 4.0)
        self.assertEqual(InterviewQuestion.objects.filter(session=session).count(), 6)
