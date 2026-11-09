"""对 ``repo_metadata.csv`` 应用 AI 规则，产出 ``repo_ai_labels.csv``。

v0.3 起支持 README 辅助证据：只对规则判为 ``uncertain`` 的仓库补充判断，
并记录 README 快照时间与 SHA-256；规则已给出的 included/excluded 不会被覆盖。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .common import (
    project_relative,
    read_csv,
    read_jsonl,
    sha256_file,
    update_run_summary,
    utc_now,
    write_csv,
    write_json,
)
from .rules import LABEL_FIELDS, RuleSet, label_rows, load_rules, summary_counts


def _is_api_envelope(text: str) -> bool:
    """历史证据里可能把 GitHub 的错误/文件信封当成 README 正文存下来。

    这类文本不是 README，参与判定会让哈希与快照失真，按“没有正文”处理。
    """
    head = text.lstrip()[:40]
    return head.startswith('{"message"') or head.startswith('{"name":"README.md"')


def load_readme_evidence(path: Path | None) -> dict[str, dict[str, str]]:
    """读取复核/标注用 README 证据，返回 repo_id → {text, sha256, fetched_at_utc}。"""
    if path is None or not Path(path).exists():
        return {}
    evidence: dict[str, dict[str, str]] = {}
    for row in read_jsonl(path):
        if row.get("status") not in (None, "ok"):
            continue
        text = row.get("readme_excerpt") or ""
        if not text.strip() or _is_api_envelope(text):
            continue
        evidence[str(row.get("repo_id", ""))] = {
            "text": text,
            "sha256": row.get("readme_sha256") or "",
            "fetched_at_utc": row.get("fetched_at_utc") or "",
        }
    return evidence


def run(
    metadata_csv: Path,
    out_dir: Path,
    rules_path: Path,
    *,
    labelled_at: str | None = None,
    readme_evidence_path: Path | None = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    metadata_rows = read_csv(metadata_csv)
    if not metadata_rows:
        raise ValueError(f"no metadata rows in {metadata_csv}")

    rules = RuleSet(load_rules(rules_path))
    evidence = load_readme_evidence(readme_evidence_path)
    labels = label_rows(metadata_rows, rules, labelled_at=labelled_at, readme_evidence=evidence)
    write_csv(out_dir / "repo_ai_labels.csv", LABEL_FIELDS, labels)

    counts = summary_counts(labels)
    uncertain = [row for row in labels if row["ai_label"] == "uncertain"]
    used = [row for row in labels if row.get("readme_evidence") == "used"]
    summary = {
        "rules_version": rules.version,
        "rules_file": project_relative(rules_path),
        "rules_sha256": sha256_file(rules_path),
        "metadata_csv": project_relative(metadata_csv),
        "metadata_sha256": sha256_file(metadata_csv),
        "labelled_at_utc": labels[0]["labelled_at_utc"] if labels else utc_now(),
        "input_rows": len(metadata_rows),
        "labelled_rows": len(labels),
        "labels_csv": project_relative(out_dir / "repo_ai_labels.csv"),
        "labels_sha256": sha256_file(out_dir / "repo_ai_labels.csv"),
        **counts,
        "uncertain_repo_ids": [row["repo_id"] for row in uncertain],
        "readme_evidence": {
            "file": project_relative(readme_evidence_path) if readme_evidence_path else None,
            "available_repo_ids": sorted(evidence, key=int) if evidence else [],
            "used_rows": len(used),
            "used_repo_ids": [row["repo_id"] for row in used],
            "decisions": {row["rule_id"]: 0 for row in used},
            "note": "README 只补充 uncertain；快照时间与哈希写在每行 readme_* 字段。",
        },
        "counts_check": {
            "included+excluded+uncertain": sum(counts["by_label"].values()),
            "equals_input_rows": sum(counts["by_label"].values()) == len(metadata_rows),
            "unique_repo_ids": len({row["repo_id"] for row in labels}) == len(labels),
        },
    }
    for row in used:
        summary["readme_evidence"]["decisions"][row["rule_id"]] += 1
    write_json(out_dir / "label_summary.json", summary)
    update_run_summary(out_dir / "run_summary.json", "labels", summary)
    return summary


def sort_labels(labels: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    order = {"included": 0, "uncertain": 1, "excluded": 2}
    return sorted(labels, key=lambda row: (order.get(row["ai_label"], 9), int(row["repo_id"])))
