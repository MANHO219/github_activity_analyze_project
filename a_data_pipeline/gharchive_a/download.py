"""Bounded streaming downloads; caches are verified, partial attempts are kept."""
from __future__ import annotations

import gzip
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .common import expected_names, sha256_file, stage_directory, utc_now, write_json


def verify_archive(path):
    with gzip.open(path, "rb") as handle:
        while handle.read(1024 * 1024):
            pass
    return sha256_file(path)


def download(cfg, data_dir, output, allow_missing=False):
    data_dir = Path(data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"date": cfg["date"], "requested_files": expected_names(cfg), "files": []}
    with stage_directory(output, "download", cfg) as out:
        for name in expected_names(cfg):
            destination = data_dir / name
            url = cfg["base_url"].rstrip("/") + "/" + name
            entry = {"name": name, "url": url, "status": "failed", "attempts": []}
            manifest["files"].append(entry)
            if destination.exists():
                try:
                    if destination.stat().st_size > cfg["max_file_bytes"]:
                        raise ValueError("Existing archive exceeds configured byte budget")
                    entry.update(status="cached_verified", bytes=destination.stat().st_size,
                                 sha256=verify_archive(destination), checked_at=utc_now())
                except (OSError, EOFError, ValueError) as error:
                    entry["error"] = f"Cached file failed verification; preserved: {error}"
            else:
                for attempt_number in range(cfg["retries"] + 1):
                    partial = data_dir / f"{name}.{Path(output).name}.attempt-{attempt_number + 1}.part"
                    attempt = {"started_at": utc_now(), "partial_file": str(partial), "http_status": None}
                    entry["attempts"].append(attempt)
                    try:
                        request = urllib.request.Request(url, headers={"User-Agent": "CS5488-A-sample/1.0", "Accept-Encoding": "identity"})
                        with urllib.request.urlopen(request, timeout=cfg["timeout_seconds"]) as response, partial.open("xb") as handle:
                            attempt["http_status"] = response.status
                            attempt["content_type"] = response.headers.get("Content-Type")
                            length = response.headers.get("Content-Length")
                            if length is not None and int(length) > cfg["max_file_bytes"]:
                                raise ValueError("Server file exceeds configured byte budget")
                            total = 0
                            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                                total += len(chunk)
                                if total > cfg["max_file_bytes"]:
                                    raise ValueError("Download exceeds configured byte budget")
                                handle.write(chunk)
                            if length is not None and total != int(length):
                                raise OSError("Content-Length does not match downloaded bytes")
                        checksum = verify_archive(partial)
                        # No pre-existing input is overwritten by a rerun.
                        if destination.exists():
                            raise FileExistsError(f"Another run created {destination}; partial is preserved")
                        # Atomic creation without replacing a concurrently cached file.
                        os.link(partial, destination)
                        partial.unlink()
                        entry.update(status="downloaded_verified", bytes=total, sha256=checksum)
                        attempt["status"] = "completed"
                    except (OSError, ValueError, EOFError, urllib.error.URLError) as error:
                        attempt.update(status="failed", error=f"{type(error).__name__}: {error}")
                        if isinstance(error, urllib.error.HTTPError):
                            attempt["http_status"] = error.code
                        entry["error"] = attempt["error"]
                    finally:
                        attempt["finished_at"] = utc_now()
                        if partial.exists():
                            attempt["partial_bytes"] = partial.stat().st_size
                        write_json(out / "download_manifest.json", manifest)
                    if entry["status"] == "downloaded_verified":
                        break
                    if attempt_number < cfg["retries"]:
                        time.sleep(min(2**attempt_number, 4))
            write_json(out / "download_manifest.json", manifest)
            print(f"{name}: {entry['status']}", flush=True)
        failed = [row["name"] for row in manifest["files"] if row["status"] == "failed"]
        manifest.update(failed_files=failed, all_requested_archives_verified=not failed)
        write_json(out / "download_manifest.json", manifest)
        if failed and not allow_missing:
            raise RuntimeError(f"Archive download/verification failed: {failed}; see download_manifest.json")
    return manifest
