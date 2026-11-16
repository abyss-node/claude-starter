"""Backend lane tests. Run from the project root:  python -m unittest discover -s backend"""
from __future__ import annotations

import unittest

from trails import list_trails


class TrailsTest(unittest.TestCase):
    def test_every_trail_has_the_contract_fields(self) -> None:
        for trail in list_trails():
            for field in ("id", "name", "length_km", "climb_m"):
                self.assertIn(field, trail)

    def test_ids_are_unique(self) -> None:
        ids = [t["id"] for t in list_trails()]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
