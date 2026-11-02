"""Configuration, immutable run directories and provenance shared by all stages."""
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULE_VERSION = "a-events-v1"
EVENT_COLUMNS = [
    "event_id", "event_type", "event_time", "repo_id", "repo_name", "actor_id",
    "actor_login", "event_date", "source_file", "source_line", "source_hour",
    "time_outside_file_hour", "optional_field_issues",
]


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def json_line(handle, value):
    handle.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def environment():
    packages = {}
    for name in ("pyarrow", "pyspark", "py4j"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    memory = None
    try:
        memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        pass
    if memory is None and platform.system() == "Darwin":
        try:
            result = subprocess.run(["/usr/sbin/sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                memory = int(result.stdout.strip())
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    digest = hashlib.sha256()
    for path in sorted((ROOT / "gharchive_a").glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return {"python": sys.version, "executable": sys.executable,
            "platform": platform.platform(), "cpu_count": os.cpu_count(),
            "memory_bytes": memory, "packages": packages,
            "java_home": os.environ.get("JAVA_HOME"), "code_sha256": digest.hexdigest()}


def add_input_arguments(parser):
    parser.add_argument("--config", type=Path, default=ROOT / "config/sample.json")
    parser.add_argument("--date", help="Override the UTC date, YYYY-MM-DD")
    parser.add_argument("--hours", help="Override hours, e.g. 0 or 0,1,2 or 0-23")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--allow-missing", action="store_true", help="Explicitly permit a partial archive sample")


def load_config(args):
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    cfg["date"] = args.date or cfg["date"]
    date.fromisoformat(cfg["date"])
    if args.hours:
        hours = []
        for item in args.hours.split(","):
            bounds = item.split("-")
            if len(bounds) == 1:
                hours.append(int(bounds[0]))
            elif len(bounds) == 2:
                lower, upper = map(int, bounds)
                if lower > upper:
                    raise ValueError("Hour range must be increasing")
                hours.extend(range(lower, upper + 1))
            else:
                raise ValueError("Invalid hour specification")
        cfg["hours"] = hours
    if not cfg["hours"] or any(type(h) is not int or not 0 <= h <= 23 for h in cfg["hours"]):
        raise ValueError("hours must contain integers from 0 to 23")
    cfg["hours"] = sorted(set(cfg["hours"]))
    for key in ("timeout_seconds", "max_file_bytes", "parquet_batch_rows"):
        if cfg.get(key, 0) <= 0:
            raise ValueError(f"{key} must be positive")
    if cfg.get("retries", 0) < 0:
        raise ValueError("retries must be nonnegative")
    return cfg


def expected_names(cfg):
    return [f"{cfg['date']}-{hour}.json.gz" for hour in cfg["hours"]]


def select_inputs(cfg, data_dir, allow_missing=False):
    expected = expected_names(cfg)
    files = [Path(data_dir).resolve() / name for name in expected]
    present = [path for path in files if path.is_file()]
    missing = [path.name for path in files if not path.is_file()]
    if missing and not allow_missing:
        raise FileNotFoundError(f"Missing archives: {missing}. Use --allow-missing only for an intentional partial sample.")
    if not present:
        raise FileNotFoundError("No input archives found")
    manifest = {"rule_version": RULE_VERSION, "timezone": "UTC", "date": cfg["date"],
                "expected_files": expected, "missing_files": missing,
                "observed_files": [{"name": p.name, "path": str(p), "bytes": p.stat().st_size,
                                    "sha256": sha256_file(p)} for p in present],
                "all_requested_archives_present": not missing,
                "complete_utc_day_requested": cfg["hours"] == list(range(24)),
                "capture_completeness": "not established by archive availability"}
    return present, manifest


@contextlib.contextmanager
def stage_directory(output, stage, config):
    """Never overwrite an earlier result. A failure still leaves a status file."""
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    status = {"stage": stage, "state": "running", "started_at": utc_now(),
              "rule_version": RULE_VERSION, "config": config,
              "argv": sys.argv, "environment": environment()}
    write_json(output / "stage_status.json", status)
    try:
        yield output
    except BaseException as error:
        status.update(state="failed", error=f"{type(error).__name__}: {error}")
        raise
    else:
        status["state"] = "completed"
    finally:
        status.update(finished_at=utc_now(), elapsed_seconds=round(time.perf_counter() - start, 6))
        write_json(output / "stage_status.json", status)


def write_csv(path, columns, rows):
    """Write stable headers even when there are no rows."""
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def stage_parser(description):
    parser = argparse.ArgumentParser(description=description)
    add_input_arguments(parser)
    parser.add_argument("--output", type=Path, required=True, help="New output directory; an existing directory is rejected")
    return parser
