"""按首批名单抓取仓库元数据：串行、缓存、可续跑、失败也留记录。

输出与约定（与 ``B_接手指南.md`` 第 3 节的建议字段一致）：

- ``raw_api/<repo_id>.json``：每个仓库一份**原始响应信封**，包含请求的 repo_id 与
  名称、HTTP 状态、最终 URL、抓取时间、配额头和 GitHub 原始 JSON 响应体；
- ``repo_metadata.csv``：每个输入仓库一行，失败行保留 ``fetch_status``/``http_status``，
  元数据列留空；``repo_created_at`` 只来自仓库 API 的 ``created_at``；
- ``fetch_log.jsonl``：本轮每个仓库的状态、重试次数、耗时、是否命中缓存与重定向；
- ``run_summary.json`` 的 ``fetch`` 段：计数、API 调用数、pending 列表与配额状态。

只有 API 返回的 ``id`` 与 A 的 ``repo_id`` 完全一致时才写入元数据字段：
ID 不匹配意味着同名仓库可能已被重命名或复用，不能把响应当成同一个仓库。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from .api import ApiResponse, GitHubRepoClient, RateLimitExhausted
from .common import (
    ensure_dir,
    project_relative,
    update_run_summary,
    utc_now,
    write_csv,
    write_json,
)

METADATA_FIELDS = [
    "repo_id",
    "observed_repo_name",
    "api_repo_id",
    "current_full_name",
    "repo_created_at",
    "description",
    "topics_json",
    "language",
    "archived",
    "fetch_status",
    "http_status",
    "fetched_at_utc",
]

RAW_SCHEMA_VERSION = "bmeta-raw-v1"

# fetch_status 取值与含义（写入 CSV，供复核）
STATUS_MEANINGS = {
    "ok": "HTTP 200，返回 id 与输入 repo_id 一致",
    "ok_cached": "复用 raw_api 缓存，未重复请求",
    "not_found": "HTTP 404/410/451：无法获取，不推断为删除或私有化",
    "id_mismatch": "HTTP 200 但返回 id 不等于输入 repo_id，元数据不采用",
    "http_error": "其他 4xx",
    "server_error": "HTTP 5xx，重试后仍失败",
    "network_error": "网络/超时，重试后仍失败",
    "invalid_json": "响应不是合法 JSON",
    "pending": "本轮因配额或中断未处理，需续跑",
}


def _cache_path(cache_dir: Path, repo_id: int) -> Path:
    return cache_dir / f"{repo_id}.json"


def _load_cache(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if envelope.get("schema_version") != RAW_SCHEMA_VERSION:
        return None
    if not isinstance(envelope.get("response"), dict):
        return None
    return envelope


def _envelope_from_response(repo_id: int, name: str, response: ApiResponse, fetched_at: str) -> dict[str, Any]:
    return {
        "schema_version": RAW_SCHEMA_VERSION,
        "requested_repo_id": repo_id,
        "requested_name": name,
        "fetched_at_utc": fetched_at,
        "http_status": response.http_status,
        "final_url": response.final_url,
        "attempts": response.attempts,
        "elapsed_ms": response.elapsed_ms,
        "error": response.error,
        "rate_limit": {key: response.headers.get(key) for key in (
            "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-used", "x-ratelimit-reset",
        )},
        "response": response.body if isinstance(response.body, dict) else None,
        "response_text": None if response.body is not None else response.raw.decode("utf-8", "replace")[:2000],
    }


def _status_from_envelope(envelope: dict[str, Any]) -> str:
    status = envelope.get("http_status")
    if status == 200 and isinstance(envelope.get("response"), dict):
        return "ok"
    if status in (404, 410, 451):
        return "not_found"
    if isinstance(status, int) and 400 <= status < 500:
        return "http_error"
    if isinstance(status, int) and 500 <= status < 600:
        return "server_error"
    return "network_error"


def _metadata_row(repo_id: int, name: str, envelope: dict[str, Any], fetch_status: str) -> dict[str, str]:
    body = envelope.get("response") if isinstance(envelope.get("response"), dict) else {}
    row = {field: "" for field in METADATA_FIELDS}
    row["repo_id"] = str(repo_id)
    row["observed_repo_name"] = name
    row["fetch_status"] = fetch_status
    row["http_status"] = "" if envelope.get("http_status") is None else str(envelope.get("http_status"))

    if fetch_status in ("ok", "ok_cached") and body:
        api_id = body.get("id")
        row["api_repo_id"] = "" if api_id is None else str(api_id)
        if str(api_id) != str(repo_id):
            # 名称被重命名或复用：不采用返回的元数据，只保留诊断信息。
            row["current_full_name"] = body.get("full_name") or ""
            row["fetch_status"] = "id_mismatch"
            return row
        row["current_full_name"] = body.get("full_name") or ""
        row["repo_created_at"] = body.get("created_at") or ""
        row["description"] = body.get("description") or ""
        topics = body.get("topics") or []
        row["topics_json"] = json.dumps(topics if isinstance(topics, list) else [], ensure_ascii=False)
        row["language"] = body.get("language") or ""
        archived = body.get("archived")
        row["archived"] = "" if archived is None else ("true" if archived else "false")
        row["fetched_at_utc"] = envelope.get("fetched_at_utc") or ""
    elif fetch_status == "id_mismatch" and body:
        api_id = body.get("id")
        row["api_repo_id"] = "" if api_id is None else str(api_id)
        row["current_full_name"] = body.get("full_name") or ""
    return row


def fetch_one(
    client: GitHubRepoClient,
    repo_id: int,
    name: str,
    cache_dir: Path,
    *,
    now: Callable[[], str] = utc_now,
    force_refresh: bool = False,
) -> tuple[dict[str, str], dict[str, Any]]:
    """抓取或复用缓存，返回 (元数据行, 日志条目)。"""
    cache_file = _cache_path(cache_dir, repo_id)
    envelope = None if force_refresh else _load_cache(cache_file)
    started = time.time()

    if envelope is not None:
        fetch_status = _status_from_envelope(envelope)
        if fetch_status == "ok":
            fetch_status = "ok_cached"
        cached = True
    else:
        response = client.get_repo(name)
        fetched_at = now()
        envelope = _envelope_from_response(repo_id, name, response, fetched_at)
        write_json(cache_file, envelope)
        fetch_status = "ok" if response.ok else response.status_family
        if fetch_status == "ok":
            body = envelope.get("response") or {}
            if str(body.get("id")) != str(repo_id):
                fetch_status = "id_mismatch"
        cached = False

    row = _metadata_row(repo_id, name, envelope, fetch_status)
    log_entry = {
        "repo_id": str(repo_id),
        "observed_repo_name": name,
        "fetch_status": row["fetch_status"],
        "http_status": row["http_status"],
        "cached": cached,
        "attempts": envelope.get("attempts"),
        "elapsed_ms": envelope.get("elapsed_ms"),
        "request_final_url": envelope.get("final_url"),
        "redirected": bool(envelope.get("final_url")) and envelope.get("final_url", "").rsplit("/repos/", 1)[-1] != name,
        "fetched_at_utc": envelope.get("fetched_at_utc"),
        "rate_limit": envelope.get("rate_limit"),
        "error": envelope.get("error"),
        "measured_ms": int(round((time.time() - started) * 1000)),
    }
    return row, log_entry


def run(
    pilot_rows: Sequence[dict],
    out_dir: Path,
    *,
    client: GitHubRepoClient,
    force_refresh: bool = False,
    max_repos: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """执行整批抓取；配额用尽时停在当前仓库之前并给出 pending 列表。"""
    out_dir = Path(out_dir)
    cache_dir = ensure_dir(out_dir / "raw_api")
    rows: list[dict[str, str]] = []
    logs: list[dict[str, Any]] = []
    pending: list[str] = []
    stopped_reason: str | None = None
    started_at = utc_now()

    targets = list(pilot_rows)
    if max_repos is not None:
        targets = targets[:max_repos]

    quota: dict[str, Any] = {}
    for index, candidate in enumerate(targets, start=1):
        repo_id = int(candidate["repo_id"])
        name = candidate["repo_name"]
        try:
            row, log_entry = fetch_one(
                client, repo_id, name, cache_dir, force_refresh=force_refresh
            )
        except RateLimitExhausted as error:
            stopped_reason = f"rate_limited: {error}"
            pending = [str(item["repo_id"]) for item in targets[index - 1 :]]
            break

        rows.append(row)
        logs.append(log_entry)
        if log_entry.get("rate_limit"):
            quota = {key: value for key, value in log_entry["rate_limit"].items() if value is not None}
        write_csv(out_dir / "repo_metadata.csv", METADATA_FIELDS, rows)
        if progress:
            progress(f"[{index}/{len(targets)}] {repo_id} {name} -> {row['fetch_status']}")

    # 配额用尽时，未处理仓库也写进日志，便于续跑核对。
    for repo_id in pending:
        logs.append({"repo_id": repo_id, "fetch_status": "pending", "reason": stopped_reason})

    with open(out_dir / "fetch_log.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for entry in logs:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["fetch_status"]] = status_counts.get(row["fetch_status"], 0) + 1

    summary = {
        "started_at_utc": started_at,
        "finished_at_utc": utc_now(),
        "input_rows": len(targets),
        "processed_rows": len(rows),
        "pending_rows": len(pending),
        "pending_repo_ids": pending,
        "status_counts": status_counts,
        "api_calls": client.calls,
        "token_present": client.has_token,
        "token_env_var": client.token_env,
        "stopped_reason": stopped_reason,
        "last_rate_limit_headers": quota,
        "cache_dir": project_relative(cache_dir),
        "metadata_csv": project_relative(out_dir / "repo_metadata.csv"),
        "note": "失败行只记录状态，缺失元数据留空；pending 行尚未写入 repo_metadata.csv。",
    }
    write_json(out_dir / "fetch_summary.json", summary)
    update_run_summary(out_dir / "run_summary.json", "fetch", summary)
    return summary
