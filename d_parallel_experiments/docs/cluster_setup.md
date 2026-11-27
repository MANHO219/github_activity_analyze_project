# 现场部署与连续两天综合验收（按原始需求修订）

2026-11-13：任务二已完成七小时真实入口验收，跨日 6h＋1h、默认 24h 与 Python 全内容一致；执行 release 为 `/data/cs5488/releases/rolling_v1_20261113_task2_fix01/`，采样竞态修复后 Linux 21 项回归通过。全部 raw/结果保留，无扩盘、服务启停或真实清理。详见[入口验收报告](task2_entry_acceptance_20261113.md)。下面的两天及任务三、四范围仍未执行；恢复前重新预检，不能盲用旧目录或旧源包。

当前需求基准见 [原始要求解释与范围修正](requirements_alignment_20261112.md)。连续两天验证不同分批、失败续跑、限定清理及最终一致性，不默认三个示例窗口各做完整两天，也不默认同时保留全部过程数据库。

已完成事实：此前经 require_escalated 审批成功 SSH 预检，部署到全新 release，真实 L4 1h 与 Python 完整对账通过，212,804 条事件无差异；连续两天综合验收尚未执行。历史实测和旧容量模型见 [任务二报告](task2_validation_20261112.md)。本文现已在本地修订，VM 仍是原部署快照；没有因文档修订自动部署或执行新方案。

## 部署范围

建议新目录 `/data/cs5488/releases/rolling_v1_20261112/`。该名称存在时改用新后缀并记录，禁止覆盖。部署完整 `a_data_pipeline/gharchive_a/`、`config/sample.json`、`scripts/`、`rolling_pipeline/` 和 D 的新四个入口、三份 JSON 配置及本目录说明。A 原 scripts/profiled 依赖必须齐全。部署不含 raw、runs、results、大日志、归档、本机 SSH 说明、私钥或密码。

Windows 当前改动未提交；环境禁止写 `.git`，尚不能创建开发分支/提交/PR。部署时不能假设这些文件在 main 或远端。应从本次明确的工作区子集生成源文件清单和 LF/原始 SHA-256，传到新目录后逐项复核，并保存 `code_identity()` 的新版本清单。保留旧 `/data/cs5488/project/`、`reconciliation_tools_20261111/` 及历史运行目录。

## 只读预检

使用现有 SSH 用户和本机说明中的私钥路径，仅通过 `ssh/scp -i` 使用；保持 `BatchMode=yes`、`StrictHostKeyChecking=yes`。不读取密钥。需要 sudo 时提供准确命令，由用户在 VM 控制台输入密码。

逐台记录 hostname、IP、nproc、free、df、findmnt、Python/Java/PySpark/PyArrow/SQLite 版本、服务状态和已有进程/作业。确认 Worker 两台实际挂载源均为 `192.168.20.130:/data/cs5488`，不能只看同名目录存在。检查两个 Worker 能读新代码和 raw、写新 output。对 NFS 的 output/raw 锁做跨主机互斥冒烟，若不可靠，限定单协调进程且其他节点不得提交相同目录。

沿用现有 Python 环境 `/home/lishuo/cs5488-round1/env/bin/python`，先核实，不自动重装。Spark submit 预期为该环境 `lib/python3.11/site-packages/pyspark/bin/spark-submit`。本流程不依赖 DuckDB；旧周合并回归需要 `duckdb==1.4.3` 和 POSIX。L4 功能验收无需独立 Master/Worker 服务，建议在 Worker 1 上提交（历史配额 4 vCPU / 8 GB）。新配置 L1 是 local[1]，不修改 VM vCPU。

## 本次输入、输出与清理范围

| 用途 | 明确路径或区间 |
|---|---|
| 新部署 | `/data/cs5488/releases/rolling_v1_20261112/` |
| 新共享 raw | `/data/cs5488/monthly_validation/rolling_v1_20261112/raw_shared/` |
| 请求来源 | `[2024-01-15T00:00Z,2024-01-17T00:00Z)` 共 48 档 |
| 选定窗口输出命名示例 | `/data/cs5488/runs/rolling_v1_20261112_2d_l4_<window>h_<new_suffix>`；按实际验收矩阵建立，不预定三份全量 |
| Python 参照 | 同来源完整字段与最终全局裁决核对；可核实复用或按选定方案生成，不强制永久另存全部过程库 |
| 新比较与小型报告 | `/data/cs5488/monthly_validation/rolling_v1_20261112/comparison_*` |
| 作业临时空间 | `/data/cs5488/monthly_validation/rolling_v1_20261112/tmp/`，设置 TMPDIR；Spark shuffle 另核实现有本机目录 |
| 新冒烟输出 | `/data/cs5488/runs/rolling_v1_20261112_smoke_<L1,L4,D4>` |
| 冒烟来源 | `[2024-01-16T00:00Z,2024-01-16T01:00Z)` |
| 清理验收 raw | `/data/cs5488/monthly_validation/rolling_v1_20261112/raw_cleanup/`，必须新建专用 |
| 清理验收输出 | `/data/cs5488/runs/rolling_v1_20261112_cleanup_2h` |
| 清理验收来源 | `[2024-01-16T00:00Z,2024-01-16T02:00Z)`，独立输入，待现场授权后执行 |

共享输入的正常功能验证使用 `retain`。本次不触碰历史 `/data/cs5488/raw/` 和旧 results/测量/日志，不重跑旧九次性能实验。不删除共享 48 档。真实清理范围仍仅限最后一项专用 raw 中本次下载并验收的两个档案；不因需求解释而扩大对 SQLite、Parquet、partial 或历史输出的删除授权。

## 容量退出条件

现场须重新记录 `df` 和既有目录占用。利用已完成 1h 冒烟的 raw、全部有效索引、局部输出、验收 SQLite、合并 SQLite、最终事件/CSV/统计、比较库和临时文件实测，针对选定的验收矩阵及未来保留策略重新预算。区分最终必交产物、续跑/复验必需证据、当前实现的重复落盘和工作区瞬时峰值；检查单一文件系统是否承载多个路径，不能重复计算空闲量。

旧 128–136 GiB 模型及 200 GiB 可用建议只对应此前三窗口全量并保留所有重型过程库的方案，不是原需求最低容量。当前实现仍把大量 SQLite/CSV 纳入 inventory，不能未经修改和验证就假定它们可以不留；也不能承诺现有空间必够。先审查未来运行中的必要重复存储，再报告具体容量缺口。无论是否优化，已有证据均保留，不降低完整明细对账与全局裁决标准；默认预算不是硬配额。

## 授权后的执行顺序与实际 CLI

1. 完成只读预检、容量预算、新版本部署与代码哈希核对。创建上表新目录、TMPDIR；均确认未覆盖旧内容。
2. L4 运行 1h 新冒烟，核对全部保留 schema/输入/质量/配置，读出空间与吞吐。小样本 L1/D4 共用相同 raw；D4 才按授权启动 Master→两个 Worker。无需变更网卡或 VM 配额。
3. 依修订验收矩阵，用同一来源及 SHA-256 验证不同分批的最终一致性；可选择默认 24h 主运行与 6h 等价验证，12h 用短区间/合成测试补充。具体组合属于实施选择，不默认第三份完整两天运行。Python 核对须覆盖相同来源范围的完整字段、类型、统计及最终全局裁决证据。
4. 在新任务安排 SIGINT/进程终止与恢复：下载/处理失败保留、已验收跳过、清理 write-ahead journal 和 final merge 新 attempt。不要中断历史任务。
5. 在专用 raw 跑限定的 2h 清理验收，逐项复核未登记文件仍在。与正常路径、不同窗口和恢复结果一起构成连续两天适配综合验收，再汇总计时、空间及未通过项。整月月份与运行范围仍由用户另行指定。

下面只是授权后使用的命令，本文未执行：

```bash
cd /data/cs5488/releases/rolling_v1_20261112
PY=/home/lishuo/cs5488-round1/env/bin/python
SUBMIT=/home/lishuo/cs5488-round1/env/lib/python3.11/site-packages/pyspark/bin/spark-submit
export TMPDIR=/data/cs5488/monthly_validation/rolling_v1_20261112/tmp

# 这是单个 6h 窗口的参数示例，不表示必须把 6/12/24 各跑完整两天。
# 先检查目录身份和新的容量预算，执行范围以修订后的验收矩阵为准。
"$PY" d_parallel_experiments/scripts/run_batch_pipeline.py \
  --start 2024-01-15 --end 2024-01-17 --batch-hours 6 \
  --raw-dir /data/cs5488/monthly_validation/rolling_v1_20261112/raw_shared \
  --output-dir /data/cs5488/runs/rolling_v1_20261112_2d_l4_6h \
  --spark-config L4 --spark-submit "$SUBMIT" --cleanup retain --plan-only
```

预算和环境明确后，在用户已启动的现场阶段去掉 plan-only 才会提交。Python 参照、完整比较和汇总命令见 monthly_pipeline.md。

D4 小样本还需记录实际 Driver 可达地址、固定生效配置、应用 ID 与事件日志。日志目录须先在新区域创建，使用未压缩、非 rolling 日志；示例附加参数（实际节点可达地址须预检）：

```bash
--spark-config D4 --spark-master spark://192.168.20.130:7077 \
--spark-conf spark.driver.host=192.168.20.130 \
--spark-conf spark.driver.bindAddress=0.0.0.0 \
--spark-conf spark.eventLog.enabled=true \
--spark-conf spark.eventLog.compress=false \
--spark-conf spark.eventLog.rolling.enabled=false \
--spark-conf spark.eventLog.dir=file:/data/cs5488/monthly_validation/rolling_v1_20261112/event-logs
```

运行完成后根据日志中的确切 Host 名核验；不能以有两个 Executor 代替两个 Worker 成功任务证据。

```bash
"$PY" d_parallel_experiments/scripts/summarize_results.py \
  --run-dir /data/cs5488/runs/rolling_v1_20261112_smoke_D4 \
  --event-log-dir /data/cs5488/monthly_validation/rolling_v1_20261112/event-logs \
  --worker-hosts spark-worker-1 spark-worker-2
```

缺应用结束事件、日志 App ID 不符或任一主机没有成功 TaskEnd，证据检查失败。不同环境可能记录 IP 而非主机名，须按真实 Host 字段调整，不猜测通过。
