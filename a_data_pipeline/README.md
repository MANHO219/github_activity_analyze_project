# A 数据启动脚本：从小时档案到可交接事件表

**第一次接触项目，请先打开 [数据处理全解（HTML）](数据处理全解.html)：完整数据流、原始与处理后结构、每一步脚本、13 列来源、58 项文件分类与后续用途都放在一起。** 本 README 提供运行与代码交接细节；[原 Markdown 数据说明](数据说明_给组员.md) 保留为简短说明。

**B 接手时先读 [B 接手指南](B_接手指南.md)。** A 已提供唯一仓库清单；B 可以先在自己电脑跑通一个仓库，再用建议的 50 个仓库试跑元数据获取和 AI 标签。输入路径、建议交付字段和完成条件已列出；正式范围与 AI 规则由 A、B 确认。

HTML 的字段、计数、真实例子和源码从实际运行读取并内嵌，单文件即可分享。后续更新文档可运行 `python scripts/build_data_guide.py --run-dir runs/20240115_1hour_handoff`；它只更新说明文件。

按 [A 的启动计划](../A_启动任务_最小数据样本.md) 实现。默认读取 `2024-01-15` UTC 0 时；也支持指定多个小时。输出保留来源、清洗计数及异常记录，方便组员回查。

**全天扩展：** 2024-01-15 的 24 小时 Python 处理已完成；全天 Spark 复算暂未完成。Git 中提供一份可直接分析的[全天仓库活动汇总表](sample_data/20240115_24h/repo_daily_counts.csv)：1,340,785 行，字段为 `repo_id`、`event_date`、`event_type`、`event_count`，所有计数合计 5,528,300 条事件。它按仓库、UTC 日期和事件类型聚合，不包含逐条事件详情。其他数量与处理限制见[全天结果与交接](verification/20240115_1day/README.md)。完整事件表、原始档案和过程数据库保存在处理机本地；组员可按下文命令重新获取和生成。

## 最快启动

在项目仓库根目录执行：

```bash
cd a_data_pipeline
conda activate cs5488-data
python scripts/run_sample.py --with-spark
```

这条命令使用原来的**一小时默认样本**，用于熟悉环境和验证流程；它不会处理全天数据。要获取完整 24 小时事件表，请看下方[获取更长时间的数据](#获取更长时间的数据)。

每次自动建立 `runs/<UTC 时间>/`，完成后打开其中的 `HANDOFF.md`。如果原始档案已下载，程序会校验后复用。已有运行目录会被拒绝，不会覆盖此前结果或重复追加数据。

换到组员电脑，在此目录创建同样环境：

```bash
conda env create --file environment.yml
conda activate cs5488-data
python scripts/run_sample.py --with-spark
```

本地 Spark 使用 Java 17；脚本会查找 Conda 环境的 `lib/jvm` 并设置 Java 路径。PySpark 固定为 3.5.7，从 PyPI 安装到这个独立环境，因为当前 Conda-forge 未提供这一版本。PyArrow 用于 Python 导出 Parquet，Spark 使用自身的 Parquet 写入器；当前没有使用 pandas API on Spark 或 Arrow 数据交换。[对应版本的官方安装说明](https://spark.apache.org/docs/3.5.7/api/python/getting_started/install.html)

`environment.yml` 用于跨平台创建环境；`environment.lock.osx-arm64.yml` 保存本次 Apple Silicon 环境的实际版本，已去除个人安装路径。

真实样本及验证记录见 [验证摘要](verification/RESULTS.md)。

## 获取更长时间的数据

`run_sample.py` 每次处理 **一个 UTC 日期**。每个日期单独运行一次，即可逐日扩展时间范围。先在项目根目录进入 `a_data_pipeline/`，并按上面的步骤创建并激活环境，然后运行：

```bash
# 处理 2024-01-15 的完整 UTC 一天
python scripts/run_sample.py --date 2024-01-15 --hours 0-23 --run-dir runs/20240115_python

# 再处理紧接着的 2024-01-16
python scripts/run_sample.py --date 2024-01-16 --hours 0-23 --run-dir runs/20240116_python
```

将日期和运行目录改成需要的值，即可继续处理其他日期。命令默认下载该日期 24 个 GH Archive 小时文件，校验后保存到 `data/raw/`，再运行原始检查和 Python 清洗；已有档案会验证后复用。每个 `--run-dir` 必须是**尚不存在的新目录**，以免覆盖旧结果。处理失败时保留失败目录，改用新目录重跑；已验证的原始档案可以复用。

每个日期完成后，先看该运行目录里的 `HANDOFF.md`、`run_summary.json` 和 `python/quality_summary.json`；确认状态和小时覆盖后，再读取 `python/events_clean.parquet/`、`python/repo_daily_counts.csv` 和 `python/repo_candidates.csv`。2024-01-15 的全天仓库活动汇总表已放在 `sample_data/20240115_24h/` 供组员直接使用；其他运行目录和逐条事件数据默认保留在本机，不会随 Git 自动共享。

注意：每次运行只在该次输入内去重；多天结果合并时，还需检查**跨日期重复的 `event_id`**，不能直接假设每日结果相加就是全时间段的去重结果。所有日期按 UTC 处理，缺失小时不能当作没有活动。2024-01-15 全天原始压缩文件实测约 2.42 GiB，其他日期可能不同；扩大范围前请先确认网络与磁盘空间。

以上是 Python 数据获取和处理流程。若需要复算 Spark，可在小样本命令后加 `--with-spark`；本机全天 Spark 尝试尚未通过，后续需单独处理和验证。

## 按检查点运行

下面各命令的输出目录都须是新目录：

```bash
python scripts/download_sample.py --output runs/checkpoint_1_download
python scripts/inspect_sample.py --output runs/checkpoint_2_inspect
python scripts/clean_sample.py --output runs/checkpoint_3_python
python scripts/clean_sample_spark.py --output runs/checkpoint_4_spark --master 'local[2]'
python scripts/compare_outputs.py \
  --python-output runs/checkpoint_3_python \
  --spark-output runs/checkpoint_4_spark \
  --output runs/checkpoint_5_comparison
```

先打开检查阶段的 `raw_examples.json` 和 `inspection_summary.json`，确认实际字段和事件数量。想离线处理已有档案，可运行 `run_sample.py --skip-download --with-spark`。

扩展范围时使用同一套规则：

```bash
python scripts/run_sample.py --hours 0-2 --with-spark
python scripts/run_sample.py --hours 0-23 --with-spark
```

`--date YYYY-MM-DD`、`--hours` 和 `--data-dir` 均可覆盖默认配置。缺少任何请求小时默认会失败；明确接受不完整样本时才用 `--allow-missing`。只有在缺少 PyArrow 时，Python 基础流程才需要 `--csv-only`；正式交接建议保留 Parquet。

## 代码在哪里

```text
a_data_pipeline/
├── config/sample.json           # 日期、小时、下载预算与导出批大小
├── scripts/                     # 简短命令入口
├── gharchive_a/
│   ├── common.py                # 配置、运行状态、输入哈希、环境记录
│   ├── records.py               # 唯一的逐行解析与字段校验规则
│   ├── download.py              # 下载、重试、压缩完整性检查、缓存复用
│   ├── inspect.py               # 清洗前样例、分布、异常统计
│   ├── clean.py                 # Python + SQLite 清洗与去重
│   ├── export.py                # CSV 与分批 Parquet 导出
│   ├── spark_clean.py           # 同规则读取，Spark 去重、分组与导出
│   ├── compare.py               # 两条路径的输入及输出核对
│   └── cli.py                  # 分阶段命令与完整流程
├── tests/test_pipeline.py       # 已知结果的异常场景验证
├── sample_data/                 # 精选共享数据；当前含 24 小时仓库活动汇总表
├── data/raw/                    # 原始 .json.gz 与失败下载 .part
└── runs/<运行名>/               # 每次独立运行的全部过程和结果
```

`data/`、旧运行及大型过程数据库由 `.gitignore` 排除；`runs/20240115_1hour_handoff/` 中的一套 Python 最终分析表和关键报告通过白名单保留，组员 clone 后可直接使用 B 的仓库清单与当前小时样本。完整原始输入、SQLite 和 Spark 复算产物继续在 A 本机保存；需要时另行交接或复跑生成。共享范围与仓库入口见[小组首页](../README.md)。

## 哪些文件要保留，为什么

| 文件 | 分析或交接用途 |
|---|---|
| 原始小时档案 | 保留全部 `payload`，允许后续扩展事件特征 |
| `download/download_manifest.json` | HTTP 状态、重试记录、下载大小、SHA-256；失败也留记录 |
| `inspection/raw_examples.json` | 5 条真实原始记录与字段提取结果 |
| `inspection/file_statistics.csv`、`raw_event_types.csv` | 清洗前的每文件质量与事件类型分布 |
| `python/working.sqlite3` | 清洗前有效记录、去重分组、清洗事件、每日计数；可用 SQL 回查 |
| `python/rejected_records.jsonl` | 解析失败或关键字段无效，含原始行、来源、行号和主要原因 |
| `python/flagged_records.jsonl` | 可选字段缺失、时间不在文件标注小时内；这些记录会保留 |
| `python/duplicate_records.jsonl` | 内容一致的重复记录及来源，便于判断跨文件重复 |
| `python/conflicting_records.jsonl` | 相同 ID、内容不同的所有有效记录，等待人工复核 |
| `python/events_clean.parquet/`、`events_clean.csv.gz` | 同一批清洗事件；Parquet 用于分析，CSV.gz 便于通用读取和核对 |
| `python/events_preview.csv` | 最多 100 条清洗结果，便于组员快速看懂 |
| `python/repo_candidates.csv`、`repo_name_history.csv` | 样本中的仓库与已观察名称，保留名称变化信息 |
| `python/repo_daily_counts.*` | 仓库 × UTC 日期 × 事件类型计数；仅覆盖实际读取的档案 |
| `python/hourly_quality.csv`、`quality_summary.json` | 清洗前后计数、排除原因、覆盖范围及计数核对 |
| `spark/valid_before_dedup.parquet/` | Spark 清洗前有效记录，用于回查和分析 |
| `comparison/comparison_summary.json`、`parquet_validation.json`、差异样例、SQLite | 检查输入哈希、事件 ID、所有输出字段、Parquet/CSV 值及时间类型、日计数是否一致 |
| 各阶段 `stage_status.json` 与 `input_manifest.json` | 成功/失败状态、版本、耗时、参数、输入哈希、缺失小时 |
| 根目录 `resolved_config.json`、`pipeline.log`、`HANDOFF.md` | 本次实际配置、运行进度及简短交接说明 |

Spark 的异常/重复/冲突 JSON 输出是带多个 `part-*` 文件的目录；Python 路径的对应输出是单个 JSONL。空结果也保留输出与计数，不能把“文件为空”理解为该阶段未运行。

## 清洗规则与结果边界

- `event_id` 和 `repo_id` 必须为正整数 ID；事件 ID 输出为字符串，仓库 ID 为 64 位整数。`event_type` 必须为非空字符串，时间必须可解析且带时区。
- 统一输出 UTC 时间。可选字段无效时置空并标记；保留未知事件类型及机器人活动，后续分析可再按明确规则区分。
- 同一事件 ID 的完整 JSON 内容相同，只保留最早来源小时、最小行号的记录；完整内容的哈希包含 `payload`，不因只提取共同字段而漏掉冲突。
- 同一 ID 对应不同完整内容时，本轮暂排除该 ID 的所有记录。冲突文件及原始档案必须保留，复核后再决定处理。
- 没有清洗前错误样本就无法判断清洗偏差，所以原始分布、无效记录、可选字段警告和去重信息均保留。
- 仓库表来自样本中实际出现过的仓库，不是全部 GitHub/AI 仓库清单。`first_observed_at` 表示样本内首见时间，不是仓库创建时间。
- 所有分组计数的单位都是“事件条数”；开发活动、人气和持续维护的指标由后续分析阶段另行定义。
- 下载完整、24 个档案存在，不等于 GH Archive 捕获了全部活动；未读取小时不自动补零。一天数据可供原型开发，不能支持首年生命周期结论。

计数约定：

```text
非空输入行 = JSON 解析失败 + 解析成功
解析成功 = 字段/格式无效记录 + 去重前有效记录
去重前有效记录 = 清洗后事件 + 内容一致的重复记录 + 冲突 ID 的全部记录
日分组计数之和 = 清洗后事件
```

## Spark 路径与后续并行实验

为严格保留 UTF-8 错误、原始行号和相同清洗规则，本实现把独立小时文件分配给 Spark 分区，分区内仍逐行解压和解析，再按明确 schema 建立 DataFrame。Python 与 Spark 共用 `records.py`；去重、冲突处理和聚合分别由 SQLite 与 Spark 实现。不是两套独立业务定义，也不是直接调用原生 Spark JSON 解析器。

两条路径的 Parquet 时间字段统一为 `timestamp[us, tz=UTC]`，Spark 显式使用 `TIMESTAMP_MICROS`；比较阶段会分批读回 Parquet，核对全部事件字段与 CSV 是否一致。[Spark Parquet 时间格式说明](https://spark.apache.org/docs/3.5.7/sql-data-sources-parquet.html)

因此单个 gzip 输入的读取阶段只有一个文件任务；多个小时文件才有跨文件读取并行。这一版还保留大量审计输出，运行耗时不能直接当成 D 的正式性能实验。D 后续应固定输入、配置、计时边界及输出，再比较并行度。

SQLite 和逐行 Python 适用于这一轮小时/一天试跑；扩展到多年时，应改为分批和分区任务，再评估存储、API 候选规模及 Spark 部署，不能直接把多年的文件都交给当前本地试跑入口。

## 验证命令

```bash
python -m unittest discover -s tests -v
RUN_SPARK_TESTS=1 python -m unittest discover -s tests -v
```

第二条包含真实本地 Spark 运行，验证冲突、跨小时重复、缺失可选字段、UTF-8 错误、未知事件类型、UTC 日期和两个实现的字段/分组一致性。真实档案运行的结果与环境记录保存在各自运行目录；查看运行状态为 `completed` 后再交接。
