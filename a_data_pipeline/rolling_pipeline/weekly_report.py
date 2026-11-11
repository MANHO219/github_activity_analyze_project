"""Summarize accepted days and describe the local rolling-week handoff."""

from __future__ import annotations

import argparse
from pathlib import Path
import csv
import json
import statistics

from weekly_pipeline import DEFAULT_OUTPUT, GIB, read_json, save_json, sha256, size_of_tree

STEP_DESCRIPTIONS = {
    "total_seconds": "Python 清洗整体耗时，包含输入哈希和各子步骤",
    "input_hash_and_setup_seconds": "计算输入哈希并初始化清洗工作区",
    "read_parse_and_sqlite_insert_seconds": "逐小时读取解压、解析校验、写入 SQLite 和异常记录",
    "last_commit_and_event_id_index": "提交最后一个小时并为事件 ID 建索引",
    "sqlite.event_groups": "按事件 ID 汇总重复次数和内容指纹种类",
    "sqlite.group_id_index": "为事件分组建立索引",
    "sqlite.cleaned_events": "生成去重后事件表并排除冲突 ID",
    "sqlite.cleaned_id_index": "为清洗事件的 ID 建立唯一索引",
    "sqlite.cleaned_repo_time_index": "为仓库和时间建立索引",
    "sqlite.duplicate_occurrences": "创建重复事件的查询视图",
    "sqlite.conflicting_occurrences": "创建冲突事件的查询视图",
    "sqlite.daily_counts": "按仓库、UTC 日期和事件类型聚合",
    "duplicate_audit_export": "导出重复事件记录",
    "conflict_audit_export": "导出冲突事件记录",
    "export_cleaned_events_csv_and_parquet": "导出逐条事件 CSV 和 Parquet",
    "export_daily_counts_csv_and_parquet": "导出日汇总 CSV 和 Parquet",
    "write_repo_name_history.csv": "生成仓库名称历史表",
    "write_repo_candidates.csv": "生成仓库候选表",
    "hourly_quality_queries": "逐小时查询质量核对统计",
    "write_hourly_quality.csv": "写出逐小时质量统计",
    "remaining_seconds": "中间提交、最终核对和状态记录等未单独计时部分",
    "verify_accepted_inputs": "复核已验收的事件表、汇总表和索引的大小与哈希",
    "classify_event_ids": "扫描全部有效记录索引，识别跨日重复和冲突",
    "write_event_partitions_and_removals": "生成事件分区和移除明细，无移除的分区复用现有文件",
    "write_coverage_and_manifest": "写出小时覆盖和原始档案清单",
    "initialize_duckdb": "初始化 DuckDB 与 Parquet 读取视图",
    "verify_unique_event_ids": "验证全周事件 ID 唯一",
    "write_daily_activity_parquet": "聚合并写出仓库日活动 Parquet",
    "write_repository_candidates_csv": "聚合并写出仓库候选 CSV",
    "verify_exported_counts": "读回两份汇总，核对事件总数",
    "total_wall_seconds": "从复核输入到跨日汇总对账结束的墙钟耗时",
}


def optional_json(path):
    return read_json(path) if path.exists() else None


def stage_seconds(path):
    result = optional_json(path / "stage_status.json")
    if result is None:
        return None
    if result.get("state") != "completed":
        raise RuntimeError(f"Cannot report time for an incomplete stage: {path}")
    return result["elapsed_seconds"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    status = read_json(args.root / "orchestration.json")
    if status["state"] != "completed":
        raise RuntimeError("The rolling run and final merge have not completed")
    final = Path(status["final_output"])
    summary = read_json(final / "summary.json")
    rows, detailed_steps, archive_timings = [], [], []
    for day in summary["days"]:
        folder = args.root / day
        accepted = read_json(folder / "accepted.json")
        attempt = Path(accepted["attempt"])
        timing = optional_json(attempt / "python/timing_detail.json")
        download = optional_json(attempt / "download/download_manifest.json")
        downloaded = sum(entry["status"] == "downloaded_verified" for entry in download["files"]) if download else 0
        monitors = sorted(folder.glob("disk-monitor-*.json"))
        monitor = read_json(monitors[-1]) if monitors else read_json(folder / "disk_monitor.json")
        cleanup = read_json(folder / "cleanup_plan.json")
        manifest = read_json(accepted["input_manifest"])
        rows.append({"date_utc": day, "hours": accepted["archive_count"],
                     "raw_bytes": sum(item["bytes"] for item in manifest["observed_files"]),
                     "downloaded_archives": downloaded,
                     "reused_archives": accepted["archive_count"] - downloaded,
                     "valid_before_dedup": accepted["valid_before_dedup"],
                     "daily_clean_events": accepted["cleaned_events"],
                     "daily_group_rows": accepted["daily_rows"],
                     "download_seconds": stage_seconds(attempt / "download"),
                     "inspection_seconds": stage_seconds(attempt / "inspection"),
                     "python_clean_and_export_seconds": stage_seconds(attempt / "python"),
                     "python_clean_function_seconds": timing["total_seconds"] if timing else None,
                     "daily_pipeline_wall_seconds": stage_seconds(attempt),
                     "validation_and_index_seconds": accepted["validation_and_index_seconds"],
                     "local_min_free_sampled_bytes": monitor.get("min_local_free_bytes", monitor.get("min_free_bytes")),
                     "external_min_free_sampled_bytes": monitor.get("min_external_free_bytes"),
                     "max_day_output_sampled_bytes": max(monitor.get("max_day_output_bytes", 0), cleanup["day_output_bytes_before_cleanup"]),
                     "day_retained_bytes": size_of_tree(folder)})
        if timing is not None:
            for name in ("total_seconds", "input_hash_and_setup_seconds", "read_parse_and_sqlite_insert_seconds", "remaining_seconds"):
                detailed_steps.append({"date_utc": day, "step": name, "description": STEP_DESCRIPTIONS.get(name, name), "seconds": timing[name]})
            for item in timing["sql_statements"]:
                name = "sqlite." + item["step"]
                detailed_steps.append({"date_utc": day, "step": name, "description": STEP_DESCRIPTIONS.get(name, name), "seconds": item["seconds"]})
            for item in timing["other_steps"]:
                name = item["step"]
                detailed_steps.append({"date_utc": day, "step": name, "description": STEP_DESCRIPTIONS.get(name, name), "seconds": item["seconds"]})
            for name, seconds in timing["per_archive_seconds"].items():
                archive_timings.append({"date_utc": day, "archive": name, "read_parse_insert_seconds": seconds})
    with (args.root / "day_metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (args.root / "step_timings.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date_utc", "step", "description", "seconds"])
        writer.writeheader()
        writer.writerows(detailed_steps)
    with (args.root / "archive_ingest_timings.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date_utc", "archive", "read_parse_insert_seconds"])
        writer.writeheader()
        writer.writerows(archive_timings)
    merge_timings = dict(summary.get("timings_seconds", {}))
    if "total_wall_seconds" in summary:
        merge_timings["total_wall_seconds"] = summary["total_wall_seconds"]
    with (args.root / "merge_timings.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["step", "description", "seconds"])
        for name, seconds in merge_timings.items():
            writer.writerow([name, STEP_DESCRIPTIONS[name], seconds])
    average_raw = statistics.mean(row["raw_bytes"] for row in rows)
    average_retained = statistics.mean(row["day_retained_bytes"] for row in rows)
    projection = {"sample_days": len(rows), "average_raw_bytes_per_day": round(average_raw),
                  "average_retained_daily_bytes": round(average_retained),
                  "estimated_30_days_raw_if_all_kept_bytes": round(average_raw * 30),
                  "estimated_30_days_daily_retained_bytes": round(average_retained * 30),
                  "additional_final_merge_outputs_and_peak_temp_are_not_included": True,
                  "two_day_merge": status["two_day_check"],
                  "final_merge_sampled_temp_peak_bytes": summary.get("max_merge_temp_bytes"),
                  "note": "Linear estimates use one week; archive sizes and merge requirements vary."}
    save_json(args.root / "size_projection.json", projection)

    files = [final / "repo_daily_counts.parquet", final / "repo_candidates.csv", final / "coverage.json",
             final / "input_manifest.csv", final / "cross_day_removals.csv", final / "summary.json"]
    files.extend(sorted((final / "events_clean").glob("*/part-00000.parquet")))
    with (final / "SHA256SUMS.txt").open("w", encoding="utf-8") as output:
        for path in files:
            output.write(f"{sha256(path)}  {path.relative_to(final)}\n")

    daily_stages = ("download_seconds", "inspection_seconds", "python_clean_and_export_seconds", "validation_and_index_seconds")
    stage_totals = [sum(row[key] for row in rows if row[key] is not None) for key in daily_stages]
    minutes = sum(stage_totals) / 60
    merge_seconds = summary.get("total_wall_seconds", summary["elapsed_seconds"])
    daily_timing_lines = []
    for row in rows:
        values = [f"{row[key]:.2f}" if row[key] is not None else "—" for key in daily_stages]
        daily_timing_lines.append(f"| {row['date_utc']} | " + " | ".join(values) + " |")
    daily_timing_lines.append("| 合计 | " + " | ".join(f"{seconds:.2f}" for seconds in stage_totals) + " |")
    daily_timing_table = "\n".join(daily_timing_lines)
    merge_timing_table = "\n".join(f"| {STEP_DESCRIPTIONS[name]} | {seconds:.2f} |" for name, seconds in merge_timings.items())
    if not merge_timing_table:
        merge_timing_table = f"| 合并主体 | {merge_seconds:.2f} |"
    profiled_dates = ", ".join(row["date_utc"] for row in rows if row["python_clean_function_seconds"] is not None)
    table = "\n".join(f"| {row['date_utc']} | {row['hours']} | {row['daily_clean_events']:,} | "
                      f"{row['daily_group_rows']:,} | {row['raw_bytes'] / GIB:.2f} | "
                      f"{row['max_day_output_sampled_bytes'] / GIB:.2f} |" for row in rows)
    readme = f"""# 2024 年 1 月 15—21 日数据交接

这次处理包含 {len(rows)} 个 UTC 日期、{sum(row['hours'] for row in rows)} 个已校验小时档案。单日结果先用相同规则清洗，再按完整事件指纹做跨日去重。跨日合并后有 **{summary['final_events']:,} 条事件**，覆盖 **{summary['candidate_repositories']:,} 个仓库**。

```text
{args.root.name}/
├── README.md                 这份说明
├── day_metrics.csv           每天的输入量、结果、耗时和抽样磁盘占用
├── step_timings.csv          后续日期的 Python 清洗步骤计时
├── archive_ingest_timings.csv  后续日期逐小时档案的读取、解析和写库耗时
├── merge_timings.csv         跨日去重、输出和对账各阶段的实际耗时
├── size_projection.json      30 天空间粗估，未包含最终合并峰值
├── 2024-01-15/ ... 2024-01-21/
│   ├── accepted.json         每日验收结果与保留文件哈希
│   ├── index-01.parquet      全部有效记录的跨日去重索引，含当天冲突 ID
│   ├── cleanup_plan.json     当天清理前列出的文件及占用
│   ├── cleanup_done.json     已清理文件记录
│   └── attempt-01/           输入清单、质量报告、异常记录与每日 Parquet
├── {Path(status['two_day_check']).name}/  两日合并验收及结果
└── {final.name}/
    ├── events_clean/          按来源日期分目录的逐条事件 Parquet
    ├── repo_daily_counts.parquet  C 的仓库 × UTC 事件日期 × 事件类型汇总
    ├── repo_candidates.csv    B 的一仓库一行候选表
    ├── coverage.json          已处理的小时覆盖
    ├── input_manifest.csv     D 可用的原始 URL、大小和 SHA-256
    ├── cross_day_removals.csv 跨日合并从日结果移除的记录
    ├── summary.json           跨日去重和最终对账结果
    └── SHA256SUMS.txt         交付文件的哈希
```

每个 `events_clean/` 下的目录按**档案来源日期**存放，事件所属日期仍以文件内的 `event_date` 为准。`repo_daily_counts.parquet` 的 `event_count` 是公开事件条数。B 的 `repo_name` 是样本中最近一次有名称的观测值，`first_observed_at` 是样本中的首见活动时间，仓库的创建时间和 AI 标签需要继续接 B 的元数据。

| 来源日期 UTC | 档案数 | 单日清洗事件 | 单日汇总行数 | 原始压缩 GiB | 本机单日输出采样峰值 GiB |
|---|---:|---:|---:|---:|---:|
{table}

表中的单日数字是在跨日去重之前。最终事件 ID 唯一，日汇总总数和候选表事件数都与最终事件总数一致，详细检查见 `summary.json`。索引保留清洗前所有有效记录的 ID、完整记录指纹和来源，冲突 ID 的每条出现都会排除。

1 月 15 日的原始档案和原基准保留。1 月 16—21 日的原始档案在当日验收和两日合并通过后按清单清理，仍可用 `input_manifest.csv` 重新下载。每日报告、异常和清洗事件保留，本轮 SQLite 过程库和重复的 CSV 导出已按 `cleanup_done.json` 清理。

## 实测耗时

| 来源日期 UTC | 下载与校验（秒） | 原始检查（秒） | Python 清洗与导出（秒） | 索引与单日验收（秒） |
|---|---:|---:|---:|---:|
{daily_timing_table}

1 月 15 日复用已有档案。表中下载阶段包含传输、gzip 完整性检查与 SHA-256 计算。原始检查和清洗分别读取输入。四列相加约 **{minutes:.1f} 分钟**，统计各日通过验收的尝试，包含单日索引导出，跨日合并另计。`daily_pipeline_wall_seconds` 记录该日管道从启动到完成的时间，也覆盖阶段开始前的输入哈希与管道开销。磁盘占用按约 15 秒采样，可能漏掉短暂峰值。

清洗内部的实测记录覆盖 {profiled_dates or '已启用细分计时的日期'}，包括逐小时解压、解析和写库，SQLite 去重与聚合，导出以及质量查询。`total_seconds` 包含清洗开始前的输入哈希和各子步骤。较早日期保留阶段总时间。 [逐日计时](day_metrics.csv) · [清洗步骤计时](step_timings.csv) · [逐小时读取计时](archive_ingest_timings.csv)

| 跨日合并步骤 | 墙钟秒 |
|---|---:|
{merge_timing_table}

周合并用 Python 扫描索引，用 DuckDB 执行唯一性查询和汇总。各步合计与整体耗时之间的微小差值来自阶段切换、检查与关闭连接。 [合并计时](merge_timings.csv)

后续比较 Spark 时，按 `input_manifest.csv` 的 SHA-256 固定输入，在同一机器、存储和缓存条件下测量同等输出的清洗与导出。用两种实现各自的 `stage_status.json` 对齐计时边界，把下载与原始检查单列。若比较 Spark 并行度，以 Spark 单核的同任务耗时除以多核耗时。若比较跨日合并，需保持事件去重规则、汇总和验收范围一致，现有基线使用 Python 和 DuckDB。

按本周平均值线性外推，30 天原始档案全留约 **{average_raw * 30 / GIB:.1f} GiB**，逐日清理后每天保留的产物合计约 **{average_retained * 30 / GIB:.1f} GiB**。最终合并输出和临时空间需要另算。两日和一周合并的实测记录可用于进一步评估。

处理脚本在 `a_data_pipeline/rolling_pipeline/`，使用说明见该目录的 `README.md`。运行结果保存在本机。重新运行入口为 `weekly_orchestrate.py`，它会检查已验收的日期并从失败处继续。日期和批次通用化、Spark 接入的后续任务见代码目录说明。
"""
    (args.root / "README.md").write_text(readme, encoding="utf-8")
    print(f"Handoff written to {args.root / 'README.md'}", flush=True)


if __name__ == "__main__":
    main()
