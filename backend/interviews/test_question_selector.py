from django.test import TestCase

from interviews.services.question_selector import select_interview_question, selection_mode_label
from interviews.services.dynamic_question_builder import build_role_experience_question
from interviews.services.role_interview_constants import USER_APPROVED_JOB_ROLES
from interviews.services.role_question_catalog import TECHNICAL_CATALOG, collect_role_scoped_candidates


class QuestionSelectorTests(TestCase):
    def test_backend_ai_mode_label(self):
        self.assertEqual(selection_mode_label(), 'local_csv')

    def test_questions_reference_role_and_experience(self):
        for focus in ('technical', 'personality'):
            text, _, _, _, _ = select_interview_question(
                focus_area=focus,
                job_role='Python Developer',
                years_experience=4.0,
                experience_band='mid_level_expert',
                difficulty='hard',
                primary_skill='Django',
                rng=42,
                exclude=set(),
                slot_index=0,
            )
            lower = text.lower()
            self.assertIn('python developer', lower)

    def test_no_cross_role_leakage(self):
        """Java Developer must never receive another role's curated prompt."""
        exclude: set[str] = set()
        for slot in range(8):
            text, _, source, _, _ = select_interview_question(
                focus_area='technical',
                job_role='Java Developer',
                years_experience=2.0,
                experience_band='junior_professional',
                difficulty='medium',
                primary_skill='OOP',
                rng=100 + slot,
                exclude=exclude,
                slot_index=slot,
            )
            exclude.add(text)
            lower = text.lower()
            self.assertIn('java developer', lower)
            for other_role in USER_APPROVED_JOB_ROLES:
                if other_role == 'Java Developer':
                    continue
                self.assertNotIn(
                    f'as a {other_role.lower()}',
                    lower,
                    msg=f'Java interview leaked {other_role}: {text}',
                )

    def test_security_engineer_gets_role_specific_technical_questions(self):
        text, _, _, _, _ = select_interview_question(
            focus_area='technical',
            job_role='Security Engineer',
            years_experience=5.0,
            experience_band='mid_level_expert',
            difficulty='hard',
            primary_skill='Networking',
            rng=7,
            exclude=set(),
        )
        self.assertIn('Security Engineer', text)

    def test_fresher_difficulty_stays_beginner_friendly(self):
        candidates = collect_role_scoped_candidates(
            TECHNICAL_CATALOG,
            job_role='React Developer',
            experience_band='fresher',
            difficulty='hard',
            exclude=set(),
        )
        self.assertTrue(candidates)
        for question in candidates[:5]:
            key_matches = [
                key for key, qs in TECHNICAL_CATALOG.items()
                if key[0] == 'React Developer' and question in qs
            ]
            self.assertTrue(key_matches)
            _, _, difficulty = key_matches[0]
            self.assertIn(difficulty, ('easy', 'medium'))

    def test_select_respects_exclude_list(self):
        first_text, _, _, _, _ = select_interview_question(
            focus_area='technical',
            job_role='Python Developer',
            years_experience=4.0,
            experience_band='mid_level_expert',
            difficulty='hard',
            primary_skill='Django',
            rng=42,
            exclude=set(),
        )
        second_text, _, _, _, _ = select_interview_question(
            focus_area='technical',
            job_role='Python Developer',
            years_experience=4.0,
            experience_band='mid_level_expert',
            difficulty='hard',
            primary_skill='Django',
            rng=99,
            exclude={first_text},
        )
        self.assertNotEqual(first_text, second_text)

    def test_dynamic_fallback_mentions_years(self):
        question = build_role_experience_question(
            focus_area='technical',
            job_role='Python Developer',
            years_experience=4.0,
            experience_band='mid_level_expert',
            difficulty='hard',
            primary_skill='Django',
            slot_index=1,
            rng=5,
            exclude=set(),
        )
        self.assertIn('Python Developer', question)
        self.assertRegex(question.lower(), r'4 year|years|experience|mid level expert')

    def test_dynamic_respects_exclude_list(self):
        first = build_role_experience_question(
            focus_area='technical',
            job_role='Python Developer',
            years_experience=4.0,
            experience_band='mid_level_expert',
            difficulty='hard',
            primary_skill='Django',
            slot_index=0,
            rng=5,
            exclude=set(),
        )
        second = build_role_experience_question(
            focus_area='technical',
            job_role='Python Developer',
            years_experience=4.0,
            experience_band='mid_level_expert',
            difficulty='hard',
            primary_skill='Django',
            slot_index=0,
            rng=5,
            exclude={first},
            question_family='scenario',
        )
        self.assertNotEqual(first, second)

    def test_no_generic_unrelated_prompt(self):
        text, _, _, _, _ = select_interview_question(
            focus_area='technical',
            job_role='Python Developer',
            years_experience=4.0,
            experience_band='mid_level_expert',
            difficulty='hard',
            primary_skill='Django',
            rng=7,
            exclude=set(),
        )
        self.assertNotRegex(
            text.lower(),
            r'^how would you handle a .* problem',
        )
