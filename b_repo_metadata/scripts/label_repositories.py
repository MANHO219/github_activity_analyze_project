#!/usr/bin/env python3
"""对已抓取的元数据应用 AI 规则，生成 ``repo_ai_labels.csv``。

    python scripts/label_repositories.py

规则来自 ``rules/ai_rules_v0.1.json``（版本、优先级、理由都在该文件里）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from bmeta.common import B_ROOT, load_config, project_relative
from bmeta.label import run as label_run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="应用 AI 规则并输出标签表")
    parser.add_argument("--config", default=str(B_ROOT / "config" / "pilot.json"))
    parser.add_argument("--run-dir", help="运行目录；默认 runs/<pilot_version>")
    parser.add_argument("--metadata", help="默认 <run-dir>/repo_metadata.csv")
    parser.add_argument("--rules", help="默认取配置中的 rules_file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    out_dir = Path(args.run_dir or (B_ROOT / "runs" / config["pilot_version"]))
    metadata = Path(args.metadata or (out_dir / "repo_metadata.csv"))
    rules = Path(args.rules or config["rules_file"])
    for path in (metadata, rules):
        if not path.exists():
            print(f"missing input: {project_relative(path)}")
            return 1

    summary = label_run(metadata, out_dir, rules)
    print(f"rules: {summary['rules_version']} ({project_relative(rules)})")
    print(f"labels: {summary['by_label']}")
    print(f"by_rule: {summary['by_rule']}")
    print(f"labels csv: {project_relative(out_dir / 'repo_ai_labels.csv')}")
    if not all(summary["counts_check"].values()):
        print(f"WARNING: count checks failed: {summary['counts_check']}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
