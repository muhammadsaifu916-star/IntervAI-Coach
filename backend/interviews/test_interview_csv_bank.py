from django.test import TestCase

from interviews.services.interview_csv_bank import load_interview_question_bank
from interviews.services.question_quality import question_embeds_experience_markers
from interviews.services.role_interview_constants import DIFFICULTY_BY_BAND, USER_APPROVED_JOB_ROLES


class InterviewCsvBankTests(TestCase):
    def test_csv_has_substantial_unique_pool(self):
        rows = load_interview_question_bank()
        self.assertGreaterEqual(len(rows), 4000)
        unique_texts = {row["question"] for row in rows}
        self.assertGreaterEqual(len(unique_texts), 4000)

    def test_each_role_has_minimum_questions(self):
        rows = load_interview_question_bank()
        by_role = {role: 0 for role in USER_APPROVED_JOB_ROLES}
        for row in rows:
            by_role[row["role"]] += 1
        for role, count in by_role.items():
            self.assertGreaterEqual(
                count,
                120,
                msg=f"{role} only has {count} CSV questions",
            )

    def test_role_band_difficulty_coverage(self):
        rows = load_interview_question_bank()
        for role in USER_APPROVED_JOB_ROLES:
            for band, allowed in DIFFICULTY_BY_BAND.items():
                for difficulty in allowed:
                    for focus_area in ("technical", "personality"):
                        count = sum(
                            1
                            for row in rows
                            if row["role"] == role
                            and row["experience_band"] == band
                            and row["difficulty"] == difficulty
                            and row["focus_area"] == focus_area
                        )
                        self.assertGreaterEqual(
                            count,
                            1,
                            msg=f"Missing {role} {band} {difficulty} {focus_area}",
                        )

    def test_sql_developer_csv_is_on_topic(self):
        rows = load_interview_question_bank()
        forbidden = ("linked list", "array and a linked", "react component", "docker")
        sql_rows = [row for row in rows if row["role"] == "SQL Developer" and row["focus_area"] == "technical"]
        self.assertGreaterEqual(len(sql_rows), 20)
        for row in sql_rows:
            lower = row["question"].lower()
            for fragment in forbidden:
                self.assertNotIn(fragment, lower)

    def test_non_fresher_bands_exclude_entry_level_phrasing(self):
        rows = load_interview_question_bank()
        for band in ("mid_level_expert", "senior_professional", "industry_veteran"):
            band_rows = [row for row in rows if row["experience_band"] == band]
            self.assertGreater(len(band_rows), 0, msg=f"No rows for band {band}")
            for row in band_rows:
                lower = row["question"].lower()
                self.assertNotIn(
                    "starting your career",
                    lower,
                    msg=f"{row['role']} {band} question has fresher phrasing: {row['question'][:80]}",
                )

    def test_questions_do_not_embed_experience_labels(self):
        rows = load_interview_question_bank()
        offenders = [
            row["question"][:120]
            for row in rows
            if question_embeds_experience_markers(row["question"])
        ]
        self.assertEqual(
            offenders,
            [],
            msg=f"Found {len(offenders)} questions with visible experience labels, e.g. {offenders[:3]}",
        )

    def test_experience_bands_are_reasonably_balanced(self):
        rows = load_interview_question_bank()
        total = len(rows)
        self.assertGreaterEqual(total, 4000)
        by_band = {}
        for band in (
            "fresher",
            "junior_professional",
            "mid_level_expert",
            "senior_professional",
            "industry_veteran",
        ):
            count = sum(1 for row in rows if row["experience_band"] == band)
            by_band[band] = count
            share = count / total
            self.assertGreaterEqual(
                count,
                800,
                msg=f"{band} only has {count} questions; expected a balanced pool",
            )
            self.assertLessEqual(
                share,
                0.28,
                msg=f"{band} is {share:.0%} of the bank ({count}/{total}); expected <= 28%",
            )
