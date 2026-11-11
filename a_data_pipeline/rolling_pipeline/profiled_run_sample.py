"""Run the normal Python pipeline while timing its existing cleaning steps."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time

PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))
import gharchive_a.clean as cleaning
from gharchive_a.cli import main_run


def install_timing():
    original_clean = cleaning.clean
    original_iter_records = cleaning.iter_records
    original_dict_rows = cleaning.dict_rows
    original_export_events = cleaning.export_events
    original_export_daily = cleaning.export_daily
    original_write_csv = cleaning.write_csv
    original_connect = sqlite3.connect
    measurement = {"spans": [], "archive_seconds": {}, "sql_statements": []}

    def add_span(name, start):
        finish = time.perf_counter()
        measurement["spans"].append({"step": name, "seconds": round(finish - start, 6)})
        return finish

    def timed_records(path):
        started = time.perf_counter()
        measurement.setdefault("first_archive_started", started)
        try:
            yield from original_iter_records(path)
        finally:
            finished = time.perf_counter()
            measurement["archive_seconds"][Path(path).name] = round(finished - started, 6)
            measurement["last_archive_finished"] = finished

    def timed_rows(db, query):
        audit = "duplicate_occurrences" in query or "conflicting_occurrences" in query
        started = time.perf_counter() if audit else None
        try:
            yield from original_dict_rows(db, query)
        finally:
            if audit:
                name = "duplicate_audit_export" if "duplicate_occurrences" in query else "conflict_audit_export"
                add_span(name, started)

    def timed_events(*args, **kwargs):
        started = time.perf_counter()
        try:
            return original_export_events(*args, **kwargs)
        finally:
            add_span("export_cleaned_events_csv_and_parquet", started)

    def timed_daily(*args, **kwargs):
        started = time.perf_counter()
        try:
            return original_export_daily(*args, **kwargs)
        finally:
            add_span("export_daily_counts_csv_and_parquet", started)

    def timed_csv(path, *args, **kwargs):
        name = Path(path).name
        started = time.perf_counter()
        if name == "hourly_quality.csv" and "candidate_export_finished" in measurement:
            measurement["spans"].append({"step": "hourly_quality_queries",
                "seconds": round(started - measurement["candidate_export_finished"], 6)})
        try:
            return original_write_csv(path, *args, **kwargs)
        finally:
            finished = add_span("write_" + name, started)
            if name == "repo_candidates.csv":
                measurement["candidate_export_finished"] = finished

    class TimedConnection(sqlite3.Connection):
        def executescript(self, script):
            started = time.perf_counter()
            if "last_archive_finished" in measurement:
                measurement["spans"].append({"step": "last_commit_and_event_id_index",
                    "seconds": round(started - measurement["last_archive_finished"], 6)})
            active = [None, started]

            def trace(statement):
                now = time.perf_counter()
                if active[0] is not None:
                    measurement["sql_statements"].append({"step": active[0], "seconds": round(now - active[1], 6)})
                match = re.search(r"CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX|VIEW)\s+(\w+)", statement, re.I)
                active[:] = [match.group(1) if match else statement.strip().split(maxsplit=1)[0], now]

            self.set_trace_callback(trace)
            try:
                return super().executescript(script)
            finally:
                finished = time.perf_counter()
                self.set_trace_callback(None)
                if active[0] is not None:
                    measurement["sql_statements"].append({"step": active[0], "seconds": round(finished - active[1], 6)})

    def timed_connect(*args, **kwargs):
        kwargs["factory"] = TimedConnection
        return original_connect(*args, **kwargs)

    def timed_clean(cfg, data_dir, output, *args, **kwargs):
        started = time.perf_counter()
        cleaning.iter_records = timed_records
        cleaning.dict_rows = timed_rows
        cleaning.export_events = timed_events
        cleaning.export_daily = timed_daily
        cleaning.write_csv = timed_csv
        sqlite3.connect = timed_connect
        try:
            result = original_clean(cfg, data_dir, output, *args, **kwargs)
        finally:
            elapsed = time.perf_counter() - started
            cleaning.iter_records = original_iter_records
            cleaning.dict_rows = original_dict_rows
            cleaning.export_events = original_export_events
            cleaning.export_daily = original_export_daily
            cleaning.write_csv = original_write_csv
            sqlite3.connect = original_connect
        archived = sum(measurement["archive_seconds"].values())
        sql_time = sum(item["seconds"] for item in measurement["sql_statements"])
        setup = measurement.get("first_archive_started", started) - started
        accounted = setup + archived + sql_time + sum(item["seconds"] for item in measurement["spans"])
        detail = {"scope": "Python clean function, including input hashing; download and inspection are separate",
                  "clock": "time.perf_counter wall time", "total_seconds": round(elapsed, 6),
                  "input_hash_and_setup_seconds": round(setup, 6),
                  "read_parse_and_sqlite_insert_seconds": round(archived, 6),
                  "per_archive_seconds": measurement["archive_seconds"],
                  "sql_statements": measurement["sql_statements"], "other_steps": measurement["spans"],
                  "remaining_seconds": round(elapsed - accounted, 6),
                  "measurement_notes": ["Archive intervals include parsing, SQLite inserts, and anomaly writes.",
                      "The event-index interval also includes the last input-file commit.",
                      "Exports include querying rows and writing all output formats.",
                      "Remaining time includes intermediate commits, final checks, and status reporting.",
                      "SQLite statement tracing runs only during the deduplication and aggregation script."],
                  "timing_helper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        (Path(output) / "timing_detail.json").write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result

    cleaning.clean = timed_clean


if __name__ == "__main__":
    install_timing()
    main_run()
