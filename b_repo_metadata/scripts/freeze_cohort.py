#!/usr/bin/env python3
"""Freeze validated, AI-included repository IDs and their metadata/label snapshots."""
import argparse
from collections import Counter
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
import random

import _bootstrap  # noqa: F401
from bmeta.common import read_csv, read_json, write_csv, write_json, sha256_file, utc_now


def freeze(metadata_path, labels_path, output, year, start, end, *, size=None, seed=5488, allow_auto=False):
    start, end = date.fromisoformat(start), date.fromisoformat(end)
    if end < start or start.year != year or end.year != year:
        raise ValueError("Creation range must be increasing and inside cohort year")
    output = Path(output)
    if output.exists():
        raise FileExistsError("Frozen output already exists; use a new directory")
    metadata, labels = read_csv(metadata_path), read_csv(labels_path)
    def unique(rows, name):
        by_id = {int(row["repo_id"]): row for row in rows}
        if len(by_id) != len(rows):
            raise ValueError(f"Duplicate repo_id in {name}")
        return by_id
    meta, label = unique(metadata, "metadata"), unique(labels, "labels")
    selected, rejected = [], Counter()
    for rid, row in sorted(meta.items()):
        if row.get("fetch_status", "").lower() not in {"ok", "ok_cached"}:
            rejected["metadata_unavailable"] += 1
            continue
        if str(row.get("api_repo_id", "")) != str(rid):
            rejected["api_id_mismatch"] += 1
            continue
        try:
            created = datetime.fromisoformat(row["repo_created_at"].replace("Z", "+00:00"))
            if created.tzinfo is None:
                raise ValueError("Missing timezone")
            created = created.astimezone(timezone.utc).date()
        except (KeyError, ValueError):
            rejected["invalid_creation_time"] += 1
            continue
        if not start <= created <= end:
            rejected["outside_creation_range"] += 1
            continue
        if label.get(rid, {}).get("ai_label_final") != "included":
            rejected["not_included_or_no_label"] += 1
            continue
        selected.append(rid)
    if size is not None:
        if size <= 0 or size > len(selected):
            raise ValueError(f"Requested {size} repositories but eligible pool is {len(selected)}")
        selected = sorted(random.Random(seed).sample(selected, size))
    if not selected:
        raise ValueError("No eligible AI repositories; no empty research cohort frozen")
    unreviewed = [rid for rid in selected if not label[rid].get("label_source", "").startswith("manual")]
    if unreviewed and not allow_auto:
        raise ValueError(f"{len(unreviewed)} selected labels lack manual review; review first or explicitly use --allow-auto for a provisional run")
    output.mkdir(parents=True)
    cohort = [{"repo_id": rid, "cohort_year": year, "repo_created_at": meta[rid]["repo_created_at"],
               "ai_label_final": "included"} for rid in selected]
    write_csv(output / "cohort.csv", list(cohort[0]), cohort)
    write_csv(output / "repo_metadata.csv", list(metadata[0]), [meta[rid] for rid in selected])
    write_csv(output / "repo_ai_labels_analysis.csv", list(labels[0]), [label[rid] for rid in selected])
    selection_path = Path(metadata_path).parent / "selection.json"
    if selection_path.exists():
        write_json(output / "source_selection.json", read_json(selection_path))
    summary = {"cohort_year": year, "created_from": str(start), "created_to": str(end),
               "frozen_at": utc_now(), "rows": len(selected), "repo_ids": selected, "seed": seed,
               "status": "provisional_auto_labels" if unreviewed else "reviewed",
               "unreviewed_ids": unreviewed, "rejections": dict(rejected),
               "source_inputs": {str(Path(p).resolve()): sha256_file(p) for p in [metadata_path, labels_path]},
               "snapshots": {n: sha256_file(output / n) for n in ["cohort.csv", "repo_metadata.csv", "repo_ai_labels_analysis.csv", "source_selection.json"] if (output / n).exists()},
               "observation_end_21d": str(end + timedelta(days=20)),
               "scope": "Fixed eligible sample from supplied candidate pool, using current metadata and label evidence"}
    write_json(output / "cohort_manifest.json", summary)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--metadata", required=True, type=Path)
    p.add_argument("--labels", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--cohort-year", required=True, type=int)
    p.add_argument("--created-from", required=True)
    p.add_argument("--created-to", required=True)
    p.add_argument("--sample-size", type=int)
    p.add_argument("--seed", type=int, default=5488)
    p.add_argument("--allow-auto", action="store_true", help="Explicit provisional freeze of unreviewed labels")
    a = p.parse_args()
    result = freeze(a.metadata, a.labels, a.output, a.cohort_year, a.created_from, a.created_to,
                    size=a.sample_size, seed=a.seed, allow_auto=a.allow_auto)
    print(f"Frozen {result['rows']} repositories ({result['status']})")


if __name__ == "__main__":
    main()
