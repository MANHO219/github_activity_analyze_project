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
    "规则 v0.2 后仍有 19 个 uncertain：8 个是元数据缺失或空仓库（规则无法处理），11 个需要 README 才能判断（名称命中、弱信号、作品集等），而 v0.2 规则不读 README。",
    "待统一口径：弱信号是否直接 excluded、仅集成 AI 功能是否纳入、README 能否作为规则输入、课程作业边界。见 rules/ai_rules_v0.2.md 第 6 节。",
    "仓库元数据是 2026-11-02 的快照，不是 2024-01-15 事件发生时的状态；描述与 topics 可能已经变化。",
    "首批 50 个仓库为“40 随机 + 10 名称关键词过采样”的分层样本，不能用来估计整个 GitHub 的 AI 仓库比例。",
    "失败响应的缓存默认不复用，重跑会重新请求（已在 cache_retry_check.json 记录：5 个 404 重试、43 个成功响应命中缓存）。",
]


def build(run_dir: Path) -> dict:
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
    review_rows = read_csv(run_dir / "manual_review.csv")
    analysis_csv = run_dir / "repo_ai_labels_analysis.csv"
    analysis_rows = read_csv(analysis_csv) if analysis_csv.exists() else []

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
        "manual_review_complete": review.get("pending_rows") == 0 and review.get("reviewed_rows", 0) > 0,
        "manual_review_covers_three_labels": len(review.get("reviewed_by_scope", {})) == 3,
        "label_comparison_present": bool(comparison.get("old_rule_version")),
        "analysis_labels_cover_metadata": sorted(analysis_ids) == sorted(metadata_ids),
        "analysis_label_counts_sum": sum(final_labels.values()) == len(analysis_rows) if final_labels else False,
    }

    meta = {
        "pilot_version": pilot.get("pilot_version"),
        "seed": pilot.get("seed"),
        "strata": pilot.get("strata_actual"),
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
            "repo_metadata_sha256": sha256_file(run_dir / "repo_metadata.csv", normalize_newlines=True),
            "repo_ai_labels_sha256": sha256_file(run_dir / "repo_ai_labels.csv", normalize_newlines=True),
            "repo_ai_labels_v0_1_sha256": sha256_file(run_dir / "repo_ai_labels_v0.1.csv", normalize_newlines=True)
            if (run_dir / "repo_ai_labels_v0.1.csv").exists()
            else None,
            "analysis_labels_sha256": sha256_file(analysis_csv, normalize_newlines=True) if analysis_csv.exists() else None,
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
            "今晚统一口径：弱信号是否直接排除、AI 附加功能是否纳入、README 能否作为规则输入、课程作业边界。",
            "口径确认后按第 7 节流程起草 ai_rules_v0.3，并用 compare_label_versions.py 再做一次变化对比。",
            "确认标签交接口径：analysis_labels 默认 manual_override，可切换 auto_only。",
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
