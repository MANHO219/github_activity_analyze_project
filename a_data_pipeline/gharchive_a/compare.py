"""Disk-backed comparison of event identities, every exported field and daily counts."""
import csv
import gzip
import json
import sqlite3
from datetime import timezone
from pathlib import Path

from .common import EVENT_COLUMNS, stage_directory, write_csv, write_json


def require_complete(path):
    status = json.loads((path / "stage_status.json").read_text(encoding="utf-8"))
    if status["state"] != "completed":
        raise ValueError(f"Cannot compare an incomplete stage: {path}")
    return json.loads((path / "input_manifest.json").read_text(encoding="utf-8"))


def check_parquet(db, side, folder):
    """Stream Parquet values back into the same textual contract as CSV."""
    import pyarrow.dataset as ds
    dataset = ds.dataset(folder / "events_clean.parquet", format="parquet")
    schema = dataset.schema
    if schema.names != EVENT_COLUMNS:
        raise ValueError(f"Unexpected Parquet columns: {folder}")
    for key in ("event_time", "source_hour"):
        field = schema.field(key)
        if getattr(field.type, "tz", None) != "UTC" or getattr(field.type, "unit", None) != "us":
            raise ValueError(f"{side} Parquet {key} must be timestamp[us, tz=UTC], got {field.type}")
    db.execute(f"CREATE TABLE {side}_parquet ({', '.join(key + ' TEXT' for key in EVENT_COLUMNS)})")

    def rows():
        for batch in dataset.to_batches(batch_size=10000):
            for row in batch.to_pylist():
                for key in ("event_time", "source_hour"):
                    precision = "microseconds" if key == "event_time" else "seconds"
                    row[key] = row[key].astimezone(timezone.utc).isoformat(timespec=precision).replace("+00:00", "Z")
                row["event_date"] = row["event_date"].isoformat()
                row["optional_field_issues"] = json.dumps(row["optional_field_issues"], ensure_ascii=False)
                yield ["" if row[key] is None else str(row[key]) for key in EVENT_COLUMNS]

    db.executemany(f"INSERT INTO {side}_parquet VALUES ({', '.join('?' for _ in EVENT_COLUMNS)})", rows())
    query = f"SELECT COUNT(*) FROM (SELECT * FROM {side}_parquet EXCEPT SELECT * FROM {side}_events)"
    reverse = f"SELECT COUNT(*) FROM (SELECT * FROM {side}_events EXCEPT SELECT * FROM {side}_parquet)"
    equal_values = db.execute(query).fetchone()[0] == 0 and db.execute(reverse).fetchone()[0] == 0
    parquet_count = db.execute(f"SELECT COUNT(*) FROM {side}_parquet").fetchone()[0]
    csv_count = db.execute(f"SELECT COUNT(*) FROM {side}_events").fetchone()[0]
    unique = db.execute(f"SELECT COUNT(DISTINCT event_id) FROM {side}_parquet").fetchone()[0] == parquet_count
    return {"matches_csv": equal_values and parquet_count == csv_count and unique,
            "row_count": parquet_count, "types": {f.name: str(f.type) for f in schema}}


def compare(left, right, output):
    left, right = Path(left), Path(right)
    first, second = require_complete(left), require_complete(right)
    fingerprint = lambda m: sorted((f["name"], f["sha256"]) for f in m["observed_files"])
    compatible = (fingerprint(first) == fingerprint(second) and first["rule_version"] == second["rule_version"]
                  and first["expected_files"] == second["expected_files"] and first["missing_files"] == second["missing_files"])
    with stage_directory(output, "compare", {"left": str(left.resolve()), "right": str(right.resolve())}) as out:
        if not compatible:
            write_json(out / "comparison_summary.json", {"passed": False, "reason": "Different input hashes, requested coverage or rule versions"})
            raise ValueError("Inputs/rules differ; these runs cannot be compared")
        db = sqlite3.connect(out / "comparison.sqlite3")
        try:
            for side, folder in (("left", left), ("right", right)):
                db.execute(f"CREATE TABLE {side}_events ({', '.join(key + ' TEXT' for key in EVENT_COLUMNS)})")
                with gzip.open(folder / "events_clean.csv.gz", "rt", encoding="utf-8", newline="") as handle:
                    reader = csv.DictReader(handle)
                    if reader.fieldnames != EVENT_COLUMNS:
                        raise ValueError(f"Unexpected event columns in {folder}")
                    db.executemany(f"INSERT INTO {side}_events VALUES ({', '.join('?' for _ in EVENT_COLUMNS)})", ([row[key] for key in EVENT_COLUMNS] for row in reader))
                db.execute(f"CREATE INDEX {side}_id ON {side}_events(event_id)")
                db.execute(f"CREATE TABLE {side}_daily (repo_id TEXT, event_date TEXT, event_type TEXT, event_count INTEGER)")
                with (folder / "repo_daily_counts.csv").open(encoding="utf-8", newline="") as handle:
                    db.executemany(f"INSERT INTO {side}_daily VALUES (?, ?, ?, ?)", ((r["repo_id"], r["event_date"], r["event_type"], int(r["event_count"])) for r in csv.DictReader(handle)))
            differences = {}
            for label, columns, left_table, right_table in (("event_ids", ["event_id"], "left_events", "right_events"),
                                                          ("event_rows", EVENT_COLUMNS, "left_events", "right_events"),
                                                          ("daily_counts", ["repo_id", "event_date", "event_type", "event_count"], "left_daily", "right_daily")):
                for direction, a, b in (("left_only", left_table, right_table), ("right_only", right_table, left_table)):
                    query = f"SELECT {', '.join(columns)} FROM {a} EXCEPT SELECT {', '.join(columns)} FROM {b}"
                    count = db.execute(f"SELECT COUNT(*) FROM ({query})").fetchone()[0]
                    differences[f"{label}_{direction}"] = count
                    write_csv(out / f"{label}_{direction}_examples.csv", columns, (dict(zip(columns, row)) for row in db.execute(query + " LIMIT 100")))
            checks = {"same_input_hashes_and_rules": compatible}
            left_quality = json.loads((left / "quality_summary.json").read_text(encoding="utf-8"))
            right_quality = json.loads((right / "quality_summary.json").read_text(encoding="utf-8"))
            for key in ("line_status_counts", "rejection_reasons", "duplicates_removed", "conflicting_ids",
                        "conflict_occurrences_excluded", "clean_unique_repos", "clean_event_types",
                        "time_outside_file_hour_before_dedup", "time_outside_file_hour_clean"):
                checks[f"same_{key}"] = left_quality[key] == right_quality[key]
            for side in ("left", "right"):
                checks[f"{side}_ids_unique"] = db.execute(f"SELECT COUNT(*) = COUNT(DISTINCT event_id) FROM {side}_events").fetchone()[0] == 1
                reconstructed = f"SELECT repo_id, event_date, event_type, COUNT(*) AS event_count FROM {side}_events GROUP BY repo_id, event_date, event_type"
                mismatch = db.execute(f"SELECT COUNT(*) FROM (SELECT * FROM {side}_daily EXCEPT {reconstructed})").fetchone()[0]
                reverse = db.execute(f"SELECT COUNT(*) FROM ({reconstructed} EXCEPT SELECT * FROM {side}_daily)").fetchone()[0]
                checks[f"{side}_daily_matches_events"] = mismatch == 0 and reverse == 0
                checks[f"{side}_daily_keys_unique"] = db.execute(
                    f"SELECT COUNT(*) FROM {side}_daily").fetchone()[0] == db.execute(
                    f"SELECT COUNT(*) FROM (SELECT DISTINCT repo_id, event_date, event_type FROM {side}_daily)").fetchone()[0]
            parquet_results = {}
            for side, folder in (("left", left), ("right", right)):
                if (folder / "events_clean.parquet").exists():
                    parquet_results[side] = check_parquet(db, side, folder)
                    checks[f"{side}_parquet_matches_csv"] = parquet_results[side]["matches_csv"]
                else:
                    parquet_results[side] = {"skipped": "CSV-only output"}
            if "types" in parquet_results["left"] and "types" in parquet_results["right"]:
                checks["same_parquet_types"] = parquet_results["left"]["types"] == parquet_results["right"]["types"]
            write_json(out / "parquet_validation.json", parquet_results)
            summary = {"passed": all(checks.values()) and not any(differences.values()), "checks": checks,
                       "differences": differences, "left_events": db.execute("SELECT COUNT(*) FROM left_events").fetchone()[0],
                       "right_events": db.execute("SELECT COUNT(*) FROM right_events").fetchone()[0],
                       "note": "Compares ingestion and DataFrame results; shared parsing rules are also covered by adversarial fixture tests."}
            write_json(out / "comparison_summary.json", summary)
            db.commit()
            if not summary["passed"]:
                raise RuntimeError("Outputs differ; see comparison summary and difference examples")
        finally:
            db.close()
    return summary
