# 一周滚动处理代码与交接

这套程序已用 Python 清洗路径完成 2024-01-15 至 2024-01-21 的一周试跑，覆盖 168 个小时档案，产出 34,437,099 条事件和 3,301,406 个仓库。按天下载、校验、处理、验收和释放空间，最后核对跨日重复与冲突并生成汇总。小型结果与实测时间见 [一周验证记录](../verification/20240115_1week/README.md)。

本目录从 A 的本机 `local_tools/` 中整理而来。公共读取和清洗规则仍由 `../gharchive_a/` 提供，原始档案和运行产物写入独立数据目录。

## 文件和调用关系

```text
rolling_pipeline/
├── README.md
├── requirements.txt            一周合并额外需要的 DuckDB 版本
├── weekly_orchestrate.py       总入口，串联两日验收、按日续跑、清理和最终合并
├── weekly_pipeline.py          单日处理、输入快照核对、验收和去重索引导出
├── profiled_run_sample.py      调用原单日管道，补充清洗内部计时
├── weekly_merge.py             跨日去重、冲突排除、汇总和对账
├── weekly_cleanup.py           生成清理清单，通过两日验收后按清单清理
├── weekly_report.py            生成运行目录说明、计时 CSV 和交付文件哈希
└── tests/                      计时一致性、跨日重复/冲突、续跑和清理测试
```

`weekly_orchestrate.py` 调用其他脚本。`profiled_run_sample.py` 继续调用原来的 `gharchive_a.cli.main_run()`，从而复用下载、检查和 Python 清洗实现。

## 安装环境并做小样本验证

以下命令都从仓库内的 `a_data_pipeline/` 执行。脚本使用 Python 3.11、PyArrow、SQLite 和 DuckDB，运行系统为 macOS 或 Linux。D 可以在现有 Ubuntu 虚拟机内运行。

```bash
cd a_data_pipeline
# 已创建 cs5488-data 环境时，直接激活并安装额外依赖
conda env create --file environment.yml
conda activate cs5488-data
python -m pip install -r rolling_pipeline/requirements.txt
python -m unittest discover -s rolling_pipeline/tests -v
```

原始一周实测使用 Python 3.11.17、PyArrow 25.0.0、DuckDB 1.4.3。DuckDB 通过依赖清单安装对应操作系统的包。月级 Spark 版本可继续使用 D 已验证的环境，但需保留版本和结果核对记录。

## 首次获取完整的一周

当前支持任意起始日期和至少两个连续 UTC 自然日；默认仍为 2024-01-15 至 2024-01-21。两日验收使用本次起点和紧接着一天。`--plan-only` 可先打印日期与路径，不下载、不写盘。双年份三周完整示例见 [运行指南](../../双年份三周运行指南.md)。

**复现旧的 01-15 起点时，先准备该基准日的 24 个档案。其他起点无需此步，所有日期从指定 raw-root 获取。** 当前基准日固定从 `data/raw/` 读取，并保留其原始档案。新 clone 的组员先执行下面这一步，已有全部档案时会校验后复用。`--output` 应指向新的准备目录。

```bash
python scripts/download_sample.py --date 2024-01-15 --hours 0-23 \
    --data-dir data/raw --output runs/weekly_baseline_download
```

**其余日期放外接盘或共享盘。** 下面使用 A 的 T7 路径。运行前确认该卷已挂载，并将路径替换为自己的实际位置。`--volume` 必须是实际挂载点，`--raw-root` 位于该卷内，脚本会检查路径和设备是否一致。

```bash
python rolling_pipeline/weekly_orchestrate.py \
    --start 2024-01-15 --end 2024-01-21 \
    --volume "/Volumes/T7 4 Mac" \
    --raw-root "/Volumes/T7 4 Mac/cs5488/gharchive/raw" \
    --root runs/weekly_20240115_20240121_replay

python rolling_pipeline/weekly_report.py \
    --root runs/weekly_20240115_20240121_replay
```

Linux 上若共享盘实际挂载在 `/data`，可以将上述两项换成 `--volume /data --raw-root /data/cs5488/gharchive/raw`。先在挂载状态与存储预算满足要求的环境中执行。

完成后打开 `runs/weekly_20240115_20240121_replay/README.md`。本机产物使用的路径记录在 `orchestration.json` 中，最终结果目录每次采用新的编号。

## 续跑、验收和清理

处理被中断后，用同一个 `--root` 重复主入口命令。已验收的日期会先核对保留文件的大小与 SHA-256，再跳过处理。失败尝试、下载临时文件和控制台日志保留，新的尝试使用独立目录。

日验收核对 24 小时覆盖、下载与检查及清洗时的输入哈希、事件 Parquet、SQLite 计数和日汇总，并导出全部有效记录的事件 ID、完整事件指纹、来源小时和行号。当天已排除的冲突记录也保留在索引中。

主入口会先生成清理清单，并要求本次起点首两个连续日期的合并验收通过。之后只清理清单登记的原始文件、过程数据库及重复 CSV 导出。01-15 的原始基准保留，事件 Parquet、日汇总、去重索引、质量报告和异常记录保留。

当前本机最低剩余空间为 30 GiB，单日工作区预算为 12 GiB。外接卷下载前至少剩余 5 GiB，处理中低于 1 GiB 会停止。本机和外接卷都会检查。正式月级适配时由 D 将这些预算整理为可配置参数。

## 输出供谁使用

| 使用者 | 文件 | 内容 |
|---|---|---|
| B | 最终目录的 `repo_candidates.csv` | 每仓库一行，观测到的名称、首末活动时间和事件数 |
| C | `repo_daily_counts.parquet` 和 `coverage.json` | 仓库 × UTC 事件日期 × 事件类型的计数，以及来源小时覆盖 |
| D | `input_manifest.csv` | 每小时原始 URL、字节数和 SHA-256，用于固定实验输入 |
| 对账与回查 | `events_clean/`、各日 `index-*.parquet`、`summary.json` | 逐条事件、全部有效记录的去重证据、最终检查 |

`events_clean/` 按档案来源日期存放。分析时使用记录里的 UTC `event_date`。仓库创建时间及最终 AI 标签由 B 提供。已覆盖日期无活动与缺档日期分别处理。

完整事件、候选表和过程索引在处理机本地。Git 提供代码和小型验证记录，现有一周数据可按输入清单重建，或单独分享完整产物。A 的原运行目录为 `a_data_pipeline/runs/weekly_20240115_20240121/`，原最终结果为其中的 `combined_20240115_20240121_02/`。

## 计时和 D 的下一步

运行结束后，报告脚本汇总 `day_metrics.csv`、`step_timings.csv`、`archive_ingest_timings.csv` 和 `merge_timings.csv`。下载校验、原始检查、清洗导出、单日验收以及跨日各阶段分别计时。较早的 01-15—18 只有阶段总计，01-19—21 还有清洗内部细分记录。

一周基线的日清洗使用 Python/SQLite，跨日核对使用 Python，最终汇总使用两线程 DuckDB。与 Spark 比较时固定输入、输出、机器和计时范围，单列下载及检查耗时。

Python 的日期范围已经通用化。接下来由 D 适配可选批次时长、Linux/共享存储路径及 Spark 处理入口。三种 Spark 配置共用处理逻辑，保留已有六小时实验作为性能记录。批次长度改变后，需验证同一天多批合并以及跨批次/跨日期重复和冲突的处理，确保最终输出一致。

这份交接保留原一周实测，日期扩展已通过小样本复测；D 的月级与 Spark 适配通过后再更新正式入口和验收范围。
