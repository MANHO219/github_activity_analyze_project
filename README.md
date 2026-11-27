# From Hype to Sustainability: Parallel Data-Intensive Processing and Early Lifecycle Patterns of AI-Related GitHub Repositories

**City University of Hong Kong · CS5488 – Big Data Algorithms and Techniques · Group 22**

This repository contains the complete source code, deterministic AI-classification rules, Apache Spark strong-scaling and rolling-batch experiments, automated verification suites, and curated final datasets/logs for our CS5488 Group Project.

## Group Members & Responsibilities

| Role | Student Name | Student ID | Core Responsibilities |
| :---: | :--- | :---: | :--- |
| **A** | Wenhao YE | `60825646` | 54-day GH Archive rolling ingestion, validation & deduplication (`a-events-v1`), Spark cleaner prototype, pipeline integration, report synthesis |
| **B** | Junnan LIU | `61026430` | GitHub Search/REST/README collection, iterative deterministic AI rule engine (`v0.1`–`v0.3.8`), pilot validation, evidence review & cohort freezing |
| **C** | Yuemen CAO | `61018011` | Fixed-cohort UTC alignment (`cohort_analysis.py`), 21-day persistence/trajectory/skewness analysis, verification & visualizations |
| **D** | Shuo LI | `61111113` | 3-VM Apache Spark Standalone deployment, controlled 6h strong-scaling benchmark, 48h unified rolling acceptance, fault/bottleneck diagnostics |

---

## Executive Summary of Verified Results

Our project decouples **controlled parallel computing evaluation** from **large-scale empirical lifecycle analysis**, linked by a verified `a-events-v1` parser and deduplication contract:

| Evidence Stream | Dataset / Scope | Key Verified Results | Primary Artifacts |
| :--- | :--- | :--- | :--- |
| **1. Controlled Spark Strong-Scaling (6h)** | `2024-01-15` UTC 00–05 (6 archives; 1,177,282 events; 3 formal runs/mode) | `L1`: **210.2 s** (`1.00×`, CV 3.22%) → `L4`: **85.6 s** (**2.46×**, CV 0.18%) → `D4` (3-VM Standalone, `2×2` cores): **91.6 s** (**2.30×**, CV 5.97%); 0 spills; 9/9 identical fingerprints; 13-field zero-diff Python reconciliation | [`d_parallel_experiments/results/`](d_parallel_experiments/results/) |
| **2. Unified Rolling Batch Acceptance (48h)** | `2024-01-15` to `01-17` UTC (48 archives; 4.59 GiB; 10,885,513 events) | `L4 24h`, `L4 6h`, and `Python 24h`: **19/19 bidirectional checks passed** (0 discrepancies); diagnosed virtual NIC (`e1000`→`vmxnet3`), NFS `fcntl.lockf`, and SQLite-over-NFS locality bottlenecks | [`d_parallel_experiments/docs/two_day_validation_20261114.md`](d_parallel_experiments/docs/two_day_validation_20261114.md) |
| **3. Production Archival Ingestion (54d)** | April 1–27 in 2024 & 2026 (1,296 verified `.json.gz`; 89.29 GB compressed) | **243,525,356** unique cleaned events (**144.07M** in 2024; **99.46M** in 2026), 71,794,991 daily repo-event rows, 792 duplicate occurrences removed, 1 conflicting ID excluded | [`deliverables/pipeline_a_54d_summary/`](deliverables/pipeline_a_54d_summary/) |
| **4. Dual-Year AI Cohorts & 21-Day Persistence** | Independent GitHub Search API (16 AI topics, Apr 1–7) → 2 fixed cohorts of **200 repos/year** | Development active share: **71.0% vs. 71.5%** in Week 1 → **25.0% vs. 14.5%** in Week 3 (10.5 pp descriptive gap); `SWE-agent` alone drove **76.3%** of 2024 Week-1 total events (91.2% stars/forks) | [`deliverables/pipeline_b_frozen_cohorts/`](deliverables/pipeline_b_frozen_cohorts/) & [`deliverables/pipeline_c_21d_analysis/`](deliverables/pipeline_c_21d_analysis/) |

---

## Repository Structure

```text
.
├── README.md                          ← Project overview & submission entry point
├── Project.pdf                        ← Official CS5488 course project specification
├── deliverables/                      ← Curated final datasets, frozen cohorts & verification logs (~3.1 MB)
│   ├── README.md                      ← Manifest of curated evidence files
│   ├── pipeline_a_54d_summary/        ← 2024 & 2026 daily metrics, ingest/merge timings, run summaries
│   ├── pipeline_b_frozen_cohorts/     ← Frozen 200+200 AI cohorts, manifests, labels & scope policy
│   └── pipeline_c_21d_analysis/       ← 21-day summary CSVs, trajectories, SWE-agent breakdown & SHA-256 manifest
├── a_data_pipeline/                   ← Pipeline A: GH Archive ingestion, a-events-v1 validation/dedup, Spark prototype
│   ├── gharchive_a/                   ← Core shared parser, deduplicator & aggregation library
│   ├── rolling_pipeline/              ← Configurable daily/batch rolling orchestration, merge & cleanup helpers
│   ├── scripts/                       ← CLI entry points (download, clean, verify)
│   ├── sample_data/                   ← Curated 24-hour reference daily summary table
│   ├── verification/                  ← 1-hour, 1-day, and 1-week verification records
│   └── tests/                         ← Pipeline A & rolling-date unit tests
├── b_repo_metadata/                   ← Pipeline B: GitHub API discovery, v0.1–v0.3.8 AI rules & cohort freezing
│   ├── bmeta/                         ← Metadata fetcher, deterministic 19-rule classifier & cohort join helpers
│   ├── rules/                         ← Versioned AI classification rule definitions (v0.1–v0.3.8)
│   ├── scripts/                       ← Discovery, API enrichment, rule evaluation & cohort freezing CLIs
│   ├── runs/                          ← Pilot runs (pilot_01: 50 repos; pilot_02: 200 repos)
│   └── tests/                         ← 160 unit tests covering rule logic, text boundaries & freezing
├── c_lifecycle_analysis/              ← Pipeline C: Fixed-cohort UTC alignment & 21-day lifecycle analysis
│   ├── cohort_analysis.py             ← Core UTC day-offset alignment & window metric computation
│   ├── run_cohort.py                  ← CLI entry point for cohort window analysis
│   ├── lifecycle_analysis.ipynb       ← Exploratory lifecycle notebook
│   ├── cohort_90d_analysis.ipynb      ← Extended 90-day cohort analysis notebook template
│   └── tests/                         ← 15 unit tests verifying alignment, edge cases & zero-activity preservation
├── d_parallel_experiments/            ← Pipeline D: 3-VM Spark cluster, 6h benchmark & 48h unified rolling validation
│   ├── configs/                       ← Spark & rolling-batch runtime configurations (L1, L4, D4)
│   ├── scripts/                       ← Unified rolling runner, Spark batch job & 19-check parity verifier
│   ├── results/                       ← 6h strong-scaling summaries & 13-field Python reconciliation outputs
│   ├── docs/                          ← Cluster setup, 48h acceptance reports, stage timings CSV & troubleshooting logs
│   └── tests/                         ← 21 rolling-batch pipeline unit tests
├── testing_data/                      ← Synthetic 2024/2026 interface-validation fixtures
└── tools/                             ← Shared workspace utilities
```

---

## Quick Verification & Reproducibility

All automated unit tests across Pipelines A, B, C, and D can be run directly from the repository root (Python 3.11+ with `pandas` / `pyarrow` / `pytest` or standard `unittest`):

```bash
# Pipeline A + rolling-date tests
python -m unittest discover -s a_data_pipeline/tests -p "test_*.py" -v
python -m unittest discover -s a_data_pipeline/rolling_pipeline/tests -p "test_*.py" -v

# Pipeline B tests (160 tests covering v0.3.8 rules & cohort tools)
python -m unittest discover -s b_repo_metadata/tests -p "test_*.py" -v

# Pipeline C tests (15 tests covering UTC alignment & 3-week fixed-cohort metrics)
python -m unittest discover -s c_lifecycle_analysis/tests -p "test_*.py" -v

# Pipeline D unified rolling-batch tests (21 tests)
python -m unittest discover -s d_parallel_experiments/tests -p "test_*.py" -v
```

### Key Pipeline Entry Points

- **Pipeline A (1-hour quick smoke test with Spark)**:
  ```bash
  cd a_data_pipeline && python scripts/run_sample.py --with-spark
  ```
- **Pipeline C (re-run 21-day analysis directly on the committed deliverables)**:
  ```bash
  python c_lifecycle_analysis/run_cohort.py \
    --cohort-year 2024 --created-from 2024-04-01 --created-to 2024-04-07 \
    --window-days 7 --data-kind "Real Data" \
    --cohort deliverables/pipeline_b_frozen_cohorts/2024/cohort.csv \
    --metadata deliverables/pipeline_b_frozen_cohorts/2024/repo_metadata.csv \
    --labels deliverables/pipeline_b_frozen_cohorts/2024/repo_ai_labels_analysis.csv \
    --daily deliverables/pipeline_c_21d_analysis/2024/activity_input/repo_daily_counts.csv \
    --coverage deliverables/pipeline_c_21d_analysis/2024/activity_input/coverage.json \
    --output /tmp/cs5488_repro_2024
  ```
- **Pipeline D (unified Spark/Python rolling batch runner & parity verifier)**:
  See [`d_parallel_experiments/README.md`](d_parallel_experiments/README.md) and [`d_parallel_experiments/docs/monthly_pipeline.md`](d_parallel_experiments/docs/monthly_pipeline.md).

---

## Appendix: Development Alignment & Handoff History（开发过程对齐记录）

> 以下保留项目开发推进过程中的阶段性同步、交接文档索引与试跑说明，便于回溯各成员模块从 1 小时样本 → 24 小时 → 1 周滚动 → 双年份三周与 48 小时统一验收的演进过程。

### 阶段文档与内部交接入口

| 想了解什么 | 入口 |
|---|---|
| 选题、分工、课程交付和研究边界 | [小组同步说明](CS5488_AI_Repository_Lifecycle_Project.md) |
| 数据从哪里来、哪个脚本处理、每个文件在哪 | [数据处理全解 HTML](a_data_pipeline/数据处理全解.html) |
| 双年份三周完整运行命令与输出口径 | [双年份三周运行指南](双年份三周运行指南.md) |
| B 正式名单任务、交付文件和数据交接规则 | [B 当前任务](B_确定双年份%20ai%20仓库.md) |
| B 历史试跑如何开始 | [B 接手指南](a_data_pipeline/B_接手指南.md) |
| B 的实现、跑法与试跑结果 | [B 阶段 README](b_repo_metadata/README.md)、[试跑结果](b_repo_metadata/RESULTS.md) |
| 自动标签 / 人工复核 / 分析用标签的区别 | [标签交接说明](b_repo_metadata/LABELS.md) |
| A 的实现和运行命令 | [数据管道 README](a_data_pipeline/README.md) |
| 已验证的一周滚动流程与 D 的适配起点 | [滚动程序 README](a_data_pipeline/rolling_pipeline/README.md)、[一周实测](a_data_pipeline/verification/20240115_1week/README.md) |
| C 的分析修订与双年份口径 | [C 分析修订与双年份准备](C_分析修订与双年份准备.md)、[指标定义](c_lifecycle_analysis/metrics_definitions.md) |
| D 的单核、多核与虚拟机分布式实验，以及统一滚动验收 | [D 的实验计划](D_并行与分布式实验计划.md)、[D 实测成果与完整日志获取](d_parallel_experiments/README.md)、[通用滚动入口说明](d_parallel_experiments/docs/monthly_pipeline.md) |
| 实际样本与核对结果 | [样本交接记录](a_data_pipeline/runs/20240115_1hour_handoff/HANDOFF.md)、[验证摘要](a_data_pipeline/verification/RESULTS.md) |

*(HTML 请在 clone 后用本地浏览器打开；仓库里的 HTML 已内嵌样本和源码，阅读主体内容不需要启动服务。)*

### 历史开发里程碑记录

1. **一小时最小样本与交接起点（`a_data_pipeline/runs/20240115_1hour_handoff/`）**
   - 首个 1 小时样本输出 69,768 个唯一仓库（[`repo_candidates.csv`](a_data_pipeline/runs/20240115_1hour_handoff/python/repo_candidates.csv)、[`repo_name_history.csv`](a_data_pipeline/runs/20240115_1hour_handoff/python/repo_name_history.csv)、[`events_preview.csv`](a_data_pipeline/runs/20240115_1hour_handoff/python/events_preview.csv)、[`events_clean.parquet`](a_data_pipeline/runs/20240115_1hour_handoff/python/events_clean.parquet/)、[`repo_daily_counts.csv`](a_data_pipeline/runs/20240115_1hour_handoff/python/repo_daily_counts.csv)）。
   - B 基于前期样本完成两轮试跑并保留在 [`b_repo_metadata/`](b_repo_metadata/)：`pilot_01`（50 个仓库，33 条人工复核）与 `pilot_02`（200 个仓库，13 条抽查 + 1 条人工修订），规则由 `v0.1` 迭代至 `v0.3.8`（变化记录见 `b_repo_metadata/runs/pilot_02/label_changes.csv`）。
2. **24 小时基准与一周滚动程序（`2024-01-15` 至 `2024-01-21`）**
   - 2024-01-15 全天参考汇总表（1,340,785 行，5,528,300 条事件）直接保留在 [`a_data_pipeline/sample_data/20240115_24h/repo_daily_counts.csv`](a_data_pipeline/sample_data/20240115_24h/repo_daily_counts.csv)；验证说明见 [全天结果与交接](a_data_pipeline/verification/20240115_1day/README.md)。
   - 一周滚动程序按 UTC 日期逐天下载、校验、清洗、验收与清理，支持失败续跑并核对跨日重复与冲突，验证 **168 个小时档案、34,437,099 条事件、3,301,406 个仓库**（详见 [`a_data_pipeline/rolling_pipeline/README.md`](a_data_pipeline/rolling_pipeline/README.md) 与 [`a_data_pipeline/verification/20240115_1week/README.md`](a_data_pipeline/verification/20240115_1week/README.md)）。
3. **双年份三周正式生产与 48 小时 Spark 统一滚动验收**
   - 最终确定比较 **2024、2026 年各自 4 月 1–7 日新建的 AI 仓库**，源档案覆盖至各年 4 月 27 日（共 54 个 UTC 日、1,296 个已校验小时档案；2024 年 144,067,003 条事件，2026 年 99,458,353 条事件），并由 B 冻结 200+200 活动盲选队列、C 完成三周对齐分析（最终产物已整理至 [`deliverables/`](deliverables/)）。
   - D 在 6 小时受控强扩展实验（`L1`/`L4`/`D4`）基础上，完成任意 UTC 半开区间与可变批次时长的统一滚动程序（`d/unified-batch-pipeline`，已合并至 `main`），并通过 48 小时连续真实数据双向对账（19/19 零差异）。
   - 90 天窗口（第 1–30、31–60、61–90 天）作为后续扩展保留接口兼容性，不更换已冻结的研究队列。

### 历史本机一周复跑示例（参考）

```bash
cd a_data_pipeline
conda env create --file environment.yml
conda activate cs5488-data
python -m pip install -r rolling_pipeline/requirements.txt

# 1 小时快速验证（含 Spark）
python scripts/run_sample.py --with-spark

# 24 小时单日复跑
python scripts/run_sample.py --date 2024-01-15 --hours 0-23 --run-dir runs/20240115_python

# 一周按日滚动复跑（替换卷名与数据路径为实际挂载目录）
python scripts/download_sample.py --date 2024-01-15 --hours 0-23 \
    --data-dir data/raw --output runs/weekly_baseline_download

python rolling_pipeline/weekly_orchestrate.py \
    --start 2024-01-15 --end 2024-01-21 \
    --volume "/Volumes/T7 4 Mac" \
    --raw-root "/Volumes/T7 4 Mac/cs5488/gharchive/raw" \
    --root runs/weekly_20240115_20240121_replay

python rolling_pipeline/weekly_report.py \
    --root runs/weekly_20240115_20240121_replay
```
