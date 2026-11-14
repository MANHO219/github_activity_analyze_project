#!/usr/bin/env python3
"""Run one fixed cohort with three equal windows; 7 days gives a 21-day analysis."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from cohort_analysis import analyze_cohort


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ["metadata", "labels", "daily", "coverage", "cohort", "output"]:
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--cohort-year", type=int, required=True)
    p.add_argument("--created-from", required=True)
    p.add_argument("--created-to", required=True)
    p.add_argument("--window-days", type=int, default=30)
    p.add_argument("--data-kind", choices=["Real Data", "Testing Data"], required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error("Output exists; choose a new directory to preserve earlier results")
    def digest(path):
        h = hashlib.sha256()
        if path.is_dir():
            for part in sorted(p for p in path.rglob("*") if p.is_file()):
                h.update(part.relative_to(path).as_posix().encode("utf-8") + b"\0")
                h.update(bytes.fromhex(digest(part)))
            return h.hexdigest()
        with path.open("rb") as f:
            for b in iter(lambda: f.read(1024 * 1024), b""):
                h.update(b)
        return h.hexdigest()
    inputs = {str(x.resolve()): digest(x) for x in [a.metadata, a.labels, a.daily, a.coverage, a.cohort]}
    manifest_path = a.cohort.parent / "cohort_manifest.json"
    cohort_status = "Testing Data"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        for name, supplied in [("cohort.csv", a.cohort), ("repo_metadata.csv", a.metadata),
                               ("repo_ai_labels_analysis.csv", a.labels)]:
            if digest(supplied) != manifest["snapshots"][name]:
                p.error(f"Frozen snapshot changed: {name}")
        cohort_status = manifest["status"]
        inputs[str(manifest_path.resolve())] = digest(manifest_path)
    elif a.data_kind == "Real Data":
        p.error("Real Data requires the cohort_manifest.json written by freeze_cohort.py")
    started = time.perf_counter()
    result = analyze_cohort(a.metadata, a.labels, a.daily, a.coverage, a.cohort_year,
                            a.created_from, a.created_to, a.data_kind,
                            window_days=a.window_days, cohort_path=a.cohort)
    elapsed = time.perf_counter() - started
    a.output.mkdir(parents=True)
    for key, name in [("cohort", "cohort.csv"), ("stage_table", "repo_window_metrics.csv"),
                      ("aggregate", "cohort_window_summary.csv"), ("out_of_band", "out_of_band_events.csv")]:
        if "data_kind" not in result[key].columns:
            result[key]["data_kind"] = a.data_kind
        result[key]["label_validation_status"] = cohort_status
        result[key].to_csv(a.output / name, index=False)
    summary = {"cohort_year": a.cohort_year, "data_kind": a.data_kind,
               "window_days": a.window_days, "observation_days": result["observation_days"],
               "cohort_status": cohort_status,
               "analysis_seconds": elapsed, "inputs_sha256": inputs, "exclusions": result["exclusions"],
               "stage_rows": len(result["stage_table"]), "cohort_size": len(result["cohort"])}
    (a.output / "analysis_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
