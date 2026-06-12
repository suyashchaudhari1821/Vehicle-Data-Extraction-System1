import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import requests
import torque_verifier


TEST_TMP = Path(__file__).resolve().parent / "tmp"


class DescriptionShortcutTests(unittest.TestCase):
    def test_general_shortcuts_expand_to_service_description(self):
        result = torque_verifier._description_score(
            "RR BRK CAL BRKT BLT",
            "Rear Brake Caliper Bracket Bolt",
        )

        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["text"], "rear brake caliper bracket bolt")

    def test_ambiguous_mount_meaning_is_selected_by_library_row(self):
        result = torque_verifier._description_score(
            "ENG MT BRKT",
            "Engine Mount Bracket",
        )

        self.assertEqual(result["score"], 1.0)
        self.assertTrue(
            any(
                item["shortcut"] == "MT"
                and item["meaning"] == "mount"
                and item["ambiguous"]
                for item in result["expansions"]
            )
        )

    def test_ambiguous_mounting_meaning_is_selected_by_library_row(self):
        result = torque_verifier._description_score("MT BLT", "Mounting Bolt")

        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["text"], "mounting bolt")

    def test_ambiguous_transmission_meaning_is_selected_by_library_row(self):
        result = torque_verifier._description_score(
            "MT CASE",
            "Manual Transmission Case",
        )

        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["text"], "manual transmission case")

    def test_close_competing_library_meanings_require_review(self):
        best = {
            "score": 0.90,
            "torque_match": True,
            "description_score": 0.95,
            "shortcut_expansions": [
                {"shortcut": "MT", "meaning": "mount", "ambiguous": True}
            ],
        }
        competitor = {
            "score": 0.88,
            "torque_match": True,
            "description_score": 0.94,
            "shortcut_expansions": [
                {
                    "shortcut": "MT",
                    "meaning": "manual transmission",
                    "ambiguous": True,
                }
            ],
        }

        result = torque_verifier._find_ambiguous_competitor(
            best,
            [best, competitor],
        )

        self.assertIs(result, competitor)

    def test_weaker_competing_meaning_does_not_require_review(self):
        best = {
            "score": 0.90,
            "torque_match": True,
            "description_score": 0.95,
            "shortcut_expansions": [
                {"shortcut": "MT", "meaning": "mount", "ambiguous": True}
            ],
        }
        competitor = {
            "score": 0.80,
            "torque_match": True,
            "description_score": 0.90,
            "shortcut_expansions": [
                {
                    "shortcut": "MT",
                    "meaning": "manual transmission",
                    "ambiguous": True,
                }
            ],
        }

        result = torque_verifier._find_ambiguous_competitor(
            best,
            [best, competitor],
        )

        self.assertIsNone(result)


class TorqueSpecificationTests(unittest.TestCase):
    def test_same_number_with_different_units_does_not_match(self):
        self.assertFalse(torque_verifier._torque_match("18 N m", "18 ft-lb"))

    def test_equivalent_converted_units_match(self):
        self.assertTrue(torque_verifier._torque_match("24.4 N m", "18 ft-lb"))
        self.assertTrue(torque_verifier._torque_match("216 in-lb", "18 ft-lb"))
        self.assertTrue(torque_verifier._torque_match("216 in. lbs.", "18 ft. lbs."))

    def test_angle_stage_must_match(self):
        self.assertFalse(
            torque_verifier._torque_match(
                "10 N m + 90 degrees",
                "10 N m + 45 degrees",
            )
        )
        self.assertFalse(
            torque_verifier._torque_match(
                "10 N m",
                "10 N m + 90 degrees",
            )
        )

    def test_repeated_angle_stages_are_not_deduplicated(self):
        self.assertFalse(
            torque_verifier._torque_match(
                "20 N m + 90 degrees + 90 degrees",
                "20 N m + 90 degrees",
            )
        )
        self.assertTrue(
            torque_verifier._torque_match(
                "20 N m + 90 degrees + 90 degrees",
                "20 N m + 90 degrees + 90 degrees",
            )
        )

    def test_torque_stage_order_must_match(self):
        self.assertFalse(
            torque_verifier._torque_match(
                "20 N m + 30 N m",
                "30 N m + 20 N m",
            )
        )

    def test_ranges_require_both_values(self):
        self.assertTrue(
            torque_verifier._torque_match("20-25 N m", "20 to 25 Nm")
        )
        self.assertFalse(torque_verifier._torque_match("20-25 N m", "20 N m"))

    def test_bare_numeric_code_can_match_a_torque_value(self):
        self.assertTrue(torque_verifier._torque_match("0030", "30 N m"))

    def test_decimal_comma_is_parsed_as_a_decimal(self):
        self.assertTrue(torque_verifier._torque_match("2,5 N m", "2.5 N m"))
        self.assertFalse(torque_verifier._torque_match("2,5 N m", "5 N m"))

    def test_newton_centimeter_is_converted_not_treated_as_newton_meter(self):
        self.assertTrue(torque_verifier._torque_match("200 N cm", "2 N m"))
        self.assertFalse(torque_verifier._torque_match("200 N cm", "200 N m"))

    def test_unrecognized_unit_text_cannot_fall_back_to_number_only(self):
        self.assertFalse(torque_verifier._torque_match("18 lb", "18 N m"))


class ShortcutSafetyTests(unittest.TestCase):
    def test_weak_module_expansion_is_not_forced_on_mechanical_text(self):
        result = torque_verifier._description_score(
            "EM BRKT",
            "Engine Mount Bracket",
        )

        self.assertFalse(
            any(
                item["shortcut"] == "EM"
                and item["meaning"] == "expansion module"
                for item in result["expansions"]
            )
        )

    def test_exact_module_expansion_is_still_available(self):
        result = torque_verifier._description_score(
            "EAC MTG BLT",
            "Electric Air Compressor Mounting Bolt",
        )

        self.assertEqual(result["score"], 1.0)

    def test_missing_ambiguous_mechanical_meanings_are_available(self):
        cases = [
            ("ASM BRKT", "Assembly Bracket", "ASM", "assembly"),
            ("DAMP BLT", "Damper Bolt", "DAMP", "damper"),
            ("PLG", "Plug", "PLG", "plug"),
            ("ABS MTG", "Absorber Mounting", "ABS", "absorber"),
            ("EM BRKT", "Engine Mount Bracket", "EM", "engine mount"),
        ]
        for source, target, shortcut, meaning in cases:
            with self.subTest(source=source):
                result = torque_verifier._description_score(source, target)
                self.assertEqual(result["score"], 1.0)
                self.assertTrue(
                    any(
                        item["shortcut"] == shortcut
                        and item["meaning"] == meaning
                        for item in result["expansions"]
                    )
                )

    def test_explicit_category_does_not_depend_on_row_position(self):
        original_path = torque_verifier.SHORTCUT_WORKBOOK_PATH
        original_signature = torque_verifier._shortcut_cache_signature
        original_cache = torque_verifier._shortcut_cache

        TEST_TMP.mkdir(exist_ok=True)
        workbook = TEST_TMP / "category_shortcuts.xlsx"
        try:
            pd.DataFrame(
                [
                    ("MECH", "Mechanical Meaning", "Mechanical"),
                    ("MOD", "Module Meaning", "Module"),
                ],
                columns=["ACRRONYMS", "DESCRIPTION", "CATEGORY"],
            ).to_excel(workbook, sheet_name="List", index=False)
            torque_verifier.SHORTCUT_WORKBOOK_PATH = workbook
            torque_verifier._shortcut_cache_signature = None
            torque_verifier._shortcut_cache = {}
            torque_verifier._description_variants_cached.cache_clear()

            shortcuts = torque_verifier._description_shortcuts()

            self.assertEqual(shortcuts[("mech",)][0]["category"], "mechanical")
            self.assertEqual(shortcuts[("mod",)][0]["category"], "module")
        finally:
            torque_verifier.SHORTCUT_WORKBOOK_PATH = original_path
            torque_verifier._shortcut_cache_signature = original_signature
            torque_verifier._shortcut_cache = original_cache
            torque_verifier._description_variants_cached.cache_clear()

    def test_workbook_changes_reload_without_restart(self):
        original_path = torque_verifier.SHORTCUT_WORKBOOK_PATH
        original_signature = torque_verifier._shortcut_cache_signature
        original_cache = torque_verifier._shortcut_cache

        TEST_TMP.mkdir(exist_ok=True)
        workbook = TEST_TMP / "reload_shortcuts.xlsx"
        try:
            torque_verifier.SHORTCUT_WORKBOOK_PATH = workbook
            torque_verifier._shortcut_cache_signature = None
            torque_verifier._shortcut_cache = {}
            torque_verifier._description_variants_cached.cache_clear()

            pd.DataFrame(
                [("ZZTEST", "First Meaning")],
                columns=["ACRRONYMS", "DESCRIPTION"],
            ).to_excel(workbook, sheet_name="List", index=False)
            first = torque_verifier._description_score(
                "ZZTEST",
                "First Meaning",
            )

            pd.DataFrame(
                [("ZZTEST", "Second Longer Meaning")],
                columns=["ACRRONYMS", "DESCRIPTION"],
            ).to_excel(workbook, sheet_name="List", index=False)
            second = torque_verifier._description_score(
                "ZZTEST",
                "Second Longer Meaning",
            )

            self.assertEqual(first["score"], 1.0)
            self.assertEqual(second["score"], 1.0)
            self.assertEqual(second["text"], "second longer meaning")
        finally:
            torque_verifier.SHORTCUT_WORKBOOK_PATH = original_path
            torque_verifier._shortcut_cache_signature = original_signature
            torque_verifier._shortcut_cache = original_cache
            torque_verifier._description_variants_cached.cache_clear()


class SearchStrategyTests(unittest.TestCase):
    def test_weak_first_pass_requires_remaining_pages(self):
        candidates = [
            {
                "description_score": 0.80,
                "torque_match": True,
                "shortcut_expansions": [],
            }
        ]

        self.assertFalse(
            torque_verifier._has_decisive_candidate(
                candidates,
                "RR BRKT",
            )
        )

    def test_clear_first_pass_can_stop_page_expansion(self):
        candidates = [
            {
                "description_score": 0.99,
                "torque_match": True,
                "shortcut_expansions": [],
            }
        ]

        self.assertTrue(
            torque_verifier._has_decisive_candidate(
                candidates,
                "Rear Bracket",
            )
        )

    def test_ambiguous_shortcut_always_requires_remaining_pages(self):
        candidates = [
            {
                "description_score": 1.0,
                "torque_match": True,
                "shortcut_expansions": [
                    {
                        "shortcut": "MT",
                        "meaning": "mount",
                        "ambiguous": True,
                    }
                ],
            }
        ]

        self.assertFalse(
            torque_verifier._has_decisive_candidate(
                candidates,
                "ENG MT BRKT",
            )
        )

    def test_verifier_searches_late_pages_after_weak_first_pass(self):
        vehicle = {
            "brand": "TEST",
            "model": "TEST",
            "model_code": "TT",
            "version": "2026",
            "model_version_id": "vehicle-1",
        }
        engine = {
            "engine": "Test Engine",
            "engine_code": "TST",
            "model_version_engine_id": "engine-1",
        }
        leaves = [
            {
                "path": f"Page {index}",
                "name": f"Page {index}",
                "content_link_id": f"page-{index}",
                "info_code": "torque",
            }
            for index in range(40)
        ]

        def rows_for_leaf(_html, leaf):
            if leaf["content_link_id"] != "page-39":
                return []
            return [
                {
                    "page": leaf["path"],
                    "description": "Rear Bracket Bolt",
                    "specification": "30 N m",
                    "comment": "",
                }
            ]

        with (
            patch.object(torque_verifier, "_find_vehicle_versions", return_value=[vehicle]),
            patch.object(
                torque_verifier,
                "_build_engine_targets",
                return_value=([{"vehicle": vehicle, "engine": engine}], []),
            ),
            patch.object(
                torque_verifier,
                "_get_service_book",
                return_value={"modelVersionBookId": "book-1"},
            ),
            patch.object(torque_verifier, "_get_json", return_value={}),
            patch.object(torque_verifier, "_collect_torque_leaves", return_value=leaves),
            patch.object(torque_verifier, "_get_torque_content", return_value="<html />"),
            patch.object(torque_verifier, "_extract_torque_rows", side_effect=rows_for_leaf),
        ):
            result = torque_verifier.verify_torque(
                2026,
                "TT",
                "TST",
                "",
                "RR BRKT BLT",
                "30 N m",
            )

        self.assertEqual(result["status"], "Verified")
        self.assertEqual(result["best"]["page"], "Page 39")
        self.assertEqual(result["torque_pages_checked"], 40)

    def test_verifier_finishes_all_applicable_engine_targets(self):
        vehicle = {
            "brand": "TEST",
            "model": "TEST",
            "model_code": "TT",
            "version": "2026",
            "model_version_id": "vehicle-1",
        }
        engines = [
            {
                "engine": "Test Engine One",
                "engine_code": "TST",
                "model_version_engine_id": "engine-1",
            },
            {
                "engine": "Test Engine Two",
                "engine_code": "TST",
                "model_version_engine_id": "engine-2",
            },
        ]
        targets = [{"vehicle": vehicle, "engine": engine} for engine in engines]
        leaves = [
            {
                "path": "Torque Page",
                "name": "Torque Page",
                "content_link_id": "page-1",
                "info_code": "torque",
            }
        ]
        content_calls = []

        def get_content(_leaf, engine_id):
            content_calls.append(engine_id)
            return "<html />"

        with (
            patch.object(torque_verifier, "_find_vehicle_versions", return_value=[vehicle]),
            patch.object(
                torque_verifier,
                "_build_engine_targets",
                return_value=(targets, []),
            ),
            patch.object(
                torque_verifier,
                "_get_service_book",
                return_value={"modelVersionBookId": "book-1"},
            ),
            patch.object(torque_verifier, "_get_json", return_value={}),
            patch.object(torque_verifier, "_collect_torque_leaves", return_value=leaves),
            patch.object(torque_verifier, "_get_torque_content", side_effect=get_content),
            patch.object(
                torque_verifier,
                "_extract_torque_rows",
                return_value=[
                    {
                        "page": "Torque Page",
                        "description": "Rear Bracket Bolt",
                        "specification": "30 N m",
                        "comment": "",
                    }
                ],
            ),
        ):
            torque_verifier.verify_torque(
                2026,
                "TT",
                "TST",
                "",
                "RR BRKT BLT",
                "30 N m",
            )

        self.assertEqual(content_calls, ["engine-1", "engine-2"])

    def test_unreadable_page_does_not_abort_other_pages(self):
        vehicle = {
            "brand": "TEST",
            "model": "TEST",
            "model_code": "TT",
            "version": "2026",
            "model_version_id": "vehicle-1",
        }
        engine = {
            "engine": "Test Engine",
            "engine_code": "TST",
            "model_version_engine_id": "engine-1",
        }
        leaves = [
            {
                "path": "Broken Page",
                "name": "Broken Page",
                "content_link_id": "broken",
                "info_code": "torque",
            },
            {
                "path": "Readable Page",
                "name": "Readable Page",
                "content_link_id": "readable",
                "info_code": "torque",
            },
        ]
        response = requests.Response()
        response.status_code = 404
        page_error = requests.HTTPError("404 Not Found", response=response)

        def get_content(leaf, _engine_id):
            if leaf["content_link_id"] == "broken":
                raise page_error
            return "<html />"

        def rows_for_leaf(_html, leaf):
            return [
                {
                    "page": leaf["path"],
                    "description": "Rear Bracket Bolt",
                    "specification": "30 N m",
                    "comment": "",
                }
            ]

        with (
            patch.object(torque_verifier, "_find_vehicle_versions", return_value=[vehicle]),
            patch.object(
                torque_verifier,
                "_build_engine_targets",
                return_value=([{"vehicle": vehicle, "engine": engine}], []),
            ),
            patch.object(
                torque_verifier,
                "_get_service_book",
                return_value={"modelVersionBookId": "book-1"},
            ),
            patch.object(torque_verifier, "_get_json", return_value={}),
            patch.object(torque_verifier, "_collect_torque_leaves", return_value=leaves),
            patch.object(torque_verifier, "_get_torque_content", side_effect=get_content),
            patch.object(torque_verifier, "_extract_torque_rows", side_effect=rows_for_leaf),
        ):
            result = torque_verifier.verify_torque(
                2026,
                "TT",
                "TST",
                "",
                "RR BRKT BLT",
                "30 N m",
            )

        self.assertEqual(result["status"], "Needs review")
        self.assertEqual(result["unreadable_torque_pages"], 1)
        self.assertEqual(result["readable_torque_pages"], 1)
        self.assertEqual(result["best"]["page"], "Readable Page")

    def test_all_unreadable_pages_return_incomplete(self):
        vehicle = {
            "brand": "TEST",
            "model": "TEST",
            "model_code": "TT",
            "version": "2026",
            "model_version_id": "vehicle-1",
        }
        engine = {
            "engine": "Test Engine",
            "engine_code": "TST",
            "model_version_engine_id": "engine-1",
        }
        leaves = [
            {
                "path": "Broken Page",
                "name": "Broken Page",
                "content_link_id": "broken",
                "info_code": "torque",
            }
        ]
        page_error = requests.ConnectionError("page unavailable")

        with (
            patch.object(torque_verifier, "_find_vehicle_versions", return_value=[vehicle]),
            patch.object(
                torque_verifier,
                "_build_engine_targets",
                return_value=([{"vehicle": vehicle, "engine": engine}], []),
            ),
            patch.object(
                torque_verifier,
                "_get_service_book",
                return_value={"modelVersionBookId": "book-1"},
            ),
            patch.object(torque_verifier, "_get_json", return_value={}),
            patch.object(torque_verifier, "_collect_torque_leaves", return_value=leaves),
            patch.object(torque_verifier, "_get_torque_content", side_effect=page_error),
        ):
            result = torque_verifier.verify_torque(
                2026,
                "TT",
                "TST",
                "",
                "RR BRKT BLT",
                "30 N m",
            )

        self.assertEqual(result["status"], "Incomplete")
        self.assertEqual(result["unreadable_torque_pages"], 1)


if __name__ == "__main__":
    unittest.main()
