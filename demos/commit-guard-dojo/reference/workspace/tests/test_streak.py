import unittest

from habits import longest_streak


class LongestStreakTest(unittest.TestCase):
    def test_empty_log(self):
        self.assertEqual(longest_streak([]), 0)

    def test_no_kept_days(self):
        self.assertEqual(longest_streak([False, False]), 0)

    def test_longest_run_wins(self):
        self.assertEqual(longest_streak([True, True, False, True, True, True, False]), 3)

    def test_run_at_the_end_counts(self):
        self.assertEqual(longest_streak([False, True, True]), 2)


if __name__ == "__main__":
    unittest.main()
