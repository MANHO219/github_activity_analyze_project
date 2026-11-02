"""Streaming reference implementation with retained SQLite staging data.

Deduplication is disk-backed. If one event ID has multiple full-event hashes,
all occurrences are held out for review rather than choosing a winner.
"""
from collections import Counter
import json
import sqlite3

from .common import EVENT_COLUMNS, json_line, select_inputs, stage_directory, write_csv, write_json
from .export import export_daily, export_events
from .records import iter_records


def dict_rows(db, query):
    for row in db.execute(query):
        yield dict(row)


def clean(cfg, data_dir, output, allow_missing=False, parquet=True):
    if parquet:
        import pyarrow  # Fail before creating outputs if the dependency is missing.
    files, manifest = select_inputs(cfg, data_dir, allow_missing)
    counts, reasons, optional, file_counts = Counter(), Counter(), Counter(), []
    with stage_directory(output, "python_clean", cfg) as out:
        write_json(out / "input_manifest.json", manifest)
        db = sqlite3.connect(out / "working.sqlite3")
        db.row_factory = sqlite3.Row
        integer_fields = {"repo_id", "actor_id", "source_line", "time_outside_file_hour"}
        fields = ", ".join(f"{key} {'INTEGER' if key in integer_fields else 'TEXT'}" for key in EVENT_COLUMNS)
        db.execute(f"CREATE TABLE valid_events (sequence INTEGER PRIMARY KEY, canonical_sha256 TEXT NOT NULL, {fields})")
        insert = f"INSERT INTO valid_events (canonical_sha256, {', '.join(EVENT_COLUMNS)}) VALUES ({', '.join('?' for _ in range(len(EVENT_COLUMNS) + 1))})"
        try:
            with (out / "rejected_records.jsonl").open("w", encoding="utf-8") as rejected, (out / "flagged_records.jsonl").open("w", encoding="utf-8") as flagged:
                for path in files:
                    local = Counter()
                    for record in iter_records(path):
                        status = record["status"]
                        counts[status] += 1
                        local[status] += 1
                        if status == "valid":
                            values = [record["canonical_sha256"]]
                            for key in EVENT_COLUMNS:
                                value = record.get(key)
                                if key == "optional_field_issues":
                                    value = json.dumps(value, ensure_ascii=False)
                                values.append(value)
                            db.execute(insert, values)
                            optional.update(record["optional_field_issues"])
                            if record["optional_field_issues"] or record["time_outside_file_hour"]:
                                json_line(flagged, {key: record.get(key) for key in ("event_id", "source_file", "source_line", "optional_field_issues", "time_outside_file_hour")})
                            if counts["valid"] % 4096 == 0:
                                db.commit()
                        elif status != "blank":
                            reasons[record["reason"]] += 1
                            json_line(rejected, record)
                    db.commit()
                    file_counts.append({"source_file": path.name, "blank_lines": local["blank"],
                                        "nonempty_lines": local["valid"] + local["invalid"] + local["parse_error"],
                                        "parse_errors": local["parse_error"], "invalid_records": local["invalid"],
                                        "valid_before_dedup": local["valid"]})
            db.execute("CREATE INDEX event_id_index ON valid_events(event_id)")
            db.executescript("""
                CREATE TABLE event_groups AS
                SELECT event_id, COUNT(*) AS occurrences, COUNT(DISTINCT canonical_sha256) AS variants,
                       MIN(sequence) AS first_sequence
                FROM valid_events GROUP BY event_id;
                CREATE UNIQUE INDEX group_id_index ON event_groups(event_id);
                CREATE TABLE cleaned_events AS
                SELECT v.* FROM valid_events v JOIN event_groups g ON v.sequence=g.first_sequence WHERE g.variants=1;
                CREATE UNIQUE INDEX cleaned_id_index ON cleaned_events(event_id);
                CREATE INDEX cleaned_repo_time_index ON cleaned_events(repo_id, event_time DESC, sequence DESC);
                CREATE VIEW duplicate_occurrences AS
                SELECT v.* FROM valid_events v JOIN event_groups g USING(event_id)
                WHERE g.variants=1 AND v.sequence!=g.first_sequence;
                CREATE VIEW conflicting_occurrences AS
                SELECT v.* FROM valid_events v JOIN event_groups g USING(event_id) WHERE g.variants>1;
                CREATE TABLE daily_counts AS
                SELECT repo_id, event_date, event_type, COUNT(*) AS event_count
                FROM cleaned_events GROUP BY repo_id, event_date, event_type;
            """)
            for view, filename in (("duplicate_occurrences", "duplicate_records.jsonl"), ("conflicting_occurrences", "conflicting_records.jsonl")):
                with (out / filename).open("w", encoding="utf-8") as handle:
                    for row in dict_rows(db, f"SELECT * FROM {view} ORDER BY sequence"):
                        row.pop("sequence")
                        row["optional_field_issues"] = json.loads(row["optional_field_issues"])
                        json_line(handle, row)
            cleaned = export_events(dict_rows(db, f"SELECT {', '.join(EVENT_COLUMNS)} FROM cleaned_events ORDER BY sequence"),
                                    out, cfg["clean_preview_rows"], cfg["parquet_batch_rows"], parquet)
            grouped_total = export_daily(dict_rows(db, "SELECT * FROM daily_counts ORDER BY repo_id, event_date, event_type"), out, parquet)
            names_query = """SELECT repo_id, repo_name, MIN(event_time) AS first_observed_at,
                             MAX(event_time) AS last_observed_at, COUNT(*) AS event_count
                             FROM cleaned_events GROUP BY repo_id, repo_name ORDER BY repo_id, repo_name"""
            write_csv(out / "repo_name_history.csv", ["repo_id", "repo_name", "first_observed_at", "last_observed_at", "event_count"], dict_rows(db, names_query))
            candidate_query = """SELECT c.repo_id,
                (SELECT n.repo_name FROM cleaned_events n WHERE n.repo_id=c.repo_id AND n.repo_name IS NOT NULL
                 ORDER BY n.event_time DESC, n.sequence DESC LIMIT 1) AS repo_name,
                MIN(c.event_time) AS first_observed_at, MAX(c.event_time) AS last_observed_at,
                COUNT(*) AS event_count, COUNT(DISTINCT c.repo_name) AS observed_name_count
                FROM cleaned_events c GROUP BY c.repo_id ORDER BY c.repo_id"""
            write_csv(out / "repo_candidates.csv", ["repo_id", "repo_name", "first_observed_at", "last_observed_at", "event_count", "observed_name_count"], dict_rows(db, candidate_query))
            for row in file_counts:
                for view, key in (("cleaned_events", "cleaned_events"), ("duplicate_occurrences", "duplicates_removed"), ("conflicting_occurrences", "conflict_occurrences_excluded")):
                    row[key] = db.execute(f"SELECT COUNT(*) FROM {view} WHERE source_file=?", (row["source_file"],)).fetchone()[0]
                row["time_outside_file_hour_before_dedup"] = db.execute(
                    "SELECT COALESCE(SUM(time_outside_file_hour), 0) FROM valid_events WHERE source_file=?", (row["source_file"],)).fetchone()[0]
                row["time_outside_file_hour_clean"] = db.execute(
                    "SELECT COALESCE(SUM(time_outside_file_hour), 0) FROM cleaned_events WHERE source_file=?", (row["source_file"],)).fetchone()[0]
            write_csv(out / "hourly_quality.csv", list(file_counts[0]), file_counts)
            duplicates = db.execute("SELECT COUNT(*) FROM duplicate_occurrences").fetchone()[0]
            conflicts = db.execute("SELECT COUNT(*) FROM conflicting_occurrences").fetchone()[0]
            conflict_ids = db.execute("SELECT COUNT(*) FROM event_groups WHERE variants>1").fetchone()[0]
            checks = {"valid_count_reconciles": counts["valid"] == cleaned + duplicates + conflicts,
                      "grouped_count_reconciles": grouped_total == cleaned,
                      "clean_ids_unique": db.execute("SELECT COUNT(DISTINCT event_id) FROM cleaned_events").fetchone()[0] == cleaned}
            summary = {"rule_version": manifest["rule_version"], "engine": "python_sqlite", "line_status_counts": dict(counts),
                       "nonempty_lines": counts["valid"] + counts["invalid"] + counts["parse_error"],
                       "cleaned_events": cleaned, "duplicates_removed": duplicates,
                       "conflicting_ids": conflict_ids, "conflict_occurrences_excluded": conflicts,
                       "conflict_policy": "exclude all occurrences of a conflicting event ID until reviewed",
                       "rejection_reasons": dict(reasons), "optional_issues_before_dedup": dict(optional),
                       "time_outside_file_hour_before_dedup": db.execute("SELECT COALESCE(SUM(time_outside_file_hour), 0) FROM valid_events").fetchone()[0],
                       "time_outside_file_hour_clean": db.execute("SELECT COALESCE(SUM(time_outside_file_hour), 0) FROM cleaned_events").fetchone()[0],
                       "clean_event_types": {r[0]: r[1] for r in db.execute("SELECT event_type, COUNT(*) FROM cleaned_events GROUP BY event_type")},
                       "clean_unique_repos": db.execute("SELECT COUNT(DISTINCT repo_id) FROM cleaned_events").fetchone()[0],
                       "grouped_event_count_sum": grouped_total, "checks": checks, "coverage": manifest,
                       "formats": ["csv.gz", "parquet"] if parquet else ["csv.gz"]}
            write_json(out / "quality_summary.json", summary)
            db.commit()
            if not all(checks.values()):
                raise RuntimeError("Internal count reconciliation failed; outputs are not ready for handoff")
        finally:
            db.close()
    return summary
