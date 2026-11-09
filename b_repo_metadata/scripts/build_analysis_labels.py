#!/usr/bin/env python3
"""生成分析用标签表：合并自动标签与人工复核，保留来源与两种值。

    python scripts/build_analysis_labels.py --run-dir runs/pilot_01

默认口径 ``manual_override``：有人工判断的仓库用人工标签，其余用自动标签。
可切换 ``--policy auto_only`` 只采用规则结果。最终口径待 A、B 确认。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from bmeta.common import B_ROOT, load_config, project_relative
from bmeta.handoff import VALID_POLICIES, run as handoff_run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="合并自动标签与人工复核，生成分析用标签")
    parser.add_argument("--config", default=str(B_ROOT / "config" / "pilot.json"))
    parser.add_argument("--run-dir", help="运行目录；默认 runs/<pilot_version>")
    parser.add_argument("--labels", help="自动标签表；默认 <run-dir>/repo_ai_labels.csv")
    parser.add_argument("--metadata", help="默认 <run-dir>/repo_metadata.csv")
    parser.add_argument("--review", help="人工复核表；默认 <run-dir>/manual_review.csv")
    parser.add_argument("--policy", choices=VALID_POLICIES, default="manual_override", help="采用口径")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    run_dir = Path(args.run_dir or (B_ROOT / "runs" / config["pilot_version"]))
    labels = Path(args.labels or (run_dir / "repo_ai_labels.csv"))
    metadata = Path(args.metadata or (run_dir / "repo_metadata.csv"))
    review = Path(args.review or (run_dir / "manual_review.csv"))
    if not labels.exists() or not metadata.exists():
        print(f"missing input: {project_relative(labels if not labels.exists() else metadata)}")
        return 1

    summary = handoff_run(
        labels_csv=labels,
        metadata_csv=metadata,
        out_dir=run_dir,
        review_csv=review,
        policy=args.policy,
    )
    print(f"policy={summary['policy']} rows={summary['rows']}")
    print(f"final={summary['final_labels']} source={summary['label_source']}")
    print(f"manual coverage={summary['manual_rows']}/{summary['rows']}, differs from auto={summary['manual_differs_from_auto']}")
    print(f"output: {summary['output_csv']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
