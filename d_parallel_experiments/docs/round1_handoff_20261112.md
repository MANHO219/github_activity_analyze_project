# 第一轮本地实现交接：月级滚动与 Spark 适配

> 2026-11-13 后续结果：任务二入口与短区间真实验收已通过，七小时 6h＋1h、默认 24h 与 Python 结果一致，1,433,999 条事件；监控遍历竞态已修复，新身份 379d9115…，Linux 21 项回归通过。详见[新验收报告](task2_entry_acceptance_20261113.md)。本文件以下为历史阶段，连续两天综合及任务三、四现场验收仍未完成。

> 最新需求解释：支持多种可配置窗口，不等于必须三种窗口各跑完整两天；连续两天是任务 2–5 的综合功能验收。原三窗口全量及重型存储方案已修订，当前参见[需求对齐记录](requirements_alignment_20261112.md)。历史源包、测量和证据保留，后续重新设计验收及容量预算，不自动扩盘或删证据。

> 后续任务二更新：已按新用户指令完成获批 SSH、新部署和真实 1h L4/Python 完整对账；212,804 条事件无差异。两天三窗口尚未执行，容量模型约需 128–136 GiB，当前共享盘仅有 31.88 GiB 可用。详见 [任务二验收与容量报告](task2_validation_20261112.md)。旧“没有部署/真实 Spark”的表述均为此前历史阶段；没有启动任务三、四或执行扩容。

> 后续执行更新（2026-11-12）：新的用户指令已授权任务 2–5，替代本文件旧的“只读交接”及逐任务等待要求。本次现场连接在 TCP 建立前受 WinError 10013 阻塞，未部署、下载、启动服务或真实验收；已完成不依赖 VM 的复核及双 Worker 主机参数校验修复。旧包已复核，修复后另建新包，不沿用旧哈希。当前状态与新包身份以 [执行报告](execution_20261112.md) 和 [机器可读证据](execution_20261112.json) 为准；本文件以下内容为第一轮历史记录。

交接日期：2026-11-12。项目：`E:\Vibecoding_codex\cs5488proj`。

## 可直接复制给新对话的指令

> 请接手 `E:\Vibecoding_codex\cs5488proj`，先检查 Git 状态和适用的 AGENTS.md，再阅读 `d_parallel_experiments/docs/round1_handoff_20261112.md`、`docs/local_validation.md`、`docs/monthly_pipeline.md`、`docs/cluster_setup.md`（后三份均在 `d_parallel_experiments/` 下）及原方案 `d_parallel_experiments/monthly_spark_execution_plan.md`。任务 1 的六小时成果已经通过 PR #10 合并；任务 2–5 的本地实现已完成但未提交，真实运行尚未开始。不要把原方案中的“待实现”说明当作当前代码状态，也不要把本地合成测试当成真实 Spark 验收。
>
> 最新指令（2026-11-12）：只做交接，终止所有执行任务。此前现场授权已撤回。新对话仅阅读本地材料、只读检查 Git 并汇报现状，随后等待用户新指令；不连接 VM，不预检、部署、下载、测试、运行、清理或修改配置，不自动继续任务 2–5。完整只读接手提示词见同目录 project_handoff_prompt_20261112.md。下文的实施步骤仅保留为待办背景。

## 1. 当前结论与授权边界

第一轮完成了本地代码、文档、合成测试和部署源包。没有完成真实 JVM/Spark、两天真实数据、D4 双 Worker 或 NFS 验收，也没有产生新的真实性能记录。

用户曾授权逐任务推进现场阶段，但最新指令已撤回该授权并终止所有执行任务。当前只做只读交接；是否恢复及恢复范围由用户另行明确指定。

| 原任务 | 已完成的本地工作 | 现场待完成 |
|---|---|---|
| 1：六小时成果交付 | PR #10 已合并，历史成果保持原样 | 不重跑旧实验 |
| 2：统一批处理入口 | 时间范围、分批、调度、下载、共享清洗调用、正常验收与最终合并 | 真实 L4 环境验证入口正常运行及两天范围分批执行 |
| 3：三种配置共用 Spark 逻辑 | L1/L4/D4 配置和同一 Spark 桥接入口 | 同输入真实三模式一致性，D4 两 Worker 成功任务证据 |
| 4：滚动验收、续跑、清理与跨批去重 | 合成故障、恢复、安全清理、全局冲突裁决及互斥验证 | 真实数据与 NFS 锁、受控中断恢复、专用 raw 清理验收 |
| 5：阶段计时与结果汇总 | 计时记录、完整比较器、汇总器、事件日志证据检查 | 真实运行记录审查、阶段耗时、空间和结果报告 |

任务 2 正常执行自然会调用已实现的合并、验收和计时组件；这不代表任务 3–5 已经独立验收。任务 2 完成后必须停下，不自动开展三模式实验、故障注入或删除验收。

## 2. Git 状态与已有成果

- 基线 HEAD：`62dd2e53f52fc65f309535b1c2d57fa276684215`，对应 PR #10。第一轮起点是干净的 main；本次交接复核 HEAD 未变，未 fetch，远端现状未知。
- 本地实现仍在工作区，未创建开发分支、提交或新 PR。下一对话若只拉远端 main，会缺少这些实现。
- 第一轮创建分支时，环境拒绝写 `.git/refs/heads/d-monthly-spark-pipeline.lock`。本会话权限配置也将 `.git` 列为只读；这是执行环境限制，不能据此认定仓库损坏、Windows ACL 错误或 Git 自身禁止提交。新环境先核实实际权限，不绕过沙箱。
- 第一轮及交接检查在项目祖先目录和相关代码目录未发现额外 AGENTS.md；仍应在接手时重新检查。
- 不使用 `git clean`，不删除被忽略的 SSH 说明、归档、测试证据、运行记录或部署包。不迁移或覆盖六小时历史结果。
- 旧 `gharchive_a/` 十份处理代码基线未修改，第一轮 LF SHA-256 核对全部匹配；旧六小时入口和旧 weekly CLI 保留。

### 实现文件清单

| 文件（相对仓库根） | 职责 |
|---|---|
| `d_parallel_experiments/scripts/run_batch_pipeline.py` | 统一 CLI、计划、批次调度、身份、续跑和最终合并 |
| `d_parallel_experiments/scripts/spark_batch_job.py` | 复用原 Spark 清洗器并保存生效配置等产物 |
| `a_data_pipeline/rolling_pipeline/batch_support.py` | 时间、状态、校验、锁、预算、清理及公共支持 |
| `a_data_pipeline/rolling_pipeline/batch_download.py` | 新入口的下载与缓存发布适配 |
| `a_data_pipeline/rolling_pipeline/batch_merge.py` | 全有效出现索引、SQLite 全局裁决与最终产物 |
| `d_parallel_experiments/scripts/verify_results.py` | 完整运行的事件字段、类型、统计、覆盖和证据比较 |
| `d_parallel_experiments/scripts/summarize_results.py` | 阶段计时、运行汇总、D4 事件日志参与证据 |
| `d_parallel_experiments/scripts/prepare_batch_deployment.py` | 仅源文件打包及原始/LF 哈希清单 |
| `d_parallel_experiments/configs/local_1core.json` | L1：local[1] |
| `d_parallel_experiments/configs/local_4core.json` | L4：local[4]，默认 |
| `d_parallel_experiments/configs/distributed_4core.json` | D4：总计 4 核、每 Executor 2 核，实际 master 须指定 |
| `d_parallel_experiments/tests/test_batch_pipeline.py` | 新滚动流程及相关合成测试 |

已修改的既有文件：根 `README.md`、`a_data_pipeline/rolling_pipeline/README.md`、`a_data_pipeline/tests/test_pipeline.py`、`d_parallel_experiments/README.md`、`d_parallel_experiments/.gitignore`。旧测试文件的修改是 Windows 适配：显式关闭测试 SQLite 连接，硬链接受限时明确跳过对应测试。

本次整理仅新增本交接文档及其 Git 忽略规则放行项，没有改动处理代码。

## 3. 实际实现要点

- 新入口使用 UTC 半开区间 `[start,end)`，日期表示当天 00:00 UTC，时间须带时区且转换后为整点。旧 weekly 入口的 end 仍包含该日期，不混用。
- 支持正整数批次小时数，默认 24，6/12/24 已有合成覆盖。跨日、跨月、跨年及不足一批的尾批按起点连续推进。
- `--plan-only` 输出 JSON，不创建目录、下载、启动 Spark或删除文件。
- 选择的是 GH Archive 来源档案小时，不按事件发生时间过滤。日统计使用事件自身的 UTC `event_date`。
- 三种配置共用原 `gharchive_a.spark_clean.clean_spark()`；跨午夜批次按来源日期拆为内部 fragment，一批可能产生多个 Spark Application。
- 最终合并使用 Python/SQLite，不是全流程 Spark，不依赖 DuckDB。
- 全局裁决读取所有有效出现，包括局部已去重和已冲突排除的出现。相同 ID、相同内容保留最早来源；相同 ID 存在不同内容时全部排除，最终重算统计和候选表，局部产物保留原样。
- 已验收产物续跑先核验大小与哈希；损坏直接失败。身份不相容的参数或代码要求新 output。失败尝试保留并新建 attempt。
- 同 raw/output 使用互斥锁；跨主机 NFS 语义仍待现场验证，验证前不得多节点并发提交相同目录。
- `retain` 默认保留输入。`accepted-raw` 只允许本次拥有的新建空专用 raw，逐文件核验归属、路径和哈希，带删除意图日志及恢复机制。
- 默认最小空闲 2 GiB、batch 工作区预算 16 GiB、merge 预算 24 GiB、SQLite 页缓存 128 MiB；采样/检查点保护不等于系统硬配额，必须额外预留临时空间。
- Python 与 Spark 参照共享最终全局合并器，不能声称两套完全独立的全流程验证。

## 4. 第一轮验证记录

以下是第一轮已记录的结果，本次交接没有重新运行整套测试。详细命令与证据解释见 `local_validation.md`。

| 检查 | 结果 |
|---|---|
| D 测试 | 26 通过：18 项新增测试 + 8 项旧六小时对账回归 |
| A 管道测试 | 6 通过、2 明确跳过 |
| 原计时包装器 | 1 通过 |
| 总计 | 33 通过、2 跳过 |
| 新代码语法编译、git diff --check | 第一轮通过 |
| 旧六小时代码 LF 哈希 | 10 文件匹配 |
| 旧周测试 `test_weekly_cleanup/test_weekly_merge/test_weekly_resume` | 未执行，需 POSIX，其中 merge 还需 DuckDB |
| 真实 Spark、真实双 Worker、两天真实数据、NFS | 未执行 |

两项跳过分别为 Windows 沙箱拒绝 os.link 的旧下载器硬链接测试，以及未准备 PySpark/JVM 的原 Spark fixture。新 Spark 桥接和 D4 日志测试使用 fixture/合成日志，不是真实 Spark。

合成数据使用跨月 48 个 gzip 档案，按 6/12/24h 得到一致结果：15 个有效出现、最终保留 5 条、重复移除 4 次、冲突排除 6 次，满足 `15 = 5 + 4 + 6`。覆盖首批内部冲突后在后批重现、后批新冲突撤销前批保留、字段类型、事件日期、空档、缺档、续跑、损坏拒绝、安全清理和比较器内部重算等。

第一轮本地环境：Python 3.13.9、PyArrow 21.0.0，无 PySpark、DuckDB 和 POSIX fcntl。未安装 Bash/WSL；不要因本地测试通过而跳过 VM 环境检查。

## 5. 部署包与完整性

现有文件：

- `d_parallel_experiments/.deployment/rolling_v1_20261112.tar.gz`
- `d_parallel_experiments/.deployment/rolling_v1_20261112_manifest.json`

包含 50 个允许源文件，tar 另带 `DEPLOYMENT_SHA256.json`。没有历史 raw、runs、results、大日志、SSH 说明或凭据。交接时再次核对了这 50 份本地文件与 manifest 的原始/LF 哈希以及 tar 内文件，全部匹配。交接文档是在包生成后新增，不在旧包内，单独阅读即可。

```text
archive SHA-256:
4ba1ed22753153e98a528e00dabd7ba4f0d4e72c28bc17907c1139d542ece29b

runtime_identity.sha256:
d2d68b14569835a0f4b2761b532c4b6297b50c1e7669e149899c69f378899afb
```

源文件若随后改变，须用 `prepare_batch_deployment.py --archive <新名字.tar.gz> --manifest <新名字.json>` 重建，不能仍声称旧包与新代码一致。准备包不代表已经部署；传输后还须在新目录核验 manifest。

## 6. VM 连接与上一轮阻塞

| 节点 | 地址 | SSH 用户 |
|---|---|---|
| Master | `192.168.20.130` | `lishuo` |
| Worker 1 | `192.168.20.129` | `lishuo` |
| Worker 2 | `192.168.20.131` | `lishuo` |

本机连接说明见 `d_parallel_experiments/虚拟机与SSH接手说明.md`；从中取得现有私钥路径，仅以 `ssh/scp -i` 使用，不读取或输出私钥。保持严格主机指纹检查；需要 sudo 时由用户在 VM 控制台执行并输入密码。

根据上一会话记录，三台 VM 的 22 端口访问均返回 Permission denied，现场工作没有开始。上一会话将其归因为执行环境网络限制；交接时未重新联网探测。新环境应区分本地连接被拒、网络不可达与 SSH 密钥认证失败，不要仅凭相同短语就推断需要更换密钥或修改 VM。当前受限环境不能申请 sandbox 网络放宽。

## 7. 历史任务 2 待办（已停止，不作为下一对话指令）

1. 复核工作区、文档和 CLI，确认源码未丢失；重新诊断三台 VM 连接。
2. 只读记录 hostname/IP、CPU/内存、df、findmnt、现有作业和环境版本。确认两台 Worker 的挂载源为 `192.168.20.130:/data/cs5488`，核实新代码/输入/输出可访问。
3. 在新 release 部署源包并核验全部文件；已有同名目录则使用新后缀并记录，不覆盖。核实既有 Python/Spark 环境，不自动重装。
4. 先做 L4 1h 新冒烟，再按实际占用外推两天容量。任务 2 不需要启动独立 Spark Master/Worker 服务或变更 VM 配额。
5. 按原方案完成正常路径的两天 L4 6/12/24h 分批；同一来源与哈希，输出各自独立，全部 retain。完整 Python 参照与比较命令见 `monthly_pipeline.md`；需要作为入口正确性证据时执行，避免仅比较旧日汇总 CSV。
6. 报告实际命令、代码身份、输入哈希、批次覆盖、验收状态、最终结果、磁盘/错误与未执行项。完成任务 2 就停下，等待用户指示任务 3；不顺带开展 D4、受控故障、删除验收或整月运行。

若空间不足，保留现场并报告缺口，不删除旧证据，不用缩减核对字段冒充完整验收。任务 2 的正常运行中发现问题可修复并验证，但不要将后续任务提前标成完成。

### 已拟定路径与输入范围

| 用途 | 路径或范围 |
|---|---|
| 新部署 | `/data/cs5488/releases/rolling_v1_20261112/` |
| 共享输入 | `/data/cs5488/monthly_validation/rolling_v1_20261112/raw_shared/` |
| 两天来源 | `[2024-01-15T00:00Z,2024-01-17T00:00Z)`，48 档 |
| L4 输出 | `/data/cs5488/runs/rolling_v1_20261112_2d_l4_6h`、`_12h`、`_24h` |
| Python 参照 | `/data/cs5488/runs/rolling_v1_20261112_2d_python` |
| 临时目录 | `/data/cs5488/monthly_validation/rolling_v1_20261112/tmp/`，设置 TMPDIR |
| 冒烟来源 | `[2024-01-16T00:00Z,2024-01-16T01:00Z)` |
| 后续任务 4 专用清理输入 | `/data/cs5488/monthly_validation/rolling_v1_20261112/raw_cleanup/`，仅两个新下载且验收档案 |

预期 Python：`/home/lishuo/cs5488-round1/env/bin/python`。预期 spark-submit：同环境下 `lib/python3.11/site-packages/pyspark/bin/spark-submit`。这些是待核实路径，不能当作当前 VM 已确认事实。

## 8. 文档阅读优先级

1. project_handoff_prompt_20261112.md 及本文顶部更正：当前只读交接，所有执行已停止。
2. `docs/monthly_pipeline.md`：已实现 CLI、数据契约及正常使用。
3. `docs/local_validation.md`：第一轮实测结果与明确未执行项。
4. `docs/cluster_setup.md`：现场预检、容量、路径及操作命令；当前等待用户新的执行指令，历史授权已撤回。
5. `monthly_spark_execution_plan.md`：原需求和完整验收目标；其最初“尚未实现”说明不能覆盖现有实现事实。

本次只整理交接并核对源码包，没有连接 VM、重新运行整套测试、部署、提交或删除文件。
