"""把 ``rules/ai_rules_v0.1.json`` 应用到 ``repo_metadata.csv``。

规则版本、优先级和理由都来自 JSON 文件，代码只负责执行与记录，避免“规则写在
代码里、说明写在文档里”两套事实。

判定顺序（先命中先返回）：

=====================================  ==========================================
规则                                    结果
=====================================  ==========================================
R1 metadata_unavailable                 uncertain（含 404/网络错误/5xx）
R2 api_id_mismatch                      uncertain（同名不同 ID）
R3 resource_collection                  excluded（awesome/教程/课程作业等）
R4 topic_match                          included
R5 description_match                    included
R6 name_only_signal                     uncertain（只有名称像 AI）
R7 insufficient_text_evidence            uncertain（描述与 topic 都为空）
R8 no_ai_signal                         excluded
=====================================  ==========================================
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .common import read_json, utc_now

LABEL_FIELDS = [
    "repo_id",
    "ai_label",
    "reason",
    "rule_version",
    "rule_id",
    "metadata_fetched_at_utc",
    "labelled_at_utc",
]

VALID_LABELS = ("included", "excluded", "uncertain")
FETCHED_STATUSES = ("ok", "ok_cached")


def load_rules(path: str | Path) -> dict[str, Any]:
    rules = read_json(path)
    if not isinstance(rules, dict) or "version" not in rules:
        raise ValueError(f"rules file missing 'version': {path}")
    return rules


def _compile(entries: Sequence[Mapping[str, str]]) -> list[tuple[str, re.Pattern[str]]]:
    compiled: list[tuple[str, re.Pattern[str]]] = []
    for entry in entries:
        compiled.append((entry["id"], re.compile(entry["regex"], re.IGNORECASE)))
    return compiled


def _matches(compiled: Sequence[tuple[str, re.Pattern[str]]], text: str) -> list[str]:
    if not text:
        return []
    return [name for name, pattern in compiled if pattern.search(text)]


class RuleSet:
    """编译后的规则集合；构造一次即可重复判定。"""

    def __init__(self, rules: dict[str, Any]) -> None:
        self.version: str = rules["version"]
        self.topic_terms = {term.lower() for term in rules.get("ai_topic_terms", [])}
        self.description = _compile(rules.get("ai_description_patterns", []))
        self.resource_description = _compile(rules.get("resource_collection_patterns", []))
        self.resource_name = _compile(rules.get("resource_name_patterns", []))
        self.name_signals = _compile(rules.get("name_signal_patterns", []))

    # -- 单条判定 ------------------------------------------------------
    def decide(self, metadata: Mapping[str, Any], *, labelled_at: str | None = None) -> dict[str, str]:
        status = (metadata.get("fetch_status") or "").strip()
        repo_id = str(metadata.get("repo_id", ""))
        fetched_at = metadata.get("fetched_at_utc") or ""
        labelled = labelled_at or utc_now()

        def result(label: str, rule_id: str, reason: str) -> dict[str, str]:
            return {
                "repo_id": repo_id,
                "ai_label": label,
                "reason": f"{rule_id}:{reason}" if reason else rule_id,
                "rule_version": self.version,
                "rule_id": rule_id,
                "metadata_fetched_at_utc": fetched_at,
                "labelled_at_utc": labelled,
            }

        if status == "id_mismatch":
            return result(
                "uncertain",
                "R2_api_id_mismatch",
                f"api_id={metadata.get('api_repo_id') or ''} observed_name={metadata.get('current_full_name') or ''}",
            )
        if status not in FETCHED_STATUSES:
            return result("uncertain", "R1_metadata_unavailable", f"fetch_status={status or 'missing'}")

        description = (metadata.get("description") or "").strip()
        full_name = (metadata.get("current_full_name") or metadata.get("observed_repo_name") or "").strip()
        try:
            topics = json.loads(metadata.get("topics_json") or "[]")
        except json.JSONDecodeError:
            topics = []
        topics = [str(topic).lower() for topic in topics if str(topic).strip()]

        resource_hits = _matches(self.resource_name, full_name) + _matches(
            self.resource_description, description
        )
        if resource_hits:
            return result("excluded", "R3_resource_collection", ",".join(_dedupe(resource_hits)))

        topic_hits = [topic for topic in topics if topic in self.topic_terms]
        if topic_hits:
            return result("included", "R4_topic_match", "topics=" + ",".join(topic_hits))

        description_hits = _matches(self.description, description)
        if description_hits:
            return result("included", "R5_description_match", "description=" + ",".join(_dedupe(description_hits)))

        name_hits = _matches(self.name_signals, full_name.lower())
        if name_hits:
            return result("uncertain", "R6_name_only_signal", "name=" + ",".join(_dedupe(name_hits)))

        if not description and not topics:
            return result("uncertain", "R7_insufficient_text_evidence", "description_and_topics_empty")

        return result("excluded", "R8_no_ai_signal", "no_rule_matched")


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return list(seen)


def label_rows(
    metadata_rows: Sequence[Mapping[str, Any]],
    rules: RuleSet,
    *,
    labelled_at: str | None = None,
) -> list[dict[str, str]]:
    moment = labelled_at or utc_now()
    return [rules.decide(row, labelled_at=moment) for row in metadata_rows]


def summary_counts(labels: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    by_label: dict[str, int] = {label: 0 for label in VALID_LABELS}
    by_rule: dict[str, int] = {}
    for row in labels:
        by_label[row["ai_label"]] = by_label.get(row["ai_label"], 0) + 1
        by_rule[row["rule_id"]] = by_rule.get(row["rule_id"], 0) + 1
    return {
        "total": len(labels),
        "by_label": by_label,
        "by_rule": dict(sorted(by_rule.items())),
        "label_sum_equals_total": sum(by_label.values()) == len(labels),
    }
