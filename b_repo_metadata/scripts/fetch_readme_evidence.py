#!/usr/bin/env python3
"""抓取复核清单中可读取仓库的 README 摘要，作为人工判断的可回查证据。

    python scripts/fetch_readme_evidence.py --run-dir runs/pilot_01

输出 ``<run-dir>/manual_review_readmes.jsonl`` 与同名 ``.summary.json``。
规则 v0.1 本身不读 README；这里只是把 B 复核时看得到的信息记录下来。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from bmeta.api import GitHubRepoClient
from bmeta.common import B_ROOT, load_config, project_relative, read_csv, update_run_summary
from bmeta.evidence import fetch_evidence


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取复核用 README 证据")
    parser.add_argument("--config", default=str(B_ROOT / "config" / "pilot.json"))
    parser.add_argument("--run-dir", help="运行目录；默认 runs/<pilot_version>")
    parser.add_argument("--review", help="默认 <run-dir>/manual_review.csv")
    parser.add_argument("--out", help="默认 <run-dir>/manual_review_readmes.jsonl")
    parser.add_argument("--token-env", help="读取 token 的环境变量名；默认取配置")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    api = config["api"]
    out_dir = Path(args.run_dir or (B_ROOT / "runs" / config["pilot_version"]))
    review_csv = Path(args.review or (out_dir / "manual_review.csv"))
    if not review_csv.exists():
        print(f"missing review sheet: {project_relative(review_csv)}")
        return 1

    client = GitHubRepoClient(
        token_env=args.token_env or api["token_env_var"],
        base_url=api["base_url"],
        user_agent=api["user_agent"],
        timeout=float(api["timeout_seconds"]),
        max_attempts=int(api["max_attempts"]),
        backoff_seconds=tuple(float(value) for value in api["backoff_seconds"]),
        request_interval_seconds=float(api["request_interval_seconds"]),
    )
    summary = fetch_evidence(
        read_csv(review_csv),
        client=client,
        out_path=Path(args.out or (out_dir / "manual_review_readmes.jsonl")),
        progress=lambda message: print(message, flush=True),
    )
    update_run_summary(out_dir / "run_summary.json", "review_evidence", summary)
    print(f"evidence rows: {summary['evidence_rows']} status_counts={summary['status_counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
