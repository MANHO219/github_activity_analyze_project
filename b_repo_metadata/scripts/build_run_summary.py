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
    "元数据缺失或 API 返回 id 不一致的仓库一律保持 uncertain，不能据此推断删除、私有化或非 AI。",
    "README 证据是抓取时的快照，内容可能已变化；每行记录快照时间与 SHA-256，复核与判定都以此为准。",
    "试点仓库按分层抽样（名称关键词层过采样），不能用来估计整个 GitHub 的 AI 仓库比例。",
    "事件覆盖仍有限（pilot_01 一小时、pilot_02 全天），不足以支持生命周期结论，需等 A 扩展时间窗后重跑。",
    "失败响应默认不复用，重跑会重新请求；只有 HTTP 200 且响应体合法的成功响应进入缓存。",
]


def build(run_dir: Path, review_file: Path | None = None) -> dict:
    summary = read_json(run_dir / "run_summary.json")
    pilot = summary.get("pilot", {})
    fetch = summary.get("fetch", {})
    labels = summary.get("labels", {})
    join = summary.get("join", {})
    review = summary.get("manual_review", {})
    comparison = summary.get("label_comparison", {})
    analysis = summary.get("analysis_labels", {})

    metadata = read_csv(run_dir / "repo_metadata.csv")
    label_rows = read_csv(run_dir / "repo_ai_labels.csv")
    review_rows = read_csv(review_file) if review_file and Path(review_file).exists() else read_csv(run_dir / "manual_review.csv")
    analysis_csv = run_dir / "repo_ai_labels_analysis.csv"
    analysis_rows = read_csv(analysis_csv) if analysis_csv.exists() else []

    decided_review = [row for row in review_rows if (row.get("human_label") or "").strip()]
    decided_review = [row for row in review_rows if (row.get("human_label") or "").strip()]
    metadata_ids = [row["repo_id"] for row in metadata]
    label_ids = [row["repo_id"] for row in label_rows]
    analysis_ids = [row["repo_id"] for row in analysis_rows]
    by_label = labels.get("by_label", {})
    final_labels = analysis.get("final_labels", {})

    checks = {
        "fetch_processed_plus_pending_equals_input": fetch.get("processed_rows", 0) + fetch.get("pending_rows", 0)
        == fetch.get("input_rows", -1),
        "metadata_rows_equals_processed": len(metadata) == fetch.get("processed_rows", -1),
        "metadata_ids_unique": len(set(metadata_ids)) == len(metadata_ids),
        "labels_cover_metadata": sorted(label_ids) == sorted(metadata_ids),
        "label_counts_sum_equals_rows": sum(by_label.values()) == len(label_rows) if by_label else False,
        "join_checks_all_true": all(join.get("checks", {}).values()) if join.get("checks") else False,
        "manual_review_complete": len(decided_review) == len(review_rows) and len(review_rows) > 0,
        "manual_review_covers_three_labels": len({row["human_label"] for row in decided_review}) == 3,
        "label_comparison_present": bool(comparison.get("old_rule_version")),
        "analysis_labels_cover_metadata": sorted(analysis_ids) == sorted(metadata_ids),
        "analysis_label_counts_sum": sum(final_labels.values()) == len(analysis_rows) if final_labels else False,
    }

    meta = {
        "pilot_version": pilot.get("pilot_version"),
        "seed": pilot.get("seed"),
        "strata": pilot.get("strata_actual") or pilot.get("strata_requested"),
        "rules_version": labels.get("rules_version"),
        "rules_compared": [
            version
            for version in (comparison.get("old_rule_version"), comparison.get("new_rule_version"))
            if version
        ],
        "analysis_label_policy": analysis.get("policy"),
        "generated_at_utc": utc_now(),
        "environment": environment_snapshot(),
        "inputs": {
            "candidates_csv": pilot.get("input", {}).get("path"),
            "candidates_sha256": pilot.get("input", {}).get("sha256"),
            "pilot_candidates_sha256": pilot.get("output", {}).get("sha256"),
            "repo_metadata_sha256": sha256_file(run_dir / "repo_metadata.csv"),
            "repo_ai_labels_sha256": sha256_file(run_dir / "repo_ai_labels.csv"),
            "repo_ai_labels_v0_1_sha256": sha256_file(run_dir / "repo_ai_labels_v0.1.csv")
            if (run_dir / "repo_ai_labels_v0.1.csv").exists()
            else None,
            "analysis_labels_sha256": sha256_file(analysis_csv) if analysis_csv.exists() else None,
            "rules_sha256": labels.get("rules_sha256"),
        },
        "outputs": {
            "metadata_rows": len(metadata),
            "label_rows": len(label_rows),
            "review_rows": len(review_rows),
            "labels": by_label,
            "fetch_status": fetch.get("status_counts"),
            "label_changes": {
                "changed_rows": comparison.get("changed_rows"),
                "label_changed_rows": comparison.get("label_changed_rows"),
                "rule_reason_changed_rows": comparison.get("rule_reason_changed_rows"),
                "confusion_matrix": comparison.get("confusion_matrix"),
            },
            "human_agreement": {
                "old": comparison.get("human_review", {}).get("old_version"),
                "new": comparison.get("human_review", {}).get("new_version"),
                "improved_repo_ids": comparison.get("human_review", {}).get("improved_repo_ids"),
                "regressed_repo_ids": comparison.get("human_review", {}).get("regressed_repo_ids"),
            },
            "analysis_labels": {
                "policy": analysis.get("policy"),
                "final_labels": final_labels,
                "label_source": analysis.get("label_source"),
            },
            "join": {
                "event_source": join.get("event_source"),
                "events_total": join.get("events_total_in_source"),
                "events_covered_by_pilot": join.get("events_covered_by_pilot"),
                "events_covered_share_of_source": join.get("events_covered_share_of_source"),
            },
        },
        "unresolved_issues": UNRESOLVED,
        "checks": checks,
        "next_steps": [
            "等 A 扩展事件时间窗后，在同一规则版本上重跑全部候选仓库，而不是只跑试点样本。",
            "LLM API 辅助判断 uncertain：单独分支与 PR，先做 pilot_02 的小试验并记录成本。",
            "月级扩展前先补批量调度、失败续跑、跨日去重与按日分区。",
            "R12 的 purpose_patterns 与 R5d 的可选集成措辞仍缺真实样本，扩量后专门抽样验证。",
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
    parser.add_argument("--review", help="人工复核表；默认 <run-dir>/manual_review.csv")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    run_dir = Path(args.run_dir or (B_ROOT / "runs" / config["pilot_version"]))
    review = Path(args.review) if args.review else run_dir / "manual_review.csv"
    meta = build(run_dir, review)
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
