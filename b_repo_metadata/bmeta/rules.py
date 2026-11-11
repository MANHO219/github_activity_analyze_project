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
    "readme_evidence",
    "readme_sha256",
    "readme_fetched_at_utc",
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


_CJK_ASCII_BOUNDARY = re.compile(
    r"(?<=[\u4e00-\u9fff])(?=[A-Za-z0-9])|(?<=[A-Za-z0-9])(?=[\u4e00-\u9fff])"
)


def _normalize_text(text: str) -> str:
    """在中英文/数字相邻处插入空格，让 ``\\b`` 在中文里也能正确判断词边界。

    例如“用Resnet101+GPT搭建一个玩王者荣耀的AI”会变成“用 Resnet101+GPT 搭建一个玩王者荣耀的 AI”，
    避免 ``\\bai\\b``、``\\bgpt\\b`` 因为中文是 Unicode 单词字符而匹配失败。
    """
    if not text:
        return ""
    return _CJK_ASCII_BOUNDARY.sub(" ", text)


def _normalize_name(name: str) -> str:
    """把 camelCase 拆成带分隔符的小写形式，供名称信号使用。

    ``ResnetGPT`` → ``resnet-gpt``（能命中 gpt），``Whispering-Origin-2D`` 仍是
    ``whispering-origin-2-d``（不会把 whispering 当成 whisper）。
    """
    if not name:
        return ""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", name).lower()


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
        # v0.3.8：资源合集按“主要用途”判定。curated / collection of / links to
        # 标成 weak（复核线索），其余仍是 strong；只有在描述/README 明确表示
        # 仓库主要提供清单时才自动排除，处理这些资料的工具按工具判断。
        resource_patterns = list(rules.get("resource_collection_patterns", []))
        resource_rule = dict(rules.get("resource_collection") or {})
        self.resource_require_primary = bool(resource_rule.get("require_primary_purpose", False))
        self.resource_strong = _compile(
            [entry for entry in resource_patterns if (entry.get("strength") or "strong") == "strong"]
        )
        self.resource_weak = _compile(
            [entry for entry in resource_patterns if entry.get("strength") == "weak"]
        )
        self.resource_lead = _compile(resource_rule.get("list_lead_patterns", []))
        self.resource_tool = _compile(resource_rule.get("tool_signal_patterns", []))
        # 明确写着“a tool / a CLI / a library”才算与清单冲突；泛动词（build、generate）
        # 太容易出现在教程类描述里，不参与 strong 的冲突判定。
        self.resource_tool_decl = _compile(
            [entry for entry in resource_rule.get("tool_signal_patterns", []) if entry.get("id") == "tool_declaration"]
        )
        self.name_signals = _compile(rules.get("name_signal_patterns", []))
        if self.engine in ("v2", "v3"):
            self.strong_topics = {term.lower() for term in rules.get("strong_topic_terms", [])}
            self.weak_topics = {term.lower() for term in rules.get("weak_topic_terms", [])}
            self.strong_description = _compile(rules.get("strong_description_patterns", []))
            self.weak_description = _compile(rules.get("weak_description_patterns", []))
            self.corroboration = _compile(rules.get("corroboration_patterns", []))
            self.coursework_description = _compile(rules.get("coursework_description_patterns", []))
            self.coursework_name = _compile(rules.get("coursework_name_patterns", []))
            self.profile_rule = dict(rules.get("profile_repository") or {})
            if self.engine == "v3":
                self.coursework_generic = _compile(rules.get("coursework_generic_name_patterns", []))
                self.coursework_corroboration = _compile(rules.get("coursework_corroboration_patterns", []))
                self.feature_only = _compile(rules.get("ai_feature_only_patterns", []))
                readme_rules = dict(rules.get("readme_rules") or {})
                self.readme_profile = _compile(readme_rules.get("profile_patterns", []))
                # v0.3.6 起把“统计卡/贡献蛇/typing 头图”这类组件单独成表：
                # 它们只说明“像主页”，还要没有 AI 证据、正文极短才够确认。
                self.readme_profile_widgets = _compile(readme_rules.get("profile_widget_patterns", []))
                self.readme_profile_widget_max_chars = int(
                    readme_rules.get("profile_widget_max_meaningful_chars", 200) or 200
                )
                self.readme_coursework = _compile(readme_rules.get("coursework_patterns", []))
                # v0.3.1 起把 README 的 AI 证据拆成强/弱两档，并引入未来意图与工程章节过滤；
                # 兼容只有 ai_patterns 的 v0.3 规则文件。
                if readme_rules.get("ai_strong_patterns") or readme_rules.get("ai_weak_patterns"):
                    self.readme_ai_strong = _compile(readme_rules.get("ai_strong_patterns", []))
                    self.readme_ai_weak = _compile(readme_rules.get("ai_weak_patterns", []))
                else:
                    self.readme_ai_strong = _compile(readme_rules.get("ai_patterns", []))
                    self.readme_ai_weak = []
                self.readme_ai = self.readme_ai_strong
                self.readme_future = _compile(readme_rules.get("future_markers", []))
                self.readme_project_sections = _compile(readme_rules.get("project_sections", []))
                self.min_weak_mentions = int(readme_rules.get("min_weak_mentions", 3) or 3)
                # R12 只在规则文件显式配置 readme_rules.non_ai 时启用。
                # v0.3.2 及更早版本没有这个配置，加载后不会触发 R12。
                non_ai = readme_rules.get("non_ai")
                if isinstance(non_ai, dict) and non_ai.get("enabled", True):
                    self.readme_non_ai_rule = non_ai.get("rule_id", "R12_readme_non_ai")
                    self.readme_non_ai_min_chars = int(non_ai.get("min_meaningful_chars", 200) or 200)
                    self.readme_non_ai_require_purpose = bool(non_ai.get("require_purpose", False))
                    self.readme_non_ai_allowed = set(non_ai.get("allowed_base_rules") or [])
                    self.readme_non_ai_purpose = _compile(non_ai.get("purpose_patterns", []))
                    self.readme_non_ai_template = _compile(non_ai.get("template_patterns", []))
                    # v0.3.4.1 起：只命中 About/Overview 标题还不够，标题下方必须有说明正文。
                    # 旧版本规则文件没有 purpose_requires_body，行为不变。
                    self.readme_non_ai_require_body = bool(non_ai.get("purpose_requires_body", False))
                    self.readme_non_ai_min_body_chars = int(non_ai.get("min_purpose_body_chars", 40) or 40)
                    # v0.3.4.2：Overview 下只有英文安装说明时不算“说明了用途”。
                    self.readme_non_ai_ignore_install = bool(non_ai.get("ignore_install_lines", False))
                    # v0.3.4.3：编号列表（1. Download…）要先剥标记再判断正文。
                    self.readme_non_ai_strip_markers = bool(non_ai.get("strip_list_markers", False))
                    # v0.3.4.3：新增的步骤动词（copy/add/open…）同样走开关，旧版本不变。
                    self.readme_non_ai_extra_verbs = bool(non_ai.get("extra_step_verbs", False))
                    self.readme_non_ai_heading = [
                        (name, pattern) for name, pattern in self.readme_non_ai_purpose if name == "purpose_heading"
                    ]
                else:
                    self.readme_non_ai_rule = None
                    self.readme_non_ai_min_chars = 0
                    self.readme_non_ai_require_purpose = False
                    self.readme_non_ai_allowed = set()
                    self.readme_non_ai_purpose = []
                    self.readme_non_ai_template = []
                    self.readme_non_ai_require_body = False
                    self.readme_non_ai_min_body_chars = 40
                    self.readme_non_ai_ignore_install = False
                    self.readme_non_ai_strip_markers = False
                    self.readme_non_ai_extra_verbs = False
                    self.readme_non_ai_heading = []
                # README 的“可选 AI 集成”排除与“课程覆盖”都只在规则文件显式配置时启用。
                self.readme_feature_only = _compile(readme_rules.get("feature_only_patterns", []))
                course_override = readme_rules.get("course_override")
                if isinstance(course_override, dict) and course_override.get("enabled", True):
                    self.readme_course_override_rule = course_override.get(
                        "rule_id", "R13_course_override"
                    )
                    self.readme_course_positive = _compile(course_override.get("positive_patterns", []))
                    self.readme_course_negative = _compile(course_override.get("negative_patterns", []))
                else:
                    self.readme_course_override_rule = None
                    self.readme_course_positive = []
                    self.readme_course_negative = []
        else:
            self.topic_terms = {term.lower() for term in rules.get("ai_topic_terms", [])}
            self.description = _compile(rules.get("ai_description_patterns", []))

    # -- 对外接口 ------------------------------------------------------
    def decide(
        self,
        metadata: Mapping[str, Any],
        *,
        labelled_at: str | None = None,
        readme: Mapping[str, Any] | None = None,
    ) -> dict[str, str]:
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
                "readme_evidence": "",
                "readme_sha256": "",
                "readme_fetched_at_utc": "",
            }

        if status == "id_mismatch":
            return result(
                "uncertain",
                "R2_api_id_mismatch",
                f"api_id={metadata.get('api_repo_id') or ''} observed_name={metadata.get('current_full_name') or ''}",
            )
        if status not in FETCHED_STATUSES:
            return result("uncertain", "R1_metadata_unavailable", f"fetch_status={status or 'missing'}")

        description = _normalize_text((metadata.get("description") or "").strip())
        raw_name = (metadata.get("current_full_name") or metadata.get("observed_repo_name") or "").strip()
        full_name = _normalize_name(raw_name)
        language = (metadata.get("language") or "").strip()
        try:
            topics = json.loads(metadata.get("topics_json") or "[]")
        except json.JSONDecodeError:
            topics = []
        topics = [str(topic).lower() for topic in topics if str(topic).strip()]

        if self.engine == "v3":
            return self._decide_v3(result, description, full_name, topics, language, readme, raw_name)
        if self.engine == "v2":
            return self._decide_v2(result, description, full_name, topics)
        return self._decide_v1(result, description, full_name, topics)

    # -- 资源合集 --------------------------------------------------------
    def _resource_result(
        self,
        full_name: str,
        description: str,
    ) -> tuple[str, str, str] | None:
        """资源合集的判定结果；None 表示“不是合集，继续走后面的规则”。

        旧版本只看“有没有命中清单词”，于是把“用 LLM 总结一份论文列表的工具”
        也当成合集排除。v0.3.8 起看主要用途：

        - strong（awesome-/tutorial/整段 papers 清单等）命中 → 排除；
          但如果描述里同时有工具语义，就是冲突，保留 uncertain；
        - weak（curated / collection of / links to / 中间的 list of）命中时，
          只有描述开头就是清单表述（list lead）才排除；
        - weak 命中且有工具语义 → 按工具判断（返回 None）；
        - weak 命中但没有任何用途说明 → 保留 uncertain，不自动排除。
        """
        name_hits = _matches(self.resource_name, full_name)
        if not self.resource_require_primary:
            desc_hits = _matches(self.resource_description, description)
            if not (name_hits or desc_hits):
                return None
            return ("excluded", "R3_resource_collection", ",".join(_dedupe(name_hits + desc_hits)))

        strong_hits = name_hits + _matches(self.resource_strong, description)
        weak_hits = _matches(self.resource_weak, description)
        if not (strong_hits or weak_hits):
            return None

        hits = ",".join(_dedupe(strong_hits + weak_hits))
        tool = _matches(self.resource_tool, description)

        if strong_hits:
            # 只有“明确声明自己是工具”才构成冲突；教程里出现 build/generate 不算。
            conflict = _matches(self.resource_tool_decl, description)
            if conflict:
                return (
                    "uncertain",
                    "R3b_resource_vs_tool",
                    f"list={hits};tool={','.join(_dedupe(conflict))}",
                )
            return ("excluded", "R3_resource_collection", hits)

        if _matches(self.resource_lead, description):
            # 开头就是“A curated list of …”：明确在提供清单；有工具语义时按工具走。
            if tool:
                return None
            return ("excluded", "R3_resource_collection", hits)

        if tool:
            return None
        return ("uncertain", "R3c_resource_mention_only", f"mention={hits}")

    # -- v1 ------------------------------------------------------------
    def _decide_v1(self, result, description: str, full_name: str, topics: Sequence[str]) -> dict[str, str]:
        resource = self._resource_result(full_name, description)
        if resource:
            return result(*resource)

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

        resource = self._resource_result(full_name, description)
        if resource:
            return result(*resource)

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

    # -- v3 ------------------------------------------------------------
    def _decide_v3(self, result, description, full_name, topics, language, readme, raw_name=""):
        base = self._base_v3(result, description, full_name, topics, language, raw_name)
        if not readme or not (readme.get("text") or "").strip():
            return base
        text = _normalize_text(readme["text"])
        sha = readme.get("sha256") or ""
        fetched = readme.get("fetched_at_utc") or ""
        usable = self._readme_without_future(text)

        def with_readme(label: str, rule_id: str, reason: str) -> dict[str, str]:
            row = result(label, rule_id, reason)
            row["readme_evidence"] = "used"
            row["readme_sha256"] = sha
            row["readme_fetched_at_utc"] = fetched
            return row

        def course_override_hits() -> list[str]:
            """README 明确“为课程/训练营制作”才算；仅参加或当作教学示例不算。"""
            if not self.readme_course_override_rule:
                return []
            positive = _matches(self.readme_course_positive, usable)
            if not positive:
                return []
            if _matches(self.readme_course_negative, usable):
                return []
            return positive

        # 规则已判 included 时，README 的“为课程/训练营制作”证据可以覆盖为 excluded。
        if base["ai_label"] == "included":
            override = course_override_hits()
            if override:
                return with_readme(
                    "excluded",
                    self.readme_course_override_rule,
                    "readme=" + ",".join(_dedupe(override)),
                )
            return base

        if base["ai_label"] != "uncertain":
            return base

        # 个人主页：只有规则本身已判为疑似（同名 + 无描述 + 无 topics + 无语言）时，
        # 才用 README 确认；README 还必须没有工程章节，避免把 ML 项目的作者介绍当成个人主页。
        if base["rule_id"] == "R3c_profile_suspected":
            profile_hits = _matches(self.readme_profile, text)
            # 组件命中的证据更弱：README 里有 AI 强证据，或正文足够长，就说明它可能是项目说明，
            # 不能因为多了一张统计卡就判成个人主页。
            if not profile_hits and self.readme_profile_widgets:
                if _matches(self.readme_profile_widgets, text):
                    if not _matches(self.readme_ai_strong, usable) and (
                        self._meaningful_chars(usable) < self.readme_profile_widget_max_chars
                    ):
                        profile_hits = ["readme_profile_widget"]
            if profile_hits and not _matches(self.readme_project_sections, text):
                return with_readme("excluded", "R11_readme_profile", "readme=" + ",".join(_dedupe(profile_hits)))

        course_hits = _matches(self.readme_coursework, text)
        if course_hits:
            return with_readme("excluded", "R10_readme_coursework", "readme=" + ",".join(_dedupe(course_hits)))

        # README 里若明确写 AI 只是可选集成，先排除，避免被下面的 AI 关键词纳入。
        if self.readme_feature_only:
            feature_hits = _matches(self.readme_feature_only, usable)
            if feature_hits:
                return with_readme(
                    "excluded",
                    "R5d_ai_feature_only",
                    "readme=" + ",".join(_dedupe(feature_hits)),
                )

        # AI 证据：先剔除“计划/以后/roadmap”这类未来意图行；要求强证据，
        # 或弱词出现至少 N 次且有佐证词，避免一句“以后打算加 AI”就被纳入。
        strong_hits = _matches(self.readme_ai_strong, usable)
        if strong_hits:
            override = course_override_hits()
            if override:
                return with_readme(
                    "excluded", self.readme_course_override_rule, "readme=" + ",".join(_dedupe(override))
                )
            return with_readme("included", "R9_readme_ai", "readme=" + ",".join(_dedupe(strong_hits)))

        weak_count = self._count_weak_mentions(usable)
        weak_hits = _matches(self.readme_ai_weak, usable)
        corroboration = _matches(self.corroboration, usable)
        if weak_count >= self.min_weak_mentions and corroboration and weak_hits:
            override = course_override_hits()
            if override:
                return with_readme(
                    "excluded", self.readme_course_override_rule, "readme=" + ",".join(_dedupe(override))
                )
            return with_readme(
                "included",
                "R9_readme_ai",
                f"readme={','.join(_dedupe(weak_hits))};mentions={weak_count};corroboration={','.join(_dedupe(corroboration))}",
            )

        # README 确认主体非 AI：正文明说项目用途、没有 AI/课程/主页证据，且只对
        # 描述与 topics 都为空的仓库生效。模板、脚手架或只有安装说明的 README 不算确认。
        if self.readme_non_ai_rule and not weak_hits:
            allowed = self.readme_non_ai_allowed
            if not allowed or base["rule_id"] in allowed:
                meaningful = self._meaningful_chars(usable)
                if meaningful >= self.readme_non_ai_min_chars:
                    purpose = (
                        _matches(self.readme_non_ai_purpose, usable)
                        if self.readme_non_ai_require_purpose
                        else ["legacy_no_purpose_check"]
                    )
                    # v0.3.4.1：标题命中必须伴随说明正文；空 Overview 标题 + 安装步骤不算用途证据。
                    if self.readme_non_ai_require_body and "purpose_heading" in purpose:
                        if not self._has_prose_body(self._purpose_heading_body(usable)):
                            purpose = [name for name in purpose if name != "purpose_heading"]
                    template_hits = (
                        _matches(self.readme_non_ai_template, usable)
                        if self.readme_non_ai_require_purpose
                        else []
                    )
                    if purpose and not template_hits:
                        return with_readme(
                            "excluded",
                            self.readme_non_ai_rule,
                            f"purpose={','.join(_dedupe(purpose))};readme_chars={meaningful};no_ai_evidence",
                        )

        base["readme_evidence"] = "no_signal"
        base["readme_sha256"] = sha
        base["readme_fetched_at_utc"] = fetched
        return base

    def _readme_without_future(self, text: str) -> str:
        if not self.readme_future:
            return text
        kept = [line for line in text.splitlines() if not _matches(self.readme_future, line)]
        return "\n".join(kept)

    def _count_weak_mentions(self, text: str) -> int:
        total = 0
        for _, pattern in self.readme_ai_weak:
            total += len(pattern.findall(text))
        return total

    _COMMAND_LINE = re.compile(
        r"^(npm|npx|yarn|pnpm|pip3?|git|docker(-compose)?|cargo|go|make|cmake|brew|apt(-get)?|sudo|curl|wget|"
        r"python3?|node|java|mvn|gradle|bundle|composer|conda|poetry|uv|dotnet|terraform|kubectl|helm)\b",
        re.IGNORECASE,
    )

    def _purpose_heading_body(self, text: str) -> str:
        """取 About/Overview 类标题下方、到下一个标题之前的段落，去掉代码块。"""
        if not self.readme_non_ai_heading:
            return ""
        collecting = False
        in_code = False
        parts: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_code = not in_code
                continue
            if in_code:
                continue
            if _matches(self.readme_non_ai_heading, stripped):
                collecting = True
                parts = []
                continue
            if collecting and re.match(r"^#{1,6}\s", stripped):
                break
            if collecting:
                parts.append(stripped)
        return "\n".join(parts)

    # v0.3.4.2 的词表：旧规则文件加载后必须保持原样，新增词只能走 EXTRA。
    _INSTRUCTION_LINE = re.compile(
        r"^(to\s+)?(install|installation|set\s*up|setup|run|execute|launch|start|build|compile|clone|download|"
        r"configure|usage|quick\s*start|getting\s+started|requirements?|prerequisites?|dependencies)\b",
        re.IGNORECASE,
    )
    # v0.3.4.3 新增的步骤动词，只在 extra_step_verbs 打开时生效。
    _INSTRUCTION_LINE_EXTRA = re.compile(
        r"^(to\s+)?(install|installation|set\s*up|setup|run|execute|launch|start|build|compile|clone|download|"
        r"copy|move|add|open|extract|edit|select|choose|click|navigate|chmod|export|source|configure|"
        r"usage|quick\s*start|getting\s+started|requirements?|prerequisites?|dependencies)\b",
        re.IGNORECASE,
    )
    # 有序/无序列表标记与 checkbox：A 的复测里 “1. Download…” 这类编号步骤
    # 因为开头是 “1.” 绕过了指令行判断，被当成正文。先剥标记再判断。
    _LIST_MARKER = re.compile(r"^(?:[-*+]\s+(?:\[[ xX]\]\s+)?|\(?\d{1,2}[.)]\s+)")
    _INSTRUCTION_HINT = re.compile(
        r"\bthe\s+following\s+(commands?|steps?)\b"
        r"|^(then|next|afterwards?|finally)\b[^.]{0,30}\b(run|install|execute|start|launch|build|clone|download)\b",
        re.IGNORECASE,
    )

    def _strip_list_marker(self, line: str) -> str:
        """去掉列表标记与 checkbox，最多剥两层（``1. - item``）。"""
        text = line
        for _ in range(2):
            new = self._LIST_MARKER.sub("", text, count=1).strip()
            if new == text:
                break
            text = new
        return text

    def _has_prose_body(self, body: str) -> bool:
        """正文里是否真的有说明性文字：命令行、空行、列表符号都不算。

        v0.3.4.2 起，英文安装说明（Install/Run/Setup 开头，或以冒号收尾的引导句）
        也不算用途说明——A 的复测里“Overview + 安装步骤”仍被误判为说明了用途。
        v0.3.4.3 起先剥掉 Markdown 列表标记：``1. Download…``、``2. Add…`` 这类
        编号步骤与 ``- Install …`` 一样按指令行处理。
        """
        kept: list[str] = []
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if self.readme_non_ai_strip_markers:
                stripped = self._strip_list_marker(stripped)
            if not stripped or stripped in ("-", "*", "+"):
                continue
            if stripped.startswith("$") or self._COMMAND_LINE.match(stripped):
                continue
            # 形如 “mytool --help” 的调用行也不当正文。
            if self.readme_non_ai_ignore_install and re.match(r"^[\w./@+-]+\s+--?\w", stripped):
                continue
            if self.readme_non_ai_ignore_install:
                instruction = (
                    self._INSTRUCTION_LINE_EXTRA if self.readme_non_ai_extra_verbs else self._INSTRUCTION_LINE
                )
                if instruction.match(stripped) or self._INSTRUCTION_HINT.search(stripped):
                    continue
                if stripped.endswith(":") and len(stripped) <= 80:
                    continue
            kept.append(stripped)
        return self._meaningful_chars("\n".join(kept)) >= self.readme_non_ai_min_body_chars

    def _meaningful_chars(self, text: str) -> int:
        """README 的有效正文字符数：去掉链接、图片、HTML 标签后的字母/数字/汉字数。"""
        cleaned = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
        cleaned = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", cleaned)
        cleaned = re.sub(r"https?://\S+", " ", cleaned)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        return len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", cleaned))

    def _base_v3(self, result, description, full_name, topics, language, raw_name=""):
        # 课程作业：强语义（final-project / openclassrooms / capstone）可直接判定；
        # 泛词（course/lab/hw 等）必须同时有描述佐证，避免只命中关键词就排除。
        strong_course = _matches(self.coursework_name, full_name.lower())
        if strong_course:
            return result("excluded", "R3b_coursework", "name=" + ",".join(_dedupe(strong_course)))
        description_course = _matches(self.coursework_description, description)
        if description_course:
            return result("excluded", "R3b_coursework", "description=" + ",".join(_dedupe(description_course)))

        generic_course = _matches(self.coursework_generic, full_name.lower())
        if generic_course:
            corroboration = _matches(self.coursework_corroboration, description)
            if corroboration:
                return result(
                    "excluded",
                    "R3b_coursework",
                    f"name={','.join(_dedupe(generic_course))};description={','.join(_dedupe(corroboration))}",
                )

        # 个人主页：只记疑似，交给 README 或人工确认。
        # 用原始名称判断 owner==repo，避免 camelCase 拆分后把同一个名字拆成两段。
        profile_name = raw_name or full_name
        if self._is_profile_repository(profile_name, description, topics, language):
            return result(
                "uncertain",
                "R3c_profile_suspected",
                f"name={profile_name};no_description;no_topics;no_language",
            )

        resource = self._resource_result(full_name, description)
        if resource:
            return result(*resource)

        # 明确把 AI 写成附加能力时才排除；以 AI 为核心的应用仍可纳入。
        feature_hits = _matches(self.feature_only, description)
        if feature_hits:
            return result("excluded", "R5d_ai_feature_only", "description=" + ",".join(_dedupe(feature_hits)))

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
    def _is_profile_repository(
        self,
        full_name: str,
        description: str,
        topics: Sequence[str],
        language: str = "",
    ) -> bool:
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
        if self.profile_rule.get("require_language_empty", False) and language:
            return False
        return True


def label_rows(
    metadata_rows: Sequence[Mapping[str, Any]],
    rules: RuleSet,
    *,
    labelled_at: str | None = None,
    readme_evidence: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, str]]:
    moment = labelled_at or utc_now()
    evidence = readme_evidence or {}
    return [
        rules.decide(
            row,
            labelled_at=moment,
            readme=evidence.get(str(row.get("repo_id", ""))),
        )
        for row in metadata_rows
    ]


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
