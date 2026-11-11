"""Plan and safely remove rolling-pilot scratch only after two-day verification."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path
import shutil

from weekly_pipeline import DEFAULT_OUTPUT, DEFAULT_RAW, DEFAULT_VOLUME, accepted_day, read_json, save_json, sha256, size_of_tree, volume_check


def plan_cleanup(day_string, root, raw_root):
    day = root / day_string
    info = accepted_day(day)
    if info is None:
        raise RuntimeError(f"Day has not been accepted: {day_string}")
    attempt = Path(info["attempt"])
    expected_attempt = day.resolve()
    if attempt.parent != expected_attempt or not attempt.name.startswith("attempt-"):
        raise RuntimeError(f"Unexpected daily attempt: {attempt}")
    targets = []
    for filename in ("working.sqlite3", "events_clean.csv.gz", "repo_daily_counts.csv"):
        path = attempt / "python" / filename
        if path.is_file():
            targets.append({"path": str(path), "kind": "local_scratch", "bytes": path.stat().st_size})
    if day_string != "2024-01-15":
        download_path = attempt / "download/download_manifest.json"
        download = read_json(download_path)
        if not download.get("all_requested_archives_verified") or len(download["files"]) != 24:
            raise RuntimeError(f"Download was not fully verified: {download_path}")
        day_raw = (raw_root / day_string).resolve()
        if day_raw.parent != raw_root.resolve():
            raise RuntimeError(f"Unexpected raw directory: {day_raw}")
        for entry in download["files"]:
            name = entry["name"]
            if name not in {f"{day_string}-{hour}.json.gz" for hour in range(24)}:
                raise RuntimeError(f"Unexpected archive in download manifest: {name}")
            if entry["status"] not in ("downloaded_verified", "cached_verified"):
                raise RuntimeError(f"Archive did not pass download validation: {name}")
            path = day_raw / name
            targets.append({"path": str(path), "kind": "verified_raw", "bytes": entry["bytes"],
                            "sha256": entry["sha256"]})
        for old_attempt in day.glob("attempt-*/download/download_manifest.json"):
            for entry in read_json(old_attempt).get("files", []):
                for request in entry.get("attempts", []):
                    if not request.get("partial_file"):
                        continue
                    partial = Path(request["partial_file"])
                    if partial.parent.resolve() == day_raw and partial.name.startswith(day_string + "-") and partial.name.endswith(".part") and partial.is_file():
                        targets.append({"path": str(partial), "kind": "registered_partial", "bytes": partial.stat().st_size})
        preserved = day / "preserved_partials.json"
        if preserved.exists():
            for move in read_json(preserved):
                partial = Path(move["preserved"])
                if partial.parent.resolve() != day_raw or not partial.name.startswith(day_string + "-") or not partial.name.endswith(".part"):
                    raise RuntimeError(f"Unexpected preserved partial path: {partial}")
                if partial.exists():
                    targets.append({"path": str(partial), "kind": "registered_partial", "bytes": move["bytes"]})
    plan = {"date": day_string, "two_day_proof_required": True,
            "day_output_bytes_before_cleanup": size_of_tree(day),
            "local_free_bytes_before_cleanup": shutil.disk_usage(root).free,
            "targets": targets}
    save_json(day / "cleanup_plan.json", plan)
    print(f"{day_string}: planned {len(targets)} scratch files for cleanup", flush=True)
    return plan


def apply_cleanup(day_string, root, volume, raw_root, proof):
    summary = read_json(proof / "summary.json")
    required_checks = ("complete_hourly_coverage", "all_valid_index_counts_match", "event_ids_unique",
                       "daily_counts_reconcile", "candidate_counts_reconcile")
    if (not {"2024-01-15", "2024-01-16"}.issubset(set(summary["days"]))
            or not all(summary.get("checks", {}).get(name) is True for name in required_checks)):
        raise RuntimeError("Two-day cross-day validation has not passed")
    for proof_day in ("2024-01-15", "2024-01-16"):
        accepted = accepted_day(root / proof_day)
        expected = {name: accepted["retained_files"][name]["sha256"] for name in ("events", "daily", "valid_index")}
        if summary.get("input_hashes", {}).get(proof_day) != expected:
            raise RuntimeError(f"Two-day proof does not match accepted inputs for {proof_day}")
    day = root / day_string
    accepted_day(day)
    plan = read_json(day / "cleanup_plan.json")
    state_path = day / "cleanup_done.json"
    state = read_json(state_path) if state_path.exists() else {"date": day_string, "removed": [], "missing": []}
    if state.get("completed"):
        print(f"{day_string}: cleanup already completed", flush=True)
        return
    raw_targets = {"verified_raw", "registered_partial"}
    device = volume_check(volume, raw_root) if any(target["kind"] in raw_targets for target in plan["targets"]) else None
    for target in plan["targets"]:
        path = Path(target["path"])
        if target["kind"] in raw_targets and volume_check(volume, raw_root) != device:
            raise RuntimeError("The external volume changed during cleanup")
        if not path.exists():
            if str(path) not in state["removed"] and str(path) not in state["missing"]:
                state["missing"].append(str(path))
            save_json(state_path, state)
            continue
        if path.is_symlink():
            raise RuntimeError(f"Refusing to remove a symlink: {path}")
        if target["kind"] in raw_targets:
            if path.parent.resolve() != (raw_root / day_string).resolve():
                raise RuntimeError(f"Refusing to remove a file outside the daily raw directory: {path}")
        elif path.parent.parent.parent != day.resolve():
            raise RuntimeError(f"Refusing to remove scratch outside this day's attempt: {path}")
        if path.stat().st_size != target["bytes"]:
            raise RuntimeError(f"File size changed after cleanup planning: {path}")
        if target["kind"] == "verified_raw" and sha256(path) != target["sha256"]:
            raise RuntimeError(f"Archive hash changed after verification: {path}")
        path.unlink()
        state["removed"].append(str(path))
        save_json(state_path, state)
    state["completed"] = True
    save_json(state_path, state)
    print(f"{day_string}: cleaned {len(state['removed'])} recorded files", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--volume", type=Path, default=DEFAULT_VOLUME)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--proof", type=Path)
    args = parser.parse_args()
    if args.apply and not args.proof:
        parser.error("--proof is required with --apply")
    current, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if current > end:
        raise ValueError("Start date must not be later than end date")
    while current <= end:
        day = current.isoformat()
        if args.apply:
            apply_cleanup(day, args.root, args.volume, args.raw_root, args.proof)
        else:
            plan_cleanup(day, args.root, args.raw_root)
        current += timedelta(days=1)


if __name__ == "__main__":
    main()
