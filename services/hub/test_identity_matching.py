import unittest

import app


class IdentityMatchingTests(unittest.TestCase):
    def setUp(self):
        self.user = {"sub": "alice-sub", "preferred_username": "alice", "email": "alice@example.invalid"}
        self.exact = {"subject": "alice-sub", "username": "old-alice", "email": "old@example.invalid", "marker": "alice"}
        self.conflict = {"subject": "bob-sub", "username": "alice", "email": "alice@example.invalid", "marker": "bob"}

    def test_exact_subject_beats_earlier_conflicting_name_or_email(self):
        for rows in ([self.conflict, self.exact], [self.exact, self.conflict]):
            with self.subTest(rows=rows):
                self.assertIs(app.find_record(rows, self.user), self.exact)

    def test_exact_subject_beats_subjectless_legacy_alias(self):
        legacy = {"username": "alice", "email": "alice@example.invalid"}
        self.assertIs(app.find_record([legacy, self.exact], self.user), self.exact)

    def test_conflicting_subject_cannot_fallback_even_when_subject_matching_disabled(self):
        for subject in (False, True):
            with self.subTest(subject=subject):
                self.assertIsNone(app.find_record([self.conflict], self.user, subject=subject))

    def test_unique_legacy_username_or_email_is_still_supported(self):
        for legacy in ({"username": "alice"}, {"email": "ALICE@example.invalid"},
                       {"subject": "", "username": "alice"}, {"subject": None, "email": "alice@example.invalid"}):
            with self.subTest(legacy=legacy):
                self.assertIs(app.find_record([legacy], self.user), legacy)

    def test_duplicate_subject_or_legacy_alias_is_ambiguous(self):
        for rows in ([self.exact, dict(self.exact)], [{"username": "alice"}, {"email": "alice@example.invalid"}],
                     [{"email": "alice@example.invalid"}, {"email": "ALICE@example.invalid"}]):
            with self.subTest(rows=rows):
                self.assertIsNone(app.find_record(rows, self.user))

    def test_single_legacy_row_matching_both_aliases_is_not_ambiguous(self):
        legacy = {"username": "alice", "email": "alice@example.invalid"}
        self.assertIs(app.find_record([legacy], self.user), legacy)

    def test_drive_subjectless_username_lookup_and_email_fallback(self):
        for legacy in ({"username": "alice"}, {"username": "drive-alice", "email": "alice@example.invalid"}):
            with self.subTest(legacy=legacy):
                self.assertIs(app.find_record([legacy], self.user, subject=False), legacy)
        self.assertIsNone(app.find_record([self.exact], self.user, subject=False))

    def test_disabled_aliases_and_case_sensitive_usernames_remain_disabled(self):
        self.assertIsNone(app.find_record([{"username": "alice"}], self.user, username=False))
        self.assertIsNone(app.find_record([{"email": "alice@example.invalid"}], self.user, email=False))
        self.assertIsNone(app.find_record([{"username": "ALICE"}], self.user))

    def test_missing_identity_or_empty_aliases_never_match(self):
        for user in ({}, {"sub": None}, {"sub": ""}, {"sub": "alice-sub"}, {"sub": "alice-sub", "email": None}):
            with self.subTest(user=user):
                self.assertIsNone(app.find_record([{"username": "", "email": "", "subject": ""}], user))

    def test_conflicting_alias_makes_legacy_fallback_ambiguous(self):
        legacy = {"username": "alice"}
        self.assertIsNone(app.find_record([self.conflict, legacy], self.user))


if __name__ == "__main__":
    unittest.main()
