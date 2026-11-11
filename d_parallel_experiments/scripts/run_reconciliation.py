"""Rebuild the six-hour Python reference and require both comparisons to pass."""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "a_data_pipeline"))
from gharchive_a.clean import clean
from gharchive_a.compare import compare
from compare_python_slice import run as compare_fields


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_code(root, manifest):
    expected = json.loads(manifest.read_text(encoding="utf-8"))
    if not expected:
        raise ValueError("The normalized source-code manifest must not be empty")
    raw, normalized = {}, {}
    for name in expected:
        data = (root / name).read_bytes()
        raw[name] = hashlib.sha256(data).hexdigest()
        normalized[name] = hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()
    different = [name for name in expected if normalized[name] != expected[name]]
    if different:
        raise ValueError("Source code differs from the LF baseline: " + ", ".join(different))
    return {"normalization": "CRLF to LF for source code only",
            "sha256_raw": raw, "sha256_lf": normalized}


def require_passed(report, label):
    checks = report.get("checks", {})
    if report.get("passed") is not True or not checks or not all(v is True for v in checks.values()):
        raise ValueError(f"{label} did not pass; inspect its comparison_summary.json")


def run(args):
    output, spark = args.output.resolve(), args.spark_run.resolve()
    output.mkdir(parents=True, exist_ok=False)
    status = {"state": "running", "spark_run": str(spark),
              "reference_origin": "Python recomputed from the same six raw archives"}
    state_file = output / "reconciliation_status.json"
    write_json(state_file, status)
    try:
        write_json(output / "code_sha256.json", verify_code(ROOT, args.expected_code))
        shutil.copyfile(args.expected_code, output / "expected_code_lf.json")
        cfg = json.loads((ROOT / "a_data_pipeline/config/sample.json").read_text())
        cfg["hours"] = list(range(6))
        records = json.loads(args.input_manifest.read_text())["groups"]["6h"]["archives"]
        names = [f"{cfg['date']}-{hour}.json.gz" for hour in cfg["hours"]]
        if len(records) != 6 or {r["name"] for r in records} != set(names):
            raise ValueError("Expected exactly the six published source files")
        for row in records:
            path = args.raw_dir / row["name"]
            if path.stat().st_size != row["bytes"] or file_digest(path) != row["sha256"]:
                raise ValueError(f"Input archive differs from the manifest: {path}")
        write_json(output / "input_hash_verification.json", records)
        quality = clean(cfg, args.raw_dir, output / "python")
        status["python_events"] = quality["cleaned_events"]
        original = compare(output / "python", spark, output / "original_comparison")
        status["original_comparison_passed"] = original.get("passed") is True
        write_json(state_file, status)
        require_passed(original, "Original Python/Spark comparison")
        fields = compare_fields(SimpleNamespace(
            output=str(output / "field_comparison"),
            python_parquet=str(output / "python/events_clean.parquet"),
            spark_parquet=str(spark / "events_clean.parquet"),
            spark_daily=str(spark / "repo_daily_counts.csv"),
            source_files=names, expected_rows=args.expected_rows))
        status["field_comparison_passed"] = fields.get("passed") is True
        require_passed(fields, "Full-field comparison")
        status["state"] = "completed"
    except Exception as exc:
        status.update(state="error", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        write_json(state_file, status)
    return status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("/data/cs5488/raw"))
    parser.add_argument("--spark-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New directory; existing output is refused")
    parser.add_argument("--expected-code", type=Path,
                        default=ROOT / "d_parallel_experiments/configs/reconciliation_code_lf.json")
    parser.add_argument("--input-manifest", type=Path,
                        default=ROOT / "a_data_pipeline/verification/20240115_1day/input_slices.json")
    parser.add_argument("--expected-rows", type=int, default=1177282)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args), ensure_ascii=False))
    except Exception as exc:
        print(f"Reconciliation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
