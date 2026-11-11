"""把自动标签与人工复核合并成“分析用标签”，并保留来源以便追溯。

三张表的关系：

- ``repo_ai_labels.csv``：规则输出的**自动标签**，覆盖全部 50 个仓库，可重复生成；
- ``manual_review.csv``：B 对 33 个仓库的**人工判断**，只覆盖被抽中的样本；
- ``repo_ai_labels_analysis.csv``：本模块生成的**分析用标签**，一行一个仓库，
  同时保留自动值、人工值与最终采用值，供 C 直接合并或按来源过滤。

采用哪种口径（人工优先 / 只用自动）需要 A、B 确认，因此本模块把口径写成参数，
默认 ``manual_override``，并允许随时用其他口径重算，不覆盖原始两表。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import (
    project_relative,
    read_csv,
    update_run_summary,
    utc_now,
    write_csv,
    write_json,
)

ANALYSIS_FIELDS = [
    "repo_id",
    "observed_repo_name",
    "ai_label_auto",
    "rule_id",
    "ai_label_manual",
    "ai_label_final",
    "label_source",
    "rule_version",
    "reason_auto",
    "reason_human",
    "metadata_fetched_at_utc",
    "labelled_at_utc",
    "policy",
]

VALID_POLICIES = ("manual_override", "auto_only")


def build(
    labels: list[dict[str, str]],
    metadata: list[dict[str, str]],
    review: list[dict[str, str]],
    *,
    policy: str,
    revisions: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    if policy not in VALID_POLICIES:
        raise ValueError(f"unknown policy: {policy!r}; expected one of {VALID_POLICIES}")
    names = {row["repo_id"]: row.get("observed_repo_name", "") for row in metadata}
    manual = {
        row["repo_id"]: row
        for row in review
        if (row.get("human_label") or "").strip() in ("included", "excluded", "uncertain")
    }
    # 人工修订晚于原复核记录：按 repo_id 覆盖，原文件保持不动，修订单独留痕。
    for row in revisions or []:
        if (row.get("human_label") or "").strip() in ("included", "excluded", "uncertain"):
            manual[row["repo_id"]] = row
    rows: list[dict[str, str]] = []
    for row in labels:
        repo_id = row["repo_id"]
        manual_row = manual.get(repo_id)
        manual_label = manual_row["human_label"] if manual_row else ""
        if policy == "manual_override" and manual_label:
            final_label = manual_label
            source = "manual_review"
        else:
            final_label = row["ai_label"]
            source = "auto_rule"
        rows.append(
            {
                "repo_id": repo_id,
                "observed_repo_name": names.get(repo_id, ""),
                "ai_label_auto": row["ai_label"],
                "rule_id": row["rule_id"],
                "ai_label_manual": manual_label,
                "ai_label_final": final_label,
                "label_source": source,
                "rule_version": row["rule_version"],
                "reason_auto": row["reason"],
                "reason_human": manual_row.get("human_reason", "") if manual_row else "",
                "metadata_fetched_at_utc": row.get("metadata_fetched_at_utc", ""),
                "labelled_at_utc": row.get("labelled_at_utc", ""),
                "policy": policy,
            }
        )
    return rows


def run(
    *,
    labels_csv: Path,
    metadata_csv: Path,
    out_dir: Path,
    review_csv: Path | None = None,
    revisions_csv: Path | None = None,
    policy: str = "manual_override",
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    labels = read_csv(labels_csv)
    metadata = read_csv(metadata_csv)
    review = read_csv(review_csv) if review_csv and Path(review_csv).exists() else []
    revisions = read_csv(revisions_csv) if revisions_csv and Path(revisions_csv).exists() else []

    rows = build(labels, metadata, review, policy=policy, revisions=revisions)
    out_csv = out_dir / "repo_ai_labels_analysis.csv"
    write_csv(out_csv, ANALYSIS_FIELDS, rows)

    final_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for row in rows:
        final_counts[row["ai_label_final"]] = final_counts.get(row["ai_label_final"], 0) + 1
        source_counts[row["label_source"]] = source_counts.get(row["label_source"], 0) + 1

    overridden = [
        row for row in rows if row["ai_label_manual"] and row["ai_label_manual"] != row["ai_label_auto"]
    ]
    summary = {
        "generated_at_utc": utc_now(),
        "policy": policy,
        "policy_note": (
            "人工复核优先：有人工判断的仓库采用人工标签，其余采用规则自动标签。"
            if policy == "manual_override"
            else "只用规则自动标签；人工判断保留在 manual_review.csv 中作为审计记录。"
        ),
        "rows": len(rows),
        "final_labels": dict(sorted(final_counts.items())),
        "label_source": dict(sorted(source_counts.items())),
        "manual_rows": sum(1 for row in rows if row["ai_label_manual"]),
        "manual_coverage": round(sum(1 for row in rows if row["ai_label_manual"]) / len(rows), 4) if rows else None,
        "manual_differs_from_auto": len(overridden),
        "manual_differs_repo_ids": [row["repo_id"] for row in overridden],
        "revision_rows": len(
            [row for row in revisions if (row.get("human_label") or "").strip() in ("included", "excluded", "uncertain")]
        ),
        "revision_repo_ids": sorted(
            {
                row["repo_id"]
                for row in revisions
                if (row.get("human_label") or "").strip() in ("included", "excluded", "uncertain")
            },
            key=int,
        ),
        "inputs": {
            "labels_csv": project_relative(labels_csv),
            "metadata_csv": project_relative(metadata_csv),
            "review_csv": project_relative(review_csv) if review_csv else None,
            "revisions_csv": project_relative(revisions_csv) if revisions_csv else None,
        },
        "output_csv": project_relative(out_csv),
        "decision_pending": "最终采用自动、人工还是混合口径，需 A、B 确认（见 LABELS.md）。",
    }
    write_json(out_dir / "label_analysis_summary.json", summary)
    update_run_summary(out_dir / "run_summary.json", "analysis_labels", summary)
    return summary
