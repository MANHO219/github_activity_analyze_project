"""Disk-backed global adjudication over EVERY valid source occurrence.

The reference parser and export schemas remain authoritative. Spark fragments
retain string timestamps and hex hashes in valid_before_dedup; this adapter
normalizes them explicitly. SQLite, not Spark, performs the final merge.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
import time

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from gharchive_a.common import EVENT_COLUMNS, write_csv, write_json
from gharchive_a.export import event_schema, export_daily, export_events
from rolling_pipeline.batch_support import read_json, timed

DAILY_COLUMNS = ["repo_id", "event_date", "event_type", "event_count"]
CANDIDATE_COLUMNS = ["repo_id", "repo_name", "first_observed_at", "last_observed_at", "event_count", "observed_name_count"]
VALID_SCHEMA = pa.schema([(f.name, pa.string() if f.name in ("event_time", "source_hour", "event_date") else f.type)
                          for f in event_schema()] + [("canonical_sha256", pa.string())])
INTEGER_FIELDS = {"repo_id", "actor_id", "source_line", "time_outside_file_hour"}


def normalized(row):
    row = {k: row[k] for k in EVENT_COLUMNS}
    for key in ("event_time", "source_hour"):
        value = row[key]
        value = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        if value.tzinfo is None:
            raise ValueError(f"Naive timestamp in {key}")
        row[key] = value.astimezone(timezone.utc).isoformat(
            timespec="microseconds" if key == "event_time" else "seconds").replace("+00:00", "Z")
    if isinstance(row["event_date"], date):
        row["event_date"] = row["event_date"].isoformat()
    flags = row["optional_field_issues"]
    row["optional_field_issues"] = json.dumps(json.loads(flags) if isinstance(flags, str) else flags, ensure_ascii=False)
    row["time_outside_file_hour"] = int(row["time_outside_file_hour"])
    return row


def create_db(path, cache_mib=128):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA temp_store=FILE")
    db.execute(f"PRAGMA cache_size={-int(cache_mib)*1024}")
    return db


def load_valid(db, fragments, guard=lambda: None):
    fields = ", ".join(f"{k} {'INTEGER' if k in INTEGER_FIELDS else 'TEXT'}" for k in EVENT_COLUMNS)
    db.execute(f"CREATE TABLE valid (batch TEXT, fragment TEXT, canonical_sha256 TEXT NOT NULL, {fields})")
    count = 0
    for fragment in fragments:
        dataset = ds.dataset(fragment["valid"], format="parquet")
        if set(dataset.schema.names) != set(EVENT_COLUMNS + ["canonical_sha256"]):
            raise ValueError("All-valid index must contain all event fields and the content fingerprint")
        for batch in dataset.to_batches(batch_size=10000):
            records = []
            for original in batch.to_pylist():
                fingerprint = original["canonical_sha256"]
                fingerprint = fingerprint.hex() if isinstance(fingerprint, bytes) else fingerprint
                if not isinstance(fingerprint, str) or len(fingerprint) != 64 or len(bytes.fromhex(fingerprint)) != 32:
                    raise ValueError("Invalid canonical SHA-256")
                row = normalized(original)
                records.append([fragment["batch"], fragment["fragment"], fingerprint.lower()] + [row[k] for k in EVENT_COLUMNS])
            db.executemany("INSERT INTO valid VALUES (" + ",".join("?" for _ in range(3+len(EVENT_COLUMNS))) + ")", records)
            count += len(records)
            db.commit()
            guard()
    # A source occurrence must belong to exactly one fragment and batch.
    db.execute("CREATE UNIQUE INDEX source_location ON valid(source_hour,source_line)")
    db.execute("CREATE INDEX valid_id ON valid(event_id)")
    return count


def classify(db):
    db.executescript("""
        CREATE TABLE groups AS SELECT event_id, COUNT(*) AS occurrences,
          COUNT(DISTINCT canonical_sha256) AS variants FROM valid GROUP BY event_id;
        CREATE UNIQUE INDEX groups_id ON groups(event_id);
        CREATE TABLE winners AS SELECT event_id, source_hour, source_line FROM (
          SELECT v.event_id, v.source_hour, v.source_line,
          ROW_NUMBER() OVER (PARTITION BY v.event_id ORDER BY v.source_hour,v.source_line) AS rank
          FROM valid v JOIN groups g USING(event_id) WHERE g.variants=1) WHERE rank=1;
        CREATE UNIQUE INDEX winner_location ON winners(source_hour,source_line);
        CREATE TABLE cleaned AS SELECT v.* FROM valid v JOIN winners w
          ON v.source_hour=w.source_hour AND v.source_line=w.source_line;
        CREATE UNIQUE INDEX cleaned_id ON cleaned(event_id);
        CREATE INDEX cleaned_repo_time ON cleaned(repo_id,event_time DESC,source_hour DESC,source_line DESC);
        CREATE VIEW daily AS SELECT repo_id,event_date,event_type,COUNT(*) AS event_count
          FROM cleaned GROUP BY repo_id,event_date,event_type;
        CREATE VIEW candidates AS SELECT c.repo_id,
          (SELECT n.repo_name FROM cleaned n WHERE n.repo_id=c.repo_id AND n.repo_name IS NOT NULL
           ORDER BY n.event_time DESC,n.source_hour DESC,n.source_line DESC LIMIT 1) AS repo_name,
          MIN(c.event_time) AS first_observed_at, MAX(c.event_time) AS last_observed_at,
          COUNT(*) AS event_count, COUNT(DISTINCT c.repo_name) AS observed_name_count
          FROM cleaned c GROUP BY c.repo_id;
    """)
    valid = db.execute("SELECT COUNT(*) FROM valid").fetchone()[0]
    kept = db.execute("SELECT COUNT(*) FROM winners").fetchone()[0]
    conflicts, excluded = db.execute("SELECT COUNT(*), COALESCE(SUM(occurrences),0) FROM groups WHERE variants>1").fetchone()
    duplicates = db.execute("SELECT COALESCE(SUM(occurrences-1),0) FROM groups WHERE variants=1").fetchone()[0]
    return {"valid_occurrences": valid, "final_events": kept, "duplicate_occurrences_removed": duplicates,
            "conflicting_event_ids": conflicts, "conflicting_occurrences_excluded": excluded}


def dict_rows(db, query):
    return (dict(r) for r in db.execute(query))


def python_valid_index(clean_dir):
    """Export Python's retained SQLite staging without losing rejected conflicts."""
    clean_dir = Path(clean_dir)
    db = sqlite3.connect((clean_dir / "working.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        with pq.ParquetWriter(clean_dir / "valid_before_dedup.parquet", VALID_SCHEMA) as writer:
            cursor = db.execute("SELECT " + ",".join(EVENT_COLUMNS + ["canonical_sha256"]) + " FROM valid_events ORDER BY sequence")
            while rows := cursor.fetchmany(10000):
                values = []
                for original in rows:
                    row = dict(original)
                    row["optional_field_issues"] = json.loads(row["optional_field_issues"])
                    row["time_outside_file_hour"] = bool(row["time_outside_file_hour"])
                    values.append(row)
                writer.write_table(pa.Table.from_pylist(values, schema=VALID_SCHEMA))
    finally:
        db.close()


def require_event_schema(schema):
    expected = event_schema()
    if schema.names != expected.names or any(schema.field(k).type != expected.field(k).type for k in expected.names):
        raise ValueError(f"Event field/type contract differs: {schema}")


def exact_difference(db, a, b, columns):
    cols = ",".join(columns)
    # GROUP BY includes multiplicity, so a duplicated row cannot pass EXCEPT.
    qa = f"SELECT {cols},COUNT(*) AS multiplicity FROM {a} GROUP BY {cols}"
    qb = f"SELECT {cols},COUNT(*) AS multiplicity FROM {b} GROUP BY {cols}"
    return [db.execute(f"SELECT COUNT(*) FROM ({x} EXCEPT {y})").fetchone()[0] for x,y in ((qa,qb),(qb,qa))]


def validate_fragment(clean_dir, scratch, guard=lambda: None):
    """Recompute local adjudication, then check exported values, types and counts."""
    from gharchive_a.compare import check_parquet
    clean_dir = Path(clean_dir)
    quality = read_json(clean_dir / "quality_summary.json")
    if read_json(clean_dir / "stage_status.json")["state"] != "completed" or not quality["checks"] or not all(quality["checks"].values()):
        raise RuntimeError("Cleaning stage/checks did not complete")
    db = create_db(scratch)
    try:
        load_valid(db, [{"batch": "local", "fragment": clean_dir.name, "valid": str(clean_dir / "valid_before_dedup.parquet")}], guard)
        stats = classify(db)
        checks = {"valid": stats["valid_occurrences"] == quality["line_status_counts"].get("valid",0),
                  "clean": stats["final_events"] == quality["cleaned_events"],
                  "duplicates": stats["duplicate_occurrences_removed"] == quality["duplicates_removed"],
                  "conflicts": stats["conflicting_event_ids"] == quality["conflicting_ids"],
                  "excluded": stats["conflicting_occurrences_excluded"] == quality["conflict_occurrences_excluded"]}
        dataset = ds.dataset(clean_dir / "events_clean.parquet", format="parquet")
        require_event_schema(dataset.schema)
        fields = ",".join(f"{k} {'INTEGER' if k in INTEGER_FIELDS else 'TEXT'}" for k in EVENT_COLUMNS)
        db.execute(f"CREATE TABLE exported ({fields})")
        for batch in dataset.to_batches(batch_size=10000):
            values = [normalized(r) for r in batch.to_pylist()]
            db.executemany("INSERT INTO exported VALUES ("+",".join("?" for _ in EVENT_COLUMNS)+")",
                           ([r[k] for k in EVENT_COLUMNS] for r in values))
            guard()
        checks["all_event_fields"] = exact_difference(db,"exported","cleaned",EVENT_COLUMNS)==[0,0]
        # Reuse the established CSV/Parquet conversion and validation contract.
        import gzip
        db.execute("CREATE TABLE actual_events ("+",".join(k+" TEXT" for k in EVENT_COLUMNS)+")")
        with gzip.open(clean_dir / "events_clean.csv.gz", "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != EVENT_COLUMNS:
                raise ValueError("Unexpected event CSV fields")
            db.executemany("INSERT INTO actual_events VALUES ("+",".join("?" for _ in EVENT_COLUMNS)+")",
                           ([r[k] for k in EVENT_COLUMNS] for r in reader))
        checks["csv_parquet"] = check_parquet(db,"actual",clean_dir)["matches_csv"]
        daily_ds = ds.dataset(clean_dir / "repo_daily_counts.parquet", format="parquet")
        expected_types = [pa.int64(), pa.date32(), pa.string(), pa.int64()]
        if daily_ds.schema.names != DAILY_COLUMNS or [f.type for f in daily_ds.schema] != expected_types:
            raise ValueError("Daily schema differs")
        db.execute("CREATE TABLE exported_daily (repo_id INTEGER,event_date TEXT,event_type TEXT,event_count INTEGER)")
        for batch in daily_ds.to_batches(batch_size=10000):
            db.executemany("INSERT INTO exported_daily VALUES (?,?,?,?)",
                           ((r["repo_id"],r["event_date"].isoformat(),r["event_type"],r["event_count"]) for r in batch.to_pylist()))
        checks["daily_values"] = exact_difference(db,"daily","exported_daily",DAILY_COLUMNS)==[0,0]
        for filename, view, columns, numeric in (
            ("repo_daily_counts.csv","daily",DAILY_COLUMNS,{"repo_id","event_count"}),
            ("repo_candidates.csv","candidates",CANDIDATE_COLUMNS,{"repo_id","event_count","observed_name_count"})):
            table = "csv_" + view
            db.execute("CREATE TABLE "+table+" ("+",".join(k+(" INTEGER" if k in numeric else " TEXT") for k in columns)+")")
            with (clean_dir / filename).open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames != columns:
                    raise ValueError(f"Unexpected columns: {filename}")
                db.executemany("INSERT INTO "+table+" VALUES ("+",".join("?" for _ in columns)+")",
                               ([int(r[k]) if k in numeric else (r[k] or None) for k in columns] for r in reader))
            checks[filename] = exact_difference(db,view,table,columns)==[0,0]
        result = {"passed": all(checks.values()), "checks": checks, "counts": stats}
        if not result["passed"]:
            raise RuntimeError(f"Fragment acceptance failed: {checks}")
        return result
    finally:
        db.close()


def merge_outputs(fragments, destination, inputs, coverage, cache_mib=128, guard=lambda: None):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    db = create_db(destination / "merge.sqlite3",cache_mib)
    def progress():
        guard()
        return 0
    db.set_progress_handler(progress,1000000)
    started = time.monotonic()
    try:
        with timed(destination / "timing_dedup.json","cross_batch_dedup"):
            load_valid(db,fragments,guard)
            stats = classify(db)
            for filename, condition, reason in (
                ("conflicts.csv","g.variants>1","conflicting_payload"),
                ("duplicates.csv","g.variants=1 AND w.event_id IS NULL","duplicate_payload")):
                write_csv(destination / filename,["event_id","canonical_sha256","source_hour","source_line","batch","fragment","reason"],
                          (dict(r,reason=reason) for r in db.execute(
                              "SELECT v.event_id,v.canonical_sha256,v.source_hour,v.source_line,v.batch,v.fragment "
                              "FROM valid v JOIN groups g USING(event_id) LEFT JOIN winners w "
                              "ON v.source_hour=w.source_hour AND v.source_line=w.source_line WHERE "+condition+
                              " ORDER BY v.source_hour,v.source_line")))
            guard()
        with timed(destination / "timing_aggregate.json","final_aggregate_export"):
            count = export_events(dict_rows(db,"SELECT "+",".join(EVENT_COLUMNS)+" FROM cleaned ORDER BY source_hour,source_line"),destination)
            total = export_daily(dict_rows(db,"SELECT * FROM daily ORDER BY repo_id,event_date,event_type"),destination)
            write_csv(destination / "repo_candidates.csv",CANDIDATE_COLUMNS,dict_rows(db,"SELECT * FROM candidates ORDER BY repo_id"))
            write_csv(destination / "repo_name_history.csv",["repo_id","repo_name","first_observed_at","last_observed_at","event_count"],
                      dict_rows(db,"SELECT repo_id,repo_name,MIN(event_time) AS first_observed_at,MAX(event_time) AS last_observed_at,COUNT(*) AS event_count "
                                "FROM cleaned GROUP BY repo_id,repo_name ORDER BY repo_id,repo_name"))
            candidate_sum = db.execute("SELECT COALESCE(SUM(event_count),0) FROM candidates").fetchone()[0]
            unique = db.execute("SELECT COUNT(DISTINCT event_id) FROM cleaned").fetchone()[0]
            checks = {"valid_occurrences_reconcile": stats["valid_occurrences"] == count+stats["duplicate_occurrences_removed"]+stats["conflicting_occurrences_excluded"],
                      "event_ids_unique": unique==count==stats["final_events"], "daily_sum": total==count,"candidate_sum": candidate_sum==count}
            write_json(destination / "coverage.json",coverage)
            write_json(destination / "input_manifest.json",{"archives": inputs})
            write_csv(destination / "input_manifest.csv",["name","url","bytes","sha256"],inputs)
            guard()
        summary = {"backend":"python_sqlite", "sqlite_cache_mib":cache_mib, "counts":stats,"checks":checks,
                   "final_events":count, "daily_sum":total,"candidate_sum":candidate_sum,
                   "elapsed_seconds":time.monotonic()-started,"fragments":fragments}
        if not all(checks.values()):
            raise RuntimeError("Global merge failed conservation checks")
        write_json(destination / "summary.json",summary)
        db.commit()
        return summary
    finally:
        db.close()
