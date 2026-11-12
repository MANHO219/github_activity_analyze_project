"""Regression checks for empty cohorts and irrelevant activity rows.

Run from the repository root:
    python -m unittest discover -s c_lifecycle_analysis/tests -v
"""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cohort_analysis import (  # noqa: E402
    BAND_ORDER,
    aggregate_cohort,
    analyze_cohort,
    out_of_band_events,
    per_repo_stage_table,
    read_daily_counts,
)


class CohortRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # All inputs in these tests are synthetic Testing Data.
        pd.DataFrame({
            "repo_id": [1, 2, 3],
            "api_repo_id": [1, 2, 3],
            "repo_created_at": ["2024-04-01T12:00:00Z"] * 3,
            "fetch_status": ["ok"] * 3,
        }).to_csv(self.root / "metadata.csv", index=False)
        pd.DataFrame({
            "repo_id": [1, 2, 3],
            "ai_label_final": ["included", "included", "excluded"],
        }).to_csv(self.root / "labels.csv", index=False)
        pd.DataFrame({
            "repo_id": [1, 1, 1, 1, 1, 3],
            "event_date": ["2024-03-31", "2024-04-01", "2024-05-01",
                           "2024-06-29", "2024-06-30", "2024-04-01"],
            "event_type": ["PushEvent"] * 6,
            "event_count": [1, 5, 1, 2, 3, 100],
        }).to_csv(self.root / "daily.csv", index=False)
        self.coverage = {
            "requested_days": pd.date_range("2024-04-01", "2024-07-28").strftime("%Y-%m-%d").tolist(),
            "requested_hours": 119 * 24,
            "verified_hours": 119 * 24,
            "missing_source_hours": [],
        }
        self._write_coverage()

    def _write_coverage(self):
        import json
        (self.root / "coverage.json").write_text(json.dumps(self.coverage), encoding="utf-8")

    def analyze(self, **overrides):
        args = dict(
            metadata_path=self.root / "metadata.csv",
            labels_path=self.root / "labels.csv",
            daily_counts_path=self.root / "daily.csv",
            coverage_path=self.root / "coverage.json",
            cohort_year=2024,
            created_from="2024-04-01",
            created_to="2024-04-30",
            data_kind="Testing Data",
        )
        args.update(overrides)
        return analyze_cohort(**args)

    def assert_empty_result(self, result):
        self.assertEqual(result["exclusions"]["cohort_size"], 0)
        self.assertTrue(result["cohort"].empty)
        self.assertTrue(result["stage_table"].empty)
        self.assertIn("total_events", result["stage_table"].columns)
        self.assertTrue(result["out_of_band"].empty)
        summary = result["aggregate"]
        self.assertEqual(summary["band"].tolist(), BAND_ORDER)
        self.assertTrue(summary["cohort_size"].eq(0).all())
        self.assertTrue(summary["complete_90d_repos"].eq(0).all())
        self.assertTrue(summary["active_ratio"].isna().all())
        self.assertTrue(summary["total_events_sum"].isna().all())
        self.assertTrue(summary["events_median"].isna().all())
        self.assertTrue(summary["cohort_year"].eq(2024).all())
        self.assertTrue(summary["data_kind"].eq("Testing Data").all())

    def test_all_excluded_returns_structured_empty_result(self):
        labels = pd.read_csv(self.root / "labels.csv")
        labels["ai_label_final"] = "excluded"
        labels.to_csv(self.root / "labels.csv", index=False)
        result = self.analyze()
        self.assert_empty_result(result)
        self.assertEqual(result["exclusions"]["excluded"], 3)

    def test_created_range_with_no_matches_returns_empty_result(self):
        result = self.analyze(created_from="2024-05-01", created_to="2024-05-31")
        self.assert_empty_result(result)
        self.assertEqual(result["exclusions"]["out_of_range"], 2)

    def test_zero_activity_repository_stays_in_all_three_bands(self):
        result = self.analyze()
        idle = result["stage_table"].loc[result["stage_table"]["repo_id"].eq(2)]
        self.assertEqual(len(idle), 3)
        self.assertTrue(idle["band_complete"].all())
        self.assertTrue(idle["total_events"].eq(0).all())
        self.assertTrue(idle["active_days"].eq(0).all())
        self.assertEqual(result["aggregate"]["active_ratio"].tolist(), [0.5, 0.5, 0.5])

    def test_old_nonempty_aggregate_call_remains_compatible(self):
        result = self.analyze()
        actual = aggregate_cohort(result["stage_table"], cohort_size=2)
        pd.testing.assert_frame_equal(actual, result["aggregate"])

    def test_no_fully_covered_repository_is_not_zero_activity(self):
        self.coverage["missing_source_hours"] = ["2024-04-10T03:00:00Z"]
        self.coverage["verified_hours"] -= 1
        self._write_coverage()
        result = self.analyze()
        self.assertEqual(len(result["cohort"]), 2)
        self.assertEqual(len(result["stage_table"]), 6)
        self.assertTrue(result["aggregate"]["complete_90d_repos"].eq(0).all())
        self.assertTrue(result["aggregate"]["not_complete_90d_repos"].eq(2).all())
        self.assertTrue(result["aggregate"]["active_ratio"].isna().all())

    def test_helpers_ignore_unrelated_repositories_before_grouping(self):
        result = self.analyze()
        daily = read_daily_counts(self.root / "daily.csv")
        unrelated = pd.DataFrame({
            "repo_id": range(100, 1100),
            "event_date": pd.Timestamp("2024-04-01"),
            "event_type": "PushEvent",
            "event_count": 1,
        })
        expanded = pd.concat([daily, unrelated], ignore_index=True)
        grouped_ids = []
        original_groupby = pd.DataFrame.groupby

        def record_groupby(frame, by=None, *args, **kwargs):
            if by == "repo_id":
                grouped_ids.append(set(frame["repo_id"]))
            return original_groupby(frame, by, *args, **kwargs)

        with patch.object(pd.DataFrame, "groupby", record_groupby):
            stages = per_repo_stage_table(
                result["cohort"], expanded, result["coverage"], 2024, "Testing Data"
            )
            outside = out_of_band_events(result["cohort"], expanded)
        self.assertEqual(grouped_ids, [{1}, {1}])
        pd.testing.assert_frame_equal(stages, result["stage_table"])
        pd.testing.assert_frame_equal(outside, result["out_of_band"])


if __name__ == "__main__":
    unittest.main()
