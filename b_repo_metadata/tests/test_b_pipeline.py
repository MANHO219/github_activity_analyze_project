"""B 阶段的可复现验证：已知输入 → 已知结论，全部离线，不访问 GitHub。

覆盖四件事：
1. 名单抽样的确定性与分层规模；
2. AI 规则在构造样本上的判定（包含、排除、存疑各分支）；
3. 抓取层对 200 / 404 / id 不一致 / 限流 / 缓存的处理；
4. 复核合并与 repo_id 接回的计数、唯一性和失败路径。
"""

from __future__ import annotations

import base64
import json
import shutil
import sys
import unittest
import urllib.error
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bmeta.api import GitHubRepoClient  # noqa: E402
from bmeta.common import read_csv, write_csv, write_json  # noqa: E402
from bmeta.evidence import _readme_text  # noqa: E402
from bmeta.fetch import METADATA_FIELDS, fetch_one, run as fetch_run  # noqa: E402
from bmeta.join import run as join_run  # noqa: E402
from bmeta.review import (  # noqa: E402
    REVIEW_FIELDS,
    build_sheet,
    merge_decisions,
    run as review_run,
)
from bmeta.rules import LABEL_FIELDS, RuleSet, label_rows, load_rules  # noqa: E402
from bmeta.select import select_pilot  # noqa: E402

B_ROOT = Path(__file__).resolve().parents[1]
RULES = RuleSet(load_rules(B_ROOT / "rules" / "ai_rules_v0.1.json"))
# 临时目录放在仓库内：受限环境可能不允许写系统临时目录，也不允许删除系统临时目录。
TEST_TMP_ROOT = B_ROOT / ".test_tmp"


def candidate(repo_id: int, name: str, events: int = 1) -> dict:
    return {
        "repo_id": str(repo_id),
        "repo_name": name,
        "first_observed_at": "2024-01-15T00:00:00Z",
        "last_observed_at": "2024-01-15T00:30:00Z",
        "event_count": str(events),
        "observed_name_count": "1",
    }


def metadata(repo_id: int, *, status="ok", description="", topics=(), name=None, api_id=None) -> dict:
    return {
        "repo_id": str(repo_id),
        "observed_repo_name": name or f"owner{repo_id}/repo{repo_id}",
        "api_repo_id": str(api_id if api_id is not None else repo_id),
        "current_full_name": name or f"owner{repo_id}/repo{repo_id}",
        "repo_created_at": "2020-01-01T00:00:00Z",
        "description": description,
        "topics_json": json.dumps(list(topics)),
        "language": "Python",
        "archived": "false",
        "fetch_status": status,
        "http_status": "200" if status in ("ok", "ok_cached") else "404",
        "fetched_at_utc": "2026-11-02T00:00:00Z" if status in ("ok", "ok_cached") else "",
    }


def repo_body(repo_id: int, full_name: str, **extra) -> dict:
    body = {
        "id": repo_id,
        "full_name": full_name,
        "created_at": "2019-05-06T07:08:09Z",
        "description": "a project",
        "topics": ["tool"],
        "language": "Go",
        "archived": False,
    }
    body.update(extra)
    return body


def read_json_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class SelectTests(unittest.TestCase):
    def setUp(self):
        self.rows = [candidate(1000 + i, f"user{i}/repo{i}") for i in range(30)]
        self.rows += [candidate(5000 + i, f"org{i}/ml-toolkit-{i}") for i in range(10)]

    def test_deterministic_and_stratified(self):
        first = select_pilot(self.rows, seed=5488, random_size=12, keyword_size=5)
        second = select_pilot(self.rows, seed=5488, random_size=12, keyword_size=5)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 17)
        self.assertEqual(len({row["repo_id"] for row in first}), 17)
        strata = {}
        for row in first:
            strata[row["sample_stratum"]] = strata.get(row["sample_stratum"], 0) + 1
        self.assertEqual(strata, {"random": 12, "keyword_name": 5})
        keyword_ids = {row["repo_id"] for row in first if row["sample_stratum"] == "keyword_name"}
        self.assertTrue(all(int(repo_id) >= 5000 for repo_id in keyword_ids))

    def test_insufficient_keyword_pool_raises(self):
        with self.assertRaises(ValueError):
            select_pilot(self.rows, seed=1, random_size=30, keyword_size=5)


class RulesTests(unittest.TestCase):
    def label(self, row):
        return RULES.decide(row)

    def test_topic_match_included(self):
        result = self.label(metadata(1, topics=["machine-learning", "python"]))
        self.assertEqual(result["ai_label"], "included")
        self.assertEqual(result["rule_id"], "R4_topic_match")
        self.assertIn("machine-learning", result["reason"])

    def test_description_match_included(self):
        result = self.label(metadata(2, description="An LLM inference engine for transformers"))
        self.assertEqual(result["ai_label"], "included")
        self.assertEqual(result["rule_id"], "R5_description_match")

    def test_chinese_description_included(self):
        result = self.label(metadata(3, description="基于深度学习的中文分词工具"))
        self.assertEqual(result["ai_label"], "included")

    def test_awesome_list_excluded_even_with_ai_topic(self):
        result = self.label(
            metadata(4, description="A curated list of LLM papers", topics=["llm"], name="someone/awesome-llm")
        )
        self.assertEqual(result["ai_label"], "excluded")
        self.assertEqual(result["rule_id"], "R3_resource_collection")

    def test_course_repo_excluded(self):
        result = self.label(metadata(5, description="Machine learning course assignments"))
        self.assertEqual(result["ai_label"], "excluded")
        self.assertEqual(result["rule_id"], "R3_resource_collection")

    def test_name_only_signal_uncertain(self):
        result = self.label(metadata(6, name="someone/ML-project"))
        self.assertEqual(result["ai_label"], "uncertain")
        self.assertEqual(result["rule_id"], "R6_name_only_signal")

    def test_insufficient_text_uncertain(self):
        result = self.label(metadata(7))
        self.assertEqual(result["ai_label"], "uncertain")
        self.assertEqual(result["rule_id"], "R7_insufficient_text_evidence")

    def test_missing_metadata_uncertain(self):
        result = self.label(metadata(8, status="not_found"))
        self.assertEqual(result["ai_label"], "uncertain")
        self.assertEqual(result["rule_id"], "R1_metadata_unavailable")

    def test_id_mismatch_uncertain_even_with_ai_text(self):
        result = self.label(
            metadata(9, status="id_mismatch", description="deep learning", api_id=999)
        )
        self.assertEqual(result["ai_label"], "uncertain")
        self.assertEqual(result["rule_id"], "R2_api_id_mismatch")

    def test_no_signal_excluded(self):
        result = self.label(metadata(10, description="A web proxy tester written in Go", topics=["proxy"]))
        self.assertEqual(result["ai_label"], "excluded")
        self.assertEqual(result["rule_id"], "R8_no_ai_signal")

    def test_label_rows_unique_and_complete(self):
        rows = [
            metadata(11, topics=["llm"]),
            metadata(12, description="proxy tool"),
            metadata(13, status="not_found"),
        ]
        labels = label_rows(rows, RULES, labelled_at="2026-11-02T00:00:00Z")
        self.assertEqual(len(labels), 3)
        self.assertEqual(len({row["repo_id"] for row in labels}), 3)
        self.assertEqual({row["ai_label"] for row in labels}, {"included", "excluded", "uncertain"})
        self.assertTrue(all(set(LABEL_FIELDS) <= set(row) for row in labels))
        self.assertTrue(all(row["rule_version"] == "ai_rules_v0.1" for row in labels))


class FetchTests(unittest.TestCase):
    def setUp(self):
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.root = TEST_TMP_ROOT / uuid.uuid4().hex
        self.root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def client(self, responses):
        calls = {"n": 0}

        def transport(url, headers, timeout):
            calls["n"] += 1
            key = url.rsplit("/repos/", 1)[-1]
            status, headers_map, body = responses[key]
            return status, headers_map, body

        client = GitHubRepoClient(
            token="", transport=transport, sleep=lambda _: None, now=lambda: 0.0
        )
        client.test_calls = calls
        return client

    def test_ok_and_cache_reuse(self):
        body = json.dumps(repo_body(42, "acme/widget")).encode()
        client = self.client({"acme/widget": (200, {"x-ratelimit-remaining": "4999"}, body)})
        cache_dir = self.root / "raw_api"
        row, log = fetch_one(client, 42, "acme/widget", cache_dir)
        self.assertEqual(row["fetch_status"], "ok")
        self.assertEqual(row["api_repo_id"], "42")
        self.assertEqual(row["repo_created_at"], "2019-05-06T07:08:09Z")
        self.assertEqual(row["topics_json"], '["tool"]')
        self.assertEqual(log["attempts"], 1)
        self.assertTrue((cache_dir / "42.json").exists())

        row2, log2 = fetch_one(client, 42, "acme/widget", cache_dir)
        self.assertEqual(row2["fetch_status"], "ok_cached")
        self.assertTrue(log2["cached"])
        self.assertEqual(client.test_calls["n"], 1)

    def test_404_keeps_row_without_metadata(self):
        client = self.client({"acme/gone": (404, {}, b'{"message":"Not Found"}')})
        row, _ = fetch_one(client, 7, "acme/gone", self.root / "raw_api")
        self.assertEqual(row["fetch_status"], "not_found")
        self.assertEqual(row["http_status"], "404")
        self.assertEqual(row["repo_created_at"], "")
        self.assertEqual(row["description"], "")
        self.assertEqual(row["fetched_at_utc"], "")

    def test_id_mismatch_drops_metadata(self):
        body = json.dumps(repo_body(999, "acme/widget")).encode()
        client = self.client({"acme/widget": (200, {}, body)})
        row, _ = fetch_one(client, 42, "acme/widget", self.root / "raw_api")
        self.assertEqual(row["fetch_status"], "id_mismatch")
        self.assertEqual(row["api_repo_id"], "999")
        self.assertEqual(row["description"], "")

    def test_rate_limit_stops_batch_and_records_pending(self):
        body = json.dumps(repo_body(1, "a/one")).encode()
        client = self.client(
            {
                "a/one": (200, {"x-ratelimit-remaining": "1"}, body),
                "b/two": (403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "9999999999"}, b"{}"),
            }
        )
        pilot = [candidate(1, "a/one"), candidate(2, "b/two"), candidate(3, "c/three")]
        summary = fetch_run(pilot, self.root, client=client)
        self.assertEqual(summary["processed_rows"], 1)
        self.assertEqual(summary["pending_repo_ids"], ["2", "3"])
        self.assertIn("rate_limited", summary["stopped_reason"])
        rows = read_csv(self.root / "repo_metadata.csv")
        self.assertEqual([row["repo_id"] for row in rows], ["1"])
        log = read_json_lines(self.root / "fetch_log.jsonl")
        self.assertEqual([entry["repo_id"] for entry in log], ["1", "2", "3"])
        self.assertEqual(log[-1]["fetch_status"], "pending")

    def test_server_error_after_retries(self):
        client = self.client({"a/flaky": (500, {}, b"oops")})
        row, log = fetch_one(client, 5, "a/flaky", self.root / "raw_api")
        self.assertEqual(row["fetch_status"], "server_error")
        self.assertEqual(log["attempts"], 3)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.metadata = [
            metadata(1, topics=["llm"], name="a/llm"),
            metadata(2, description="proxy", name="a/proxy"),
            metadata(3, status="not_found", name="a/gone"),
            metadata(4, name="a/other"),
        ]
        self.labels = [RULES.decide(row) for row in self.metadata]

    def test_sheet_covers_each_scope(self):
        sheet = build_sheet(self.labels, self.metadata, per_label=1, uncertain_limit=None, seed=5488)
        scopes = [row["review_scope"] for row in sheet]
        self.assertEqual(scopes.count("included"), 1)
        self.assertEqual(scopes.count("excluded"), 1)
        self.assertEqual(scopes.count("uncertain"), 2)

    def test_merge_decisions_counts(self):
        sheet = build_sheet(self.labels, self.metadata, per_label=5, uncertain_limit=None, seed=5488)
        decisions = {
            "reviewer": "B",
            "reviewed_at_utc": "2026-11-02T00:00:00Z",
            "decisions": [
                {"repo_id": "1", "human_label": "included", "human_reason": "ai sdk"},
                {"repo_id": "2", "human_label": "excluded", "human_reason": "proxy tool"},
                {"repo_id": "3", "human_label": "uncertain", "human_reason": "404"},
                {"repo_id": "4", "human_label": "excluded", "human_reason": "no signal"},
            ],
        }
        rows, summary = merge_decisions(sheet, decisions)
        self.assertEqual(summary["reviewed_rows"], 4)
        self.assertEqual(summary["auto_decided_rows"]["agree"], 2)
        self.assertEqual(summary["auto_decided_rows"]["disagree"], 0)
        self.assertEqual(summary["auto_uncertain_rows"]["resolved_by_reviewer"], 1)
        self.assertEqual(summary["auto_uncertain_rows"]["kept_uncertain"], 1)
        self.assertTrue(all(set(REVIEW_FIELDS) <= set(row) for row in rows))

    def test_unknown_repo_id_rejected(self):
        sheet = build_sheet(self.labels, self.metadata, per_label=5, uncertain_limit=None, seed=5488)
        with self.assertRaises(ValueError):
            merge_decisions(sheet, {"decisions": [{"repo_id": "999", "human_label": "included", "human_reason": "x"}]})

    def test_duplicate_decision_rejected(self):
        sheet = build_sheet(self.labels, self.metadata, per_label=5, uncertain_limit=None, seed=5488)
        with self.assertRaises(ValueError):
            merge_decisions(
                sheet,
                {
                    "decisions": [
                        {"repo_id": "1", "human_label": "included", "human_reason": "a"},
                        {"repo_id": "1", "human_label": "excluded", "human_reason": "b"},
                    ]
                },
            )


class JoinTests(unittest.TestCase):
    def setUp(self):
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.root = TEST_TMP_ROOT / uuid.uuid4().hex
        self.root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_join_uses_candidate_counts_and_checks_uniqueness(self):
        metadata_rows = [metadata(1, topics=["llm"]), metadata(2, description="proxy")]
        labels = label_rows(metadata_rows, RULES)
        write_csv(self.root / "repo_metadata.csv", METADATA_FIELDS, metadata_rows)
        write_csv(self.root / "repo_ai_labels.csv", LABEL_FIELDS, labels)
        candidates = [
            candidate(1, "a/llm", events=5),
            candidate(2, "a/proxy", events=3),
            candidate(3, "a/other", events=2),
        ]
        write_csv(self.root / "candidates.csv", list(candidates[0]), candidates)

        summary = join_run(
            metadata_csv=self.root / "repo_metadata.csv",
            labels_csv=self.root / "repo_ai_labels.csv",
            out_dir=self.root,
            events_parquet=None,
            candidates_csv=self.root / "candidates.csv",
        )
        self.assertEqual(summary["event_source"], "repo_candidates.csv:event_count")
        self.assertEqual(summary["events_total_in_source"], 10)
        self.assertEqual(summary["events_covered_by_pilot"], 8)
        self.assertTrue(all(summary["checks"].values()))

        joined = read_csv(self.root / "repo_labels_joined_events.csv")
        by_id = {row["repo_id"]: row for row in joined}
        # 5/10 是整个事件表的口径；5/8 是试点仓库内部的口径。
        self.assertEqual(by_id["1"]["event_share_of_source"], "0.5")
        self.assertEqual(by_id["1"]["event_share_of_pilot_events"], "0.625")
        self.assertEqual(by_id["2"]["event_share_of_pilot_events"], "0.375")

    def test_missing_repo_fails_check(self):
        metadata_rows = [metadata(9, topics=["llm"])]
        labels = label_rows(metadata_rows, RULES)
        write_csv(self.root / "repo_metadata.csv", METADATA_FIELDS, metadata_rows)
        write_csv(self.root / "repo_ai_labels.csv", LABEL_FIELDS, labels)
        write_csv(self.root / "candidates.csv", ["repo_id", "repo_name", "event_count"], [candidate(1, "a/one")])
        summary = join_run(
            metadata_csv=self.root / "repo_metadata.csv",
            labels_csv=self.root / "repo_ai_labels.csv",
            out_dir=self.root,
            events_parquet=None,
            candidates_csv=self.root / "candidates.csv",
        )
        self.assertFalse(summary["checks"]["all_pilot_repos_present_in_events"])
        self.assertEqual(summary["missing_from_events"], ["9"])


class EvidenceTests(unittest.TestCase):
    def test_base64_readme_decoded(self):
        payload = base64.b64encode("# Hello 世界".encode("utf-8")).decode()

        class Response:
            body = {"content": payload, "encoding": "base64"}
            raw = b"{}"

        self.assertEqual(_readme_text(Response()), "# Hello 世界")

    def test_raw_readme_passthrough(self):
        class Response:
            body = None
            raw = "# raw readme".encode()

        self.assertEqual(_readme_text(Response()), "# raw readme")


class RulesV2Tests(unittest.TestCase):
    """v0.2 的弱信号、课程作业、个人主页与旧分支保持已知结果。"""

    RULES = RuleSet(load_rules(B_ROOT / "rules" / "ai_rules_v0.2.json"))

    def label(self, row):
        return self.RULES.decide(row)

    def test_strong_topic_still_included(self):
        result = self.label(metadata(1, topics=["llm", "transformer"]))
        self.assertEqual(result["ai_label"], "included")
        self.assertEqual(result["rule_id"], "R4_topic_match")

    def test_bare_ai_topic_without_corroboration_is_uncertain(self):
        result = self.label(
            metadata(2, description="Team collaboration software using markdown", topics=["ai"])
        )
        self.assertEqual(result["ai_label"], "uncertain")
        self.assertEqual(result["rule_id"], "R4b_weak_topic_only")

    def test_bare_ai_topic_with_corroboration_is_included(self):
        result = self.label(metadata(3, description="An AI SDK for Python", topics=["ai"]))
        self.assertEqual(result["ai_label"], "included")
        self.assertEqual(result["rule_id"], "R5b_weak_signal_corroborated")

    def test_bare_ai_description_with_corroboration_is_included(self):
        result = self.label(metadata(4, description="AI platform for model training"))
        self.assertEqual(result["ai_label"], "included")
        self.assertEqual(result["rule_id"], "R5b_weak_signal_corroborated")

    def test_bare_ai_description_without_corroboration_is_uncertain(self):
        result = self.label(metadata(5, description="An AI company website"))
        self.assertEqual(result["ai_label"], "uncertain")
        self.assertEqual(result["rule_id"], "R5c_weak_signal_only")

    def test_coursework_name_excluded(self):
        for name in ("org/final-project-ai", "Openclassrooms-P11_Kasa", "org/cs933-lab"):
            with self.subTest(name=name):
                result = self.label(metadata(6, name=name, description="something"))
                self.assertEqual(result["ai_label"], "excluded")
                self.assertEqual(result["rule_id"], "R3b_coursework")

    def test_coursework_description_excluded(self):
        result = self.label(metadata(7, description="Machine learning course assignments"))
        self.assertEqual(result["ai_label"], "excluded")
        self.assertEqual(result["rule_id"], "R3b_coursework")

    def test_lab_website_not_coursework(self):
        result = self.label(metadata(8, name="someone/lab-webpage", description="Lab website"))
        self.assertEqual(result["ai_label"], "excluded")
        self.assertEqual(result["rule_id"], "R8_no_ai_signal")

    def test_profile_repository_excluded(self):
        result = self.label(metadata(9, name="alice/alice"))
        self.assertEqual(result["ai_label"], "excluded")
        self.assertEqual(result["rule_id"], "R3c_profile_repository")

    def test_profile_name_with_description_not_profile_rule(self):
        result = self.label(metadata(10, name="alice/alice", description="My Github Profile"))
        self.assertEqual(result["ai_label"], "excluded")
        self.assertEqual(result["rule_id"], "R8_no_ai_signal")

    def test_resource_collection_still_wins(self):
        result = self.label(
            metadata(11, name="someone/awesome-llm", description="A curated list of LLM papers", topics=["llm"])
        )
        self.assertEqual(result["ai_label"], "excluded")
        self.assertEqual(result["rule_id"], "R3_resource_collection")

    def test_name_only_remains_uncertain(self):
        result = self.label(metadata(12, name="someone/ML-project"))
        self.assertEqual(result["ai_label"], "uncertain")
        self.assertEqual(result["rule_id"], "R6_name_only_signal")

    def test_missing_metadata_still_uncertain(self):
        result = self.label(metadata(13, status="not_found", name="someone/ai-thing"))
        self.assertEqual(result["ai_label"], "uncertain")
        self.assertEqual(result["rule_id"], "R1_metadata_unavailable")


class FetchCachePolicyTests(unittest.TestCase):
    """失败响应不应被默认缓存复用；成功响应仍应复用。"""

    def setUp(self):
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.root = TEST_TMP_ROOT / uuid.uuid4().hex
        self.root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def client(self, responses):
        calls = {"n": 0}

        def transport(url, headers, timeout):
            calls["n"] += 1
            key = url.rsplit("/repos/", 1)[-1]
            return responses[key]

        client = GitHubRepoClient(token="", transport=transport, sleep=lambda _: None, now=lambda: 0.0)
        client.test_calls = calls
        return client

    def test_404_cache_is_retried_by_default(self):
        client = self.client({"acme/gone": (404, {}, b'{"message":"Not Found"}')})
        cache_dir = self.root / "raw_api"
        first, log1 = fetch_one(client, 7, "acme/gone", cache_dir)
        self.assertEqual(first["fetch_status"], "not_found")
        self.assertEqual(log1["cache_decision"], "requested")

        second, log2 = fetch_one(client, 7, "acme/gone", cache_dir)
        self.assertEqual(second["fetch_status"], "not_found")
        self.assertEqual(log2["cache_decision"], "requested")
        self.assertEqual(client.test_calls["n"], 2)

    def test_404_cache_can_be_reused_explicitly(self):
        client = self.client({"acme/gone": (404, {}, b'{"message":"Not Found"}')})
        cache_dir = self.root / "raw_api"
        fetch_one(client, 7, "acme/gone", cache_dir)

        row, log = fetch_one(client, 7, "acme/gone", cache_dir, reuse_failed=True)
        self.assertEqual(row["fetch_status"], "not_found")
        self.assertEqual(log["cache_decision"], "reused_failure")
        self.assertEqual(client.test_calls["n"], 1)

    def test_success_cache_reused(self):
        body = json.dumps(repo_body(8, "acme/ok")).encode()
        client = self.client({"acme/ok": (200, {}, body)})
        cache_dir = self.root / "raw_api"
        fetch_one(client, 8, "acme/ok", cache_dir)
        row, log = fetch_one(client, 8, "acme/ok", cache_dir)
        self.assertEqual(row["fetch_status"], "ok_cached")
        self.assertEqual(log["cache_decision"], "reused_success")
        self.assertEqual(client.test_calls["n"], 1)

    def test_network_error_cache_retried_by_default_then_reusable(self):
        def transport(url, headers, timeout):
            transport.calls += 1
            raise urllib.error.URLError("temporary network failure")

        transport.calls = 0
        client = GitHubRepoClient(token="", transport=transport, sleep=lambda _: None, now=lambda: 0.0)
        cache_dir = self.root / "raw_api"

        first, log1 = fetch_one(client, 9, "acme/flaky", cache_dir)
        self.assertEqual(first["fetch_status"], "network_error")
        self.assertEqual(log1["cache_decision"], "requested")
        calls_after_first = transport.calls
        self.assertGreaterEqual(calls_after_first, 1)

        # 默认重跑：仍然重新请求，不会命中失败缓存
        second, log2 = fetch_one(client, 9, "acme/flaky", cache_dir)
        self.assertEqual(second["fetch_status"], "network_error")
        self.assertEqual(log2["cache_decision"], "requested")
        self.assertGreater(transport.calls, calls_after_first)

        # 显式复用：不再发请求，状态由缓存里的错误重建
        calls_before_reuse = transport.calls
        reused, log3 = fetch_one(client, 9, "acme/flaky", cache_dir, reuse_failed=True)
        self.assertEqual(reused["fetch_status"], "network_error")
        self.assertEqual(log3["cache_decision"], "reused_failure")
        self.assertEqual(transport.calls, calls_before_reuse)

    def test_server_error_without_json_body_can_be_reused(self):
        client = self.client({"acme/down": (503, {}, b"<html>maintenance</html>")})
        cache_dir = self.root / "raw_api"
        first, _ = fetch_one(client, 10, "acme/down", cache_dir)
        self.assertEqual(first["fetch_status"], "server_error")

        calls_before = client.test_calls["n"]
        reused, log = fetch_one(client, 10, "acme/down", cache_dir, reuse_failed=True)
        self.assertEqual(reused["fetch_status"], "server_error")
        self.assertEqual(log["cache_decision"], "reused_failure")
        self.assertEqual(client.test_calls["n"], calls_before)


class ReviewSheetPreservationTests(unittest.TestCase):
    """重跑复核时不能悄悄用新规则覆盖已有清单。"""

    def setUp(self):
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.root = TEST_TMP_ROOT / uuid.uuid4().hex
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata = [
            metadata(1, topics=["llm"], name="a/llm"),
            metadata(2, description="proxy", name="a/proxy"),
            metadata(3, status="not_found", name="a/gone"),
            metadata(4, name="a/other"),
        ]
        write_csv(self.root / "repo_metadata.csv", METADATA_FIELDS, self.metadata)
        self.labels_v1 = label_rows(self.metadata, RULES)
        write_csv(self.root / "repo_ai_labels.csv", LABEL_FIELDS, self.labels_v1)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def decisions(self, repo_id="1"):
        return {
            "reviewer": "B",
            "reviewed_at_utc": "2026-11-02T00:00:00Z",
            "decisions": [{"repo_id": repo_id, "human_label": "uncertain", "human_reason": "looks ambiguous"}],
        }

    def test_sheet_generation_refuses_overwrite_without_force(self):
        first = review_run(
            labels_csv=self.root / "repo_ai_labels.csv",
            metadata_csv=self.root / "repo_metadata.csv",
            out_dir=self.root,
        )
        before = (self.root / "manual_review.csv").read_bytes()
        with self.assertRaises(FileExistsError):
            review_run(
                labels_csv=self.root / "repo_ai_labels.csv",
                metadata_csv=self.root / "repo_metadata.csv",
                out_dir=self.root,
            )
        self.assertEqual((self.root / "manual_review.csv").read_bytes(), before)
        self.assertEqual(first["status"], "sheet_only")

    def test_force_regenerates_sheet(self):
        review_run(
            labels_csv=self.root / "repo_ai_labels.csv",
            metadata_csv=self.root / "repo_metadata.csv",
            out_dir=self.root,
        )
        forced = review_run(
            labels_csv=self.root / "repo_ai_labels.csv",
            metadata_csv=self.root / "repo_metadata.csv",
            out_dir=self.root,
            force=True,
        )
        self.assertEqual(forced["status"], "sheet_only")
        self.assertFalse(forced["reused_existing_sheet"])

    def test_merge_reuses_existing_sheet_even_when_labels_changed(self):
        first = review_run(
            labels_csv=self.root / "repo_ai_labels.csv",
            metadata_csv=self.root / "repo_metadata.csv",
            out_dir=self.root,
        )
        # 把标签换成 v0.2，模拟“规则已更新但历史复核记录必须保留”
        v2_rules = RuleSet(load_rules(B_ROOT / "rules" / "ai_rules_v0.2.json"))
        write_csv(self.root / "repo_ai_labels.csv", LABEL_FIELDS, label_rows(self.metadata, v2_rules))
        write_json(self.root / "decisions.json", self.decisions("1"))

        merged = review_run(
            labels_csv=self.root / "repo_ai_labels.csv",
            metadata_csv=self.root / "repo_metadata.csv",
            out_dir=self.root,
            decisions_path=self.root / "decisions.json",
        )
        self.assertEqual(merged["sheet_source"], "existing_sheet")
        self.assertTrue(merged["reused_existing_sheet"])
        self.assertEqual(merged["sheet_rows"], first["sheet_rows"])
        self.assertEqual(merged["reviewed_rows"], 1)
        self.assertEqual(merged["status"], "partial")

    def test_merge_generates_sheet_when_missing(self):
        write_json(self.root / "decisions.json", self.decisions("1"))
        merged = review_run(
            labels_csv=self.root / "repo_ai_labels.csv",
            metadata_csv=self.root / "repo_metadata.csv",
            out_dir=self.root,
            decisions_path=self.root / "decisions.json",
        )
        self.assertEqual(merged["sheet_source"], "generated_sheet")
        self.assertFalse(merged["reused_existing_sheet"])
        self.assertEqual(merged["reviewed_rows"], 1)


class CompareAndHandoffTests(unittest.TestCase):
    def setUp(self):
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.root = TEST_TMP_ROOT / uuid.uuid4().hex
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata = [
            metadata(1, topics=["llm"], name="a/llm"),
            metadata(2, description="AI SDK", name="b/sdk"),
            metadata(3, description="proxy", name="c/proxy"),
            metadata(4, status="not_found", name="d/gone"),
        ]

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_compare_produces_changes_and_human_scores(self):
        from bmeta.compare import run as compare_run

        old_rules = RuleSet(load_rules(B_ROOT / "rules" / "ai_rules_v0.1.json"))
        new_rules = RuleSet(load_rules(B_ROOT / "rules" / "ai_rules_v0.2.json"))
        old_labels = label_rows(self.metadata, old_rules)
        new_labels = label_rows(self.metadata, new_rules)
        write_csv(self.root / "old.csv", LABEL_FIELDS, old_labels)
        write_csv(self.root / "new.csv", LABEL_FIELDS, new_labels)
        write_csv(self.root / "meta.csv", METADATA_FIELDS, self.metadata)
        review_rows = [
            {"repo_id": "1", "human_label": "included", "human_reason": "llm", "ai_label_auto": "included"},
            {"repo_id": "2", "human_label": "included", "human_reason": "ai sdk", "ai_label_auto": "uncertain"},
            {"repo_id": "3", "human_label": "excluded", "human_reason": "proxy", "ai_label_auto": "excluded"},
            {"repo_id": "4", "human_label": "uncertain", "human_reason": "404", "ai_label_auto": "uncertain"},
        ]
        write_csv(self.root / "review.csv", list(review_rows[0]), review_rows)

        summary = compare_run(
            old_labels_csv=self.root / "old.csv",
            new_labels_csv=self.root / "new.csv",
            metadata_csv=self.root / "meta.csv",
            out_dir=self.root,
            manual_review_csv=self.root / "review.csv",
        )
        # b/sdk：v0.1 只有裸 ai 描述 → included；v0.2 靠 sdk 佐证也是 included，规则理由变化
        self.assertEqual(summary["changed_rows"], 1)
        self.assertEqual(summary["rule_reason_changed_rows"], 1)
        self.assertEqual(summary["human_review"]["new_version"]["disagree"], 0)
        self.assertTrue((self.root / "label_changes.csv").exists())

    def test_handoff_policies(self):
        from bmeta.handoff import run as handoff_run

        labels = label_rows(self.metadata, RULES)
        write_csv(self.root / "labels.csv", LABEL_FIELDS, labels)
        write_csv(self.root / "meta.csv", METADATA_FIELDS, self.metadata)
        review_rows = [
            {"repo_id": "1", "human_label": "excluded", "human_reason": "not ai", "ai_label_auto": "included"},
        ]
        write_csv(self.root / "review.csv", list(review_rows[0]), review_rows)

        merged = handoff_run(
            labels_csv=self.root / "labels.csv",
            metadata_csv=self.root / "meta.csv",
            out_dir=self.root,
            review_csv=self.root / "review.csv",
            policy="manual_override",
        )
        rows = {row["repo_id"]: row for row in read_csv(self.root / "repo_ai_labels_analysis.csv")}
        self.assertEqual(rows["1"]["ai_label_final"], "excluded")
        self.assertEqual(rows["1"]["label_source"], "manual_review")
        self.assertEqual(rows["2"]["label_source"], "auto_rule")
        self.assertEqual(merged["manual_differs_from_auto"], 1)

        handoff_run(
            labels_csv=self.root / "labels.csv",
            metadata_csv=self.root / "meta.csv",
            out_dir=self.root,
            review_csv=self.root / "review.csv",
            policy="auto_only",
        )
        rows = {row["repo_id"]: row for row in read_csv(self.root / "repo_ai_labels_analysis.csv")}
        self.assertEqual(rows["1"]["ai_label_final"], "included")
        self.assertEqual(rows["1"]["label_source"], "auto_rule")


if __name__ == "__main__":
    unittest.main(verbosity=2)
