#!/usr/bin/env python3
"""抓取首批 50 个仓库的元数据（串行、缓存、可续跑）。

前置：``python scripts/build_pilot.py`` 已生成 ``runs/pilot_01/pilot_candidates.csv``。

    set GITHUB_TOKEN=ghp_xxx        # Windows  (export 用于 macOS/Linux)
    python scripts/fetch_metadata.py

不带 token 也能跑，只是配额为每小时 60 次；50 个仓库仍可完成，但更容易触发限流。
配额用尽时脚本会停在当前仓库之前，已抓取结果保留；重新执行同一命令即可续跑。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from bmeta.api import GitHubRepoClient
from bmeta.common import B_ROOT, load_config, project_relative, read_csv
from bmeta.fetch import run as fetch_run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取 B 首批仓库的元数据")
    parser.add_argument("--config", default=str(B_ROOT / "config" / "pilot.json"))
    parser.add_argument("--run-dir", help="运行目录；默认 runs/<pilot_version>")
    parser.add_argument("--input", help="名单 CSV；默认 <run-dir>/pilot_candidates.csv")
    parser.add_argument("--token-env", help="读取 token 的环境变量名；默认取配置")
    parser.add_argument("--interval", type=float, help="两次请求的最小间隔秒数；默认取配置")
    parser.add_argument("--max-repos", type=int, help="只处理前 N 个（调试用）")
    parser.add_argument("--force-refresh", action="store_true", help="忽略 raw_api 缓存重新请求")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    api = config["api"]
    out_dir = Path(args.run_dir or (B_ROOT / "runs" / config["pilot_version"]))
    input_csv = Path(args.input or (out_dir / "pilot_candidates.csv"))
    if not input_csv.exists():
        print(f"missing pilot list: {project_relative(input_csv)}")
        return 1

    client = GitHubRepoClient(
        token_env=args.token_env or api["token_env_var"],
        base_url=api["base_url"],
        user_agent=api["user_agent"],
        accept=api["accept"],
        timeout=float(api["timeout_seconds"]),
        max_attempts=int(api["max_attempts"]),
        backoff_seconds=tuple(float(value) for value in api["backoff_seconds"]),
        request_interval_seconds=args.interval if args.interval is not None else float(api["request_interval_seconds"]),
    )
    pilot_rows = read_csv(input_csv)
    print(
        f"fetching {len(pilot_rows)} repos from {project_relative(input_csv)} "
        f"(token: {'present' if client.has_token else 'absent -> 60 req/h'})"
    )
    summary = fetch_run(
        pilot_rows,
        out_dir,
        client=client,
        force_refresh=args.force_refresh,
        max_repos=args.max_repos,
        progress=lambda message: print(message, flush=True),
    )

    print(f"processed={summary['processed_rows']} pending={summary['pending_rows']} calls={summary['api_calls']}")
    print(f"status_counts={summary['status_counts']}")
    if summary["pending_rows"]:
        print("WARNING: rate limited; rerun the same command to continue", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
