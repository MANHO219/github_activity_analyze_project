# 2024-01-15 全天数据：处理结果与交接

本次数据覆盖 UTC 2024-01-15 00:00:00 至 2024-01-16 00:00:00（不包含结束时刻）。24 个 GH Archive 小时文件全部下载并校验；本机保留原始文件和处理过程。当前先交付 **Python 清洗结果**，全天 Spark 复算和两条路径的全天比较待完成。

## 已完成的结果

| 项目 | 结果 |
|---|---:|
| 原始小时档案 | 24 个，压缩文件共 2,593,554,046 字节（约 2.42 GiB） |
| 清洗前有效事件记录 | 5,528,301 |
| 移除的重复记录 | 1 |
| 冲突事件 ID | 0 |
| 清洗后事件 | 5,528,300 |
| 唯一仓库 | 852,777 |
| 仓库 × 日期 × 事件类型的日统计分组 | 1,340,785 |

其中 69,768 个仓库已在第一小时的样本中出现，另外 783,009 个在当天其他时段首次被本样本观察到。**这不是说它们在当天创建，也不是说它们都是 AI 仓库。**

Python 清洗的数量对账、日统计总数、事件 ID 唯一性检查均通过。另对清洗事件 Parquet 行数、日统计 CSV 和 Parquet 的分组数及总数、事件类型总数、UTC 时间字段类型进行了核对，结果在 [python_verification.json](python_verification.json)。这些核对不包含 CSV 与 Parquet 每一行的完整字段对比。

连续三小时试跑的 Python 与 Spark 对比通过，19 项检查均通过，见 [three_hour_comparison.json](three_hour_comparison.json)。这是三小时结果，不代表全天 Spark 已通过验证。

## 供 B、C、D 使用的数据

在执行数据处理的电脑上，交接文件位于 `runs/20240115_24h_validate/handoff/`：

```text
handoff/
├── README.md                           给组员的文件说明
├── cs5488_20240115_1day_handoff.zip    可单独分享的分析数据包
├── SHA256SUMS.txt                      数据包 SHA-256
├── handoff_summary.json                数量、质量和运行状态
├── input_slices.json                   D 的 1/3/6/12/24 小时输入清单
└── repo_candidates_with_baseline_status.csv  B 的候选仓库清单
```

| 使用者 | 从数据包中读取 | 用途与边界 |
|---|---|---|
| B | `handoff/repo_candidates_with_baseline_status.csv` | 一仓库一行；`seen_in_first_hour` 标识是否曾在第一小时样本出现，不能当作创建日期或 AI 标签。 |
| C | `python/events_clean.parquet/`、`python/repo_daily_counts.parquet/` 或 `.csv` | 前者是一条事件一行；后者是仓库 × UTC 日期 × 事件类型的统计。`event_count` 统计事件条数，PushEvent 次数不等于提交次数。 |
| D | `handoff/input_slices.json` | 包含嵌套的 1、3、6、12、24 小时输入文件名、下载地址、字节数和 SHA-256；原始压缩包不包含在交接 ZIP 中。 |

数据包大小 295,942,443 字节，SHA-256：

```text
2c13a26bbed84b4f5c67e93e72b2df1d457a5bde2633a4062cb38a8afe48cd36
```

数据包经过 ZIP 完整性检查与 SHA-256 复核。它和原始数据均被 `.gitignore` 排除，需要另行分享；本目录中的 [input_slices.json](input_slices.json) 是可随 Git 共享的小型输入清单。[handoff_summary.json](handoff_summary.json) 记录清洗结果、运行状态和规则版本。

## 全天 Spark 状态

首次全天运行已经完成下载、检查和 Python 清洗。后续 Spark 在把排序结果输出到驱动进程时出现异常，观察到 1 GiB 的 JVM 堆接近满载且导出阶段长时间未进展，因此主动中断，保留现场；具体根因尚待进一步验证。

因此原全天运行的 `run_summary.json` 显示 `failed`（`KeyboardInterrupt`），而其中 `python/stage_status.json` 显示 `completed`。这表示全天 Python 阶段完成，但**全天 Spark 清洗和 Python/Spark 比较尚未通过**；当前不能把中断运行的耗时作为并行实验结论。

## 重现和限制

从 Git 克隆的组员可按 [获取更长时间的数据](../../README.md#获取更长时间的数据) 下载和处理指定日期。原始档案、全天数据和上述交接 ZIP 不随 Git 提供；需要各自重跑，或由数据持有者另外分享交接包。

`first_observed_at` 是档案样本中的首见活动时间，不是仓库创建时间。创建时间和 AI 标签需要与 B 的仓库元数据接回。24 个文件存在不代表 GH Archive 捕获了 GitHub 的所有活动；一天数据也不能用于仓库的生命周期结论。
