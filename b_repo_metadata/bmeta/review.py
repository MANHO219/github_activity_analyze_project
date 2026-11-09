"""人工复核：生成复核清单、合并人工判断、统计与规则的差异。

流程与交接要求对应：

1. ``manual_review.csv`` 先由脚本生成：每个 ``included``/``excluded`` 抽 5 个，
   ``uncertain`` 全查（不足 5 个时按实际数量全部复核）；
2. B 逐条读数、写 ``human_label`` / ``human_reason``，保存为
   ``reviews/pilot_01_decisions.json``；
3. 再次运行本模块把判断合并进 CSV，并输出一致率、被推翻的案例和规则调整线索。

自动标签与人工结论不一致时，保留两者，不覆盖自动结果——差异本身就是规则 v0.2 的输入。
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .common import (
    project_relative,
    read_json,
    update_run_summary,
    utc_now,
    write_csv,
    write_json,
)

REVIEW_FIELDS = [
    "review_rank",
    "review_scope",
    "repo_id",
    "observed_repo_name",
    "current_full_name",
    "sample_stratum",
    "ai_label_auto",
    "rule_id",
    "reason",
    "description",
    "topics_json",
    "language",
    "archived",
    "repo_created_at",
    "human_label",
    "human_reason",
    "agrees_with_rule",
    "reviewer",
    "reviewed_at_utc",
]


def select_targets(
    labels: Sequence[Mapping[str, str]],
    *,
    per_label: int = 5,
    uncertain_limit: int | None = None,
    seed: int = 5488,
) -> list[dict[str, str]]:
    """按标签分层抽取复核对象；同一输入与种子结果稳定。"""
    rng = random.Random(seed)
    targets: list[dict[str, str]] = []
    for label in ("included", "excluded", "uncertain"):
        group = sorted(
            (row for row in labels if row["ai_label"] == label),
            key=lambda row: int(row["repo_id"]),
        )
        if label == "uncertain":
            limit = len(group) if uncertain_limit is None else min(uncertain_limit, len(group))
        else:
            limit = min(per_label, len(group))
        picked = rng.sample(group, limit) if limit else []
        for row in sorted(picked, key=lambda item: int(item["repo_id"])):
            targets.append(dict(row, review_scope=label))
    for index, row in enumerate(targets, start=1):
        row["review_rank"] = index
    return targets


def build_sheet(
    labels: Sequence[Mapping[str, str]],
    metadata: Sequence[Mapping[str, str]],
    *,
    per_label: int = 5,
    uncertain_limit: int | None = None,
    seed: int = 5488,
) -> list[dict[str, str]]:
    by_id = {row["repo_id"]: row for row in metadata}
    sheet: list[dict[str, str]] = []
    for target in select_targets(labels, per_label=per_label, uncertain_limit=uncertain_limit, seed=seed):
        meta = by_id.get(target["repo_id"], {})
        sheet.append(
            {
                "review_rank": target["review_rank"],
                "review_scope": target["review_scope"],
                "repo_id": target["repo_id"],
                "observed_repo_name": meta.get("observed_repo_name", ""),
                "current_full_name": meta.get("current_full_name", ""),
                "sample_stratum": meta.get("sample_stratum", ""),
                "ai_label_auto": target["ai_label"],
                "rule_id": target["rule_id"],
                "reason": target["reason"],
                "description": meta.get("description", ""),
                "topics_json": meta.get("topics_json", ""),
                "language": meta.get("language", ""),
                "archived": meta.get("archived", ""),
                "repo_created_at": meta.get("repo_created_at", ""),
                "human_label": "",
                "human_reason": "",
                "agrees_with_rule": "",
                "reviewer": "",
                "reviewed_at_utc": "",
            }
        )
    return sheet


def merge_decisions(
    sheet: Sequence[Mapping[str, str]],
    decisions: Mapping[str, Any],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """把 B 的人工判断合并进复核清单，并统计一致率。"""
    reviewer = decisions.get("reviewer") or "B"
    reviewed_at = decisions.get("reviewed_at_utc") or utc_now()
    by_id: dict[str, dict[str, Any]] = {}
    for item in decisions.get("decisions", []):
        repo_id = str(item.get("repo_id", "")).strip()
        if not repo_id:
            raise ValueError("decision entry missing repo_id")
        if repo_id in by_id:
            raise ValueError(f"duplicate decision for repo_id={repo_id}")
        if item.get("human_label") not in ("included", "excluded", "uncertain"):
            raise ValueError(f"invalid human_label for repo_id={repo_id}: {item.get('human_label')!r}")
        if not (item.get("human_reason") or "").strip():
            raise ValueError(f"decision for repo_id={repo_id} needs human_reason")
        by_id[repo_id] = item

    known_ids = {row["repo_id"] for row in sheet}
    unknown = sorted(set(by_id) - known_ids)
    if unknown:
        raise ValueError(f"decisions reference repo_ids outside the review sheet: {unknown}")

    rows: list[dict[str, str]] = []
    for row in sheet:
        merged = dict(row)
        decision = by_id.get(row["repo_id"])
        if decision:
            human_label = decision["human_label"]
            merged["human_label"] = human_label
            merged["human_reason"] = decision["human_reason"]
            merged["reviewer"] = reviewer
            merged["reviewed_at_utc"] = reviewed_at
            if row["ai_label_auto"] == "uncertain" and human_label != "uncertain":
                merged["agrees_with_rule"] = "resolves_uncertain"
            else:
                merged["agrees_with_rule"] = "yes" if human_label == row["ai_label_auto"] else "no"
        rows.append(merged)

    reviewed = [row for row in rows if row["human_label"]]
    auto_decided = [row for row in reviewed if row["ai_label_auto"] in ("included", "excluded")]
    auto_uncertain = [row for row in reviewed if row["ai_label_auto"] == "uncertain"]
    agree = sum(1 for row in auto_decided if row["agrees_with_rule"] == "yes")
    disagree = sum(1 for row in auto_decided if row["agrees_with_rule"] == "no")
    resolved = sum(1 for row in auto_uncertain if row["agrees_with_rule"] == "resolves_uncertain")
    kept_uncertain = sum(1 for row in auto_uncertain if row["agrees_with_rule"] == "yes")
    summary = {
        "reviewer": reviewer,
        "reviewed_at_utc": reviewed_at,
        "policy": decisions.get("policy", ""),
        "sheet_rows": len(rows),
        "reviewed_rows": len(reviewed),
        "pending_rows": len(rows) - len(reviewed),
        "reviewed_by_scope": _count(reviewed, "review_scope"),
        "auto_decided_rows": {
            "reviewed": len(auto_decided),
            "agree": agree,
            "disagree": disagree,
            "agreement_rate": round(agree / len(auto_decided), 4) if auto_decided else None,
        },
        "auto_uncertain_rows": {
            "reviewed": len(auto_uncertain),
            "resolved_by_reviewer": resolved,
            "kept_uncertain": kept_uncertain,
            "resolution_rate": round(resolved / len(auto_uncertain), 4) if auto_uncertain else None,
        },
        "disagreements": [
            {
                "repo_id": row["repo_id"],
                "observed_repo_name": row["observed_repo_name"],
                "auto_label": row["ai_label_auto"],
                "human_label": row["human_label"],
                "rule_id": row["rule_id"],
                "human_reason": row["human_reason"],
            }
            for row in auto_decided
            if row["agrees_with_rule"] == "no"
        ],
        "resolved_uncertain_cases": [
            {
                "repo_id": row["repo_id"],
                "observed_repo_name": row["observed_repo_name"],
                "human_label": row["human_label"],
                "rule_id": row["rule_id"],
                "human_reason": row["human_reason"],
            }
            for row in auto_uncertain
            if row["agrees_with_rule"] == "resolves_uncertain"
        ],
        "decisions_file": decisions.get("_source"),
    }
    return rows, summary


def run(
    *,
    labels_csv: Path,
    metadata_csv: Path,
    out_dir: Path,
    decisions_path: Path | None = None,
    per_label: int = 5,
    uncertain_limit: int | None = None,
    seed: int = 5488,
    force: bool = False,
    allow_generate_sheet: bool = False,
) -> dict[str, Any]:
    """生成复核清单，或把人工判断合并进**已有**清单。

    两种模式刻意分开，避免组员重跑时覆盖历史记录或把不同轮次的判断混在一起：

    - 不给 ``decisions_path``：生成新一轮清单。目标文件已存在时抛
      ``FileExistsError``，必须显式 ``force=True`` 或换一个 ``out_dir``；
    - 给 ``decisions_path``：**必须已有** ``out_dir/manual_review.csv``，只把判断
      合并进去。清单不存在时默认抛 ``FileNotFoundError``，避免“按当前规则临时
      生成清单、再合并旧判断”把两轮结果混在一起；确实要这样做时显式传
      ``allow_generate_sheet=True``。

    摘要里把“清单用的规则版本”和“本次读取的标签版本”分开记录，并统计清单里的
    自动标签与当前标签有多少条不同，避免把对旧规则的人工一致率误读成对当前规则。
    """
    from .common import read_csv

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    labels = read_csv(labels_csv)
    metadata = read_csv(metadata_csv)
    if not labels:
        raise ValueError(f"no label rows in {labels_csv}")
    labels_rule_version = labels[0].get("rule_version", "")
    sheet_path = out_dir / "manual_review.csv"

    if decisions_path is None:
        if sheet_path.exists() and not force:
            raise FileExistsError(str(sheet_path))
        sheet = build_sheet(
            labels, metadata, per_label=per_label, uncertain_limit=uncertain_limit, seed=seed
        )
        write_csv(sheet_path, REVIEW_FIELDS, sheet)
        summary = {
            "status": "sheet_only",
            "sheet_rows": len(sheet),
            "reviewed_rows": 0,
            "sheet": project_relative(sheet_path),
            "labels_rule_version": labels_rule_version,
            "sheet_rule_version": labels_rule_version,
            "sheet_auto_labels_differ_from_current": 0,
            "reused_existing_sheet": False,
            "note": "新清单已生成；按清单逐条判断后写入 decisions JSON，再用 --decisions 合并。",
        }
        write_json(out_dir / "manual_review_summary.json", summary)
        update_run_summary(out_dir / "run_summary.json", "manual_review", summary)
        return summary

    # 合并模式：必须有已有清单，避免临时按当前规则生成后与旧判断混合。
    if not sheet_path.exists():
        if not allow_generate_sheet:
            raise FileNotFoundError(str(sheet_path))
        sheet = build_sheet(
            labels, metadata, per_label=per_label, uncertain_limit=uncertain_limit, seed=seed
        )
        sheet_source = "generated_sheet"
    else:
        sheet = read_csv(sheet_path)
        if not sheet:
            raise ValueError(f"existing review sheet is empty: {sheet_path}")
        sheet_source = "existing_sheet"

    decisions = read_json(decisions_path)
    if isinstance(decisions, list):
        decisions = {"decisions": decisions}
    decisions["_source"] = project_relative(decisions_path)
    rows, summary = merge_decisions(sheet, decisions)

    # 清单里的自动标签来自生成清单时的规则；与本次读到的标签版本对比，避免混淆。
    current_labels = {row["repo_id"]: row.get("ai_label", "") for row in labels}
    differing = [
        row["repo_id"]
        for row in sheet
        if row["repo_id"] in current_labels and row.get("ai_label_auto") != current_labels[row["repo_id"]]
    ]

    write_csv(sheet_path, REVIEW_FIELDS, rows)
    summary["sheet"] = project_relative(sheet_path)
    summary["status"] = "complete" if summary["pending_rows"] == 0 else "partial"
    summary["sheet_source"] = sheet_source
    summary["labels_rule_version"] = labels_rule_version
    summary["sheet_rule_version"] = (
        labels_rule_version if sheet_source == "generated_sheet" else "unknown_existing_sheet"
    )
    summary["sheet_auto_labels_differ_from_current"] = len(differing)
    summary["sheet_auto_labels_differ_repo_ids"] = differing
    summary["reused_existing_sheet"] = sheet_source == "existing_sheet"
    summary["note"] = (
        "合并使用的是已有清单；清单里的 ai_label_auto 由生成清单时的规则版本决定，"
        "与当前标签版本的差异见 sheet_auto_labels_differ_from_current。"
        if sheet_source == "existing_sheet"
        else "清单是按当前标签临时生成的（allow_generate_sheet），可能与旧判断来自不同轮次。"
    )
    write_json(out_dir / "manual_review_summary.json", summary)
    update_run_summary(out_dir / "run_summary.json", "manual_review", summary)
    return summary


def _count(rows: Iterable[Mapping[str, str]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row[key]] = counts.get(row[key], 0) + 1
    return dict(sorted(counts.items()))
