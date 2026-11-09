"""对比两个规则版本的标签结果，并给出每条变化的理由与人工判断对照。

输出：

- ``label_changes.csv``：每个标签发生变化的仓库一行，含旧/新规则 ID 与变化原因；
- ``label_comparison.json``：3×3 混淆矩阵、按规则计数、与人工复核的一致性对比。

人工判断的比对口径与 ``review.py`` 一致：
``agree``（自动=人工）、``resolves``（自动存疑、人工已判定）、
``disagree``（自动已判定但与人工相反）、``kept_uncertain``（两边都存疑）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .common import project_relative, read_csv, update_run_summary, utc_now, write_csv, write_json

CHANGE_FIELDS = [
    "repo_id",
    "observed_repo_name",
    "old_label",
    "old_rule",
    "new_label",
    "new_rule",
    "change_type",
    "explanation",
]

# (旧规则, 新规则) → 变化原因；未覆盖的组合回退为通用描述。
EXPLANATIONS: dict[tuple[str, str], str] = {
    ("R4_topic_match", "R4b_weak_topic_only"): (
        "裸 ai/ml topic 在 v0.2 降为弱信号且描述无佐证词，由 included 改判 uncertain，交人工复核"
    ),
    ("R5_description_match", "R3b_coursework"): (
        "v0.2 新增课程作业识别：仓库名或描述命中 course/final-project/assignment 等，改判 excluded"
    ),
    ("R3_resource_collection", "R3b_coursework"): (
        "课程/作业类仓库改由更具体的 R3b_coursework 记录理由，标签仍为 excluded"
    ),
    ("R5_description_match", "R5b_weak_signal_corroborated"): (
        "ai/ml 词元由描述中的佐证词（如 sdk/platform/model）确认，标签仍为 included，仅规则理由变化"
    ),
    ("R6_name_only_signal", "R5b_weak_signal_corroborated"): (
        "v0.2 把弱信号与佐证词结合后纳入，由 uncertain 改判 included"
    ),
    ("R7_insufficient_text_evidence", "R3b_coursework"): (
        "v0.2 从仓库名识别出课程作业（如 Openclassrooms/P11），由 uncertain 改判 excluded"
    ),
    ("R7_insufficient_text_evidence", "R3c_profile_repository"): (
        "v0.2 新增个人主页仓库识别（owner/repo 同名且描述与 topics 都为空），改判 excluded"
    ),
    ("R6_name_only_signal", "R4b_weak_topic_only"): (
        "topic 中的 ai/ml 在 v0.2 为弱信号，标签仍为 uncertain，规则理由更具体"
    ),
    # v0.3：README 辅助与个人主页口径调整
    ("R3c_profile_repository", "R3c_profile_suspected"): (
        "v0.3 把个人主页改为疑似（需 README 确认）；README 无文字证据时维持 uncertain"
    ),
    ("R3c_profile_repository", "R11_readme_profile"): (
        "v0.3 用 README 确认个人主页后排除：同名 + 无描述/topics/语言 + README 自我介绍"
    ),
    ("R6_name_only_signal", "R9_readme_ai"): (
        "v0.3 允许 README 辅助：README 出现明确 AI 技术证据，由 uncertain 改判 included"
    ),
    ("R7_insufficient_text_evidence", "R9_readme_ai"): (
        "v0.3 允许 README 辅助：描述为空但 README 有明确 AI 证据，由 uncertain 改判 included"
    ),
    ("R6_name_only_signal", "R10_readme_coursework"): (
        "v0.3 用 README 确认课程/训练营资料，由 uncertain 改判 excluded"
    ),
    ("R7_insufficient_text_evidence", "R10_readme_coursework"): (
        "v0.3 用 README 确认课程/训练营资料，由 uncertain 改判 excluded"
    ),
    ("R4b_weak_topic_only", "R9_readme_ai"): (
        "v0.3 用 README 补足弱信号：README 有明确 AI 证据，由 uncertain 改判 included"
    ),
    ("R5c_weak_signal_only", "R9_readme_ai"): (
        "v0.3 用 README 补足弱信号：README 有明确 AI 证据，由 uncertain 改判 included"
    ),
}


def _explain(old_rule: str, new_rule: str) -> str:
    return EXPLANATIONS.get((old_rule, new_rule), f"规则调整：{old_rule} → {new_rule}")


def _human_category(auto_label: str, human_label: str) -> str:
    if auto_label == human_label:
        return "kept_uncertain" if auto_label == "uncertain" else "agree"
    if auto_label == "uncertain":
        return "resolves"
    if human_label == "uncertain":
        return "disagree"
    return "disagree"


def _score(labels: Mapping[str, str], human: Mapping[str, str]) -> dict[str, Any]:
    categories: dict[str, int] = {}
    for repo_id, human_label in human.items():
        auto_label = labels.get(repo_id)
        if auto_label is None or not human_label:
            continue
        category = _human_category(auto_label, human_label)
        categories[category] = categories.get(category, 0) + 1
    reviewed = sum(categories.values())
    decided = categories.get("agree", 0) + categories.get("disagree", 0)
    return {
        "reviewed_rows": reviewed,
        "agree": categories.get("agree", 0),
        "disagree": categories.get("disagree", 0),
        "resolves": categories.get("resolves", 0),
        "kept_uncertain": categories.get("kept_uncertain", 0),
        "agreement_rate_on_decided_rows": round(categories.get("agree", 0) / decided, 4) if decided else None,
    }


def run(
    *,
    old_labels_csv: Path,
    new_labels_csv: Path,
    metadata_csv: Path,
    out_dir: Path,
    manual_review_csv: Path | None = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    old_rows = {row["repo_id"]: row for row in read_csv(old_labels_csv)}
    new_rows = {row["repo_id"]: row for row in read_csv(new_labels_csv)}
    metadata = {row["repo_id"]: row for row in read_csv(metadata_csv)}
    if set(old_rows) != set(new_rows):
        raise ValueError("label tables cover different repo_id sets")

    changes: list[dict[str, str]] = []
    matrix: dict[str, dict[str, int]] = {label: {} for label in ("included", "excluded", "uncertain")}
    per_rule_old: dict[str, int] = {}
    per_rule_new: dict[str, int] = {}
    for repo_id, new in new_rows.items():
        old = old_rows[repo_id]
        matrix[old["ai_label"]][new["ai_label"]] = matrix[old["ai_label"]].get(new["ai_label"], 0) + 1
        per_rule_old[old["rule_id"]] = per_rule_old.get(old["rule_id"], 0) + 1
        per_rule_new[new["rule_id"]] = per_rule_new.get(new["rule_id"], 0) + 1
        if (old["ai_label"], old["rule_id"]) == (new["ai_label"], new["rule_id"]):
            continue
        changes.append(
            {
                "repo_id": repo_id,
                "observed_repo_name": metadata.get(repo_id, {}).get("observed_repo_name", ""),
                "old_label": old["ai_label"],
                "old_rule": old["rule_id"],
                "new_label": new["ai_label"],
                "new_rule": new["rule_id"],
                "change_type": f"{old['ai_label']}->{new['ai_label']}" if old["ai_label"] != new["ai_label"] else "rule_reason_only",
                "explanation": _explain(old["rule_id"], new["rule_id"]),
            }
        )
    changes.sort(key=lambda row: (row["change_type"], int(row["repo_id"])))
    write_csv(out_dir / "label_changes.csv", CHANGE_FIELDS, changes)

    summary: dict[str, Any] = {
        "compared_at_utc": utc_now(),
        "old_labels": project_relative(old_labels_csv),
        "new_labels": project_relative(new_labels_csv),
        "old_rule_version": next(iter(old_rows.values()))["rule_version"],
        "new_rule_version": next(iter(new_rows.values()))["rule_version"],
        "rows": len(new_rows),
        "changed_rows": len(changes),
        "label_changed_rows": sum(1 for row in changes if row["change_type"] != "rule_reason_only"),
        "rule_reason_changed_rows": sum(1 for row in changes if row["change_type"] == "rule_reason_only"),
        "confusion_matrix": {old: dict(sorted(news.items())) for old, news in matrix.items()},
        "per_rule_old": dict(sorted(per_rule_old.items())),
        "per_rule_new": dict(sorted(per_rule_new.items())),
        "changes_csv": project_relative(out_dir / "label_changes.csv"),
    }

    if manual_review_csv and Path(manual_review_csv).exists():
        review_rows = read_csv(manual_review_csv)
        human = {row["repo_id"]: row["human_label"] for row in review_rows if row.get("human_label")}
        old_labels = {repo_id: row["ai_label"] for repo_id, row in old_rows.items()}
        new_labels = {repo_id: row["ai_label"] for repo_id, row in new_rows.items()}
        score_old = _score(old_labels, human)
        score_new = _score(new_labels, human)
        improved = []
        regressed = []
        for repo_id, human_label in human.items():
            before = _human_category(old_labels[repo_id], human_label)
            after = _human_category(new_labels[repo_id], human_label)
            if before != "agree" and after == "agree":
                improved.append(repo_id)
            elif before == "agree" and after != "agree":
                regressed.append(repo_id)
        summary["human_review"] = {
            "reviewed_rows": len(human),
            "old_version": score_old,
            "new_version": score_new,
            "improved_repo_ids": sorted(improved, key=int),
            "regressed_repo_ids": sorted(regressed, key=int),
            "still_uncertain_repo_ids": sorted(
                (repo_id for repo_id in human if new_labels[repo_id] == "uncertain"), key=int
            ),
            "note": "人工判断来自 v0.1 复核（manual_review.csv），这里用于比较两个版本与人工结论的吻合度。",
        }

    write_json(out_dir / "label_comparison.json", summary)
    update_run_summary(out_dir / "run_summary.json", "label_comparison", summary)
    return summary


def load_comparison(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)
