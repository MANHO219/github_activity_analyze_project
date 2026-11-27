"""Adversarial fixtures assert known outcomes, not merely implementation agreement."""
import copy
from contextlib import closing
import csv
import gzip
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gharchive_a.clean import clean
from gharchive_a.common import ROOT, select_inputs, sha256_file
from gharchive_a.download import download
from gharchive_a.inspect import inspect


def event(identifier, hour=2, name="old/name", payload=None):
    return {"id": str(identifier), "type": "PushEvent", "created_at": f"2024-01-15T{hour:02d}:01:00Z",
            "repo": {"id": 1, "name": name}, "actor": {"id": 2, "login": "actor"}, "payload": payload or {"x": 1}}


class SampleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.raw = self.root / "raw"
        self.raw.mkdir()
        self.cfg = json.loads((ROOT / "config/sample.json").read_text())
        self.cfg["hours"] = [2, 10]
        one = event(100)
        optional = event(101)
        optional.update(type="FutureEvent", repo={"id": 5})
        optional.pop("actor")
        conflict = event(102, payload={"x": "first"})
        invalid_id = event(103)
        invalid_id["id"] = True
        invalid_repo = event(104)
        invalid_repo["repo"]["id"] = None
        naive_time = event(105)
        naive_time["created_at"] = "2024-01-15T02:00:00"
        off_hour = event(106)
        off_hour["created_at"] = "2024-01-16T00:00:00+00:00"
        lines = [json.dumps(one).encode(), json.dumps(one, sort_keys=True).encode(),
                 json.dumps(optional).encode(), json.dumps(conflict).encode(), b"bad{", b"[]",
                 json.dumps(invalid_id).encode(), json.dumps(invalid_repo).encode(),
                 json.dumps(naive_time).encode(), json.dumps(off_hour).encode(), b'{"bad":"\xff"}', b""]
        self.write_archive(2, lines)
        self.write_archive(10, [json.dumps(one).encode(), json.dumps(event(102, payload={"x": "second"})).encode(),
                                json.dumps(event(107, hour=10, name="new/name")).encode()])

    def tearDown(self):
        self.temporary.cleanup()

    def write_archive(self, hour, lines):
        with gzip.open(self.raw / f"2024-01-15-{hour}.json.gz", "wb") as handle:
            for line in lines:
                handle.write(line + b"\n")

    def test_expected_cleaning_and_process_retention(self):
        before = {p.name: sha256_file(p) for p in self.raw.iterdir()}
        out = self.root / "python"
        summary = clean(self.cfg, self.raw, out)
        self.assertEqual(summary["cleaned_events"], 4)
        self.assertEqual(summary["duplicates_removed"], 2)
        self.assertEqual(summary["conflicting_ids"], 1)
        self.assertEqual(summary["conflict_occurrences_excluded"], 2)
        self.assertEqual(summary["line_status_counts"], {"valid": 8, "parse_error": 2, "invalid": 4, "blank": 1})
        with gzip.open(out / "events_clean.csv.gz", "rt", encoding="utf-8", newline="") as handle:
            rows = {r["event_id"]: r for r in csv.DictReader(handle)}
        self.assertEqual(set(rows), {"100", "101", "106", "107"})
        self.assertEqual(rows["100"]["source_file"], "2024-01-15-2.json.gz")
        self.assertEqual(rows["101"]["event_type"], "FutureEvent")
        self.assertEqual(rows["101"]["actor_id"], "")
        self.assertEqual(rows["106"]["time_outside_file_hour"], "True")
        self.assertEqual(summary["time_outside_file_hour_before_dedup"], 3)
        self.assertEqual(summary["time_outside_file_hour_clean"], 1)
        self.assertEqual(len((out / "rejected_records.jsonl").read_text().splitlines()), 6)
        self.assertEqual(len((out / "conflicting_records.jsonl").read_text().splitlines()), 2)
        with closing(sqlite3.connect(out / "working.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM valid_events").fetchone()[0], 8)
        with (out / "repo_candidates.csv").open() as handle:
            candidates = {r["repo_id"]: r for r in csv.DictReader(handle)}
        self.assertEqual(candidates["1"]["observed_name_count"], "2")
        import pyarrow.parquet as pq
        arrow = pq.read_table(out / "events_clean.parquet")
        self.assertEqual(arrow.num_rows, 4)
        self.assertEqual(str(arrow.schema.field("event_time").type), "timestamp[us, tz=UTC]")
        self.assertEqual(before, {p.name: sha256_file(p) for p in self.raw.iterdir()})
        with self.assertRaises(FileExistsError):
            clean(self.cfg, self.raw, out)

    def test_inspection_is_before_dedup(self):
        result = inspect(self.cfg, self.raw, self.root / "inspection")
        self.assertEqual(result["line_status_counts"]["valid"], 8)
        self.assertEqual(result["unique_valid_repos"], 2)
        self.assertEqual(len(json.loads((self.root / "inspection/raw_examples.json").read_text())), 5)

    def test_empty_valid_archive_still_exports_readable_schema(self):
        self.write_archive(2, [])
        cfg = copy.deepcopy(self.cfg)
        cfg["hours"] = [2]
        result = clean(cfg, self.raw, self.root / "empty")
        self.assertEqual(result["cleaned_events"], 0)
        self.assertEqual(result["time_outside_file_hour_clean"], 0)
        import pyarrow.parquet as pq
        self.assertEqual(pq.read_table(self.root / "empty/events_clean.parquet").num_rows, 0)

    def test_missing_hours_require_explicit_opt_in(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["hours"].append(11)
        with self.assertRaises(FileNotFoundError):
            select_inputs(cfg, self.raw)
        _, manifest = select_inputs(cfg, self.raw, allow_missing=True)
        self.assertEqual(manifest["missing_files"], ["2024-01-15-11.json.gz"])
        self.assertFalse(manifest["all_requested_archives_present"])

    def test_truncated_archive_never_marks_stage_completed(self):
        path = self.raw / "2024-01-15-2.json.gz"
        path.write_bytes(path.read_bytes()[:-10])
        with self.assertRaises((EOFError, OSError)):
            clean(self.cfg, self.raw, self.root / "broken")
        status = json.loads((self.root / "broken/stage_status.json").read_text())
        self.assertEqual(status["state"], "failed")

    def test_download_cache_is_verified_and_corruption_is_preserved(self):
        cfg = copy.deepcopy(self.cfg)
        cfg.update(hours=[2], retries=0)
        result = download(cfg, self.raw, self.root / "cached")
        self.assertEqual(result["files"][0]["status"], "cached_verified")
        path = self.raw / "2024-01-15-2.json.gz"
        path.write_bytes(b"not a gzip")
        with self.assertRaises(RuntimeError):
            download(cfg, self.raw, self.root / "bad_cache")
        self.assertEqual(path.read_bytes(), b"not a gzip")

    def test_download_request_preserves_manifest_and_raw_data(self):
        probe = self.root / "hardlink-capability-probe"
        try:
            os.link(self.raw / "2024-01-15-2.json.gz", probe)
        except OSError as error:
            self.skipTest(f"Historical downloader requires hard links, unavailable here: {error}")
        else:
            probe.unlink()
        payload = (self.raw / "2024-01-15-2.json.gz").read_bytes()
        class Response(io.BytesIO):
            status = 200
            headers = {"Content-Length": str(len(payload)), "Content-Type": "application/gzip"}
        cfg = copy.deepcopy(self.cfg)
        cfg.update(hours=[2], retries=0)
        target = self.root / "downloaded"
        with patch("urllib.request.urlopen", return_value=Response(payload)):
            result = download(cfg, target, self.root / "download")
        self.assertEqual(result["files"][0]["status"], "downloaded_verified")
        self.assertEqual((target / "2024-01-15-2.json.gz").read_bytes(), payload)

    @unittest.skipUnless(os.environ.get("RUN_SPARK_TESTS") == "1", "Set RUN_SPARK_TESTS=1 for local Spark fixture verification")
    def test_spark_and_reference_agree_on_adversarial_inputs(self):
        from gharchive_a.compare import compare
        from gharchive_a.spark_clean import clean_spark
        clean(self.cfg, self.raw, self.root / "python")
        result = clean_spark(self.cfg, self.raw, self.root / "spark")
        self.assertEqual(result["cleaned_events"], 4)
        self.assertEqual(result["conflict_occurrences_excluded"], 2)
        comparison = compare(self.root / "python", self.root / "spark", self.root / "comparison")
        self.assertTrue(comparison["passed"])
        self.assertTrue(comparison["checks"]["same_parquet_types"])
        self.assertTrue(comparison["checks"]["right_parquet_matches_csv"])


if __name__ == "__main__":
    unittest.main()
