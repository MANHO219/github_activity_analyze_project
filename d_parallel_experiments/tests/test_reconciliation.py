"""Small real-data comparisons and failure paths; no JVM or cluster is needed."""
import contextlib
import gzip
import hashlib
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "d_parallel_experiments/scripts"))
import run_reconciliation as runner
import collect_reconciliation as collector


class CodeHashTests(unittest.TestCase):
    def test_lf_and_crlf_pass_but_a_code_change_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, manifest = root / "module.py", root / "expected.json"
            lf = b"def answer():\n    return 1\n"
            runner.write_json(manifest, {"module.py": hashlib.sha256(lf).hexdigest()})
            source.write_bytes(lf)
            first = runner.verify_code(root, manifest)
            source.write_bytes(lf.replace(b"\n", b"\r\n"))
            second = runner.verify_code(root, manifest)
            self.assertEqual(first["sha256_lf"], second["sha256_lf"])
            self.assertNotEqual(first["sha256_raw"], second["sha256_raw"])
            source.write_bytes(lf.replace(b"return 1", b"return 2"))
            with self.assertRaisesRegex(ValueError, "Source code differs"):
                runner.verify_code(root, manifest)

    def test_empty_manifest_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "empty.json"
            manifest.write_text("{}")
            with self.assertRaises(ValueError):
                runner.verify_code(Path(tmp), manifest)


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.raw, self.spark = self.root / "raw", self.root / "spark_fixture"
        self.raw.mkdir()
        cfg = json.loads((runner.ROOT / "a_data_pipeline/config/sample.json").read_text())
        cfg["hours"] = list(range(6))
        records = []
        for hour in range(6):
            row = {"id": str(100 + hour), "type": "PushEvent",
                   "created_at": f"{cfg['date']}T{hour:02}:00:00Z",
                   "repo": {"id": 7, "name": "owner/project"},
                   "actor": {"id": 8, "login": "actor"}, "payload": {}, "public": True}
            path = self.raw / f"{cfg['date']}-{hour}.json.gz"
            with gzip.open(path, "wt", encoding="utf-8") as stream:
                stream.write(json.dumps(row) + "\n")
            records.append({"name": path.name, "bytes": path.stat().st_size,
                            "sha256": runner.file_digest(path)})
        self.manifest = self.root / "inputs.json"
        runner.write_json(self.manifest, {"groups": {"6h": {"archives": records}}})
        # An equal Python-produced fixture stands in for Spark's persisted files.
        # This tests the comparison/packaging code, not Spark execution.
        runner.clean(cfg, self.raw, self.spark)
        self.output = self.root / "reconciliation"
        self.args = ["--raw-dir", str(self.raw), "--spark-run", str(self.spark),
                     "--output", str(self.output), "--input-manifest", str(self.manifest),
                     "--expected-rows", "6"]

    def tearDown(self):
        self.tmp.cleanup()

    def invoke(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return runner.main(self.args)

    def status(self):
        return json.loads((self.output / "reconciliation_status.json").read_text())

    def collect_args(self):
        fingerprints = {}
        for name in ("events_clean.csv.gz", "repo_daily_counts.csv",
                     "repo_candidates.csv", "repo_name_history.csv"):
            with (gzip.open(self.spark / name, "rb") if name.endswith(".gz")
                  else (self.spark / name).open("rb")) as stream:
                fingerprints[name] = hashlib.file_digest(stream, "sha256").hexdigest()
        evidence = self.root / "spark_evidence.json"
        runner.write_json(evidence, {"run_id": self.spark.name, "parquet_rows": 6,
                                     "fingerprints": fingerprints})
        self.archive = self.root / "evidence.tar.gz"
        return ["--run-dir", str(self.output), "--archive", str(self.archive),
                "--spark-evidence", str(evidence)]

    def collect(self, args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return collector.main(args)

    def test_matching_fixture_passes_and_archives_without_large_data(self):
        self.assertEqual(self.invoke(), 0)
        self.assertEqual(self.status()["state"], "completed")
        self.assertEqual(self.collect(self.collect_args()), 0)
        with tarfile.open(self.archive) as archive:
            names = archive.getnames()
        self.assertIn("expected_code_lf.json", names)
        self.assertIn("execution/run_reconciliation.py", names)
        self.assertFalse(any(".sqlite" in name or ".parquet" in name for name in names))

    def test_original_comparison_false_exits_nonzero_and_cannot_archive(self):
        failed = {"passed": False, "checks": {"rows_equal": False}}
        with patch.object(runner, "compare", return_value=failed):
            self.assertEqual(self.invoke(), 1)
        self.assertEqual(self.status()["state"], "error")
        self.assertFalse(self.status()["original_comparison_passed"])
        self.assertEqual(self.collect(self.collect_args()), 1)
        self.assertFalse(self.archive.exists())

    def test_field_comparison_false_exits_nonzero(self):
        failed = {"passed": False, "checks": {"fields_equal": False}}
        with patch.object(runner, "compare_fields", return_value=failed):
            self.assertEqual(self.invoke(), 1)
        self.assertTrue(self.status()["original_comparison_passed"])
        self.assertFalse(self.status()["field_comparison_passed"])
        self.assertEqual(self.status()["state"], "error")

    def test_comparator_exception_exits_nonzero(self):
        with patch.object(runner, "compare", side_effect=RuntimeError("injected failure")):
            self.assertEqual(self.invoke(), 1)
        self.assertEqual(self.status()["state"], "error")
        self.assertIn("injected failure", self.status()["error"])

    def test_collector_checks_reports_even_if_status_says_passed(self):
        self.assertEqual(self.invoke(), 0)
        runner.write_json(self.output / "field_comparison/comparison_summary.json",
                          {"passed": False, "checks": {"fields_equal": False}})
        self.assertEqual(self.collect(self.collect_args()), 1)
        self.assertFalse(self.archive.exists())

    def test_collector_rejects_changed_spark_export(self):
        self.assertEqual(self.invoke(), 0)
        args = self.collect_args()
        with (self.spark / "repo_candidates.csv").open("a") as stream:
            stream.write("changed\n")
        self.assertEqual(self.collect(args), 1)
        self.assertFalse(self.archive.exists())


if __name__ == "__main__":
    unittest.main()
