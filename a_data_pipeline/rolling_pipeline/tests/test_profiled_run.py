"""The timing wrapper must retain the existing cleaning results."""

import csv
import json
from pathlib import Path
import subprocess
import sys
import unittest

import pyarrow.parquet as pq

PIPELINE = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))
import tests.test_pipeline as fixtures


class ProfiledRunTest(unittest.TestCase):
    def test_profiled_pipeline_matches_reference(self):
        fixture = fixtures.SampleTests("test_expected_cleaning_and_process_retention")
        fixture.setUp()
        try:
            reference, profiled = fixture.root / "reference", fixture.root / "profiled"
            common = ["--date", "2024-01-15", "--hours", "2,10", "--skip-download", "--data-dir", str(fixture.raw)]
            for entry, target in ((PIPELINE / "scripts/run_sample.py", reference),
                                  (TOOLS / "profiled_run_sample.py", profiled)):
                subprocess.run([sys.executable, str(entry), *common, "--run-dir", str(target)],
                               check=True, capture_output=True, text=True)
            left = json.loads((reference / "python/quality_summary.json").read_text())
            right = json.loads((profiled / "python/quality_summary.json").read_text())
            self.assertEqual(left, right)
            self.assertTrue(pq.read_table(reference / "python/events_clean.parquet").equals(
                pq.read_table(profiled / "python/events_clean.parquet")))
            with (reference / "python/repo_daily_counts.csv").open(newline="") as source:
                reference_daily = list(csv.DictReader(source))
            with (profiled / "python/repo_daily_counts.csv").open(newline="") as source:
                self.assertEqual(reference_daily, list(csv.DictReader(source)))
            timing = json.loads((profiled / "python/timing_detail.json").read_text())
            self.assertEqual(len(timing["per_archive_seconds"]), 2)
            self.assertTrue(any(row["step"] == "event_groups" for row in timing["sql_statements"]))
            self.assertGreaterEqual(timing["total_seconds"], 0)
            self.assertGreaterEqual(timing["remaining_seconds"], -0.01)
        finally:
            fixture.tearDown()


if __name__ == "__main__":
    unittest.main()
