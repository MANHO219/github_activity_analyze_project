#!/usr/bin/env python3
"""固定 B 的首批试跑名单（默认 50 个：40 随机 + 10 关键词过采样）。

用法：

    python scripts/build_pilot.py

默认输出到 ``runs/pilot_01/``；已存在名单时拒绝覆盖，需显式 ``--force``。
名单与选取依据（种子、输入 SHA-256、分层计数）同时写入 ``selection.json``。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401  (设置 sys.path)
from bmeta.common import (
    B_ROOT,
    load_config,
    project_relative,
    read_csv,
    sha256_file,
    update_run_summary,
    utc_now,
    write_csv,
    write_json,
)
from bmeta.select import SELECTED_FIELDS, select_pilot, stratum_counts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="固定 B 的首批试跑仓库名单")
    parser.add_argument("--config", default=str(B_ROOT / "config" / "pilot.json"))
    parser.add_argument("--candidates", help="A 的 repo_candidates.csv；默认取配置")
    parser.add_argument("--out-dir", help="运行目录；默认 runs/<pilot_version>")
    parser.add_argument("--seed", type=int, help="随机种子；默认取配置")
    parser.add_argument("--random-size", type=int, help="随机层大小；默认取配置")
    parser.add_argument("--keyword-size", type=int, help="关键词层大小；默认取配置")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的 pilot_candidates.csv")
    parser.add_argument(
        "--exclude",
        help="排除名单 CSV（读取 repo_id 列，如上一轮的 pilot_candidates.csv），用于扩大试跑时不重叠",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    candidates = Path(args.candidates or config["candidates_csv"])
    out_dir = Path(args.out_dir or (B_ROOT / "runs" / config["pilot_version"]))
    seed = args.seed if args.seed is not None else int(config["seed"])
    random_size = args.random_size if args.random_size is not None else int(config["strata"]["random"])
    keyword_size = args.keyword_size if args.keyword_size is not None else int(config["strata"]["keyword_name"])

    pilot_csv = out_dir / "pilot_candidates.csv"
    if pilot_csv.exists() and not args.force:
        print(f"refusing to overwrite frozen pilot list: {project_relative(pilot_csv)} (use --force)")
        return 1

    candidates_rows = read_csv(candidates)
    exclude_rows = read_csv(Path(args.exclude)) if args.exclude else []
    exclude_ids = {int(row["repo_id"]) for row in exclude_rows}
    pilot_rows = select_pilot(
        candidates_rows,
        seed=seed,
        random_size=random_size,
        keyword_size=keyword_size,
        exclude_ids=exclude_ids,
    )
    write_csv(pilot_csv, SELECTED_FIELDS, pilot_rows)

    strata = stratum_counts(pilot_rows)
    selection = {
        "pilot_version": out_dir.name,
        "generated_at_utc": utc_now(),
        "method": (
            "Sort candidates by repo_id (after removing excluded ids); draw `random` stratum with "
            "random.Random(seed).sample; then draw `keyword_name` stratum from remaining rows whose "
            "owner/repo name matches the coarse AI name probe. The keyword stratum is deliberately "
            "oversampled for rule coverage and must not be used to estimate GitHub-wide AI share."
        ),
        "seed": seed,
        "strata_requested": {"random": random_size, "keyword_name": keyword_size},
        "strata_actual": strata,
        "excluded": {
            "path": project_relative(Path(args.exclude)),
            "rows": len(exclude_ids),
            "sha256": sha256_file(Path(args.exclude)),
        }
        if args.exclude
        else None,
        "input": {
            "path": project_relative(candidates),
            "rows": len(candidates_rows),
            "sha256": sha256_file(candidates),
        },
        "output": {
            "path": project_relative(pilot_csv),
            "rows": len(pilot_rows),
            "sha256": sha256_file(pilot_csv),
        },
        "repo_ids": [row["repo_id"] for row in pilot_rows],
        "debug_sample": {
            **config.get("debug_sample", {}),
            "counted_in_pilot": False,
        },
        "notes": [
            "首批名单用于跑通流程与调规则，不能据此直接估计整个 GitHub 的 AI 仓库比例。",
            "keyword_name 层来自名称粗筛，名称命中不等于 AI 判定；实际标签仍由 rules 决定。",
        ],
    }
    write_json(out_dir / "selection.json", selection)
    update_run_summary(out_dir / "run_summary.json", "pilot", selection)

    print(f"pilot rows: {len(pilot_rows)} -> {project_relative(pilot_csv)}")
    print(f"strata: {strata}")
    print(f"selection sha256: {selection['output']['sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
