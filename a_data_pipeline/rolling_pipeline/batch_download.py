"""Rolling download adapter with portable no-overwrite publication and guards.

The historical downloader stays byte-for-byte unchanged. Windows rename is
atomic and refuses an existing destination; POSIX uses an exclusive hard link.
"""
from pathlib import Path
import os
import time
import urllib.request

from gharchive_a.common import expected_names, stage_directory, utc_now, write_json
from gharchive_a.download import verify_archive


def publish(partial,destination):
    if os.name=="nt":
        os.rename(partial,destination)
    else:
        os.link(partial,destination)
        partial.unlink()


def download(cfg,data_dir,output,guard=lambda:None):
    data_dir = Path(data_dir)
    manifest = {"date":cfg["date"],"requested_files":expected_names(cfg),"files":[]}
    with stage_directory(output,"rolling_download",cfg) as out:
        for name in expected_names(cfg):
            destination = data_dir / name
            entry = {"name":name,"url":cfg["base_url"].rstrip("/")+"/"+name,"status":"failed","attempts":[]}
            manifest["files"].append(entry)
            if destination.exists():
                if destination.stat().st_size > cfg["max_file_bytes"]:
                    raise ValueError("Cached archive exceeds byte budget; preserved")
                entry.update(status="cached_verified",bytes=destination.stat().st_size,sha256=verify_archive(destination))
            else:
                for number in range(cfg["retries"]+1):
                    partial = data_dir / f"{name}.{out.name}.attempt-{number+1}.part"
                    attempt = {"started_at":utc_now(),"partial_file":str(partial)}
                    entry["attempts"].append(attempt)
                    try:
                        request = urllib.request.Request(entry["url"],headers={"User-Agent":"CS5488-rolling/1.0","Accept-Encoding":"identity"})
                        with urllib.request.urlopen(request,timeout=cfg["timeout_seconds"]) as response,partial.open("xb") as handle:
                            attempt["http_status"] = response.status
                            length = response.headers.get("Content-Length")
                            if length is not None and int(length)>cfg["max_file_bytes"]:
                                raise ValueError("Server archive exceeds byte budget")
                            total = 0
                            for chunk in iter(lambda:response.read(1024*1024),b""):
                                total += len(chunk)
                                if total>cfg["max_file_bytes"]:
                                    raise ValueError("Archive exceeds byte budget")
                                handle.write(chunk)
                                guard()
                            if length is not None and total!=int(length):
                                raise ValueError("Content-Length mismatch")
                        checksum = verify_archive(partial)
                        publish(partial,destination)
                        entry.update(status="downloaded_verified",bytes=total,sha256=checksum)
                        attempt["state"] = "completed"
                    except (OSError,ValueError,EOFError) as error:
                        attempt.update(state="error",error=f"{type(error).__name__}: {error}")
                    finally:
                        attempt["finished_at"] = utc_now()
                        write_json(out / "download_manifest.json",manifest)
                    if entry["status"]=="downloaded_verified":
                        break
                    if number<cfg["retries"]:
                        time.sleep(min(2**number,4))
            write_json(out / "download_manifest.json",manifest)
            guard()
        manifest["all_requested_archives_verified"] = all(r["status"]!="failed" for r in manifest["files"])
        write_json(out / "download_manifest.json",manifest)
        if not manifest["all_requested_archives_verified"]:
            raise RuntimeError("Missing or unverified archives; see download_manifest.json")
    return manifest
