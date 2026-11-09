#!/usr/bin/env python3
"""抓取 README 摘要，作为复核或标注的可回查证据。

两种输入：

- 复核清单（默认）：``runs/<run>/manual_review.csv``，跳过 404 / ID 不一致的仓库；
- 候选名单：``--input runs/pilot_02/pilot_candidates.csv``，按 ``repo_name`` 抓取，
  用于新一批扩大试跑的证据快照。

输出默认 ``<run-dir>/manual_review_readmes.jsonl``（复核）或 ``<run-dir>/readme_evidence.jsonl``
（候选名单，需显式 ``--out``）；每行含 README 前 4000 字符、SHA-256 与抓取时间。
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
    parser = argparse.ArgumentParser(description="抓取 README 证据")
    parser.add_argument("--config", default=str(B_ROOT / "config" / "pilot.json"))
    parser.add_argument("--run-dir", help="运行目录；默认 runs/<pilot_version>")
    parser.add_argument("--input", help="候选名单 CSV（含 repo_id、repo_name）；默认用复核清单")
    parser.add_argument("--review", help="复核清单；默认 <run-dir>/manual_review.csv")
    parser.add_argument("--out", help="输出 JSONL；默认 <run-dir>/manual_review_readmes.jsonl")
    parser.add_argument("--token-env", help="读取 token 的环境变量名；默认取配置")
    return parser.parse_args(argv)


def _rows_from_candidates(path: Path) -> list[dict]:
    rows = []
    for row in read_csv(path):
        rows.append(
            {
                "repo_id": row["repo_id"],
                "current_full_name": row.get("repo_name", ""),
                "ai_label_auto": "",
                "rule_id": "",
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    api = config["api"]
    out_dir = Path(args.run_dir or (B_ROOT / "runs" / config["pilot_version"]))

    if args.input:
        input_csv = Path(args.input)
        if not input_csv.exists():
            print(f"missing candidate list: {project_relative(input_csv)}")
            return 1
        rows = _rows_from_candidates(input_csv)
        default_out = out_dir / "readme_evidence.jsonl"
    else:
        input_csv = Path(args.review or (out_dir / "manual_review.csv"))
        if not input_csv.exists():
            print(f"missing review sheet: {project_relative(input_csv)}")
            return 1
        rows = read_csv(input_csv)
        default_out = out_dir / "manual_review_readmes.jsonl"

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
        rows,
        client=client,
        out_path=Path(args.out or default_out),
        progress=lambda message: print(message, flush=True),
    )
    update_run_summary(out_dir / "run_summary.json", "review_evidence", summary)
    print(f"evidence rows: {summary['evidence_rows']} status_counts={summary['status_counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
