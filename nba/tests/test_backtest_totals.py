import unittest

from nba.src.backtest_totals import american_to_decimal, grade, summarize


class TotalsBacktestTests(unittest.TestCase):
    def test_american_to_decimal(self):
        self.assertAlmostEqual(american_to_decimal(-110), 1.9090909, places=6)
        self.assertAlmostEqual(american_to_decimal(150), 2.5, places=6)
        self.assertIsNone(american_to_decimal(0))

    def test_total_grading_and_push(self):
        self.assertEqual(grade(230, 229.5), "over")
        self.assertEqual(grade(228, 229.5), "under")
        self.assertEqual(grade(229, 229), "push")

    def test_push_is_excluded_from_hit_rate(self):
        report = summarize([
            {"outcome": "win", "profit": 0.5},
            {"outcome": "loss", "profit": -1.0},
            {"outcome": "push", "profit": 0.0},
        ])
        self.assertEqual(report["graded_bets"], 2)
        self.assertEqual(report["pushes"], 1)
        self.assertAlmostEqual(report["hit_rate"], 0.5)
        self.assertAlmostEqual(report["roi"], -0.1666667, places=6)


if __name__ == "__main__":
    unittest.main()
