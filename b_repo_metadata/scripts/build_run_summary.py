#!/usr/bin/env python3
"""汇总本次试跑：补齐 ``run_summary.json`` 的版本、环境与验收检查。

在 ``build_pilot → fetch_metadata → label_repositories → manual_review → join_check``
之后运行：

    python scripts/build_run_summary.py --run-dir runs/pilot_01

只做汇总与核对，不修改任何数据表；检查结果 false 时以退出码 2 提示。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from bmeta.common import (
    B_ROOT,
    environment_snapshot,
    load_config,
    project_relative,
    read_csv,
    read_json,
    sha256_file,
    utc_now,
    write_json,
)

UNRESOLVED = [
    "7 个候选仓库无法按名称取回元数据（5 个 404、2 个 id 不一致），标签保持 uncertain；不能据此推断删除或非 AI。",
    "15 个仓库的 description 与 topics 都为空，规则只能判 uncertain；人工复核用 README 补证后部分改判，但 README 不是 v0.1 规则的输入。",
    "规则 v0.1 未覆盖三类人工复核发现的模式：个人主页/作品集仓库、课程作业仓库、AI 只作为附加功能的仓库。",
    "仓库元数据是 2026-11-02 的快照，不是 2024-01-15 事件发生时的状态；描述与 topics 可能已经变化。",
    "首批 50 个仓库为“40 随机 + 10 名称关键词过采样”的分层样本，不能用来估计整个 GitHub 的 AI 仓库比例。",
]


def build(run_dir: Path) -> dict:
    summary = read_json(run_dir / "run_summary.json")
    pilot = summary.get("pilot", {})
    fetch = summary.get("fetch", {})
    labels = summary.get("labels", {})
    join = summary.get("join", {})
    review = summary.get("manual_review", {})

    metadata = read_csv(run_dir / "repo_metadata.csv")
    label_rows = read_csv(run_dir / "repo_ai_labels.csv")
    review_rows = read_csv(run_dir / "manual_review.csv")

    metadata_ids = [row["repo_id"] for row in metadata]
    label_ids = [row["repo_id"] for row in label_rows]
    by_label = labels.get("by_label", {})

    checks = {
        "fetch_processed_plus_pending_equals_input": fetch.get("processed_rows", 0) + fetch.get("pending_rows", 0)
        == fetch.get("input_rows", -1),
        "metadata_rows_equals_processed": len(metadata) == fetch.get("processed_rows", -1),
        "metadata_ids_unique": len(set(metadata_ids)) == len(metadata_ids),
        "labels_cover_metadata": sorted(label_ids) == sorted(metadata_ids),
        "label_counts_sum_equals_rows": sum(by_label.values()) == len(label_rows) if by_label else False,
        "join_checks_all_true": all(join.get("checks", {}).values()) if join.get("checks") else False,
        "manual_review_complete": review.get("pending_rows") == 0 and review.get("reviewed_rows", 0) > 0,
        "manual_review_covers_three_labels": len(review.get("reviewed_by_scope", {})) == 3,
    }

    meta = {
        "pilot_version": pilot.get("pilot_version"),
        "seed": pilot.get("seed"),
        "strata": pilot.get("strata_actual"),
        "rules_version": labels.get("rules_version"),
        "generated_at_utc": utc_now(),
        "environment": environment_snapshot(),
        "inputs": {
            "candidates_csv": pilot.get("input", {}).get("path"),
            "candidates_sha256": pilot.get("input", {}).get("sha256"),
            "pilot_candidates_sha256": pilot.get("output", {}).get("sha256"),
            "repo_metadata_sha256": sha256_file(run_dir / "repo_metadata.csv"),
            "repo_ai_labels_sha256": sha256_file(run_dir / "repo_ai_labels.csv"),
            "rules_sha256": labels.get("rules_sha256"),
        },
        "outputs": {
            "metadata_rows": len(metadata),
            "label_rows": len(label_rows),
            "review_rows": len(review_rows),
            "labels": by_label,
            "fetch_status": fetch.get("status_counts"),
            "join": {
                "event_source": join.get("event_source"),
                "events_total": join.get("events_total_in_source"),
                "events_covered_by_pilot": join.get("events_covered_by_pilot"),
            },
        },
        "unresolved_issues": UNRESOLVED,
        "checks": checks,
        "next_steps": [
            "A、B 确认规则 v0.1 的纳入/排除口径后固定字段与版本号。",
            "按复核差异起草 ai_rules_v0.2：裸 ai 词元降权、个人主页与课程作业排除、名称命中改查 README。",
            "A 扩展事件时间窗后，B 在同一规则版本上重跑全部候选仓库，而不是只跑这 50 个。",
        ],
        "run_dir": project_relative(run_dir),
    }
    summary["meta"] = meta
    write_json(run_dir / "run_summary.json", summary)
    return meta


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="汇总并核对 B 的试跑结果")
    parser.add_argument("--config", default=str(B_ROOT / "config" / "pilot.json"))
    parser.add_argument("--run-dir", help="运行目录；默认 runs/<pilot_version>")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    run_dir = Path(args.run_dir or (B_ROOT / "runs" / config["pilot_version"]))
    meta = build(run_dir)
    print(f"labels={meta['outputs']['labels']}")
    print(f"fetch_status={meta['outputs']['fetch_status']}")
    print(f"checks={meta['checks']}")
    failed = [name for name, passed in meta["checks"].items() if not passed]
    if failed:
        print(f"WARNING: failed checks: {failed}", file=sys.stderr)
        return 2
    print(f"run summary: {project_relative(run_dir / 'run_summary.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
