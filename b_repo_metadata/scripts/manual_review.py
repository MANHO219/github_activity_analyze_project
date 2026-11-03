#!/usr/bin/env python3
"""人工复核：生成新清单，或把已有判断合并进已有清单。

两种用法刻意分开，避免重跑时覆盖历史复核记录。

A. 复现本次成果（复用已有清单，只合并判断，不重新抽样）：

       python scripts/manual_review.py --run-dir runs/pilot_01 \
           --decisions reviews/pilot_01_decisions.json

   已有 ``runs/pilot_01/manual_review.csv`` 会被原样读取，只把人工判断写回去；
   即使当前规则已经换成 v0.2，也不会用 v0.2 重新生成名单。

B. 创建新一轮复核清单（务必换输出目录，不要覆盖 pilot_01）：

       python scripts/manual_review.py --run-dir runs/pilot_02_review \
           --labels runs/pilot_01/repo_ai_labels.csv \
           --metadata runs/pilot_01/repo_metadata.csv

   没有 ``--decisions`` 时只生成清单。目标目录里已有 ``manual_review.csv``
   会直接报错退出；确实要覆盖同一目录时加 ``--force``。
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
    parser.add_argument("--run-dir", help="输出目录；默认 runs/<pilot_version>")
    parser.add_argument("--labels", help="标签表；默认 <run-dir>/repo_ai_labels.csv")
    parser.add_argument("--metadata", help="元数据表；默认 <run-dir>/repo_metadata.csv")
    parser.add_argument("--decisions", help="人工判断 JSON；不给则只生成新清单")
    parser.add_argument("--per-label", type=int, default=5, help="included/excluded 各复核几个（默认 5）")
    parser.add_argument("--uncertain-limit", type=int, help="uncertain 最多复核几个；默认全查")
    parser.add_argument("--seed", type=int, help="抽样种子；默认取配置")
    parser.add_argument("--force", action="store_true", help="覆盖已有的 manual_review.csv（危险）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    out_dir = Path(args.run_dir or (B_ROOT / "runs" / config["pilot_version"]))
    labels_csv = Path(args.labels) if args.labels else out_dir / "repo_ai_labels.csv"
    metadata_csv = Path(args.metadata) if args.metadata else out_dir / "repo_metadata.csv"
    for path in (labels_csv, metadata_csv):
        if not path.exists():
            print(f"missing input: {project_relative(path)}")
            return 1

    decisions = Path(args.decisions) if args.decisions else None
    if decisions is not None and not decisions.is_absolute():
        decisions = (Path.cwd() / decisions).resolve()
    if decisions is not None and not decisions.exists():
        print(f"missing decisions file: {project_relative(decisions)}")
        return 1

    try:
        summary = review_run(
            labels_csv=labels_csv,
            metadata_csv=metadata_csv,
            out_dir=out_dir,
            decisions_path=decisions,
            per_label=args.per_label,
            uncertain_limit=args.uncertain_limit,
            seed=args.seed if args.seed is not None else int(config["seed"]),
            force=args.force,
        )
    except FileExistsError as error:
        print(f"refusing to overwrite existing review sheet: {project_relative(Path(str(error)))}")
        print("换一个 --run-dir 生成新清单，或加 --force 覆盖（会丢失该目录已有的复核记录）。")
        return 3
    except ValueError as error:
        print(f"cannot merge decisions: {error}")
        print("如果判断文件对应的是另一轮清单，请换 --run-dir 并带上对应的 --decisions。")
        return 4

    print(f"status={summary['status']} sheet_rows={summary['sheet_rows']} reviewed={summary['reviewed_rows']}")
    if "auto_decided_rows" in summary:
        print(f"auto_decided={summary['auto_decided_rows']}")
        print(f"auto_uncertain={summary['auto_uncertain_rows']}")
        print(f"disagreements={len(summary['disagreements'])}")
    if "sheet_source" in summary:
        print(f"sheet_source={summary['sheet_source']} rules_version={summary['rules_version_used']}")
    print(f"sheet: {summary['sheet']}")
    return 0 if summary["status"] in ("complete", "sheet_only") else 2


if __name__ == "__main__":
    sys.exit(main())
