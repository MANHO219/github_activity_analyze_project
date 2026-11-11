"""为人工复核补充 README 证据。

规则 v0.1 只读 ``description`` 与 ``topics``，但人工复核时 B 会打开仓库页面。
为了让复核证据可回查，这里把复核清单里**元数据抓取成功**的仓库 README 前 4000 字符
存成 JSONL，并记录 HTTP 状态与 SHA-256。

跳过的情况（不制造误导性证据）：

- 元数据取不到（404/网络错误）——仓库已改名或被删除；
- ``id_mismatch``——同名仓库已指向另一个 ID，README 不属于 A 的那个 repo_id。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable, Sequence

from .api import GitHubRepoClient
from .common import project_relative, utc_now, write_json

SKIP_RULES = {"R1_metadata_unavailable", "R2_api_id_mismatch"}
MAX_CHARS = 4000


def _readme_url(client: GitHubRepoClient, full_name: str) -> str:
    return f"{client.base_url}/repos/{full_name}/readme"


def _readme_text(response) -> str:
    """README 接口的正文；取不到正文时返回空串，绝不回退成响应的 JSON 信封。

    两类历史问题都由这个回退造成：404 的 ``{"message": "Not Found"}`` 与空 README
    的 ``{"name": "README.md", ..., "size": 0}`` 都曾被当成正文写进证据，
    导致 ``readme_chars`` 虚高、哈希对不上真实 README。
    """
    status = getattr(response, "http_status", None)
    if status is not None and status != 200:
        return ""
    body = response.body
    if isinstance(body, dict):
        content = body.get("content") or ""
        if not content:
            return ""
        encoding = (body.get("encoding") or "").lower()
        if encoding == "base64":
            try:
                import base64

                return base64.b64decode(content).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001 - 证据缺失时保留原文比中断更好
                return ""
        return str(content)
    raw = response.raw.decode("utf-8", "replace") if response.raw else ""
    # 原始响应也可能是错误 JSON（没有可解析的 body），按无正文处理。
    if raw.lstrip().startswith("{"):
        return ""
    return raw


def fetch_evidence(
    review_rows: Sequence[dict[str, Any]],
    *,
    client: GitHubRepoClient,
    out_path: Path,
    max_chars: int = MAX_CHARS,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    skipped: list[str] = []

    for row in review_rows:
        repo_id = str(row["repo_id"])
        full_name = (row.get("current_full_name") or "").strip()
        if row.get("rule_id") in SKIP_RULES or not full_name:
            skipped.append(repo_id)
            status_counts["skipped"] = status_counts.get("skipped", 0) + 1
            continue

        response = client.request(_readme_url(client, full_name))
        text = _readme_text(response)
        status = "ok" if response.http_status == 200 else response.status_family
        status_counts[status] = status_counts.get(status, 0) + 1
        entry = {
            "repo_id": repo_id,
            "full_name": full_name,
            "ai_label_auto": row.get("ai_label_auto"),
            "rule_id": row.get("rule_id"),
            "http_status": response.http_status,
            "status": status,
            "fetched_at_utc": utc_now(),
            "readme_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "readme_chars": len(text),
            "readme_excerpt": text[:max_chars],
        }
        entries.append(entry)
        if progress:
            progress(f"{repo_id} {full_name} -> {status} ({len(text)} chars)")

    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        for entry in entries:
            import json

            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    summary = {
        "generated_at_utc": utc_now(),
        "requested_rows": len(review_rows),
        "evidence_rows": len(entries),
        "skipped_repo_ids": skipped,
        "status_counts": status_counts,
        "max_chars": max_chars,
        "evidence_file": project_relative(out_path),
        "note": "README 仅作人工复核证据；v0.1 规则不读取该字段。",
    }
    write_json(out_path.with_suffix(".summary.json"), summary)
    return summary
