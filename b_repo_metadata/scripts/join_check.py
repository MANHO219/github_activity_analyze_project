#!/usr/bin/env python3
"""按 ``repo_id`` 把标签接回 A 的事件表，核对唯一性与覆盖情况。

    python scripts/join_check.py

首选读取 ``a_data_pipeline/runs/20240115_1hour_handoff/python/events_clean.parquet``
（需要 pyarrow）；缺少 pyarrow 时回退到 ``repo_candidates.csv`` 的 ``event_count``，
并在 ``join_check.json`` 中写明数据源与限制。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from bmeta.common import (
    B_ROOT,
    DEFAULT_CANDIDATES,
    DEFAULT_EVENTS_PARQUET,
    load_config,
    project_relative,
)
from bmeta.join import run as join_run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="标签接回事件表并核对")
    parser.add_argument("--config", default=str(B_ROOT / "config" / "pilot.json"))
    parser.add_argument("--run-dir", help="运行目录；默认 runs/<pilot_version>")
    parser.add_argument(
        "--labels",
        help="标签表；默认优先 <run-dir>/repo_ai_labels_analysis.csv（最终标签），缺失时用 repo_ai_labels.csv",
    )
    parser.add_argument("--events-parquet", default=str(DEFAULT_EVENTS_PARQUET))
    parser.add_argument("--candidates", default=str(DEFAULT_CANDIDATES))
    parser.add_argument(
        "--daily-csv",
        help="全天活动汇总表（repo_daily_counts.csv）；给了就按 repo_id 汇总 event_count，优先于 parquet",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    out_dir = Path(args.run_dir or (B_ROOT / "runs" / config["pilot_version"]))
    metadata_csv = out_dir / "repo_metadata.csv"
    if args.labels:
        labels_csv = Path(args.labels)
    else:
        final_labels = out_dir / "repo_ai_labels_analysis.csv"
        labels_csv = final_labels if final_labels.exists() else out_dir / "repo_ai_labels.csv"
    label_field = "ai_label_final" if labels_csv.name.endswith("_analysis.csv") else "ai_label"
    for path in (metadata_csv, labels_csv):
        if not path.exists():
            print(f"missing input: {project_relative(path)}")
            return 1

    summary = join_run(
        metadata_csv=metadata_csv,
        labels_csv=labels_csv,
        out_dir=out_dir,
        events_parquet=Path(args.events_parquet),
        candidates_csv=Path(args.candidates),
        daily_counts_csv=Path(args.daily_csv) if args.daily_csv else None,
        label_field=label_field,
    )
    print(f"label source: {summary['inputs']['labels_csv']} ({summary['inputs']['label_field']})")
    print(f"event source: {summary['event_source']} (events={summary['events_total_in_source']})")
    print(f"pilot repos: {summary['pilot_repos']} found={summary['pilot_repos_found_in_events']}")
    print(f"events covered by pilot: {summary['events_covered_by_pilot']}")
    print(f"checks: {summary['checks']}")
    failed = [name for name, passed in summary["checks"].items() if not passed]
    if failed:
        print(f"WARNING: failed checks: {failed}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
