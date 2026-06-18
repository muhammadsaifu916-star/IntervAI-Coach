from django.test import TestCase

from interviews.services.question_quality import (
    is_polished_interview_question,
    normalize_for_dedupe,
    question_matches_experience_band,
)


class QuestionQualityTests(TestCase):
    def test_rejects_robotic_template_tail(self):
        robotic = (
            "As a SQL Developer with 3–5 years of experience, explain how you would approach "
            "index design during a production incident. What would you do first, what trade-offs "
            "would you consider, and how would you validate the outcome?"
        )
        self.assertFalse(is_polished_interview_question(robotic))

    def test_accepts_natural_prompt(self):
        natural = (
            "As a SQL Developer with 3–5 years of experience, how would you optimize a slow "
            "report query joining five tables with date-range filters?"
        )
        self.assertTrue(is_polished_interview_question(natural))

    def test_rejects_mid_level_phrasing_for_junior_band(self):
        mid_phrased = (
            "As a Python Developer with 3–5 years of experience, how would you handle "
            "Django ORM performance issues during a production incident?"
        )
        self.assertFalse(question_matches_experience_band(mid_phrased, "junior_professional"))

    def test_accepts_junior_phrasing_for_junior_band(self):
        junior_phrased = (
            "As a Python Developer with 1–2 years of experience, explain your approach to "
            "Django ORM performance when a production incident occurs."
        )
        self.assertTrue(question_matches_experience_band(junior_phrased, "junior_professional"))

    def test_dedupe_normalizes_punctuation(self):
        a = normalize_for_dedupe("Explain SQL joins — when would you use LEFT JOIN?")
        b = normalize_for_dedupe("Explain SQL joins - when would you use LEFT JOIN?")
        self.assertEqual(a, b)
