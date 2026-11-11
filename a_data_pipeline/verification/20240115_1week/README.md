# 一周滚动处理的验证记录

数据范围为 UTC 2024-01-15 至 2024-01-21，含首尾七天。2026-11-10 完成单日验收、空间清理和最终跨日合并。处理代码已整理到 [rolling_pipeline](../../rolling_pipeline/README.md)，可按其中步骤获取与处理数据。

| 检查项 | 结果 |
|---|---:|
| 已验证小时档案 | 168 / 168 |
| 原始压缩档案累计 | 13.77 GiB |
| 清洗前有效记录 | 34,437,133 |
| 内容一致的重复出现 | 34 |
| 冲突事件 ID | 0 |
| 最终事件 | 34,437,099 |
| 最终日活动分组 | 8,636,288 |
| 唯一仓库 | 3,301,406 |
| 跨日合并另需移除的日结果行 | 0 |

事件 ID 唯一性、日汇总总数和候选表总数均通过核对。完整交付文件另经过 SHA-256 校验。本批重复出现在日清洗范围内，跨日重复与冲突场景由代码目录中的小样本测试覆盖。详见 [summary.json](summary.json)。

## 哪些文件已共享

```text
verification/20240115_1week/
├── README.md
├── summary.json                 最终计数、检查、输入产物哈希和合并环境
├── coverage.json                七天及 168 小时覆盖
├── input_manifest.csv           原始 URL、大小、SHA-256
├── day_metrics.csv              每日输入、结果、计时和磁盘采样
├── step_timings.csv             01-19—21 的清洗内部计时
├── archive_ingest_timings.csv   同三天逐小时读取/解析/写库计时
├── merge_timings.csv            一周合并各阶段计时
├── cross_day_removals.csv       本批为空表，保留字段
└── reference_outputs.sha256     A 原完整交付产物的哈希
```

本目录的 CSV 统一为 LF 换行，字段和数值保持原运行结果。`reference_outputs.sha256` 对应完整最终产物目录，用于校验另行传输的原数据。输入文件的重新下载按 `input_manifest.csv` 校验。不同环境重算的 Parquet 应核对逻辑内容、schema 和计数。

## 本机完整产物的位置

A 的完整目录为仓库下的 `a_data_pipeline/runs/weekly_20240115_20240121/`，最终产物在 `combined_20240115_20240121_02/`。

- C 使用 `repo_daily_counts.parquet`，原文件约 40 MiB，以及 `coverage.json`。
- B 使用 `repo_candidates.csv`，原文件约 278 MiB。
- 逐条事件在 `events_clean/`，全部有效记录的去重索引在每个来源日期的 `index-*.parquet`。

这些完整数据按本机运行目录管理，可单独分享或按程序重建。代码和本目录的小型记录随 Git 同步。

## 实测时间

| 阶段 | 已完成尝试的累计秒数 |
|---|---:|
| 下载和校验（01-15 复用已有档案） | 1125.526 |
| 原始检查 | 1101.236 |
| Python 清洗和导出 | 2187.812 |
| 索引导出和单日验收 | 62.620 |
| 最终跨日合并，含输入产物复核 | 53.423 |

日清洗基线使用 Python/SQLite。周合并使用 Python 和 DuckDB 1.4.3，DuckDB 配置两线程、3 GB 内存限制和 12 GB 临时文件预算。合并各步见 [merge_timings.csv](merge_timings.csv)。细分计时覆盖 01-19—21，01-15—18 保留阶段总时间。

计时范围、输入和输出一致后再与 Spark 计算加速比。按仓库创建日划分的三个 30 天分析窗口由 C 在日活动表上继续计算。
