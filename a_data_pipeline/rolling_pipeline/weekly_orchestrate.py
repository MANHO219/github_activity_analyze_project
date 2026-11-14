"""Run the two-day gate, rolling cleanup, and final cross-day merge."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path
import subprocess
import sys

from weekly_pipeline import DEFAULT_OUTPUT, DEFAULT_RAW, DEFAULT_VOLUME, read_json, save_json, validate_input_snapshots


TOOLS = Path(__file__).resolve().parent


def run(script, *arguments):
    command = [sys.executable, str(TOOLS / script), *map(str, arguments)]
    print("Running:", " ".join(command), flush=True)
    subprocess.run(command, check=True)


def completed_output(parent, prefix, days):
    for candidate in sorted(parent.glob(prefix + "*"), reverse=True):
        summary_path = candidate / "summary.json"
        if summary_path.is_file():
            summary = read_json(summary_path)
            checks = summary.get("checks", {})
            hashes = {day: {name: read_json(parent / day / "accepted.json")["retained_files"][name]["sha256"]
                            for name in ("events", "daily", "valid_index")} for day in days}
            if checks and all(checks.values()) and summary.get("days") == days and summary.get("input_hashes") == hashes:
                return candidate
    return None


def new_output(parent, prefix):
    number = 1
    while (parent / f"{prefix}_{number:02d}").exists():
        number += 1
    return parent / f"{prefix}_{number:02d}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2024-01-15")
    parser.add_argument("--end", default="2024-01-21")
    parser.add_argument("--root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--volume", type=Path, default=DEFAULT_VOLUME)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--plan-only", action="store_true", help="Print dates and paths without downloading or changing files")
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if end < start + timedelta(days=1):
        parser.error("The rolling pipeline requires at least two consecutive UTC days")
    first_two = [start.isoformat(), (start + timedelta(days=1)).isoformat()]
    days = [(start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1)]
    if args.plan_only:
        import json
        print(json.dumps({"start": args.start, "end": args.end, "days": days,
                          "first_two_days": first_two, "requested_hours": len(days) * 24,
                          "root": str(args.root.resolve()), "raw_root": str(args.raw_root.resolve())}, indent=2))
        return
    previous = args.root / "orchestration.json"
    if previous.exists() and read_json(previous).get("start") != args.start:
        parser.error("Existing run uses a different start date; choose a new --root")
    args.root.mkdir(parents=True, exist_ok=True)
    status = {"start": args.start, "end": args.end, "state": "running", "stage": "first_two_days"}
    save_json(args.root / "orchestration.json", status)
    common = ["--output", args.root, "--volume", args.volume, "--raw-root", args.raw_root]
    cleanup_args = ["--root", args.root, "--volume", args.volume, "--raw-root", args.raw_root]
    try:
        run("weekly_pipeline.py", "--start", first_two[0], "--end", first_two[1], *common)
        for day in first_two:
            validate_input_snapshots(read_json(args.root / day / "accepted.json")["attempt"])
            if not (args.root / day / "cleanup_plan.json").exists():
                run("weekly_cleanup.py", "--start", day, "--end", day, *cleanup_args)
        status["stage"] = "two_day_cross_check"
        save_json(args.root / "orchestration.json", status)
        proof = completed_output(args.root, "two_day_check_", first_two)
        if proof is None:
            proof = new_output(args.root, "two_day_check")
            run("weekly_merge.py", "--start", first_two[0], "--end", first_two[1],
                "--root", args.root, "--output", proof)
        for day in first_two:
            run("weekly_cleanup.py", "--start", day, "--end", day, *cleanup_args, "--apply", "--proof", proof)

        current = start + timedelta(days=2)
        while current <= end:
            day = current.isoformat()
            status["stage"] = day
            save_json(args.root / "orchestration.json", status)
            run("weekly_pipeline.py", "--start", day, "--end", day, *common)
            validate_input_snapshots(read_json(args.root / day / "accepted.json")["attempt"])
            if not (args.root / day / "cleanup_plan.json").exists():
                run("weekly_cleanup.py", "--start", day, "--end", day, *cleanup_args)
            run("weekly_cleanup.py", "--start", day, "--end", day, *cleanup_args, "--apply", "--proof", proof)
            current += timedelta(days=1)

        status["stage"] = "final_cross_day_merge"
        save_json(args.root / "orchestration.json", status)
        prefix = "combined_" + args.start.replace("-", "") + "_" + args.end.replace("-", "")
        days = [(start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1)]
        final = completed_output(args.root, prefix + "_", days)
        if final is None:
            final = new_output(args.root, prefix)
            run("weekly_merge.py", "--start", args.start, "--end", args.end,
                "--root", args.root, "--output", final)
        status.update(state="completed", stage="completed", two_day_check=str(proof.resolve()),
                      final_output=str(final.resolve()))
    except BaseException as error:
        status.update(state="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        save_json(args.root / "orchestration.json", status)
    print(f"Completed: {status['final_output']}", flush=True)


if __name__ == "__main__":
    main()
