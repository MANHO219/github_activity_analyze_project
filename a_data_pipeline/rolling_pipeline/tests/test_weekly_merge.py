"""Regression checks for duplicates and conflicts across daily boundaries."""

from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parent))
from gharchive_a.export import event_schema
from weekly_pipeline import INDEX_SCHEMA, sha256
from weekly_merge import make_outputs


class CrossDayMergeTest(unittest.TestCase):
    def test_duplicates_conflicts_and_daily_conflicts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            indexes = {
                "2024-01-15": [("1", 1, 1), ("2", 1, 2), ("3", 1, 3), ("3", 1, 4), ("4", 1, 5), ("4", 2, 6)],
                "2024-01-16": [("1", 1, 1), ("2", 2, 2), ("4", 1, 3), ("5", 1, 4)],
            }
            cleaned = {"2024-01-15": [("1", 1), ("2", 2), ("3", 3)],
                       "2024-01-16": [("1", 1), ("2", 2), ("4", 3), ("5", 4)]}
            for day, records in indexes.items():
                folder = root / day
                folder.mkdir()
                hour = day + "T00:00:00Z"
                index = folder / "index.parquet"
                pq.write_table(pa.Table.from_pylist([
                    {"event_id": event_id, "canonical_sha256": bytes([fingerprint]) * 32,
                     "source_hour": hour, "source_line": line}
                    for event_id, fingerprint, line in records
                ], schema=INDEX_SCHEMA), index)
                events = folder / "events.parquet"
                stamp = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
                pq.write_table(pa.Table.from_pylist([
                    {"event_id": event_id, "event_type": "PushEvent", "event_time": stamp,
                     "repo_id": int(event_id), "repo_name": f"owner/repo{event_id}",
                     "actor_id": 1, "actor_login": "actor", "event_date": date.fromisoformat(day),
                     "source_file": day + "-0.json.gz", "source_line": line, "source_hour": stamp,
                     "time_outside_file_hour": False, "optional_field_issues": []}
                    for event_id, line in cleaned[day]
                ], schema=event_schema()), events)
                daily = folder / "daily.parquet"
                pq.write_table(pa.table({"dummy": [1]}), daily)
                manifest = folder / "manifest.json"
                manifest.write_text(json.dumps({"observed_files": [
                    {"name": f"{day}-{hour_number}.json.gz", "bytes": 1, "sha256": "fixture"}
                    for hour_number in range(24)]}), encoding="utf-8")
                retained = {}
                for name, path in (("events", events), ("daily", daily), ("valid_index", index)):
                    retained[name] = {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
                (folder / "accepted.json").write_text(json.dumps({"archive_count": 24,
                    "code_sha256": "fixture-code", "rule_version": "a-events-v1",
                    "valid_before_dedup": len(records), "cleaned_events": len(cleaned[day]),
                    "input_manifest": str(manifest), "retained_files": retained}), encoding="utf-8")

            args = type("Args", (), {"root": root})()
            output = root / "merged"
            make_outputs(list(indexes), output, args)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["final_events"], 3)
            self.assertEqual(summary["index_counts"]["duplicate_occurrences_removed"], 2)
            self.assertEqual(summary["index_counts"]["conflicting_occurrences_excluded"], 5)
            self.assertEqual(summary["cross_day_daily_rows_removed"], 4)
            self.assertEqual(summary["daily_sum"], 3)
            self.assertEqual(summary["candidate_sum"], 3)


if __name__ == "__main__":
    unittest.main()
