#!/usr/bin/env python3
"""对已抓取的元数据应用 AI 规则，生成 ``repo_ai_labels.csv``。

    python scripts/label_repositories.py

规则默认取 ``config/pilot.json`` 的 ``rules_file``（当前 v0.3）。
v0.3 起会用 README 补足规则判为 uncertain 的仓库：默认读取
``<run-dir>/manual_review_readmes.jsonl``（存在时），也可用
``--readme-evidence`` 指定，或用 ``--no-readme`` 关闭。
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
    parser.add_argument(
        "--readme-evidence",
        help="README 证据 JSONL；默认 <run-dir>/manual_review_readmes.jsonl（存在时使用）",
    )
    parser.add_argument("--no-readme", action="store_true", help="关闭 README 辅助判断")
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

    if args.no_readme:
        evidence: Path | None = None
    elif args.readme_evidence:
        evidence = Path(args.readme_evidence)
    else:
        candidate = out_dir / "manual_review_readmes.jsonl"
        evidence = candidate if candidate.exists() else None
    if evidence is not None and not evidence.exists():
        print(f"missing readme evidence: {project_relative(evidence)}")
        return 1

    summary = label_run(metadata, out_dir, rules, readme_evidence_path=evidence)
    print(f"rules: {summary['rules_version']} ({project_relative(rules)})")
    print(f"labels: {summary['by_label']}")
    print(f"by_rule: {summary['by_rule']}")
    readme = summary.get("readme_evidence", {})
    print(f"readme_evidence: used={readme.get('used_rows', 0)} decisions={readme.get('decisions', {})}")
    print(f"labels csv: {project_relative(out_dir / 'repo_ai_labels.csv')}")
    if not all(summary["counts_check"].values()):
        print(f"WARNING: count checks failed: {summary['counts_check']}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

