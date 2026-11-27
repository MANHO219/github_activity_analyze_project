"""Portable planning, provenance, locks and strictly scoped raw-file cleanup."""
from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import time
import threading
from datetime import datetime, timedelta, timezone

from gharchive_a.common import ROOT, RULE_VERSION, sha256_file, utc_now, write_json

PROJECT = ROOT.parent
GIB = 1024**3
_HELD_LOCKS = set()
_HELD_LOCKS_GUARD = threading.Lock()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        if len(value) != 10:
            raise ValueError("A time must include an explicit timezone; dates mean midnight UTC")
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    if parsed.minute or parsed.second or parsed.microsecond:
        raise ValueError("Source archive boundaries must be whole UTC hours")
    return parsed


def make_plan(start, end, batch_hours):
    start, end = parse_time(start), parse_time(end)
    if start >= end or type(batch_hours) is not int or batch_hours <= 0:
        raise ValueError("Require start < end and a positive integer batch-hours")
    batches = []
    cursor = start
    while cursor < end:
        finish = min(cursor + timedelta(hours=batch_hours), end)
        hours = [cursor + timedelta(hours=i) for i in range(int((finish-cursor).total_seconds() // 3600))]
        batches.append({"id": cursor.strftime("%Y%m%dT%H%MZ") + "_" + finish.strftime("%Y%m%dT%H%MZ"),
                        "start": stamp(cursor), "end": stamp(finish),
                        "archives": [f"{h:%Y-%m-%d}-{h.hour}.json.gz" for h in hours]})
        cursor = finish
    return {"start": stamp(start), "end": stamp(end), "interval": "[start,end)",
            "selection": "source archive hour; event timestamps are not filtered",
            "batch_hours": batch_hours, "batches": batches}


def fragments(batch, cfg):
    days = {}
    for name in batch["archives"]:
        day, hour = name.removesuffix(".json.gz").rsplit("-", 1)
        days.setdefault(day, []).append(int(hour))
    return [dict(cfg, date=day, hours=hours) for day, hours in days.items()]


def code_identity():
    """New version identity; never rewrite the historical LF hash manifest."""
    files = list((ROOT / "gharchive_a").glob("*.py"))
    files += list((ROOT / "rolling_pipeline").glob("batch_*.py"))
    files += [PROJECT / "d_parallel_experiments/scripts" / name for name in
              ("run_batch_pipeline.py", "spark_batch_job.py", "verify_results.py", "summarize_results.py")]
    hashes = {str(p.relative_to(PROJECT)).replace("\\", "/"):
              hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in sorted(files)}
    return {"rule_version": RULE_VERSION, "source_sha256_lf": hashes,
            "sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}


@contextlib.contextmanager
def exclusive_lock(path):
    """OS advisory lock: process death releases it; stale files do not block resumes.

    All cooperating runs lock output AND raw roots, so another run cannot read
    an archive while this runner deletes it. External readers must use retain.
    """
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    # POSIX record locks are process-scoped. Reject re-entry BEFORE opening a
    # second descriptor: closing it could release this process's existing lock.
    key = (os.getpid(), str(path))
    with _HELD_LOCKS_GUARD:
        if key in _HELD_LOCKS:
            raise RuntimeError(f"Another pipeline holds {path}")
        _HELD_LOCKS.add(key)
    try:
        with path.open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    # flock on an NFS client is translated to POSIX locks, but
                    # local flock on the server is a separate lock domain.
                    # Use the same POSIX protocol on server and clients.
                    fcntl.lockf(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in (errno.EACCES, errno.EAGAIN):
                    raise RuntimeError(f"Another pipeline holds {path}") from error
                raise
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.lockf(handle, fcntl.LOCK_UN)
    finally:
        with _HELD_LOCKS_GUARD:
            _HELD_LOCKS.discard(key)


@contextlib.contextmanager
def timed(path, stage, **details):
    started = time.monotonic()
    record = dict(stage=stage, started_at=utc_now(), state="running", parent="invocation", **details)
    write_json(path, record)
    try:
        yield record
    except BaseException as error:
        record.update(state="error", exit_code=1, error=f"{type(error).__name__}: {error}")
        raise
    else:
        record.update(state="completed", exit_code=0)
    finally:
        record.update(finished_at=utc_now(), elapsed_seconds=time.monotonic()-started)
        write_json(path, record)


def tree_bytes(root):
    """Sample a changing tree without treating removed Spark temp dirs as failure.

    A directory can disappear after it is discovered, including while opening
    its iterator. Only missing paths are tolerated; access and I/O failures must
    still propagate so a broken space check cannot silently report zero usage.
    """
    total = 0
    pending = [Path(root)]
    while pending:
        folder = pending.pop()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(Path(entry.path))
                        elif entry.is_file():
                            total += entry.stat().st_size
                    except FileNotFoundError:
                        pass
        except FileNotFoundError:
            # Covers directories removed between discovery and enumeration too.
            pass
    return total


def check_space(raw, output, minimum, workspace=None, budget=None):
    for folder in {Path(raw), Path(output)}:
        if shutil.disk_usage(folder).free < minimum:
            raise RuntimeError(f"Free space below configured reserve: {folder}")
    if workspace is not None and budget is not None and tree_bytes(workspace) > budget:
        raise RuntimeError(f"Workspace exceeds configured budget: {workspace}")


@contextlib.contextmanager
def monitor_space(raw, output, workspace, minimum, budget):
    """Sample active stages too, including existing Python download/inspect code."""
    stop = threading.Event()
    stats = {"sample_interval_seconds":1,"minimum_free_bytes":None,"maximum_workspace_bytes":0}

    def sample():
        used = tree_bytes(workspace)
        free = min(shutil.disk_usage(raw).free,shutil.disk_usage(output).free)
        stats["minimum_free_bytes"] = min(stats["minimum_free_bytes"] or free,free)
        stats["maximum_workspace_bytes"] = max(stats["maximum_workspace_bytes"],used)
        check_space(raw,output,minimum,workspace,budget)

    sample()

    def watch():
        while not stop.wait(1):
            try:
                sample()
            except Exception as error:
                stats["stop_reason"] = str(error)
                return

    thread = threading.Thread(target=watch,daemon=True)
    thread.start()
    try:
        yield
        if stats.get("stop_reason"):
            raise RuntimeError(stats["stop_reason"])
        sample()
    finally:
        stop.set()
        thread.join(timeout=2)
        write_json(Path(workspace) / "disk_monitor.json",stats)


def inventory(folder):
    folder = Path(folder).resolve()
    result = []
    for p in sorted(folder.rglob("*")):
        if p.is_symlink():
            raise RuntimeError(f"Unexpected artifact symlink: {p}")
        if p.is_file():
            result.append({"path": p.relative_to(folder).as_posix(), "bytes": p.stat().st_size,
                           "sha256": sha256_file(p)})
    if not result:
        raise RuntimeError("Cannot accept an empty artifact directory")
    return result


def verify_inventory(folder, items):
    if inventory(folder) != items:
        raise RuntimeError(f"Accepted artifacts changed: {folder}")


def new_attempt(parent):
    parent.mkdir(parents=True, exist_ok=True)
    number = 1
    while (parent / f"attempt-{number:04d}").exists():
        number += 1
    path = parent / f"attempt-{number:04d}"
    path.mkdir()
    return path


def safe_raw(root, name):
    root = Path(root).resolve()
    if Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError(f"Unsafe archive name: {name}")
    # Validate filename semantics as well as containment.
    from gharchive_a.records import source_hour
    source_hour(name)
    path = root / name
    if path.is_symlink() or path.resolve().parent != root:
        raise ValueError(f"Archive escapes raw root: {path}")
    return path


def cleanup_raw(raw, batch_dir, accepted, run_id):
    """Per-file write-ahead journal tolerates interruption after unlink.

    Requires both root locks held by the caller. A dedicated raw-root ownership
    marker is checked as well as per-file download ownership. Cached historical
    files are always retained. No glob deletion and no directory deletion.
    """
    if accepted.get("state") != "accepted":
        raise RuntimeError("Raw cleanup requires accepted outputs")
    if read_json(Path(raw) / ".batch-owner.json")["run_id"] != run_id:
        raise RuntimeError("Cleanup requires a raw root owned by this run")
    path = Path(batch_dir) / "cleanup.json"
    targets = [r for r in accepted["inputs"] if r.get("owner_run") == run_id]
    journal = read_json(path) if path.exists() else {"targets": targets, "files": {}, "completed": False}
    if journal["targets"] != targets:
        raise RuntimeError("Cleanup targets changed")
    write_json(path, journal)
    for row in targets:
        source = safe_raw(raw, row["name"])
        previous = journal["files"].get(row["name"])
        if previous == "deleted":
            if source.exists():
                raise RuntimeError(f"Cleaned archive reappeared; preserved: {source}")
            continue
        if not source.exists():
            if previous != "deleting":
                raise RuntimeError(f"Archive missing without cleanup intent: {source}")
        else:
            if source.stat().st_size != row["bytes"] or sha256_file(source) != row["sha256"]:
                raise RuntimeError(f"Archive changed before deletion: {source}")
            journal["files"][row["name"]] = "deleting"
            write_json(path, journal)
            source.unlink()
        journal["files"][row["name"]] = "deleted"
        write_json(path, journal)
    journal["completed"] = True
    write_json(path, journal)
    return journal


def host_record():
    import importlib.metadata
    versions = {}
    for package in ("pyarrow", "pyspark", "duckdb"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    import platform
    import sqlite3
    return {"hostname": socket.gethostname(), "cpu_count": os.cpu_count(), "platform": platform.platform(),
            "python": platform.python_version(), "sqlite": sqlite3.sqlite_version, "packages": versions,
            "meminfo": Path("/proc/meminfo").read_text() if Path("/proc/meminfo").exists() else None}
