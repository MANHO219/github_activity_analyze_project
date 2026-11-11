"""Keep cleanup restricted to accepted, explicitly recorded pilot files."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from weekly_cleanup import apply_cleanup, plan_cleanup


class CleanupTest(unittest.TestCase):
    def test_only_recorded_files_are_removed_after_two_day_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "results"
            day = root / "2024-01-16"
            attempt = day / "attempt-01"
            python_dir = attempt / "python"
            download_dir = attempt / "download"
            python_dir.mkdir(parents=True)
            download_dir.mkdir()
            for name in ("working.sqlite3", "events_clean.csv.gz", "repo_daily_counts.csv"):
                (python_dir / name).write_text("scratch", encoding="utf-8")
            keep_local = python_dir / "quality_summary.json"
            keep_local.write_text("keep", encoding="utf-8")
            raw_root = base / "volume" / "raw"
            raw = raw_root / "2024-01-16"
            raw.mkdir(parents=True)
            entries = []
            for hour in range(24):
                filename = f"2024-01-16-{hour}.json.gz"
                (raw / filename).write_bytes(b"verified fixture")
                entries.append({"name": filename, "status": "downloaded_verified", "bytes": 16,
                                "sha256": hashlib.sha256(b"verified fixture").hexdigest(), "attempts": []})
            keep_raw = raw / "unregistered.part"
            keep_raw.write_text("keep", encoding="utf-8")
            (download_dir / "download_manifest.json").write_text(json.dumps({
                "all_requested_archives_verified": True, "files": entries}), encoding="utf-8")
            proof = base / "proof"
            proof.mkdir()
            retained = {name: {"sha256": "fixture"} for name in ("events", "daily", "valid_index")}
            expected_hashes = {name: "fixture" for name in retained}
            checks = {name: True for name in ("complete_hourly_coverage", "all_valid_index_counts_match",
                      "event_ids_unique", "daily_counts_reconcile", "candidate_counts_reconcile")}
            (proof / "summary.json").write_text(json.dumps({"days": ["2024-01-15", "2024-01-16"],
                "checks": checks, "input_hashes": {"2024-01-15": expected_hashes, "2024-01-16": expected_hashes}}), encoding="utf-8")
            with patch("weekly_cleanup.accepted_day", return_value={"attempt": str(attempt.resolve()), "retained_files": retained}):
                plan_cleanup("2024-01-16", root, raw_root)
                with patch("weekly_cleanup.volume_check", side_effect=RuntimeError("volume missing")):
                    with self.assertRaisesRegex(RuntimeError, "volume missing"):
                        apply_cleanup("2024-01-16", root, base / "volume", raw_root, proof)
                self.assertTrue((python_dir / "working.sqlite3").exists())
                self.assertTrue((raw / "2024-01-16-0.json.gz").exists())
                with patch("weekly_cleanup.volume_check", return_value=1):
                    apply_cleanup("2024-01-16", root, base / "volume", raw_root, proof)
            self.assertTrue(keep_local.exists())
            self.assertTrue(keep_raw.exists())
            self.assertFalse((python_dir / "working.sqlite3").exists())
            self.assertFalse((raw / "2024-01-16-0.json.gz").exists())
            self.assertEqual(len(json.loads((day / "cleanup_done.json").read_text())["removed"]), 27)


if __name__ == "__main__":
    unittest.main()
