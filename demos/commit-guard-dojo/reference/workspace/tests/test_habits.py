import unittest

from habits import completion_rate, count_done


class CountDoneTest(unittest.TestCase):
    def test_counts_kept_days(self):
        self.assertEqual(count_done([True, False, True, True]), 3)

    def test_empty_log(self):
        self.assertEqual(count_done([]), 0)


class CompletionRateTest(unittest.TestCase):
    def test_share_of_kept_days(self):
        self.assertAlmostEqual(completion_rate([True, False, True, False]), 0.5)

    def test_empty_log_is_zero(self):
        self.assertEqual(completion_rate([]), 0.0)


if __name__ == "__main__":
    unittest.main()
