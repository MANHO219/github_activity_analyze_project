#!/usr/bin/env python3
"""按 ``repo_id`` 把标签接回 A 的事件表，核对唯一性与覆盖情况。

    python scripts/join_check.py --run-dir runs/pilot_02

默认读仓库共享的全天活动表
``a_data_pipeline/sample_data/20240115_24h/repo_daily_counts.csv``；
显式传入 ``--daily-csv`` 但文件不存在时直接报错，避免悄悄退回一小时数据。

标签列默认按**表头**选：有 ``ai_label_final`` 就用它，否则用 ``ai_label``；
也可以用 ``--label-field`` 指定。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from bmeta.common import (
    B_ROOT,
    DEFAULT_CANDIDATES,
    DEFAULT_DAILY_COUNTS,
    DEFAULT_EVENTS_PARQUET,
    load_config,
    project_relative,
)
from bmeta.join import run as join_run

NO_DAILY = "none"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="标签接回事件表并核对")
    parser.add_argument("--config", default=str(B_ROOT / "config" / "pilot.json"))
    parser.add_argument("--run-dir", help="运行目录；默认 runs/<pilot_version>")
    parser.add_argument(
        "--labels",
        help="标签表；默认优先 <run-dir>/repo_ai_labels_analysis.csv（最终标签），缺失时用 repo_ai_labels.csv",
    )
    parser.add_argument(
        "--label-field",
        default="auto",
        help="标签列；默认 auto（按表头选 ai_label_final，缺失时 ai_label）",
    )
    parser.add_argument("--events-parquet", default=str(DEFAULT_EVENTS_PARQUET))
    parser.add_argument("--candidates", default=str(DEFAULT_CANDIDATES))
    parser.add_argument(
        "--daily-csv",
        default=str(DEFAULT_DAILY_COUNTS),
        help=f"全天活动汇总表；默认 {project_relative(DEFAULT_DAILY_COUNTS)}。"
        f"传 {NO_DAILY} 可禁用（退回 parquet/候选表）",
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

    for path in (metadata_csv, labels_csv):
        if not path.exists():
            print(f"missing input: {project_relative(path)}")
            return 1

    daily_csv: Path | None = None
    if args.daily_csv and args.daily_csv.strip().lower() != NO_DAILY:
        daily_csv = Path(args.daily_csv)
        if not daily_csv.exists():
            print(
                f"daily counts csv not found: {project_relative(daily_csv)}\n"
                "显式给出的全天表必须存在；如需退回一小时数据，请传 --daily-csv none",
                file=sys.stderr,
            )
            return 2

    try:
        summary = join_run(
            metadata_csv=metadata_csv,
            labels_csv=labels_csv,
            out_dir=out_dir,
            events_parquet=Path(args.events_parquet),
            candidates_csv=Path(args.candidates),
            daily_counts_csv=daily_csv,
            label_field=args.label_field,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"join failed: {exc}", file=sys.stderr)
        return 2

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
