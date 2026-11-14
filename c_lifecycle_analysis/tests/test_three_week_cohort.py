"""Testing Data: UTC boundaries, fixed membership, coverage, and cached API success."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import hashlib
import subprocess
import importlib.util
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cohort_analysis import analyze_cohort, InputError, bands_for


class ThreeWeekTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        pd.DataFrame({"repo_id": [1, 2], "api_repo_id": [1, 2],
                      "repo_created_at": ["2024-04-01T23:59:00Z", "2024-04-07T00:00:00Z"],
                      "fetch_status": ["ok_cached", "ok"]}).to_csv(self.root / "metadata.csv", index=False)
        pd.DataFrame({"repo_id": [1, 2], "ai_label_final": ["included"]*2}).to_csv(self.root / "labels.csv", index=False)
        dates = ["2024-03-31", "2024-04-01", "2024-04-07", "2024-04-08", "2024-04-14",
                 "2024-04-15", "2024-04-21", "2024-04-22"]
        pd.DataFrame({"repo_id": [1]*8, "event_date": dates, "event_type": ["PushEvent"]*8,
                      "event_count": [11, 1, 2, 3, 4, 5, 6, 7]}).to_csv(self.root / "daily.csv", index=False)
        self.coverage = {"requested_days": pd.date_range("2024-04-01", "2024-04-27").strftime("%Y-%m-%d").tolist(),
                         "requested_hours": 648, "verified_hours": 648, "missing_source_hours": []}
        pd.DataFrame({"repo_id": [1, 2]}).to_csv(self.root / "cohort.csv", index=False)

    def run_analysis(self, **overrides):
        (self.root / "coverage.json").write_text(json.dumps(self.coverage))
        args = dict(metadata_path=self.root / "metadata.csv", labels_path=self.root / "labels.csv",
                    daily_counts_path=self.root / "daily.csv", coverage_path=self.root / "coverage.json",
                    cohort_year=2024, created_from="2024-04-01", created_to="2024-04-07",
                    data_kind="Testing Data", window_days=7, cohort_path=self.root / "cohort.csv")
        args.update(overrides)
        return analyze_cohort(**args)

    def test_boundaries_cached_success_and_inactive_repos(self):
        r = self.run_analysis()
        self.assertEqual(len(r["cohort"]), 2)
        self.assertEqual(len(r["stage_table"]), 6)
        active = r["stage_table"].query("repo_id == 1")
        self.assertEqual(active.total_events.tolist(), [3, 7, 11])
        self.assertEqual(active.active_days.tolist(), [2, 2, 2])
        self.assertTrue(r["stage_table"].query("repo_id == 2").total_events.eq(0).all())
        self.assertEqual(r["aggregate"].complete_21d_repos.tolist(), [2, 2, 2])
        self.assertEqual(r["aggregate"].active_ratio.tolist(), [0.5]*3)
        self.assertNotIn("complete_90d_repos", r["aggregate"])
        self.assertEqual(r["out_of_band"].beyond_21_events.tolist(), [7])
        self.assertEqual(r["out_of_band"].pre_creation_events.tolist(), [11])

    def test_last_day_required_for_latest_created_repo(self):
        self.coverage["missing_source_hours"] = ["2024-04-27T23:00:00Z"]
        self.coverage["verified_hours"] -= 1
        r = self.run_analysis()
        self.assertEqual(r["aggregate"].complete_21d_repos.tolist(), [1]*3)
        self.assertEqual(r["aggregate"].active_ratio.tolist(), [1.0]*3)
        self.assertEqual(len(r["stage_table"]), 6)

    def test_no_complete_observation_stays_nan(self):
        self.coverage["missing_source_hours"] = ["2024-04-10T00:00:00Z"]
        self.coverage["verified_hours"] -= 1
        r = self.run_analysis()
        self.assertTrue(r["aggregate"].active_ratio.isna().all())
        self.assertTrue(r["aggregate"].complete_21d_repos.eq(0).all())

    def test_frozen_ids_do_not_expand_with_input(self):
        pd.DataFrame({"repo_id": [2]}).to_csv(self.root / "cohort.csv", index=False)
        r = self.run_analysis()
        self.assertEqual(r["cohort"].repo_id.tolist(), [2])
        self.assertEqual(len(r["stage_table"]), 3)
        self.assertTrue(r["aggregate"].active_ratio.eq(0).all())

    def test_invalid_or_duplicate_frozen_ids_fail(self):
        for ids in [[3], [1, 1]]:
            with self.subTest(ids=ids):
                pd.DataFrame({"repo_id": ids}).to_csv(self.root / "cohort.csv", index=False)
                with self.assertRaises(InputError):
                    self.run_analysis()

    def test_invalid_window_rejected(self):
        for n in [0, -1, True, 1.5]:
            with self.assertRaises(InputError):
                bands_for(n)

    def test_wrong_year_is_not_silently_relabelled(self):
        with self.assertRaisesRegex(InputError, "cohort_year"):
            self.run_analysis(cohort_year=2026)

    def test_cli_rejects_modified_frozen_snapshot(self):
        paths = {"cohort.csv": "cohort.csv", "repo_metadata.csv": "metadata.csv",
                 "repo_ai_labels_analysis.csv": "labels.csv"}
        hashes = {key: hashlib.sha256((self.root/value).read_bytes()).hexdigest() for key, value in paths.items()}
        (self.root / "cohort_manifest.json").write_text(json.dumps({"status": "Testing Data", "snapshots": hashes}))
        p = self.root / "metadata.csv"
        p.write_text(p.read_text().replace("ok_cached", "ok"))
        cmd = [sys.executable, str(Path(__file__).resolve().parents[1] / "run_cohort.py")]
        for name, value in {"metadata": p, "labels": self.root/"labels.csv", "cohort": self.root/"cohort.csv",
                            "daily": self.root/"daily.csv", "coverage": self.root/"coverage.json",
                            "output": self.root/"not_created", "cohort-year": 2024,
                            "created-from": "2024-04-01", "created-to": "2024-04-07",
                            "window-days": 7, "data-kind": "Testing Data"}.items():
            cmd.extend(["--"+name, str(value)])
        (self.root/"coverage.json").write_text(json.dumps(self.coverage))
        r = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Frozen snapshot changed", r.stderr)
        self.assertFalse((self.root/"not_created").exists())

    @unittest.skipUnless(importlib.util.find_spec("pyarrow"), "Parquet integration requires pyarrow")
    def test_cli_accepts_a_partitioned_parquet_directory(self):
        daily_dir = self.root / "daily.parquet"
        daily_dir.mkdir()
        pd.read_csv(self.root/"daily.csv").to_parquet(daily_dir/"part-00000.parquet", index=False)
        (self.root/"coverage.json").write_text(json.dumps(self.coverage))
        command = [sys.executable, str(Path(__file__).resolve().parents[1]/"run_cohort.py")]
        for name, value in {"metadata": self.root/"metadata.csv", "labels": self.root/"labels.csv",
                            "cohort": self.root/"cohort.csv", "daily": daily_dir,
                            "coverage": self.root/"coverage.json", "output": self.root/"cli_results",
                            "cohort-year": 2024, "created-from": "2024-04-01", "created-to": "2024-04-07",
                            "window-days": 7, "data-kind": "Testing Data"}.items():
            command.extend(["--"+name, str(value)])
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = pd.read_csv(self.root/"cli_results/cohort_window_summary.csv")
        self.assertEqual(summary.complete_21d_repos.tolist(), [2]*3)
