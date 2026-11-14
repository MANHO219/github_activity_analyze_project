"""Testing Data: generic planning and proof dates must not depend on January."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from weekly_cleanup import apply_cleanup


class RollingDateTests(unittest.TestCase):
    def test_both_years_plan_27_days_without_creating_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "not_created"
            for year in [2024, 2026]:
                p = subprocess.run([sys.executable, str(TOOLS / "weekly_orchestrate.py"),
                                    "--start", f"{year}-04-01", "--end", f"{year}-04-27",
                                    "--root", str(root), "--plan-only"], capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stderr)
                plan = json.loads(p.stdout)
                self.assertEqual(plan["requested_hours"], 648)
                self.assertEqual(plan["first_two_days"], [f"{year}-04-01", f"{year}-04-02"])
                self.assertFalse(root.exists())

    def test_nonconsecutive_proof_fails_before_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            (p / "summary.json").write_text(json.dumps({"days": ["2026-04-01", "2026-04-03"]}))
            with self.assertRaisesRegex(RuntimeError, "Two-day"):
                apply_cleanup("2026-04-03", p, p, p, p)

    def test_new_dates_still_require_matching_accepted_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            checks = {n: True for n in ["complete_hourly_coverage", "all_valid_index_counts_match",
                                        "event_ids_unique", "daily_counts_reconcile", "candidate_counts_reconcile"]}
            (p / "summary.json").write_text(json.dumps({"days": ["2026-04-01", "2026-04-02"],
                                                      "checks": checks, "input_hashes": {}}))
            retained = {n: {"sha256": "Testing Data"} for n in ["events", "daily", "valid_index"]}
            with patch("weekly_cleanup.accepted_day", return_value={"retained_files": retained}):
                with self.assertRaisesRegex(RuntimeError, "does not match accepted inputs"):
                    apply_cleanup("2026-04-02", p, p, p, p)
