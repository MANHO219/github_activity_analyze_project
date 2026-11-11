"""Merge accepted daily results with all-valid event-ID conflict detection."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, timedelta
import csv
import heapq
from itertools import groupby
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import threading
import time

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from weekly_pipeline import DEFAULT_OUTPUT, MIN_FREE, accepted_day, read_json, save_json, size_of_tree

def index_rows(path):
    previous = None
    for batch in pq.ParquetFile(path).iter_batches(batch_size=65536):
        data = batch.to_pydict()
        for row in zip(data["event_id"], data["canonical_sha256"], data["source_hour"], data["source_line"]):
            if previous is not None and row[0] < previous:
                raise RuntimeError(f"Cross-day index is not sorted: {path}")
            previous = row[0]
            yield row


def classify_indexes(paths):
    streams = [index_rows(path) for path in paths]
    merged = heapq.merge(*streams, key=lambda row: row[0])
    removals = defaultdict(dict)
    stats = {"valid_occurrences": 0, "unique_event_ids": 0, "surviving_event_ids": 0,
             "duplicate_occurrences_removed": 0, "conflicting_event_ids": 0,
             "conflicting_occurrences_excluded": 0}
    for event_id, group in groupby(merged, key=lambda row: row[0]):
        fingerprints = set()
        per_day = {}
        count = 0
        for _, fingerprint, hour, line in group:
            day = hour[:10]
            local = per_day.setdefault(day, {"fingerprints": set(), "first": (hour, line)})
            local["fingerprints"].add(fingerprint)
            local["first"] = min(local["first"], (hour, line))
            fingerprints.add(fingerprint)
            count += 1
        stats["valid_occurrences"] += count
        stats["unique_event_ids"] += 1
        if len(fingerprints) > 1:
            stats["conflicting_event_ids"] += 1
            stats["conflicting_occurrences_excluded"] += count
            for day, local in per_day.items():
                if len(local["fingerprints"]) == 1:
                    removals[day][event_id] = (local["first"], "conflicting_payload")
        else:
            stats["surviving_event_ids"] += 1
            stats["duplicate_occurrences_removed"] += count - 1
            first = min(local["first"] for local in per_day.values())
            for day, local in per_day.items():
                if local["first"] != first:
                    removals[day][event_id] = (local["first"], "duplicate_payload")
    return stats, removals


def filter_events(source, destination, removals):
    destination.parent.mkdir(parents=True, exist_ok=False)
    if not removals:
        os.link(source, destination)
        return pq.ParquetFile(source).metadata.num_rows, 0
    values = pa.array(list(removals), type=pa.string())
    found = set()
    kept = 0
    source_file = pq.ParquetFile(source)
    with pq.ParquetWriter(destination, source_file.schema_arrow, compression="snappy") as writer:
        for batch in source_file.iter_batches(batch_size=65536):
            matched = pc.is_in(batch.column(batch.schema.get_field_index("event_id")), value_set=values)
            selected = batch.filter(matched).select(["event_id", "source_hour", "source_line"]).to_pydict()
            for event_id, hour, line in zip(selected["event_id"], selected["source_hour"], selected["source_line"]):
                original_hour = hour.isoformat().replace("+00:00", "Z")
                if (original_hour, line) != removals[event_id][0] or event_id in found:
                    raise RuntimeError(f"Unexpected duplicate/conflict row in daily output: {event_id}")
                found.add(event_id)
            clean = batch.filter(pc.invert(matched))
            if clean.num_rows:
                writer.write_batch(clean)
                kept += clean.num_rows
    if found != set(removals):
        raise RuntimeError(f"Could not find {len(set(removals) - found)} expected rows in {source}")
    return kept, len(found)


def quoted(path):
    return "'" + str(path).replace("'", "''") + "'"


def record_elapsed(timings, step, started):
    finished = time.perf_counter()
    timings[step] = round(finished - started, 6)
    print(f"{step}: {timings[step]:.2f} s", flush=True)
    return finished


def watch_disk(root, stop, stats):
    while not stop.wait(10):
        free = shutil.disk_usage(root).free
        stats["min_local_free_bytes"] = min(stats.get("min_local_free_bytes", free), free)
        temp_size = size_of_tree(root / "duckdb_temp")
        stats["max_merge_temp_bytes"] = max(stats.get("max_merge_temp_bytes", 0), temp_size)
        if free < MIN_FREE:
            stats["stop_reason"] = "Local free space fell below 30 GiB"
            os.kill(os.getpid(), signal.SIGINT)
            return


def make_outputs(days, destination, args):
    overall_started = time.perf_counter()
    timings = {}
    accepted = [accepted_day(args.root / day) for day in days]
    if any(value is None for value in accepted):
        raise RuntimeError("Every selected date must pass daily acceptance")
    code_versions = set()
    rule_versions = set()
    for info in accepted:
        if "code_sha256" in info:
            code_versions.add(info["code_sha256"])
            rule_versions.add(info["rule_version"])
        else:
            status = read_json(Path(info["attempt"]) / "python/stage_status.json")
            code_versions.add(status["environment"]["code_sha256"])
            rule_versions.add(status["rule_version"])
    if len(code_versions) != 1 or len(rule_versions) != 1:
        raise RuntimeError("Daily data were produced with different code or cleaning rules")
    record_elapsed(timings, "verify_accepted_inputs", overall_started)
    destination.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    disk_stats = {"min_local_free_bytes": shutil.disk_usage(destination).free, "max_merge_temp_bytes": 0}
    if disk_stats["min_local_free_bytes"] < MIN_FREE:
        raise RuntimeError("Local free space is below 30 GiB")
    stop = threading.Event()
    watcher = threading.Thread(target=watch_disk, args=(destination, stop, disk_stats), daemon=True)
    watcher.start()
    try:
        print("Comparing sorted all-valid event indexes", flush=True)
        index_paths = [a["retained_files"]["valid_index"]["path"] for a in accepted]
        phase_started = time.perf_counter()
        stats, removals = classify_indexes(index_paths)
        if stats["valid_occurrences"] != sum(a["valid_before_dedup"] for a in accepted):
            raise RuntimeError("Index records do not reconcile with daily acceptance")
        phase_started = record_elapsed(timings, "classify_event_ids", phase_started)
        event_files, event_count, removed_count = [], 0, 0
        with (destination / "cross_day_removals.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["source_day", "event_id", "source_hour", "source_line", "reason"])
            for day in days:
                for event_id, (location, reason) in removals.get(day, {}).items():
                    writer.writerow([day, event_id, location[0], location[1], reason])
        for day, info in zip(days, accepted):
            source = Path(info["retained_files"]["events"]["path"])
            target = destination / "events_clean" / day / "part-00000.parquet"
            count, removed = filter_events(source, target, removals.get(day, {}))
            if count + removed != info["cleaned_events"]:
                raise RuntimeError(f"Event count mismatch for {day}")
            event_count += count
            removed_count += removed
            event_files.append(str(target.resolve()))
        if event_count != stats["surviving_event_ids"]:
            raise RuntimeError("Final rows do not match surviving IDs from all-valid indexes")
        phase_started = record_elapsed(timings, "write_event_partitions_and_removals", phase_started)

        with (destination / "input_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["source_day", "name", "url", "bytes", "sha256"])
            writer.writeheader()
            for day, info in zip(days, accepted):
                manifest = read_json(info["input_manifest"])
                for archive in manifest["observed_files"]:
                    writer.writerow({"source_day": day, "name": archive["name"],
                                     "url": "https://data.gharchive.org/" + archive["name"],
                                     "bytes": archive["bytes"], "sha256": archive["sha256"]})
        coverage = {"requested_days": days, "requested_hours": 24 * len(days),
                    "verified_hours": sum(a["archive_count"] for a in accepted),
                    "missing_source_hours": [],
                    "event_dates_use_utc_event_time": True,
                    "archive_presence_does_not_prove_all_public_activity_was_captured": True}
        if coverage["requested_hours"] != coverage["verified_hours"]:
            raise RuntimeError("Hourly coverage does not match requested dates")
        save_json(destination / "coverage.json", coverage)
        phase_started = record_elapsed(timings, "write_coverage_and_manifest", phase_started)

        print("Validating event ID uniqueness and writing aggregate tables", flush=True)
        scratch = destination / "duckdb_temp"
        scratch.mkdir()
        db = duckdb.connect()
        try:
            db.execute("SET threads=2")
            db.execute("SET memory_limit='3GB'")
            db.execute("SET max_temp_directory_size='12GB'")
            db.execute("SET temp_directory=" + quoted(scratch.resolve()))
            file_list = ", ".join(quoted(path) for path in event_files)
            db.execute(f"CREATE TEMP VIEW events AS SELECT * FROM read_parquet([{file_list}])")
            phase_started = record_elapsed(timings, "initialize_duckdb", phase_started)
            counted, unique = db.execute("SELECT COUNT(*), COUNT(DISTINCT event_id) FROM events").fetchone()
            if counted != event_count or unique != event_count:
                raise RuntimeError(f"Final event IDs are not unique: {counted} rows, {unique} IDs")
            phase_started = record_elapsed(timings, "verify_unique_event_ids", phase_started)
            daily = destination / "repo_daily_counts.parquet"
            db.execute("COPY (SELECT repo_id, event_date, event_type, COUNT(*)::BIGINT AS event_count "
                       "FROM events GROUP BY repo_id, event_date, event_type) TO " + quoted(daily) +
                       " (FORMAT PARQUET, COMPRESSION ZSTD)")
            phase_started = record_elapsed(timings, "write_daily_activity_parquet", phase_started)
            candidates = destination / "repo_candidates.csv"
            db.execute("COPY (SELECT repo_id, "
                       "arg_max(repo_name, struct_pack(t := event_time, h := source_hour, l := source_line)) AS repo_name, "
                       "MIN(event_time) AS first_observed_at, MAX(event_time) AS last_observed_at, "
                       "COUNT(*)::BIGINT AS event_count, COUNT(DISTINCT repo_name)::BIGINT AS observed_name_count "
                       "FROM events GROUP BY repo_id ORDER BY repo_id) TO " + quoted(candidates) +
                       " (HEADER, FORMAT CSV)")
            phase_started = record_elapsed(timings, "write_repository_candidates_csv", phase_started)
            daily_rows, daily_sum = db.execute("SELECT COUNT(*), COALESCE(SUM(event_count), 0) FROM read_parquet(?)", [str(daily)]).fetchone()
            candidate_rows, candidate_sum = db.execute("SELECT COUNT(*), COALESCE(SUM(event_count), 0) FROM read_csv_auto(?, header=true)", [str(candidates)]).fetchone()
            if daily_sum != event_count or candidate_sum != event_count:
                raise RuntimeError("Daily or candidate counts do not reconcile with final events")
            record_elapsed(timings, "verify_exported_counts", phase_started)
        finally:
            db.close()
        if not any(scratch.iterdir()):
            scratch.rmdir()
        input_hashes = {day: {name: info["retained_files"][name]["sha256"]
                              for name in ("events", "daily", "valid_index")}
                        for day, info in zip(days, accepted)}
        finished = time.perf_counter()
        summary = {"days": days, "input_hashes": input_hashes,
                   "code_sha256": next(iter(code_versions)),
                   "rule_version": next(iter(rule_versions)),
                   "checks": {"complete_hourly_coverage": True,
                    "all_valid_index_counts_match": True, "event_ids_unique": True,
                    "daily_counts_reconcile": True, "candidate_counts_reconcile": True},
                   "index_counts": stats, "cross_day_daily_rows_removed": removed_count,
                   "final_events": event_count, "daily_rows": daily_rows, "daily_sum": daily_sum,
                   "candidate_repositories": candidate_rows, "candidate_sum": candidate_sum,
                   "elapsed_seconds": round(finished - started, 2),
                   "total_wall_seconds": round(finished - overall_started, 6),
                   "timings_seconds": timings,
                   "environment": {"python": sys.version.split()[0], "pyarrow": pa.__version__,
                                   "duckdb": duckdb.__version__, "duckdb_threads": 2,
                                   "duckdb_memory_limit": "3GB", "duckdb_max_temp_size": "12GB"},
                   **disk_stats,
                   "files": {"events": "events_clean/", "daily": daily.name,
                             "candidates": candidates.name, "coverage": "coverage.json",
                             "input_manifest": "input_manifest.csv", "removals": "cross_day_removals.csv"}}
        save_json(destination / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    finally:
        stop.set()
        watcher.join(timeout=12)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    current, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if current > end:
        raise ValueError("Start date must not be later than end date")
    days = []
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    make_outputs(days, args.output, args)


if __name__ == "__main__":
    main()
