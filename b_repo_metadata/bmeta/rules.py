"""把 ``rules/ai_rules_v*.json`` 应用到 ``repo_metadata.csv``。

支持两代引擎，由 JSON 的 ``engine`` 字段选择：

- ``v1``（ai_rules_v0.1）：topic 精确命中即纳入；裸 ``ai``/``ml`` 也算强证据。
- ``v2``（ai_rules_v0.2）：strong/weak 信号分层、佐证词、课程作业与个人主页识别。

判定顺序（v2，先命中先返回）：

=====================================  ==========================================
规则                                    结果
=====================================  ==========================================
R1 metadata_unavailable                 uncertain
R2 api_id_mismatch                      uncertain
R3b coursework                          excluded
R3c profile_repository                  excluded
R3 resource_collection                  excluded
R4 topic_match（strong topic）           included
R5 description_match（strong 关键词）    included
R5b weak_signal_corroborated             included（弱信号 + 佐证词）
R4b weak_topic_only                      uncertain（只有裸 ai/ml topic）
R5c weak_signal_only                     uncertain（只有裸 ai/ml 描述）
R6 name_only_signal                      uncertain
R7 insufficient_text_evidence            uncertain
R8 no_ai_signal                          excluded
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


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return list(seen)


class RuleSet:
    """编译后的规则集合；构造一次即可重复判定。"""

    def __init__(self, rules: dict[str, Any]) -> None:
        self.version: str = rules["version"]
        self.engine: str = rules.get("engine", "v1")
        self.resource_description = _compile(rules.get("resource_collection_patterns", []))
        self.resource_name = _compile(rules.get("resource_name_patterns", []))
        self.name_signals = _compile(rules.get("name_signal_patterns", []))
        if self.engine == "v2":
            self.strong_topics = {term.lower() for term in rules.get("strong_topic_terms", [])}
            self.weak_topics = {term.lower() for term in rules.get("weak_topic_terms", [])}
            self.strong_description = _compile(rules.get("strong_description_patterns", []))
            self.weak_description = _compile(rules.get("weak_description_patterns", []))
            self.corroboration = _compile(rules.get("corroboration_patterns", []))
            self.coursework_description = _compile(rules.get("coursework_description_patterns", []))
            self.coursework_name = _compile(rules.get("coursework_name_patterns", []))
            self.profile_rule = dict(rules.get("profile_repository") or {})
        else:
            self.topic_terms = {term.lower() for term in rules.get("ai_topic_terms", [])}
            self.description = _compile(rules.get("ai_description_patterns", []))

    # -- 对外接口 ------------------------------------------------------
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

        if self.engine == "v2":
            return self._decide_v2(result, description, full_name, topics)
        return self._decide_v1(result, description, full_name, topics)

    # -- v1 ------------------------------------------------------------
    def _decide_v1(self, result, description: str, full_name: str, topics: Sequence[str]) -> dict[str, str]:
        resource_hits = _matches(self.resource_name, full_name) + _matches(self.resource_description, description)
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

    # -- v2 ------------------------------------------------------------
    def _decide_v2(self, result, description: str, full_name: str, topics: Sequence[str]) -> dict[str, str]:
        coursework_hits = _matches(self.coursework_name, full_name.lower()) + _matches(
            self.coursework_description, description
        )
        if coursework_hits:
            return result("excluded", "R3b_coursework", ",".join(_dedupe(coursework_hits)))

        if self._is_profile_repository(full_name, description, topics):
            return result("excluded", "R3c_profile_repository", f"name={full_name};no_description;no_topics")

        resource_hits = _matches(self.resource_name, full_name) + _matches(self.resource_description, description)
        if resource_hits:
            return result("excluded", "R3_resource_collection", ",".join(_dedupe(resource_hits)))

        strong_topic_hits = [topic for topic in topics if topic in self.strong_topics]
        if strong_topic_hits:
            return result("included", "R4_topic_match", "topics=" + ",".join(strong_topic_hits))

        strong_hits = _matches(self.strong_description, description)
        if strong_hits:
            return result("included", "R5_description_match", "description=" + ",".join(_dedupe(strong_hits)))

        weak_topic_hits = [topic for topic in topics if topic in self.weak_topics]
        weak_description_hits = _matches(self.weak_description, description)
        if weak_topic_hits or weak_description_hits:
            corroboration = _matches(self.corroboration, description)
            if corroboration:
                signals = ",".join(weak_topic_hits + _dedupe(weak_description_hits))
                return result(
                    "included",
                    "R5b_weak_signal_corroborated",
                    f"weak={signals};corroboration={','.join(_dedupe(corroboration))}",
                )
            if weak_topic_hits:
                return result("uncertain", "R4b_weak_topic_only", "topics=" + ",".join(weak_topic_hits))
            return result("uncertain", "R5c_weak_signal_only", "description=" + ",".join(_dedupe(weak_description_hits)))

        name_hits = _matches(self.name_signals, full_name.lower())
        if name_hits:
            return result("uncertain", "R6_name_only_signal", "name=" + ",".join(_dedupe(name_hits)))

        if not description and not topics:
            return result("uncertain", "R7_insufficient_text_evidence", "description_and_topics_empty")

        return result("excluded", "R8_no_ai_signal", "no_rule_matched")

    # -- 工具 ----------------------------------------------------------
    def _is_profile_repository(self, full_name: str, description: str, topics: Sequence[str]) -> bool:
        if not self.profile_rule.get("enabled"):
            return False
        owner, sep, repo = full_name.partition("/")
        if not sep or not owner or not repo:
            return False
        if owner.strip().lower() != repo.strip().lower():
            return False
        if self.profile_rule.get("require_description_empty", True) and description:
            return False
        if self.profile_rule.get("require_topics_empty", True) and topics:
            return False
        return True


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
