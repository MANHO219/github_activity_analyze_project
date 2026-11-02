#!/usr/bin/env python3
"""人工复核：先出清单（sheet），补充判断后再合并。

1. 生成清单（不传 ``--decisions``）：

       python scripts/manual_review.py --run-dir runs/pilot_01

2. 按清单逐条读数，把判断写进 ``reviews/pilot_01_decisions.json``；

3. 合并并统计一致率：

       python scripts/manual_review.py --run-dir runs/pilot_01 \
           --decisions reviews/pilot_01_decisions.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from bmeta.common import B_ROOT, load_config, project_relative
from bmeta.review import run as review_run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成/合并人工复核清单")
    parser.add_argument("--config", default=str(B_ROOT / "config" / "pilot.json"))
    parser.add_argument("--run-dir", help="运行目录；默认 runs/<pilot_version>")
    parser.add_argument("--decisions", help="人工判断 JSON；不给则只生成清单")
    parser.add_argument("--per-label", type=int, default=5, help="included/excluded 各复核几个（默认 5）")
    parser.add_argument("--uncertain-limit", type=int, help="uncertain 最多复核几个；默认全查")
    parser.add_argument("--seed", type=int, help="抽样种子；默认取配置")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    out_dir = Path(args.run_dir or (B_ROOT / "runs" / config["pilot_version"]))
    labels_csv = out_dir / "repo_ai_labels.csv"
    metadata_csv = out_dir / "repo_metadata.csv"
    for path in (labels_csv, metadata_csv):
        if not path.exists():
            print(f"missing input: {project_relative(path)}")
            return 1

    decisions = Path(args.decisions) if args.decisions else None
    if decisions is not None and not decisions.is_absolute():
        decisions = (Path.cwd() / decisions).resolve()
    summary = review_run(
        labels_csv=labels_csv,
        metadata_csv=metadata_csv,
        out_dir=out_dir,
        decisions_path=decisions,
        per_label=args.per_label,
        uncertain_limit=args.uncertain_limit,
        seed=args.seed if args.seed is not None else int(config["seed"]),
    )
    print(f"status={summary['status']} sheet_rows={summary['sheet_rows']} reviewed={summary['reviewed_rows']}")
    if "auto_decided_rows" in summary:
        print(f"auto_decided={summary['auto_decided_rows']}")
        print(f"auto_uncertain={summary['auto_uncertain_rows']}")
        print(f"disagreements={len(summary['disagreements'])}")
    print(f"sheet: {summary['sheet']}")
    return 0 if summary["status"] in ("complete", "sheet_only") else 2


if __name__ == "__main__":
    sys.exit(main())
