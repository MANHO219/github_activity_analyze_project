# 任务 2–5 本次执行与阻塞报告

> 当前需求解释见[需求对齐记录](requirements_alignment_20261112.md)。本文的三窗口完整两天计划是此前方案，不能继续作为原需求硬性条件；本文件及 JSON 保留历史阻塞和命令记录。

> 后续更新：用户要求按审批流程重试后，三台只读 SSH 成功；随后任务二完成新部署、真实 L4 1h 冒烟及同输入 Python 完整比较。两天正式运行因容量不足未执行。最新结果见 [任务二验收与容量报告](task2_validation_20261112.md)。本文以下及配套 execution JSON 保留为之前连接阻塞阶段的历史记录。

日期：2026-11-12，北京时间。本次依据用户新指令恢复指定任务，不恢复旧后台作业。现场工作在连接预检阶段停止；本地复核完成。机器可读命令、退出状态、耗时、主机信息和源包身份见 [execution_20261112.json](execution_20261112.json)。

## 任务结果

| 任务 | 本次完成 | 阻塞与未执行 |
|---|---|---|
| 2：通用入口真实正常路径 | 14 份文档按顺序读取；入口、三配置、下载、验收、全部有效出现合并器、比较器及相关测试审查；本地回归和旧源包核验 | 三台 SSH 在 TCP 建立前被拒；主机身份、资源、NFS、服务、依赖和目录状态未知。未部署、未下载、未做 L4 1h 冒烟、容量评估、两天三窗口及完整 Python 对账 |
| 3：L1/L4/D4 共用逻辑 | 确认共用入口与配置请求；修复双 Worker 证据检查允许重复主机名的缺口并通过专项回归 | 未运行三种真实配置，未启动服务，没有新应用 ID、生效配置或两个真实 Worker 的成功 TaskEnd |
| 4：续跑、互斥与限定清理 | 重新运行既有本地合成续跑、损坏拒绝、互斥和清理日志测试 | 未做 NFS 跨主机锁、真实中断恢复、最终合并恢复或两档真实清理；没有删除 VM 文件 |
| 5：计时与结果汇总 | 保存本地命令、环境、实际退出状态、墙钟耗时、源码/包哈希及任务状态 | 真实输入哈希、阶段计时、空间峰值、吞吐和比较结果均未测量，不能给出真实验收通过结论 |

任务 3、4 没有越过任务 2 的阻塞开始现场执行。真实验收项没有以合成测试替代，也没有填入虚构的 0 秒。

## 工作区与连接证据

最初检查为 main，HEAD `62dd2e53f52fc65f309535b1c2d57fa276684215`，5 个跟踪文件修改、17 个未跟踪文件（展开 docs 后的文件数），未 fetch。项目及祖先、相关子目录未发现适用 AGENTS.md。保留所有原修改、未跟踪内容、忽略文件、旧部署包和历史日志；未操作 Git 索引、分支、提交或 PR。

三节点均按下列形式调用，保留严格主机指纹校验，私钥仅经 `-i` 使用，没有读取或输出内容：

```powershell
ssh -i C:\Users\lenovo\.ssh\cs5488_d_round1 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 lishuo@192.168.20.130 hostname
ssh -i C:\Users\lenovo\.ssh\cs5488_d_round1 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 lishuo@192.168.20.129 hostname
ssh -i C:\Users\lenovo\.ssh\cs5488_d_round1 -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 lishuo@192.168.20.131 hostname
```

三条均退出 1，输出 `ssh: connect to host <IP> port 22: Permission denied`。随后本机 Python `socket.create_connection((host,22),timeout=3)` 三台均报告 `PermissionError, errno=13, winerror=10013`。这证明本机 socket 访问权限阻止了 TCP 建立；没有进入 SSH 主机指纹或密钥认证阶段。无法据此判定 VM 关机、网络超时或密钥失效，也不能仅凭该错误定位到具体沙箱/防火墙规则。未申请网络放宽、关闭指纹校验、改端口或改用其他通道。

本次没有实际 VM 运行身份；`lishuo` 只是请求的 SSH 用户。Windows 测试主机及软件版本保存在 JSON，不能代替远端预检。SSH/socket 观察由前序工具结果转录，未伪称已有原始 SSH 日志文件。

## 本地审查与修复

审查确认来源小时 UTC `[start,end)` 与事件 UTC 日期分开处理；三配置共用原清洗器；最终合并读取全部有效出现，包括局部已重复或已冲突排除的记录，按 ID/内容指纹裁决后重算统计。该结论来自源码审查及合成回归，真实 Spark 导出和 NFS 行为仍待验收。Python 与 Spark 共享最终 Python/SQLite 合并器，不是两套完全独立实现，也不是全流程 Spark。

发现 `summarize_results.worker_evidence()` 对要求的主机列表没有校验：同一个名称传两次时，两次查询同一主机的成功计数即可通过。现要求恰好两个不同且非空的字符串；缺少、重复或空名称提前拒绝。新测试在修复前失败，修复后两个 WorkerEvidenceTests 均通过。不同名称仍需现场预检确认映射到两个真实 Worker；此修复不证明真实双节点参与。

本地环境为 Python 3.13.9、PyArrow 21.0.0、SQLite 3.51.0，无 PySpark 或 DuckDB。测试使用本次新建的专用 tmp，不清理原有忽略目录。

| 检查 | 结果 | 子进程墙钟秒数 |
|---|---|---:|
| 修复前 D 全套回归 | 26 通过 | 42.857 |
| A 管道回归 | 6 通过、2 跳过 | 1.750 |
| 原计时包装器回归 | 1 通过 | 3.827 |
| 修复后 WorkerEvidenceTests | 2 通过（含 1 项新增） | 1.010 |

基线共 33 项通过、2 项跳过；修复后只重跑受影响的两项，不能把重复执行项计为更多独立测试。旧硬链接下载器测试因 Windows WinError 5 跳过；Spark fixture 因未启用 RUN_SPARK_TESTS 且环境无 PySpark 跳过。POSIX weekly cleanup/merge/resume 未执行。新桥接测试仍用替代输出，Worker 日志仍为合成日志。

完整本地日志位于 `d_parallel_experiments/local_only/execution_20261112_103904_6b228d/`，继续被忽略；JSON 保存路径和日志 SHA-256。报告只引用本次测量，不累计旧会话耗时。

## 源包和未部署路径

修复前重新核验旧包：50 个允许源文件的大小、原始/LF SHA-256、tar 成员及嵌入清单全部匹配当前基线。旧包 SHA-256 为 `4ba1ed22753153e98a528e00dabd7ba4f0d4e72c28bc17907c1139d542ece29b`，旧运行身份为 `d2d68b14569835a0f4b2761b532c4b6297b50c1e7669e149899c69f378899afb`。修复与文档更新后这些哈希仅描述旧包，不能用于新代码；新名字源包与当前身份另记在 JSON 的 `current_source_package`，未部署。

以下仍是计划路径，未检查是否已存在，未创建远端目录。重试现场时必须先核验，已占用则记录新后缀，不覆盖或盲目续跑：

| 用途 | 路径或范围 |
|---|---|
| release | `/data/cs5488/releases/rolling_v1_20261112/` |
| 共享 raw | `/data/cs5488/monthly_validation/rolling_v1_20261112/raw_shared/` |
| L4 及容量冒烟 | `[2024-01-16T00:00Z,2024-01-16T01:00Z)`；`/data/cs5488/runs/rolling_v1_20261112_smoke_L4` |
| 正式输入 | `[2024-01-15T00:00Z,2024-01-17T00:00Z)`，48 档，共享 SHA-256，全部 retain |
| 两天输出 | `/data/cs5488/runs/rolling_v1_20261112_2d_l4_6h`、`_12h`、`_24h` 及 `/data/cs5488/runs/rolling_v1_20261112_2d_python` |
| 限定清理 raw | `/data/cs5488/monthly_validation/rolling_v1_20261112/raw_cleanup/`，须本次新建并拥有；来源仅 `[2024-01-16T00:00Z,2024-01-16T02:00Z)` |

恢复顺序仍为只读预检/部署 → Worker 1 L4 新冒烟与实际容量预算 → 两天三窗口及完整 Python 比较 → 相同小样本三配置与真实双 Worker 证据 → 专用任务故障恢复、NFS 锁及限定清理 → 真实计时汇总。没有扩大输入或处理整月，旧九次实验不重跑。

本轮受影响步骤已停止，未留下本轮后台任务。等待用户处理连接条件并给出新指令；不自动重试或沿用旧任务现场。
