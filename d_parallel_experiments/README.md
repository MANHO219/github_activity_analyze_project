# D：单核、多核与双 Worker 实验

三小时双 Worker 参与验收和六小时三种配置各三次测量已完成。2026-11-14 连续两天 **L4 24h、L4 6h、完整 Python 参照均已完成**，各 10,885,513 条最终事件；两次完整直接比较各 **19/19 通过、差异 0**。关机后的 6h 续跑保留原 5 批验收标记，48 档输入全部 retain，限定清理复用任务四已通过的两档证据；本次未删除、提交或 PR，已停止执行，整月继续搁置。见[两天完成报告及记录导航](docs/two_day_validation_20261114.md)。以下短区间及较早暂停记录保留为历史证据。

新增通用 UTC 滚动入口、L1/L4/D4 配置、全部有效出现的全局去重、验收续跑和限定原始档案清理。**任务二入口及七小时短区间真实验收已通过**：6h＋1h、默认 24h 和 Python 参照各 1,433,999 条事件，两次完整比较无差异；修复真实 NFS 采样竞态后 Linux 21 项回归通过。详见[入口验收](docs/task2_entry_acceptance_20261113.md)。**任务三小样本验证也已通过**：L1/L4/D4 同一小时各 193,073 条事件一致，D4 两 Worker 均有真实成功任务，服务已恢复停止，见[三配置结果](docs/task3_validation_20261113.md)。**任务四两小时恢复/互斥/限定清理验收通过**：修复 NFS 服务端与客户端锁协议不一致，完成受控中断、缓存复用、验收跳过、损坏拒绝、部分删除和最终合并恢复，仅删除专用目录内本次新下载的两档，见[任务四结果](docs/task4_validation_20261113.md)。连续两天的跨窗口及 Python 完整比较也已通过，尚无月级性能结论。三窗口全量方案不是原需求硬性条件，解释见[需求对齐记录](docs/requirements_alignment_20261112.md)；原一小时测量见[历史报告](docs/task2_validation_20261112.md)。

- [通用滚动使用说明](docs/monthly_pipeline.md)：实际 CLI、输出、续跑、比较与计时。
- [本地验证记录](docs/local_validation.md)：通过、跳过和未执行项。
- [现场范围与边界](docs/cluster_setup.md)：部署、来源范围、独立输出与清理边界；验收矩阵按最新需求修正。
- [任务五计时与结果汇总](docs/task5_summary_20261113.md)：截至 2026-11-13 的 105 条记录；[本次两天汇总](docs/two_day_validation_20261114.md)另有 98 条记录，三份运行和两次完整比较已通过，月级未运行。

## 统一批处理入口与 Linux 依赖

实际入口为 `scripts/run_batch_pipeline.py`，默认 L4、24 小时一批；日期范围与窗口独立，采用 UTC `[start,end)`，当前时间边界须为 UTC 整点。`--spark-config` 接受 L1/L4/D4 或配置 JSON 路径；D4 另需实际 `--spark-master`。A 的三个 `batch_*.py` 负责公共调度支持、下载及最终合并；三种 Spark 配置调用同一个 `spark_batch_job.py` 和原清洗器。

新 Linux 环境需先具备 Python 3.11 和 Java 17，再在新的独立环境安装本轮实测版本。例如（已有同名环境应先检查，不覆盖）：

```bash
python3.11 -m venv ~/cs5488-rolling-env
source ~/cs5488-rolling-env/bin/activate
python -m pip install 'pyspark==3.5.7' 'pyarrow==26.0.1'
python -m pip check
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
```

这些是重建说明；本轮复用了 VM 已有环境，没有重新安装软件。最终合并使用 Python/SQLite，不依赖 DuckDB；旧 weekly 附加依赖保持原样。L1/L4 使用独立 `SPARK_CONF_DIR`，避免套用历史 D4 的默认配置；实际环境、命令和生效参数保存到每次运行证据中。集群输入输出路径须在 Worker 上可访问。

从仓库根目录先检查计划（示例路径需自行替换成新路径）：

```bash
python d_parallel_experiments/scripts/run_batch_pipeline.py \
  --start 2024-01-15T21:00Z --end 2024-01-16T04:00Z \
  --batch-hours 6 --raw-dir /path/to/raw --output-dir /path/to/new_run \
  --spark-config L4 --cleanup retain --plan-only
```

确认输入、输出目录身份、依赖、挂载及容量后，去掉 `--plan-only` 才执行。实际提交可通过 `--spark-submit` 指定所选环境的绝对路径；代理可由启动该进程时的 `http_proxy`、`https_proxy` 环境变量传入，下载器沿用标准 urllib 行为。完整参数、时间语义和续跑约束见[通用滚动使用说明](docs/monthly_pipeline.md)。源包只包含允许的代码、配置、测试与核心说明，完整实验产物和历史报告另行保留。

- [六小时 Python 对账](results/python_spark_6h_20261111/README.md)：完整事件字段、日汇总键与计数全部一致。
- [六小时对账复跑入口](运行与复核说明.md#六小时对账复跑入口)：统一源代码换行校验，任一比较未通过即非零退出，打包前再次检查通过状态。
- [六小时实验报告](六小时实验结果_20261111.md)：配置、原始耗时、加速比、吞吐、正确性和稳定性。
- [运行与复核说明](运行与复核说明.md)：提交命令、预热、有效 run ID 和复核方法。
- [提交说明](提交说明.md)：原仓库适配、提交范围及验证限制。
- [证据包说明](证据包说明.md)：原始日志、完整交付材料和校验值。
- [原始实验计划](../D_并行与分布式实验计划.md)。

scripts/ 与 configs/ 为本次实测使用的脚本与集群配置；results/ 为精选的计时、环境、有效配置、结果指纹和故障摘要。A 的共用适配代码位于 ../a_data_pipeline/gharchive_a/spark_clean.py。

配置中保留实测私网地址与 Ubuntu 项目路径，属于实验拓扑参数，不是通用安装默认值。在其他电脑上复现前，需要按节点调整并重新记录实际配置。SSH 密钥、Windows 本机路径和控制台登录步骤不随 Git 提交。

## Git 提交范围与完整日志获取

Git 只提交代码、配置、报告和精选小型记录，包括 JSON 核对结果、空差异示例以及简短执行日志。完整 Spark 事件日志、节点日志、压缩包、原始输入、逐事件输出和 SQLite 数据库不进入 Git。

完整日志包由 D 实验负责人通过小组交付渠道另行提供；请按以下文件名索取。具有实验机访问权限的成员也可从下列 Master 位置复制。**目前尚未上传 GitHub 附件，也没有公开下载链接；Master 是实验内网存储，仓库读权限不等于实验机访问权限。**

| 附件文件名 | 获取位置 | 大小（字节） | SHA-256 |
|---|---|---:|---|
| experiment_evidence_20261111.tar.gz | 实验 Master：`/data/cs5488/experiment_evidence_20261111.tar.gz`；或向 D 实验负责人索取 | 10,640,921 | `72a2c248fd30055e9cad12bbdc4b8b1f10bd019faa03cef8ccb1163f1529c7b2` |
| python_spark_6h_reconciliation_20261111.tar.gz | 实验 Master：`/data/cs5488/python_spark_6h_reconciliation_20261111.tar.gz`；或向 D 实验负责人索取 | 11,528 | `3214121668e34fc71d75d148bf7b5a4b8389b2de1d250cea93a5bdb311f1adbd` |
| 六小时实验交付包_20261111.zip | D 实验负责人本地项目 `d_parallel_experiments/`，单独索取 | 11,380,091 | `ee352bb7126093dbddcfd30547ffc293fbdbdc7b57482be3e740393c0f1df573` |

第一包含六小时原始控制台、Spark 事件及节点日志；第二包是后来追加的 Python 对账证据；第三包是对账之前的完整六小时交付快照，不能代替第二包。获取后使用 `sha256sum <文件名>`（Ubuntu）或 `Get-FileHash -Algorithm SHA256 <文件路径>`（PowerShell）核验。若后续上传附件，应在这里补充真实下载链接，不将文件系统路径写成公开链接。
