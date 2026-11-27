# 任务二至五完成后的接手提示词

下面内容可直接作为新对话的接手指令。整理日期为 2026-11-13，北京时间；记录的是本轮结束时的事实，不保证 VM、服务或磁盘的实时状态。

请接手 `E:\Vibecoding_codex\cs5488proj`。本次仅做本地只读接手：理解已完成的任务二至五、核对记录和未提交代码，汇报后等待我的新指令。不要自动继续验收、运行脚本或沿用旧现场授权。

1. 工作区与项目背景

项目使用 GH Archive 事件整理 GitHub 仓库日活动和候选仓库，供后续生命周期研究。D 负责 Spark 单核、多核、双 Worker 实验，以及在 A 的滚动程序基础上整理统一批处理入口。

已知 Git 基线为 main / `62dd2e53f52fc65f309535b1c2d57fa276684215`，未 fetch；请以本次只读检查为准。任务一六小时实验材料已经由 PR #10 合并。任务二至五的实现、配置、测试和文档仍在本地未提交工作区；只拉远端 main 会缺少这些实现。

先只读检查 Git 分支、HEAD、修改、未跟踪和被忽略文件，以及适用的 AGENTS.md（包括父目录）。最后核实有 5 个跟踪文件修改，另有未跟踪文件/目录；数量仅作对照。保护全部已有改动、部署包、忽略目录、完整日志和失败证据。不要 reset、checkout 覆盖、git clean、删除忽略文件、提交、推送、创建或合并 PR；不要修改 .git 来绕过限制。

2. 原始需求与实际完成范围

原需求是：范围与窗口独立的统一入口；UTC 起点包含、终点不包含；默认 24h，支持例如 6/12/24h；raw/output 路径参数化；L1/L4/D4 共用 Spark 清洗逻辑；每批下载校验、检查、处理、验收、保存清单/质量/全部有效出现索引，支持失败保留、输入复用、复验后跳过和限定清理；最终跨批去重/冲突裁决、重算日统计，交付事件 Parquet、日活动表、候选表、覆盖和质量摘要；各阶段独立墙钟计时。

用户随后要求只做满足需求的必要验证和记录，不重做三配置×三窗口×三次性能实验，也不把三种窗口各保存一份完整两天输出当作硬性要求。连续两天仍是综合验收里程碑，并未取消；它尚未执行，不能把短区间拼称两天通过。

本轮结果：

- 任务二：统一入口与七小时真实正常路径通过。来源 `[2024-01-15T21:00Z,2024-01-16T04:00Z)`，七档共 584,484,555 字节；L4 6h＋1h、L4 默认 24h、Python 默认 24h 各 1,433,999 条事件。两次直接完整比较各 19 项通过、双向差异为 0：L4 6h 对默认 24h、Python 对 L4 6h。没有冒称第三次直接比较。所有输入 retain。跨日、尾批有真实覆盖，12h/跨月/年等还有已知答案测试补充。
- 任务三：同一新样本 `[2024-01-16T03:00Z,04:00Z)`，73,463,349 字节，L1/L4/D4 均 193,073 条事件。复用任务二已验收的 L4 尾批，仅新增 L1/D4 各一次。L1 是 local[1]，没有改 VM vCPU。D4 应用 `app-20261113045658-0000`，真实日志中 Worker 1/2 成功 TaskEnd 为 531/9，应用正常结束；不是靠两个 Executor 或合成日志证明参与。本轮所启 Master/Workers 已恢复原停止状态，这是历史收尾快照。
- 任务四：来源 `[2024-01-16T00:00Z,02:00Z)`，两档共 156,880,050 字节，单个 2h 批次，最终 433,588 条事件。真实验证 NFS raw/output 互斥、Spark 受控中断、失败保留、缓存复用、验收复验后跳过、损坏副本拒绝、最终合并中断恢复、清理意图和部分删除恢复。SQLite 第一次合并已提交 10,000 行后中断，失败 attempt 保留，再建新 attempt 完成；不是原地续写 SQLite。真实清理仅删本轮新建专用 raw_cleanup 内本次下载的 00/01 两档，清单外哨兵、共享七档和全部索引/Parquet/SQLite/失败/部分产物保留。
- 任务五：汇总已有实测，105 条计时明细＝91 条流水线阶段＋12 条外层进程＋2 条事后完整比较。只读采集已有 VM 元数据，没有新增 Spark、下载、清理或服务操作。修复清理计时漏收，专项测试及四条真实原始清理记录核对通过。

这些是各自短区间的完成结论，不等于原始连续两天综合验收全部完成。整月范围未指定、未运行，也没有月级性能或长期稳定性结论。

3. 阅读顺序：以最新汇总为入口

先读：

- `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\docs\task5_summary_20261113.md`
- 同目录 `task5_summary_20261113.json` 和 `task5_stage_timings_20261113.csv`（下节说明结构）。
- `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\docs\task2_entry_acceptance_20261113.md` 及配套 JSON。
- `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\docs\task3_validation_20261113.md` 及配套 JSON。
- `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\docs\task4_validation_20261113.md` 及配套 JSON。

再读需求、实际 CLI 和代码导航：

- `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\docs\requirements_alignment_20261112.md`
- `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\docs\monthly_pipeline.md`
- `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\README.md`
- `E:\Vibecoding_codex\cs5488proj\README.md`
- `E:\Vibecoding_codex\cs5488proj\a_data_pipeline\rolling_pipeline\README.md`

按需补充：

- `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\六小时实验结果_20261111.md`，以及 `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\results\completed_20261111\measurements\six_hour_comparison.json`：历史性能依据，九次正式测量，不重跑。
- `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\docs\project_handoff_prompt_20261112.md`、`round1_handoff_20261112.md`：早期实现背景及原十四份文档导航。
- `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\docs\local_validation.md`：早期本地测试及预先确定的冲突/重复答案。
- `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\docs\cluster_setup.md`：部署与验收方案，不是实时现场状态。
- `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\虚拟机与SSH接手说明.md`：仅在以后另获现场授权时用于连接方式。

旧文档保留了当时的“只读等待”“尚未执行”“工作区干净”“入口待实现”及重型容量方案等历史表述，不得盖过最新结果。旧 128–136 GiB 外推及 200 GiB/250 GB 建议对应已撤销为硬要求的重型方案；不能据此自动要求扩盘。旧全天计划、六小时命令不属于本次接手执行指令。

4. 记录在哪里、如何读取

总 JSON 为：
`E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\docs\task5_summary_20261113.json`

关键字段：

- `cases`：七个运行条目 `task2_l4_6h`、`task2_l4_default24`、`task2_python_default24`、`task2_failed`、`task3_L1`、`task3_D4`、`task4`。每个有 root、run_id、运行状态、identity、host/environment、输入清单与 SHA-256、阶段汇总、父计时、磁盘采样；命令在 external_execution 或 external_executions 中。task3 的 L4 是复用引用，不是第八次新运行。
- `sources`：既有证据文件的绝对路径、大小、SHA-256；可向任务二/三/四原 JSON 和原始采集回溯。
- `performance_baseline`：六小时历史三配置各三次成绩及计时边界。
- `comparison_results`：完整比较和真实双 Worker 参与证据。
- `disk`、`failures_and_recovery`：采样、保留占用、真实失败、预期中断及限定删除记录。
- `report_tool_change`：汇总器修复与本地新身份，不代表新版本已跑 Spark。
- `local_delivery_package`：本地源包、清单、哈希，`deployed=false`。
- `remaining`、`timing_boundaries`：未执行项和统计边界，必须完整读取。

CSV 为：
`E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\docs\task5_stage_timings_20261113.csv`

重点列是 case、run_id、run_state、kind、path、stage、batch、started_at、finished_at、elapsed_seconds、state、exit_code、is_parent、input_bytes、final_events、code_sha256、rule_version、source_sha256。kind 分为 pipeline_record、external_process_span、post_run_comparison。用 case 与总 JSON 对应；CSV 的输入大小/最终事件数描述运行范围，不是每个分片或失败尝试的实际产出。

更深一层原始只读采集：
`E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\local_only\task5_20261113_exec01\collected_timings.json`

其中 runs[case] 保存原 run.json、输入注册表、原阶段记录、disk_monitors、metadata_sha256。其他本地完整小型日志/脚本分别保留在同一 local_only 下的 task2_20261113_exec01、task3_20261113_exec01、task4_20261113_exec01、task5_20261113_exec01；以实际目录和 JSON 的路径为准。local_only 被忽略是正常的，不能因此删除或认为不存在。

推荐用 Python 标准库读取，避免 PowerShell ConvertTo-Json 默认深度截断、长输出被工具截断或误改写原文。以下示例只读本地文件，不导入项目模块、不连接 VM：

```python
import csv
import json
from collections import Counter
from pathlib import Path

root = Path(r"E:\Vibecoding_codex\cs5488proj")
docs = root / "d_parallel_experiments" / "docs"
report = json.loads((docs / "task5_summary_20261113.json").read_text(encoding="utf-8-sig"))
print("state:", report["state"])
for name, case in report["cases"].items():
    print(name, case["run_state"], case["input_bytes"], case["final_events"], case["root"])
print("remaining:", report["remaining"])
with (docs / "task5_stage_timings_20261113.csv").open(encoding="utf-8-sig", newline="") as stream:
    rows = list(csv.DictReader(stream))
print("rows/kinds:", len(rows), dict(Counter(row["kind"] for row in rows)))
print("cleanup:", [(row["path"], row["state"], row["elapsed_seconds"])
                    for row in rows if row["stage"] == "raw_cleanup"])
```

5. 统计与解释边界

不要把 batch/merge/invocation/外层父计时与子阶段相加。elapsed_seconds 是单调时钟墙钟测量，起止字符串有时只精确到秒，不要反算替换已有耗时。CSV 布尔是字符串，不能用 bool("False") 判断父计时。

completed_leaf_stage_seconds 只是已完成子步骤的工作量，可以包含后来整次调用失败之前已经完成的阶段；不能据此把失败运行标为验收成功。task2_failed 没有最终验收事件数。

缓存必须分开：任务二首个成功运行是六档缓存＋一档新下载，后两个全缓存；更早失败尝试五档新下载＋一档缓存，不能把失败下载挪成成功冷启动测量。任务四首次两档新下载，重跑两档缓存，最终注册表反映的是最近缓存状态，首轮状态见 attempt 下载清单。

任务四 178.863s 是首次外层启动至恢复成功，含故障等待、失败与重试；18.161s 只是最后恢复调用。全跳过外层 0.669s、损坏拒绝 0.468s 均另列。跳过计算没有一条虚构 0 秒的首次计算记录。三个受控中断及损坏副本退出 1 是预期负向结果，任务二采样竞态才是实际缺陷导致的失败。

task3 外层 finished_at、两次事后比较独立墙钟边界未完整记录，应留空或说明未计时，不猜测补齐。磁盘为 1s 采样，组件峰值可能异时，NFS 与 Worker 本地 scratch 不同盘，不能把各峰值相加；失败采样线程停止后的峰值不完整。15.07 GiB 可用仅为任务五采集时快照，不保证现状。

性能结论继续沿用历史六小时相同输入输出、每组三次的中位数：L1 210.215s / 5,600 事件每秒；L4 85.588s / 13,755 事件每秒 / 2.46×；D4 91.566s / 12,857 事件每秒 / 2.30×。L4 最快，所以入口默认 L4。历史计时为 Spark 启动到写出，不含下载/事后验收；不能与新入口端到端直接比较。本轮短样本不是新性能基准。

6. 实现、修复和版本身份

代码阅读入口：

- `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\scripts\run_batch_pipeline.py`
- `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\scripts\spark_batch_job.py`
- `E:\Vibecoding_codex\cs5488proj\a_data_pipeline\rolling_pipeline\batch_support.py`
- `E:\Vibecoding_codex\cs5488proj\a_data_pipeline\rolling_pipeline\batch_download.py`
- `E:\Vibecoding_codex\cs5488proj\a_data_pipeline\rolling_pipeline\batch_merge.py`
- `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\scripts\verify_results.py`
- `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\scripts\summarize_results.py`
- `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\tests\test_batch_pipeline.py`

三种配置分别在 `E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\configs\` 下的 local_1core.json、local_4core.json、distributed_4core.json；三者调用同一套 Spark 逻辑。

本轮三处必要修复：

- 任务二：容量采样 Path.rglob 遇 Spark 正常移除临时目录而失败，改为 os.scandir，仅容忍 FileNotFoundError；权限/I/O 错误仍失败。新代码 Linux 21 项回归通过，随后真实正常路径通过。
- 任务四：服务端本地 flock 与 NFS 客户端锁域不一致，实测 Worker 可绕过 Master 锁；改为 POSIX fcntl.lockf，并在打开第二个描述符前拒绝同进程重入。Linux 两项锁相关测试及两 Worker 真实 NFS 互斥通过；Windows 仍用 msvcrt。
- 任务五：原汇总只读 timing*.json，漏掉 invocations/attempt-*/*_cleanup.json；新增 collect_timings 补收。一个清理失败/重试专项测试通过，真实四条清理计时与旧 audit 完全一致；没有重复大测试或 Spark。

运行身份前缀：任务二/三真实执行 `379d9115…`，任务四 `68d9b405…`，最终本地汇总修复后 `b729053f…`。完整身份见 JSON。最后这个变化只涉及参与身份计算的汇总脚本，没有修改清洗/全局裁决规则；但身份确实不同，不能声称旧运行执行了新版本。

最终本地源包在：
`E:\Vibecoding_codex\cs5488proj\d_parallel_experiments\local_only\task5_20261113_exec01\rolling_v1_20261113_task5_delivery01.tar.gz`

52 个源文件和逐文件清单已核验，包 SHA-256 为 `8db86502b73f62d821939be2bd9a06667c8299d7b30d66a07e73143b794c55e1`。这是源文件包，未部署，也不包含全部原始档案和历史证据；不是完整工作区替代品。不要用旧源包哈希宣称新增文件一致，不覆盖旧 release，不以新身份续跑旧输出。

7. 数据规则不能改变

新入口按 UTC 整点半开来源区间 [start,end)，旧 weekly 的 end 包含日期，不混用。按来源档案小时选输入，日统计按事件自身 UTC 日期，不新增事件时间过滤。

全局裁决必须读取全部有效出现，包括局部被重复/冲突排除的记录。同 ID 同内容保留最早来源；同 ID 不同内容全部排除，再重算日统计/候选表。日活动表仍为 repo_id、event_date、event_type、event_count。

最终合并为 Python/SQLite；Python 与 Spark 共享最终合并器，不叫全流程 Spark，也不叫两套完全独立的参照。真实短样本重复/冲突均为 0；相关边界以预先确定答案的合成测试补充，不能冒称真实数据包含跨批冲突。历史 Spark 桥接替代输出、双 Worker 合成日志只是单元测试，真正现场证据在本轮应用日志与报告中。

8. 现场路径与访问边界

以下仅作历史位置导航，本次不连接：Master lishuo@192.168.20.130，Worker 1 .129，Worker 2 .131；两 Worker 的 NFS 源为 192.168.20.130:/data/cs5488。

- 任务二/三实际 release：`/data/cs5488/releases/rolling_v1_20261113_task2_fix01/`。
- 任务四实际 release：`/data/cs5488/releases/rolling_v1_20261113_task4_lockfix01/`。
- 共享七档输入：`/data/cs5488/monthly_validation/rolling_v1_20261112/raw_shared/`，保留，不能删除。
- 唯一实际清理目录：`/data/cs5488/monthly_validation/rolling_v1_20261112/raw_cleanup/`，本轮新建，仅删 2024-01-16-0.json.gz、2024-01-16-1.json.gz；所有其他数据保留。
- 任务二证据：`/data/cs5488/monthly_validation/rolling_v1_20261113_task2_fix01/`。
- 任务三证据：`/data/cs5488/monthly_validation/rolling_v1_20261113_task3/`。
- 任务四证据/损坏副本：`/data/cs5488/monthly_validation/rolling_v1_20261113_task4/`。
- 各 output/run 根和最终输出直接查总 JSON 的 cases[case].root 及任务二/三/四原 JSON；不要靠名字盲目续跑。

如果以后我另行授权现场工作，连接方式先读本地 SSH 接手说明；私钥只经 ssh/scp -i 使用，不读、不输出、不打包；保留严格主机指纹校验。工具需 require_escalated 时遵循当时审批，不绕过沙箱。网络受限/WinError10013 不等于认证失败或密钥损坏。Windows Clash Verge Rev mixed 端口曾为 7897，Worker 1 曾通过已有 127.0.0.1:17897 转发下载成功；这些也不是现状保证，不自动修改或恢复代理。sudo 密码由用户在 VM 控制台输入，不在聊天索取。

9. 不要为了读记录误执行脚本

本次只读已有文件即可。summarize_results.py 的 summarize() 会写 stage_timings.csv/run_summary.json；worker_evidence() 会写 worker_evidence.json；verify_results.py 会建立比较目录和数据库；prepare_batch_deployment.py 会创建源包。collect_timings() 本身只读，但本次也无需重新 SSH 采集。

local_only 中 build_summary.py 会新建报告/CSV，finalize.py 会重写任务五 JSON，collect.py 用于历史采集；只阅读，不运行。尤其任务四 recovery.py 会真实下载、启动 Spark、向本次子进程发信号并执行真实删除，绝不能当作普通日志读取器或无害自检重跑。不要重新运行测试、打包或采集来重复证明已有结果。

10. 读完后的回复要求

只汇报项目目的、任务二至五各自完成范围、主要修复、未提交状态、记录入口、未执行的连续两天/整月/PR事项，以及任何实际发现的文件缺失或身份不一致。区分“已验证”“历史记录”“未执行”，不要虚构通过。不要自动继续下一步，不连接 VM、不部署、不启动旧任务、不清理、不提交；等待我的新指令。
