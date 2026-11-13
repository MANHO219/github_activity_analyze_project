# 通用滚动入口与 Spark 适配

当前需求解释见 [原始要求解释与范围修正](requirements_alignment_20261112.md)。2026-11-13 已完成七小时真实 6h＋1h、默认 24h 和 Python 全字段比较，1,433,999 条事件一致，见[入口验收报告](task2_entry_acceptance_20261113.md)；连续两天综合验收未完成。可配置多种窗口不意味着每个窗口都必须做完整两天实验。双 Worker 证据参数要求两个不同且非空的主机名，仍须以实际日志及预检确认两个真实 Worker。

本地实现版本：rolling-v1，含 2026-11-13 空间采样目录竞态修复。真实 L4 一小时冒烟和七小时入口验收已通过，两天综合验收及月级吞吐尚未实测。旧六小时实验及一周入口保持原状；旧入口 `--end` 仍包含该日期，新入口为排除终点。

## 入口与时间语义

从仓库根目录执行。依赖 Python 3.11+、PyArrow；Spark 路径另需既有 Java 17 / PySpark 3.5.7 环境和 `spark-submit`。新最终合并使用 Python/SQLite，不要求 DuckDB，不能称为全流程 Spark。

```powershell
python d_parallel_experiments/scripts/run_batch_pipeline.py --start 2024-01-31T20:00:00Z --end 2024-02-01T05:00:00Z --batch-hours 6 --raw-dir E:/data/new_raw --output-dir E:/data/new_run --spark-config L4 --cleanup retain --plan-only
```

该命令实际支持，生成 6+3 小时两批。`--plan-only` 仅输出 JSON，不创建目录、连接网络、启动 Spark 或删除文件。日期表示 00:00 UTC；时间必须带时区，转换为 UTC 后须为整点。选择的是 GH Archive 来源档案小时，绝不按事件时间过滤；日统计仍使用 UTC `event_date`。

| 参数 | 默认/要求 |
|---|---|
| `--start / --end` | 必填，UTC `[start,end)`，start < end |
| `--batch-hours` | 正整数，默认 24，6/12/24 均有合成验证 |
| `--raw-dir / --output-dir` | 必填，不能互相包含；运行结果须为新目录或身份相容的续跑目录 |
| `--spark-config` | L1/L4/D4 别名或配置 JSON 路径，默认 L4 |
| `--spark-master` | 覆盖 master；D4 模板必须显式提供实际端点 |
| `--spark-submit` | 默认 spark-submit，可用既有环境中可执行文件的绝对路径 |
| `--spark-conf` | 可重复 `spark.key=value`；记录请求及生效值，UTC 和微秒时间戳不可改变 |
| `--engine` | 默认 spark；python 用原 Python 清洗器生成新参照，不代表 Spark 已实测 |
| `--cleanup` | 默认 retain；accepted-raw 限制为本次拥有的专用 raw 目录 |
| `--min-free-gib` | 默认 2，raw 与 output 分别检查；可为 0 |
| `--batch-budget-gib / --merge-budget-gib` | 默认 16 / 24，单次 attempt 工作区预算；不是整月容量承诺 |
| `--sqlite-cache-mib` | 默认 128，最终合并 SQLite 页缓存，不等于总进程内存上限 |
| `--base-url` | 默认 https://data.gharchive.org，备用源作为运行身份的一部分 |

## 实现与数据契约

`run_batch_pipeline.py` 调用 `a_data_pipeline/rolling_pipeline/batch_*.py`。三种配置共用 `spark_batch_job.py` 和未改动的 `gharchive_a.spark_clean.clean_spark()`，配置分别为 local[1]、local[4]、双 Worker 总计 4 核/每 Executor 2 核。Shuffle=12、AQE=false、UTC、TIMESTAMP_MICROS。是否真正启动双 Worker 及两者是否参与，以事件日志验证，不能由配置名推断。

批次 ID 包含完整起止时间。跨午夜批次按来源日期拆成内部 fragment，每个 fragment 调用一次现有清洗器，因此跨午夜的一批可能包含多个 Spark Application。这避免改写原日期选择器，也保持旧六小时源代码哈希基线。窗口从用户起点持续推进，不在午夜重新划分。

每个 Spark fragment 原样保存 `valid_before_dedup.parquet`，含 13 个事件字段及完整原始事件的 `canonical_sha256`。Python fragment 从原 SQLite `valid_events` 导出同一内容索引，包括本地重复及冲突出现。合并显式规范化十六进制/二进制 SHA-256、UTC 字符串/时间戳、布尔、数组和空值。

最终 SQLite 读取所有有效出现，先按 ID 判定指纹种类：一种指纹则保留最早 `(source_hour,source_line)`；多种指纹则排除所有出现。索引来源位置唯一性约束防止一个出现被两个批次重复登记。`conflicts.csv` 与 `duplicates.csv` 逐出现记录来源、batch、fragment 和原因；不同分批比较时忽略 batch/fragment 标签，保留全部语义字段和重复次数。

最终事件从全部有效出现重建，局部已验收产物不修改。之后重算日统计、名称历史与候选表，不能累加局部结果。事件保持现有 13 字段及 Arrow 类型，日统计固定 `repo_id,event_date,event_type,event_count`。覆盖清单与事件日期分布分开，缺档失败，已覆盖无有效事件输出有类型的空表。

## 状态、续跑与清理

典型路径：

```text
<output>/run.json
         inputs.json
         invocations/attempt-0001/timing.json
         batches/<start>_<end>/state.json
                                accepted.json
                                cleanup.json
                                attempt-0001/fragments/<date>/...
         merge/attempt-0001/result/...
         final_accepted.json
```

批次状态 planned → input_verified → processed → accepted → raw_cleaned；错误保留阶段、异常和所有尝试。最终合并有独立 attempt、原始计时及验收标记。失败保留，下一次另建 attempt，不覆盖失败输出。

续跑用完全相同的 CLI。运行身份包含规范化区间、窗口、raw 路径、策略、后端、配置、预算、解析规则与 LF 归一化代码哈希。更换不相容参数/代码要求新 output。已验收批次先重算保留目录全部文件的大小与 SHA-256，再跳过；输出缺失或改变直接失败。raw 已清理也不强制重下。未验收输入对照历史验证哈希复用；截断或改变的缓存保留并报错。每次下载的 partial 名包含 run/attempt/fragment，失败 partial 保留，不影响新尝试。

同一个 output 和同一个 raw 根分别用 Windows `msvcrt` / POSIX `fcntl.lockf` 互斥，进程退出自动释放，不靠锁文件是否存在判断。POSIX 端统一使用记录锁，使 NFS 服务端本地路径与客户端挂载路径采用同一锁协议；同进程重复获取在打开第二个文件描述符前拒绝，避免关闭描述符释放已有锁。共享 raw 的多个新入口串行运行；外部不遵守锁的读取程序只能搭配 retain。本轮已验证 Master 持锁时两 Worker 均被阻止、释放后可获取，证据见[任务四验收](task4_validation_20261113.md)；更换挂载或环境后仍须先验证，验证前禁止跨节点同时提交相同目录。

`accepted-raw` 要求新建空的专用 raw，绑定 run ID。它仅删除本次下载且验收清单登记的 `.json.gz`：逐文件验证归属、文件名、解析路径、符号链接、大小和哈希；先持久化 deleting 意图，再 unlink，再记录 deleted。中断后可恢复，删除后重现的文件保留并报错。已有共享缓存、清单外文件和其他 run 的输入不删除。Parquet、索引、质量报告、输入清单、SQLite、partial 及所有旧证据保留。

JSON 使用同目录临时文件加原子替换。清理日志记录逐文件状态，接受标记只在全部校验完成后写入。预算每秒采样，同时在下载块、Spark 子进程轮询、索引批读和阶段边界检查；最终 SQLite 查询使用进度回调。原有同步 Python 检查/导出只在安全检查点停止，短暂峰值可能高于预算，必须预留额外空间。SQLite 临时排序可能使用系统临时目录；现场须将 TMPDIR 指向本次专用临时目录并单独核验磁盘。预算不是 OS 硬配额。

## 复核与报告

```bash
# 若选定方案需要新生成完整两天 Python 参照，可使用此命令。
# 它是接口示例，不是原需求强制另存完整参照及全部过程库的条件。
# 必须保持 Python 与 Spark 的输入来源及哈希一致。
python d_parallel_experiments/scripts/run_batch_pipeline.py \
  --start 2024-01-15 --end 2024-01-17 --batch-hours 24 \
  --raw-dir /data/cs5488/monthly_validation/rolling_v1_20261112/raw_shared \
  --output-dir /data/cs5488/runs/rolling_v1_20261112_2d_python \
  --engine python --cleanup retain

python d_parallel_experiments/scripts/verify_results.py \
  --left /data/cs5488/runs/rolling_v1_20261112_2d_python \
  --right /data/cs5488/runs/rolling_v1_20261112_2d_l4_6h \
  --output /data/cs5488/monthly_validation/rolling_v1_20261112/comparison_python_6h

python d_parallel_experiments/scripts/summarize_results.py \
  --run-dir /data/cs5488/runs/rolling_v1_20261112_2d_l4_6h
```

比较器接收两个完整新入口的 run 根，不切片、无硬编码行数。复核保留文件后，核对来源清单/哈希、覆盖、规则、13 字段及类型、重复次数、日统计 CSV/Parquet、候选表及内部重算、冲突/重复证据。双向差异及小型示例保存，任一失败退出码非零。比较允许不同 Parquet 文件布局。

Python 参照使用原解析与 Python/SQLite 清洗，Spark 使用原 DataFrame 去重；两者最后使用同一新增全局合并器。因此最终全局裁决不是两套独立实现，其正确性还依赖预先给定答案的跨批冲突测试，不能只凭两者一致宣布算法独立验证。

`stage_timings.csv`、`run_summary.json` 保存成功、失败与续跑尝试、输入大小、代码/规则、主机资源及配置。下载、检查、清洗、验收、全局去重、最终汇总分别记录单调时钟墙钟时间和 UTC 起止；清理记录位于 `invocations/attempt-*/*_cleanup.json`，汇总器同时收集它们，包含中断、恢复及已完成清理的复验。batch/merge/invocation 是父计时，不能与子阶段重复相加。跳过计算没有虚构的 0 秒测量。任务二至四已有实测的阶段、吞吐、占用与边界汇总见[任务五报告](task5_summary_20261113.md)；六小时历史实验仍为性能结论依据。

现场部署、命令和授权范围见 [cluster_setup.md](cluster_setup.md)，本地验证与未执行项见 [local_validation.md](local_validation.md)。旧六小时专用比较和打包入口继续使用原哈希清单，不冒充本版本验证。
