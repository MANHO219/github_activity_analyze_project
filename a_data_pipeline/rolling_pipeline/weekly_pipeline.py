"""Run and verify one UTC day at a time for the January 2024 rolling pilot.

An accepted day retains its event table, daily table, and all-valid event index.
Run artifacts are stored separately from these shared handoff scripts.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import date, timedelta

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


PIPELINE = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PIPELINE / "runs/weekly_20240115_20240121"
DEFAULT_VOLUME = Path("/Volumes/T7 4 Mac")
DEFAULT_RAW = DEFAULT_VOLUME / "cs5488/gharchive/raw"
GIB = 1024**3
MIN_FREE = 30 * GIB
DAY_BUDGET = 12 * GIB
INDEX_SCHEMA = pa.schema([
    ("event_id", pa.string()),
    ("canonical_sha256", pa.binary(32)),
    ("source_hour", pa.string()),
    ("source_line", pa.int64()),
])


def save_json(path, obj):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def volume_check(volume, raw_root):
    volume = Path(volume).resolve()
    raw_root = Path(raw_root).resolve()
    if not os.path.ismount(volume):
        raise RuntimeError(f"Required volume is not mounted: {volume}")
    if not raw_root.is_relative_to(volume) or raw_root == volume:
        raise RuntimeError(f"Raw directory must be inside the mounted volume: {raw_root}")
    return os.stat(volume).st_dev


def size_of_tree(path):
    total = 0
    for parent, _, files in os.walk(path):
        for name in files:
            try:
                total += (Path(parent) / name).stat().st_size
            except FileNotFoundError:
                pass
    return total


def check_space(output, day_dir, raw_volume=None):
    local_free = shutil.disk_usage(output).free
    day_bytes = size_of_tree(day_dir)
    if local_free < MIN_FREE:
        raise RuntimeError(f"Local free space fell below 30 GiB: {local_free}")
    if day_bytes > DAY_BUDGET:
        raise RuntimeError(f"Daily workspace exceeded 12 GiB: {day_bytes}")
    external_free = shutil.disk_usage(raw_volume).free if raw_volume else None
    if external_free is not None and external_free < GIB:
        raise RuntimeError(f"External free space fell below 1 GiB: {external_free}")
    return local_free, day_bytes, external_free


def next_attempt(day):
    number = 1
    while (day / f"attempt-{number:02d}").exists():
        number += 1
    return number


def completed_attempt(day):
    for attempt in sorted(day.glob("attempt-*"), reverse=True):
        summary = attempt / "run_summary.json"
        if summary.is_file() and read_json(summary).get("state") == "completed":
            return attempt
    return None


def preserve_partial_files(day, raw_dir):
    """Keep failed download evidence while freeing the retry filenames."""
    log_path = day / "preserved_partials.json"
    moves = read_json(log_path) if log_path.exists() else []
    manifests = sorted(day.glob("attempt-*/download/download_manifest.json"), reverse=True)
    for manifest_path in manifests:
        attempt_name = manifest_path.parents[1].name
        for entry in read_json(manifest_path).get("files", []):
            for request in entry.get("attempts", []):
                if not request.get("partial_file"):
                    continue
                source = Path(request["partial_file"])
                if not source.exists():
                    continue
                if (source.is_symlink() or source.parent.resolve() != raw_dir.resolve()
                        or not source.name.startswith(day.name + "-") or not source.name.endswith(".part")):
                    raise RuntimeError(f"Unexpected failed partial path: {source}")
                target = source.with_name(source.name[:-5] + f".saved-{attempt_name}.part")
                if target.exists():
                    if os.stat(source).st_ino != os.stat(target).st_ino:
                        raise RuntimeError(f"Cannot preserve partial without overwriting: {target}")
                else:
                    os.link(source, target)
                move = {"original": str(source), "preserved": str(target),
                        "bytes": target.stat().st_size, "manifest": str(manifest_path)}
                if move not in moves:
                    moves.append(move)
                    save_json(log_path, moves)
                source.unlink()


def run_daily(day_string, output, volume, raw_root):
    day = output / day_string
    day.mkdir(parents=True, exist_ok=True)
    existing = completed_attempt(day)
    if existing:
        print(f"{day_string}: using completed attempt {existing.name}", flush=True)
        return existing

    device = None
    if day_string == "2024-01-15":
        raw_dir = PIPELINE / "data/raw"
        skip = ["--skip-download"]
    else:
        device = volume_check(volume, raw_root)
        raw_dir = raw_root / day_string
        raw_dir.mkdir(parents=True, exist_ok=True)
        if raw_dir.resolve().parent != raw_root.resolve() or os.stat(raw_dir).st_dev != device:
            raise RuntimeError(f"Daily raw directory is not on the required volume: {raw_dir}")
        if shutil.disk_usage(volume).free < 5 * GIB:
            raise RuntimeError("External volume has less than 5 GiB free before downloading")
        preserve_partial_files(day, raw_dir)
        skip = []
    check_space(output, day, volume if device is not None else None)
    number = next_attempt(day)
    attempt = day / f"attempt-{number:02d}"
    command = [sys.executable, str(Path(__file__).with_name("profiled_run_sample.py")),
               "--date", day_string, "--hours", "0-23", "--data-dir", str(raw_dir),
               "--run-dir", str(attempt), *skip]
    print(f"{day_string}: starting {attempt.name}", flush=True)
    started = time.monotonic()
    stats = {"min_local_free_bytes": None, "min_external_free_bytes": None,
             "max_day_output_bytes": 0, "command": command}
    with (day / f"console-{number:02d}.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                if device is not None and volume_check(volume, raw_root) != device:
                    raise RuntimeError("The external volume changed during processing")
                local, used, external = check_space(output, day, volume if device is not None else None)
                stats["min_local_free_bytes"] = min(stats["min_local_free_bytes"] or local, local)
                stats["max_day_output_bytes"] = max(stats["max_day_output_bytes"], used)
                if external is not None:
                    stats["min_external_free_bytes"] = min(stats["min_external_free_bytes"] or external, external)
                stats["elapsed_seconds"] = round(time.monotonic() - started, 2)
                save_json(day / f"disk-monitor-{number:02d}.json", stats)
                time.sleep(15)
        except BaseException as error:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            stats["stop_reason"] = str(error)
            save_json(day / f"disk-monitor-{number:02d}.json", stats)
            raise
        code = process.wait()
    stats.update(exit_code=code, elapsed_seconds=round(time.monotonic() - started, 2))
    save_json(day / f"disk-monitor-{number:02d}.json", stats)
    if code:
        raise RuntimeError(f"{day_string} failed with exit code {code}; see {day / f'console-{number:02d}.log'}")
    return attempt


def one_parquet(directory):
    files = sorted(Path(directory).glob("*.parquet"))
    if len(files) != 1:
        raise RuntimeError(f"Expected one Parquet file in {directory}, found {len(files)}")
    return files[0]


def accepted_day(day):
    marker = day / "accepted.json"
    if not marker.exists():
        return None
    value = read_json(marker)
    for item in value["retained_files"].values():
        file = Path(item["path"])
        if not file.is_file() or file.stat().st_size != item["bytes"] or sha256(file) != item["sha256"]:
            raise RuntimeError(f"Accepted output has changed or disappeared: {file}")
    return value


def validate_input_snapshots(attempt):
    attempt = Path(attempt)
    manifest = read_json(attempt / "python/input_manifest.json")
    fingerprints = {row["name"]: (row["bytes"], row["sha256"]) for row in manifest["observed_files"]}
    inspected = read_json(attempt / "inspection/input_manifest.json")
    inspection_fingerprints = {row["name"]: (row["bytes"], row["sha256"]) for row in inspected["observed_files"]}
    if fingerprints != inspection_fingerprints:
        raise RuntimeError("Input archives changed between inspection and cleaning")
    download_path = attempt / "download/download_manifest.json"
    if download_path.exists():
        download = read_json(download_path)
        downloaded = {row["name"]: (row["bytes"], row["sha256"]) for row in download["files"]}
        if not download["all_requested_archives_verified"] or fingerprints != downloaded:
            raise RuntimeError("Input archives changed between download and cleaning")


def accept_day(day_string, output):
    day = output / day_string
    existing = accepted_day(day)
    if existing:
        print(f"{day_string}: accepted outputs verified", flush=True)
        return existing
    attempt = completed_attempt(day)
    if not attempt:
        raise RuntimeError(f"No completed run for {day_string}")
    clean = attempt / "python"
    quality = read_json(clean / "quality_summary.json")
    manifest = read_json(clean / "input_manifest.json")
    expected = {f"{day_string}-{h}.json.gz" for h in range(24)}
    observed = {row["name"] for row in manifest["observed_files"]}
    if observed != expected or manifest["missing_files"] or not all(quality["checks"].values()):
        raise RuntimeError(f"Coverage or cleaning checks failed for {day_string}")
    validate_input_snapshots(attempt)
    if read_json(attempt / "inspection/stage_status.json")["state"] != "completed":
        raise RuntimeError("Inspection was not completed")
    if read_json(clean / "stage_status.json")["state"] != "completed":
        raise RuntimeError("Python cleaning was not completed")

    event_file = one_parquet(clean / "events_clean.parquet")
    daily_file = one_parquet(clean / "repo_daily_counts.parquet")
    sqlite_path = clean / "working.sqlite3"
    db = sqlite3.connect(sqlite_path.resolve().as_uri() + "?mode=ro", uri=True)
    started = time.monotonic()
    try:
        valid_count = db.execute("SELECT COUNT(*) FROM valid_events").fetchone()[0]
        if valid_count != quality["line_status_counts"].get("valid", 0):
            raise RuntimeError("SQLite valid count differs from quality report")
        cleaned_cursor = db.execute("SELECT event_id, source_file, source_line FROM cleaned_events ORDER BY sequence")
        event_rows = 0
        for batch in pq.ParquetFile(event_file).iter_batches(batch_size=65536):
            values = batch.select(["event_id", "source_file", "source_line"]).to_pydict()
            for actual in zip(values["event_id"], values["source_file"], values["source_line"]):
                if actual != cleaned_cursor.fetchone():
                    raise RuntimeError(f"Event Parquet differs from cleaned SQLite at row {event_rows}")
                event_rows += 1
            check_space(output, day)
        if cleaned_cursor.fetchone() is not None or event_rows != quality["cleaned_events"]:
            raise RuntimeError("Event Parquet count differs from cleaned SQLite")
        daily_rows = daily_total = 0
        for batch in pq.ParquetFile(daily_file).iter_batches(batch_size=65536):
            daily_rows += batch.num_rows
            daily_total += pc.sum(batch.column(batch.schema.get_field_index("event_count"))).as_py() or 0
        if daily_total != event_rows:
            raise RuntimeError("Daily Parquet counts do not sum to the event table")
        if day_string == "2024-01-15" and (event_rows, daily_rows, daily_total) != (5528300, 1340785, 5528300):
            raise RuntimeError("The reproduced baseline differs from the documented baseline")

        number = 1
        while (day / f"index-{number:02d}.parquet").exists() or (day / f"index-{number:02d}.partial").exists():
            number += 1
        partial = day / f"index-{number:02d}.partial"
        index = day / f"index-{number:02d}.parquet"
        cursor = db.execute("SELECT event_id, canonical_sha256, source_hour, source_line FROM valid_events ORDER BY event_id, sequence")
        rows = 0
        with pq.ParquetWriter(partial, INDEX_SCHEMA, compression="zstd") as writer:
            while True:
                batch = cursor.fetchmany(65536)
                if not batch:
                    break
                arrays = [pa.array([row[0] for row in batch], type=pa.string()),
                          pa.array([bytes.fromhex(row[1]) for row in batch], type=pa.binary(32)),
                          pa.array([row[2] for row in batch], type=pa.string()),
                          pa.array([row[3] for row in batch], type=pa.int64())]
                writer.write_table(pa.Table.from_arrays(arrays, schema=INDEX_SCHEMA))
                rows += len(batch)
                check_space(output, day)
        if rows != valid_count or pq.ParquetFile(partial).metadata.num_rows != valid_count:
            raise RuntimeError("Cross-day index count differs from valid events")
        partial.replace(index)
    finally:
        db.close()

    retained = {}
    for name, path in (("events", event_file), ("daily", daily_file), ("valid_index", index)):
        retained[name] = {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": sha256(path)}
    clean_status = read_json(clean / "stage_status.json")
    result = {"date": day_string, "attempt": str(attempt.resolve()), "archive_count": len(observed),
              "rule_version": manifest["rule_version"],
              "code_sha256": clean_status["environment"]["code_sha256"],
              "valid_before_dedup": valid_count, "cleaned_events": event_rows,
              "daily_rows": daily_rows, "daily_sum": daily_total,
              "index_rows": rows, "input_manifest": str((clean / 'input_manifest.json').resolve()),
              "quality_summary": str((clean / 'quality_summary.json').resolve()),
              "validation_and_index_seconds": round(time.monotonic() - started, 2),
              "retained_files": retained}
    save_json(day / "accepted.json", result)
    print(f"{day_string}: accepted {event_rows:,} events, {daily_rows:,} daily rows", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--volume", type=Path, default=DEFAULT_VOLUME)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW)
    args = parser.parse_args()
    current, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if current > end:
        raise ValueError("Start date must not be later than end date")
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / ".weekly_pipeline.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f"Another daily pipeline is running for {args.output}") from None
        while current <= end:
            day = current.isoformat()
            if accepted_day(args.output / day):
                print(f"{day}: already accepted", flush=True)
            else:
                run_daily(day, args.output, args.volume, args.raw_root)
                accept_day(day, args.output)
            current += timedelta(days=1)


if __name__ == "__main__":
    main()
