"""Thin command-line entry points; data rules live in records.py."""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .common import ROOT, add_input_arguments, load_config, stage_directory, stage_parser, write_json


def main_stage(name):
    if name == "compare":
        parser = argparse.ArgumentParser(description="Compare completed Python and Spark sample runs")
        parser.add_argument("--python-output", type=Path, required=True)
        parser.add_argument("--spark-output", type=Path, required=True)
        parser.add_argument("--output", type=Path, required=True)
        args = parser.parse_args()
        from .compare import compare
        result = compare(args.python_output, args.spark_output, args.output)
    else:
        parser = stage_parser(f"GH Archive A role: {name}")
        if name == "clean":
            parser.add_argument("--csv-only", action="store_true", help="Skip Parquet when PyArrow is unavailable")
        if name == "spark":
            parser.add_argument("--master", default="local[2]")
        args = parser.parse_args()
        cfg = load_config(args)
        if name == "download":
            from .download import download
            result = download(cfg, args.data_dir, args.output, args.allow_missing)
        elif name == "inspect":
            from .inspect import inspect
            result = inspect(cfg, args.data_dir, args.output, args.allow_missing)
        elif name == "clean":
            from .clean import clean
            result = clean(cfg, args.data_dir, args.output, args.allow_missing, not args.csv_only)
        elif name == "spark":
            from .spark_clean import clean_spark
            result = clean_spark(cfg, args.data_dir, args.output, args.allow_missing, args.master)
        else:
            raise ValueError(f"Unknown stage {name}")
    print(json.dumps({"output": str(args.output.resolve()), "completed": True,
                      "cleaned_events": result.get("cleaned_events"), "passed": result.get("passed")}, ensure_ascii=False))


def main_run():
    parser = argparse.ArgumentParser(description="Run the A-role sample pipeline in a new, auditable directory")
    add_input_arguments(parser)
    parser.add_argument("--run-dir", type=Path, help="Must not already exist; defaults to runs/<UTC timestamp>")
    parser.add_argument("--skip-download", action="store_true", help="Use existing local archives without network requests")
    parser.add_argument("--csv-only", action="store_true", help="Skip Python Parquet output")
    parser.add_argument("--with-spark", action="store_true", help="Also run Spark and compare results")
    parser.add_argument("--master", default="local[2]")
    args = parser.parse_args()
    cfg = load_config(args)
    out = args.run_dir or ROOT / "runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    with stage_directory(out, "pipeline", cfg) as directory:
        logger = logging.getLogger("gharchive_a")
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(directory / "pipeline.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        summary = {"state": "running", "run_directory": str(directory), "config": cfg, "stages": {}}
        write_json(directory / "resolved_config.json", cfg)

        def run_stage(name, fn):
            logger.info("Starting %s", name)
            print(f"Starting {name}", flush=True)
            value = fn()
            summary["stages"][name] = {"completed": True, "output": str(directory / name)}
            if "cleaned_events" in value:
                summary["stages"][name]["cleaned_events"] = value["cleaned_events"]
            logger.info("Completed %s", name)
            write_json(directory / "run_summary.json", summary)
            return value

        try:
            from .clean import clean
            from .download import download
            from .inspect import inspect
            if not args.skip_download:
                run_stage("download", lambda: download(cfg, args.data_dir, directory / "download", args.allow_missing))
            run_stage("inspection", lambda: inspect(cfg, args.data_dir, directory / "inspection", args.allow_missing))
            quality = run_stage("python", lambda: clean(cfg, args.data_dir, directory / "python", args.allow_missing, not args.csv_only))
            if args.with_spark:
                from .compare import compare
                from .spark_clean import clean_spark
                run_stage("spark", lambda: clean_spark(cfg, args.data_dir, directory / "spark", args.allow_missing, args.master))
                run_stage("comparison", lambda: compare(directory / "python", directory / "spark", directory / "comparison"))
            summary.update(state="completed", clean_events=quality["cleaned_events"], coverage=quality["coverage"])
            note = (f"# A 样本运行交接\n\n清洗后事件：{quality['cleaned_events']}；仓库：{quality['clean_unique_repos']}。\n\n"
                    f"重复记录移除：{quality['duplicates_removed']}；冲突 ID：{quality['conflicting_ids']}；"
                    f"冲突记录暂排除：{quality['conflict_occurrences_excluded']}。\n\n"
                    f"本次覆盖：{', '.join(f['name'] for f in quality['coverage']['observed_files'])}。\n\n"
                    "交接优先读取 `python/quality_summary.json`、`python/events_preview.csv`、"
                    "`python/repo_candidates.csv` 和 `python/events_clean.parquet/`（CSV-only 时用 CSV.gz）。\n\n"
                    "小时覆盖清单在 `python/input_manifest.json`；日计数仅覆盖已读取档案，不能补推未读取时段的活动。"
                    "AI 分类与生命周期判断由后续阶段完成。\n\n"
                    "清洗前有效记录在 `python/working.sqlite3`，异常、重复和冲突记录另有文件；原始 payload 保存在原始小时档案。\n")
            (directory / "HANDOFF.md").write_text(note, encoding="utf-8")
        except BaseException as error:
            summary.update(state="failed", error=f"{type(error).__name__}: {error}")
            logger.exception("Pipeline failed")
            raise
        finally:
            write_json(directory / "run_summary.json", summary)
            logger.removeHandler(handler)
            handler.close()
    print(f"Completed. Handoff: {Path(out).resolve() / 'HANDOFF.md'}", flush=True)
