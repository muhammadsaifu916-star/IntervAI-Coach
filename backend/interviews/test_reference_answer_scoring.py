from django.test import TestCase
import re

from interviews.services.reference_answer_scoring import (
    MAX_REFERENCE_KEYWORDS,
    PERSONALITY_TRAIT_REFERENCE_KEYWORDS,
    QUESTION_HINT_STOPWORDS,
    REFERENCE_BLEND_WEIGHT,
    ROLE_REFERENCE_KEYWORDS,
    TOPIC_REFERENCE_KEYWORDS,
    blend_with_reference_score,
    build_reference_metadata,
    evaluate_reference_match,
    parse_reference_keywords,
)
from interviews.services.role_interview_constants import (
    ROLE_INTERVIEW_SKILLS,
    ROLE_PERSONALITY_TRAITS,
    USER_APPROVED_JOB_ROLES,
)
from interviews.services.interview_engine import evaluate_session
from interviews.services.interview_ai.engine import experience_band_from_years


class ReferenceAnswerScoringTests(TestCase):
    def test_every_role_has_reference_keywords(self):
        for role in USER_APPROVED_JOB_ROLES:
            self.assertIn(role, ROLE_REFERENCE_KEYWORDS)
            self.assertGreaterEqual(len(ROLE_REFERENCE_KEYWORDS[role]), 8)

    def test_every_interview_skill_has_topic_keywords(self):
        skills = {skill for skills in ROLE_INTERVIEW_SKILLS.values() for skill in skills}
        skills.add('Behavioral')
        for skill in skills:
            self.assertIn(skill, TOPIC_REFERENCE_KEYWORDS, msg=f'Missing topic keywords for {skill}')

    def test_every_personality_trait_has_reference_keywords(self):
        traits = {trait for traits in ROLE_PERSONALITY_TRAITS.values() for trait in traits}
        for trait in traits:
            self.assertIn(trait, PERSONALITY_TRAIT_REFERENCE_KEYWORDS, msg=f'Missing trait keywords for {trait}')

    def test_build_reference_metadata_includes_role_and_topic_terms(self):
        keywords, _ = build_reference_metadata(
            'Explain window functions for a monthly sales report.',
            'DBMS',
            'technical',
            'SQL Developer',
        )
        parsed = parse_reference_keywords(keywords)
        self.assertLessEqual(len(parsed), MAX_REFERENCE_KEYWORDS)
        self.assertIn('sql', parsed)
        self.assertTrue(any(k in parsed for k in ('window', 'functions', 'window function', 'report')))

    def test_personality_metadata_includes_role_traits(self):
        keywords, _ = build_reference_metadata(
            'Tell me about a time you handled a tight deadline.',
            'Behavioral',
            'personality',
            'DevOps Engineer',
        )
        parsed = parse_reference_keywords(keywords)
        self.assertIn('deadline', parsed)
        self.assertTrue(any(k in parsed for k in ('pressure', 'prioritize', 'team', 'docker')))

    def test_enriched_roles_include_skill_topic_keywords(self):
        for role in USER_APPROVED_JOB_ROLES:
            role_keywords = set(ROLE_REFERENCE_KEYWORDS[role])
            for skill in ROLE_INTERVIEW_SKILLS.get(role, []):
                topic_terms = TOPIC_REFERENCE_KEYWORDS.get(skill, ())
                self.assertTrue(
                    any(term in role_keywords for term in topic_terms),
                    msg=f'{role} missing keywords from skill {skill}',
                )

    def test_dataset_questions_have_reference_token_overlap(self):
        """Each catalog/CSV question should share at least one keyword with its metadata."""
        import csv
        from pathlib import Path

        from interviews.services.role_question_catalog import PERSONALITY_CATALOG, TECHNICAL_CATALOG

        base = Path(__file__).resolve().parents[1] / 'services'
        samples: list[tuple[str, str, str, str]] = []

        csv_path = base / 'interview_question_bank.csv'
        if csv_path.exists():
            with csv_path.open(encoding='utf-8-sig') as file:
                for row in csv.DictReader(file):
                    q = (row.get('question') or '').strip()
                    role = (row.get('role') or '').strip()
                    topic = (row.get('topic') or 'Software Engineering').strip()
                    fa = (row.get('focus_area') or 'technical').strip().lower()
                    if q and role in USER_APPROVED_JOB_ROLES:
                        samples.append((role, topic, fa, q))

        for (role, _band, _diff), qs in list(TECHNICAL_CATALOG.items())[:21]:
            skill = ROLE_INTERVIEW_SKILLS.get(role, ['Software Engineering'])[0]
            for q in qs[:2]:
                samples.append((role, skill, 'technical', q))

        for (role, _band, _diff), qs in list(PERSONALITY_CATALOG.items())[:21]:
            for q in qs[:2]:
                samples.append((role, 'Behavioral', 'personality', q))

        self.assertGreater(len(samples), 0)
        misses = 0
        for role, topic, fa, question in samples:
            keywords, _ = build_reference_metadata(question, topic, fa, role)
            parsed = parse_reference_keywords(keywords)
            question_tokens = {
                t for t in re.findall(r'[a-zA-Z][a-zA-Z0-9+\-]{2,}', question.lower())
                if t not in QUESTION_HINT_STOPWORDS and len(t) > 2
            }
            overlap = any(
                token in parsed or any(token in kw or kw in token for kw in parsed)
                for token in question_tokens
            )
            if not overlap:
                misses += 1
        self.assertLess(
            misses / len(samples),
            0.05,
            msg=f'{misses} of {len(samples)} sampled questions had no keyword overlap',
        )

    def test_parse_reference_keywords(self):
        keywords = parse_reference_keywords('state|props|useState| state ')
        self.assertEqual(keywords, ['state', 'props', 'usestate'])

    def test_evaluate_reference_match(self):
        keywords, _ = build_reference_metadata(
            'Explain props versus state in React with an example.',
            'React',
            'technical',
            'React Developer',
        )
        good = evaluate_reference_match(
            'Props are passed from parent and are read-only while state is local and managed with useState. '
            'Changing state triggers a re-render of the component.',
            keywords,
        )
        weak = evaluate_reference_match('I think React is a library for UI.', keywords)

        self.assertIsNotNone(good)
        self.assertIsNotNone(weak)
        self.assertGreater(good['reference_match_pct'], weak['reference_match_pct'])
        self.assertIn('state', good['hit_keywords'])
        self.assertTrue(weak['missed_keywords'])

    def test_blend_with_reference_score(self):
        reference = evaluate_reference_match(
            'useState manages local state and props come from parent',
            'state|props|usestate|render|component',
        )
        blended = blend_with_reference_score(80.0, reference)
        expected = (80.0 * (1 - REFERENCE_BLEND_WEIGHT)) + (reference['reference_score'] * REFERENCE_BLEND_WEIGHT)
        self.assertAlmostEqual(blended, round(expected, 2))

    def test_substantive_answer_scores_higher_with_reference_keywords(self):
        question = 'Explain props versus state in React with a controlled form example.'
        keywords, _ = build_reference_metadata(question, 'React', 'technical', 'React Developer')
        session_meta = {
            'job_role': 'React Developer',
            'experience_years': 2.0,
            'experience_band': experience_band_from_years(2.0),
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
        weak = evaluate_session(
            answers=[{
                'question_type': 'technical',
                'category': 'React',
                'question_text': question,
                'transcript': 'React is used for building user interfaces.',
                'reference_keywords': keywords,
            }],
            session_meta=session_meta,
        )
        strong = evaluate_session(
            answers=[{
                'question_type': 'technical',
                'category': 'React',
                'question_text': question,
                'transcript': (
                    'Props are inputs from the parent and should stay immutable, while state is local data '
                    'managed with useState in a controlled form. Updating state triggers a re-render and '
                    'you pass handlers through props to keep the component predictable.'
                ),
                'reference_keywords': keywords,
            }],
            session_meta=session_meta,
        )
        weak_score = weak['per_question_scores'][0]['score']
        strong_score = strong['per_question_scores'][0]['score']
        self.assertGreater(strong_score, weak_score)
        self.assertGreater(
            strong['per_question_scores'][0]['reference_match_pct'],
            weak['per_question_scores'][0]['reference_match_pct'],
        )
