#!/usr/bin/env python3

import importlib.util
import pathlib
import sys
import unittest


SCRIPT = pathlib.Path(__file__).parents[1] / "tools" / "discover_usda_release.py"
SPEC = importlib.util.spec_from_file_location("discover_usda_release", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class DiscoverUSDAReleaseTests(unittest.TestCase):
    def test_selects_newest_branded_csv_and_normalizes_relative_url(self):
        document = """
        <a href="/fdc-datasets/FoodData_Central_branded_food_csv_2025-12-18.zip">old</a>
        <a href="https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_branded_food_csv_2026-04-30.zip">new</a>
        <a href="/fdc-datasets/FoodData_Central_foundation_food_csv_2099-01-01.zip">wrong dataset</a>
        """
        release = MODULE.discover(document)
        self.assertEqual(release.source_date, "2026-04-30")
        self.assertEqual(
            release.url,
            "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_branded_food_csv_2026-04-30.zip",
        )

    def test_rejects_page_without_expected_archive(self):
        with self.assertRaises(RuntimeError):
            MODULE.discover("<html>No download here</html>")


if __name__ == "__main__":
    unittest.main()
