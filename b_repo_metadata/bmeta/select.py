"""从 A 的仓库候选清单中固定 B 的首批试跑名单。

选取方法（写入 ``runs/pilot_01/selection.json``，并由 run_summary 复核）：

1. 以 ``repo_id`` 升序排列候选清单，保证同样的输入 + 同样的种子得到同样的名单；
2. **随机层**：用 ``random.Random(seed).sample`` 抽取 40 个未分层仓库；
3. **关键词层**：在剩余仓库中，只保留 ``owner/repo`` 名称命中粗粒度 AI 关键词的仓库，
   再抽取 10 个，用于覆盖规则中 ``included`` 的判定路径。

关键词层是**有意过采样**的：它提高 trial 中 AI 仓库的命中数，便于调试规则，
不能用来估计整个 GitHub 的 AI 仓库比例。两层都记录在 ``sample_stratum`` 列。

这里的关键词集合只用于“抽谁进试跑”，与 ``rules/ai_rules_v0.1.json`` 的正式判定
规则解耦：前者是粗筛，后者有优先级、理由与版本。
"""

from __future__ import annotations

import random
import re
from typing import Iterable, Sequence

# 名称粗筛：只用于分层抽样，不是 AI 判定规则。
NAME_PROBE_PATTERNS = [
    r"(^|[/_\-.])ai($|[/_\-.])",
    r"(^|[/_\-.])ml($|[/_\-.])",
    r"(^|[/_\-.])llms?($|[/_\-.])",
    r"gpt",
    r"chatgpt",
    r"openai",
    r"anthropic",
    r"llama",
    r"langchain",
    r"huggingface",
    r"transformer",
    r"tensorflow",
    r"pytorch",
    r"keras",
    r"sklearn",
    r"scikit",
    r"nlp",
    r"computer[-_]?vision",
    r"machine[-_]?learning",
    r"deep[-_]?learning",
    r"neural",
    r"diffusion",
    r"stable[-_]?diffusion",
    r"embedding",
    r"vector[-_]?(db|database|store)",
    r"rag($|[/_\-.])",
    r"chatbot",
    r"mlops",
    r"mistral",
    r"qwen",
    r"whisper",
    r"yolo",
    r"agent(s)?($|[/_\-.])",
]

_NAME_PROBE = [re.compile(pattern) for pattern in NAME_PROBE_PATTERNS]

SELECTED_FIELDS = [
    "repo_id",
    "repo_name",
    "first_observed_at",
    "last_observed_at",
    "event_count",
    "observed_name_count",
    "sample_stratum",
    "selection_rank",
]


def name_probe_matches(repo_name: str) -> list[str]:
    """返回名称命中的粗筛模式文本（空列表表示未命中）。"""
    lowered = (repo_name or "").lower()
    return [pattern.pattern for pattern in _NAME_PROBE if pattern.search(lowered)]


def _sorted_keys(rows: Sequence[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: int(row["repo_id"]))


def select_pilot(
    candidates: Sequence[dict],
    *,
    seed: int,
    random_size: int,
    keyword_size: int,
) -> list[dict]:
    """按“随机层 + 关键词层”固定名单；同样的输入与种子结果一致。"""
    if random_size < 0 or keyword_size < 0:
        raise ValueError("strata sizes must be non-negative")
    rows = _sorted_keys(candidates)
    if not rows:
        raise ValueError("candidate list is empty")
    if random_size + keyword_size > len(rows):
        raise ValueError("requested pilot larger than candidate list")

    rng = random.Random(seed)
    random_pick = rng.sample(rows, random_size)
    picked_ids = {int(row["repo_id"]) for row in random_pick}

    keyword_pool = [
        row
        for row in rows
        if int(row["repo_id"]) not in picked_ids and name_probe_matches(row["repo_name"])
    ]
    if len(keyword_pool) < keyword_size:
        raise ValueError(
            f"keyword stratum needs {keyword_size} rows but only {len(keyword_pool)} name probes matched"
        )
    keyword_pick = rng.sample(keyword_pool, keyword_size)

    selected: list[dict] = []
    for row in random_pick:
        selected.append(_as_pilot_row(row, "random"))
    for row in keyword_pick:
        selected.append(_as_pilot_row(row, "keyword_name"))
    selected.sort(key=lambda row: (row["sample_stratum"] != "random", int(row["repo_id"])))
    for index, row in enumerate(selected, start=1):
        row["selection_rank"] = index
    return selected


def _as_pilot_row(row: dict, stratum: str) -> dict:
    return {
        "repo_id": row["repo_id"],
        "repo_name": row["repo_name"],
        "first_observed_at": row.get("first_observed_at", ""),
        "last_observed_at": row.get("last_observed_at", ""),
        "event_count": row.get("event_count", ""),
        "observed_name_count": row.get("observed_name_count", ""),
        "sample_stratum": stratum,
        "selection_rank": "",
    }


def stratum_counts(rows: Iterable[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["sample_stratum"]] = counts.get(row["sample_stratum"], 0) + 1
    return counts
