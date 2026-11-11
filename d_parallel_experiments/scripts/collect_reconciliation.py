"""Archive only a successful reconciliation, preserving historical evidence."""
import argparse
import gzip
import hashlib
import json
import sys
import tarfile
from pathlib import Path

from run_reconciliation import ROOT, require_passed, write_json


def collect(args):
    base = args.run_dir.resolve()
    status = json.loads((base / "reconciliation_status.json").read_text())
    if not (status.get("state") == "completed"
            and status.get("original_comparison_passed") is True
            and status.get("field_comparison_passed") is True):
        raise ValueError("Refusing to archive an incomplete or failed reconciliation")
    for folder in ("original_comparison", "field_comparison"):
        require_passed(json.loads((base / folder / "comparison_summary.json").read_text()), folder)
    spark = Path(status["spark_run"])
    evidence = json.loads(args.spark_evidence.read_text())
    if evidence["run_id"] != spark.name or evidence["parquet_rows"] != status["python_events"]:
        raise ValueError("Spark evidence does not describe the reconciled output")
    expected = evidence["fingerprints"]
    if set(expected) != {"events_clean.csv.gz", "repo_daily_counts.csv",
                         "repo_candidates.csv", "repo_name_history.csv"}:
        raise ValueError("Spark evidence must cover all four exported files")
    observed = {}
    for name in expected:
        digest = hashlib.sha256()
        with (gzip.open(spark / name, "rb") if name.endswith(".gz") else (spark / name).open("rb")) as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        observed[name] = digest.hexdigest()
    if observed != expected:
        raise ValueError("Spark output changed since the recorded experiment")
    if args.archive.exists():
        raise FileExistsError(f"Refusing to overwrite archive: {args.archive}")
    write_json(base / "spark_fingerprint_reverification.json", {"passed": True, "fingerprints": observed})
    args.archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.archive, "x:gz") as archive:
        for path in sorted(base.glob("*.json")):
            archive.add(path, arcname=path.name)
        for folder in ("python", "original_comparison", "field_comparison"):
            for path in sorted((base / folder).iterdir()):
                if path.is_file() and (path.suffix == ".json" or path.name.endswith("_examples.csv")):
                    archive.add(path, arcname=f"{folder}/{path.name}")
        for name in ("run_reconciliation.py", "collect_reconciliation.py", "compare_python_slice.py"):
            archive.add(Path(__file__).with_name(name), arcname=f"execution/{name}")
    return args.archive


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--spark-evidence", type=Path,
                        default=ROOT / "d_parallel_experiments/results/completed_20261111/measurements/d4stable_6h_r1_evidence.json")
    args = parser.parse_args(argv)
    try:
        print(collect(args))
    except Exception as exc:
        print(f"Archive refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
