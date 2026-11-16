"""Backend lane tests. Run from the project root:  python -m unittest discover -s backend"""
from __future__ import annotations

import unittest

from trails import difficulty, list_trails


class TrailsTest(unittest.TestCase):
    def test_every_trail_has_the_contract_fields(self) -> None:
        for trail in list_trails():
            for field in ("id", "name", "length_km", "climb_m", "difficulty"):
                self.assertIn(field, trail)

    def test_ids_are_unique(self) -> None:
        ids = [t["id"] for t in list_trails()]
        self.assertEqual(len(ids), len(set(ids)))


class DifficultyTest(unittest.TestCase):
    def test_bands(self) -> None:
        self.assertEqual(difficulty(2.0, 100), "easy")
        self.assertEqual(difficulty(9.0, 420), "moderate")
        self.assertEqual(difficulty(14.5, 1150), "hard")

    def test_boundaries(self) -> None:
        self.assertEqual(difficulty(5.99, 200), "easy")      # 7.99
        self.assertEqual(difficulty(6.5, 150), "moderate")   # exactly 8
        self.assertEqual(difficulty(7.0, 800), "hard")       # exactly 15


if __name__ == "__main__":
    unittest.main()
