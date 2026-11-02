#!/usr/bin/env python3
"""单仓库连通性样例：``GET /repos/apache/superset``，核对返回 id 是否等于 39464018。

这是 ``B_接手指南.md`` 第 2 节第 1 步的“先跑通 1 个仓库”，结果单独放在
``runs/debug_api_sample/``，不计入 50 个试跑名单。

    python scripts/check_api_sample.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from bmeta.api import GitHubRepoClient
from bmeta.common import (
    B_ROOT,
    load_config,
    project_relative,
    update_run_summary,
    utc_now,
    write_json,
)
from bmeta.fetch import (
    _cache_path,
    _envelope_from_response,
    _load_cache,
    _metadata_row,
    _status_from_envelope,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="单仓库 API 连通性与 ID 一致性检查")
    parser.add_argument("--config", default=str(B_ROOT / "config" / "pilot.json"))
    parser.add_argument("--out-dir", help="默认 runs/debug_api_sample")
    parser.add_argument("--repo-name", help="默认取配置中的 debug_sample.repo_name")
    parser.add_argument("--repo-id", type=int, help="默认取配置中的 debug_sample.repo_id")
    parser.add_argument("--token-env", help="读取 token 的环境变量名；默认取配置")
    parser.add_argument("--force-refresh", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    api = config["api"]
    debug = config.get("debug_sample", {})
    out_dir = Path(args.out_dir or (B_ROOT / "runs" / "debug_api_sample"))
    name = args.repo_name or debug.get("repo_name", "apache/superset")
    repo_id = int(args.repo_id or debug.get("repo_id", 39464018))

    client = GitHubRepoClient(
        token_env=args.token_env or api["token_env_var"],
        base_url=api["base_url"],
        user_agent=api["user_agent"],
        accept=api["accept"],
        timeout=float(api["timeout_seconds"]),
        max_attempts=int(api["max_attempts"]),
        backoff_seconds=tuple(float(value) for value in api["backoff_seconds"]),
        request_interval_seconds=float(api["request_interval_seconds"]),
    )
    cache_dir = out_dir / "raw_api"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = _cache_path(cache_dir, repo_id)

    envelope = None if args.force_refresh else _load_cache(cache_file)
    cached = envelope is not None
    if envelope is None:
        response = client.get_repo(name)
        envelope = _envelope_from_response(repo_id, name, response, utc_now())
        write_json(cache_file, envelope)

    row = _metadata_row(repo_id, name, envelope, "ok")
    body = envelope.get("response") or {}
    id_match = str(body.get("id")) == str(repo_id)
    check = {
        "checked_at_utc": utc_now(),
        "requested_repo_id": repo_id,
        "requested_name": name,
        "api_repo_id": body.get("id"),
        "current_full_name": body.get("full_name"),
        "repo_created_at": body.get("created_at"),
        "description": body.get("description"),
        "topics": body.get("topics"),
        "language": body.get("language"),
        "archived": body.get("archived"),
        "http_status": envelope.get("http_status"),
        "final_url": envelope.get("final_url"),
        "redirected": bool(envelope.get("final_url")) and envelope.get("final_url", "").rsplit("/repos/", 1)[-1] != name,
        "cached": cached,
        "token_present": client.has_token,
        "id_match": id_match,
        "metadata_row": row,
        "raw_file": project_relative(cache_file),
        "rate_limit": envelope.get("rate_limit"),
    }
    write_json(out_dir / "api_sample_check.json", check)
    update_run_summary(out_dir / "run_summary.json", "api_sample", check)

    print(f"GET /repos/{name} -> HTTP {check['http_status']}")
    print(f"api id={check['api_repo_id']} requested={repo_id} match={id_match}")
    print(f"full_name={check['current_full_name']} created_at={check['repo_created_at']}")
    print(f"raw saved: {check['raw_file']}")
    return 0 if id_match else 2


if __name__ == "__main__":
    sys.exit(main())
