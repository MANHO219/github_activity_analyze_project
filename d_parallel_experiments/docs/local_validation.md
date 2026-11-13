# 本地代码验证与现场交接结果

> 2026-11-13 后续验证：真实七小时 L4 不同窗口与 Python 完整比较通过；真实运行发现 `tree_bytes()` 目录遍历竞态，修复后新增目录消失与权限错误回归，Linux 21 项测试通过。旧 Windows 33 通过/2 跳过是下文历史记录，不能与新测试重复累计。当前证据与未执行边界见[新入口验收](task2_entry_acceptance_20261113.md)。

> 当前需求解释见 [需求对齐记录](requirements_alignment_20261112.md)。以下保留本地合成测试的历史事实；现场后来已完成 1h L4/Python 对账。未来连续两天综合验收不默认三窗口全量或同时保留四份重型过程输出，容量须按修订矩阵重新预算。

> 本次复核更新（2026-11-12）：用户新授权下重新运行下列本地回归，基线仍为 33 项通过、2 项跳过。随后修复双 Worker 证据函数允许重复主机名的缺口，新增拒绝重复/缺少/空白主机名的回归；修复后 WorkerEvidenceTests 两项通过。该修复仍只验证合成日志，真实 Spark/双 Worker/NFS 验收未执行。三台 VM 连接在 TCP 建立前遭 WinError 10013 拒绝；未部署或下载。完整命令、退出状态、耗时及修复前后源码身份见 [执行报告](execution_20261112.md) 与 [小型证据](execution_20261112.json)。以下保留第一轮结果，不将两次测量累计为新的实验性能。

日期：2026-11-12。验证范围为 Windows 本地代码与合成档案，没有连接 VM、部署代码、启动 Spark、重跑旧实验或执行真实档案清理。两天真实数据验收尚未开始，整月范围尚未指定。

## 基线与工作区

起点为 main / `62dd2e53f52fc65f309535b1c2d57fa276684215`（PR #10），初始工作区干净。检查项目及祖先路径未发现额外 AGENTS.md，遵循本次提供的项目指令。未 fetch，不能据本地 origin/main 推断远端现状。

环境拒绝创建 `.git/refs/heads/d-monthly-spark-pipeline.lock`，因此改动保留为 main 上的未提交工作区文件，未创建开发分支、提交或 PR。未尝试绕过 `.git` 只读限制。原有被忽略证据、SSH 说明、归档及运行目录均保留。

新代码为 D 的滚动、比较、汇总、源代码打包入口与三份配置，及 A rolling_pipeline 的三个 batch 公共模块。`gharchive_a/` 的十份旧基线代码未改动：运行原 `verify_code()`，全部 LF SHA-256 仍匹配 `configs/reconciliation_code_lf.json`。旧六小时脚本、证据、清单、运行 ID 和旧 weekly CLI 均未改变。

原测试仅有两处 Windows 适配：显式关闭测试自身的 SQLite 连接；在操作系统拒绝硬链接时将旧下载器硬链接测试标记 skipped。新下载适配器 Windows 用不覆盖目标的 rename、POSIX 用硬链接发布；没有通过修改旧生产下载器或改写旧哈希让历史回归通过。

## 实际测试结果

本地：Python 3.13.9、PyArrow 21.0.0；没有 PySpark、fcntl 或 DuckDB。DuckDB 安装尝试因网络访问受限失败，未安装 Bash/WSL 或替换 VM 环境。测试用专用临时路径避开沙箱系统临时目录权限问题。

```powershell
$env:TMP = Join-Path (Get-Location) 'd_parallel_experiments/.test_tmp'
$env:TEMP = $env:TMP
$env:PYTHONUTF8 = '1'
python -m unittest discover -s d_parallel_experiments/tests -v
python -m unittest discover -s a_data_pipeline/tests -v
python -m unittest discover -s a_data_pipeline/rolling_pipeline/tests -p test_profiled_run.py -v
```

运行前创建这个新的测试专用目录，不清理任何已有本地证据。新环境可改为其他可写临时目录。

| 检查 | 实际结果 |
|---|---|
| D 全部测试 | 26/26 通过，最终一轮 55.218 秒 |
| 其中新增滚动、清理、比较及参与证据测试 | 18 项通过，无 VM/JVM |
| 其中旧六小时对账回归 | 8 项通过 |
| A 原管道测试 | 6 项通过，2 项明确跳过 |
| 原计时包装器回归 | 1 项通过 |
| 总计已通过 | 33 项 |
| 旧下载器硬链接测试 | 跳过，Windows 沙箱拒绝 os.link；新下载适配器发布及清理流程已用真实文件验证 |
| 原 Spark 对账 fixture | 跳过，未设置 RUN_SPARK_TESTS，环境无 PySpark/JVM 测试准备 |
| 旧 test_weekly_cleanup / test_weekly_merge / test_weekly_resume | 未执行，依赖 POSIX fcntl，其中 merge 还依赖 DuckDB；须在获准的 Linux 阶段回归 |
| 新 Python 文件语法编译、git diff --check | 通过 |
| 原六小时处理代码 LF 哈希基线 | 10 文件匹配 |

Spark 提交桥接测试将 Python 生成的持久文件作为 Spark 输出 fixture，验证参数流转、生效配置检查和拒绝不相容配置；参与证据测试使用合成 TaskEnd/ApplicationEnd 日志。这些都不能称为真实 Spark 或双 Worker 实测。

## 合成数据的预先确定答案

来源覆盖 `[2024-01-31T00:00Z,2024-02-02T00:00Z)`，48 个真实 gzip 合成档案，包含空档案、非法行、空行、可选字段缺失、Unicode 名称、同日/跨日重复、跨月冲突及事件时间落在来源小时以外的情况。按 6/12/24 小时分别完成 8/4/2 批。

| 预期结果 | 三种窗口实际结果 |
|---|---|
| 全部有效出现 | 15 |
| 最终保留 ID | 1、4、5、6、7（共 5 条） |
| 同内容重复移除出现 | 4 |
| 冲突 ID | 2 个 |
| 冲突排除出现 | 6 |
| 守恒 | 15 = 5 + 4 + 6 |
| 最早来源 | ID=1 保留首档第 1 行 |
| 事件日期 | 仍为 2024-01-30，未按来源范围过滤 |
| 精确比较 | 事件所有字段/类型、日统计、候选表、覆盖、冲突/重复证据及重复次数一致 |

ID=2 在首批内部出现 p/q 冲突、后批再次出现 p，最终全部排除。ID=3 的较后批内容改变，使前批已保留的该 ID 同样从最终输出排除。局部产物保留原样。

另验证了：日期与时区、整点拒绝、闰日/跨年/尾批、plan-only 零写入、空有效结果与缺档区分、处理/验收/最终合并中断、失败现场保留、缓存复用、验收跳过、损坏拒绝、不相容身份拒绝、互斥锁、删除后写日志前中断恢复、哈希变化/越界/符号链接拒绝、清单外与外来缓存保留，以及比较器不能把“两份同样错误的候选表”判为通过。

## 尚待现场验证与主要限制

- 三份配置的真实 Spark 输出、生效 JVM/资源环境、Spark 停止后的进程状态，尤其 D4 两 Worker 成功任务。
- 连续两天不同分批方式的最终一致性及同来源 Python 明细参照核对，具体矩阵按最新需求对齐记录制定，不预定三个窗口各做全量。合成 48 档不能当作真实两天验收。
- NFS 跨节点锁、挂载源、当前空闲空间、断连恢复和系统临时目录峰值。
- 合并为 Python/SQLite；完整有效出现、验收 SQLite、局部输出、最终 SQLite/CSV/Parquet 和比较库均占空间。当前实现的保留方式需要审查，但不等于原需求要求永久保留所有过程库；先按选定矩阵和已完成冒烟重新预算，不引用历史空闲量或删除旧证据。
- Python/Spark 参照的最终全局合并器共享；已用已知答案的合成冲突案例补充验证，但不能声称两个完全独立的全流程实现。
- 预算为采样与检查点保护，不是系统硬配额；同步检查/导出阶段可能在下一安全检查点才停止。

明确的部署、输入、输出、清理和现场命令见 [cluster_setup.md](cluster_setup.md)。只有用户明确启动现场阶段后才执行；两天验收后先报告结果，不自动运行整月。

可用 `scripts/prepare_batch_deployment.py --archive <新tar.gz> --manifest <新json>` 准备只含允许源文件的包。它包括 A scripts/rolling_pipeline/gharchive_a 和新 D 入口，逐个读回 tar 成员核验 SHA-256，不包含历史输入、证据、SSH 说明或凭据。准备源文件包不代表已经部署。
