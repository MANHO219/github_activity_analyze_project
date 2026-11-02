#!/usr/bin/env python3
"""对比两个规则版本的标签，输出变化清单与人工判断对照。

    python scripts/compare_label_versions.py \
        --old runs/pilot_01/repo_ai_labels_v0.1.csv \
        --new runs/pilot_01/repo_ai_labels.csv \
        --run-dir runs/pilot_01
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from bmeta.common import B_ROOT, load_config, project_relative
from bmeta.compare import run as compare_run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="比较两个规则版本的标签结果")
    parser.add_argument("--config", default=str(B_ROOT / "config" / "pilot.json"))
    parser.add_argument("--run-dir", help="运行目录；默认 runs/<pilot_version>")
    parser.add_argument("--old", help="旧标签表；默认 <run-dir>/repo_ai_labels_v0.1.csv")
    parser.add_argument("--new", help="新标签表；默认 <run-dir>/repo_ai_labels.csv")
    parser.add_argument("--metadata", help="默认 <run-dir>/repo_metadata.csv")
    parser.add_argument("--review", help="人工复核表；默认 <run-dir>/manual_review.csv")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    run_dir = Path(args.run_dir or (B_ROOT / "runs" / config["pilot_version"]))
    old = Path(args.old or (run_dir / "repo_ai_labels_v0.1.csv"))
    new = Path(args.new or (run_dir / "repo_ai_labels.csv"))
    metadata = Path(args.metadata or (run_dir / "repo_metadata.csv"))
    review = Path(args.review or (run_dir / "manual_review.csv"))
    for path in (old, new, metadata):
        if not path.exists():
            print(f"missing input: {project_relative(path)}")
            return 1

    summary = compare_run(
        old_labels_csv=old,
        new_labels_csv=new,
        metadata_csv=metadata,
        out_dir=run_dir,
        manual_review_csv=review,
    )
    print(f"versions: {summary['old_rule_version']} -> {summary['new_rule_version']}")
    print(f"changed: {summary['changed_rows']} (label {summary['label_changed_rows']}, reason-only {summary['rule_reason_changed_rows']})")
    print(f"confusion: {summary['confusion_matrix']}")
    if "human_review" in summary:
        print(f"human old: {summary['human_review']['old_version']}")
        print(f"human new: {summary['human_review']['new_version']}")
    print(f"changes csv: {summary['changes_csv']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
