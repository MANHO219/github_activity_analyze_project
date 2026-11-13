# 任务二：真实冒烟通过，两天验收因容量不足停止

> 2026-11-13：已按修订范围完成七小时入口真实验收，1,433,999 条事件在 6h＋1h、默认 24h 和 Python 间一致；未扩盘，连续两天综合仍未做。最新证据见[入口验收报告](task2_entry_acceptance_20261113.md)。本文及配套 JSON 继续保留前一天历史测量。

> 需求修正：本文记载此前实际执行及旧重型验收方案的容量外推，保留为历史证据。用户随后重新给出原始要求，明确按功能和连续两天综合验收解读；三种窗口各跑完整两天、永久保留三份比较库、200 GiB 可用及扩至 250 GB 均不再作为原需求硬性条件。1h 实测结果不变，修订后的容量尚未测定。当前请先读[原始要求解释与范围修正](requirements_alignment_20261112.md)，不要据本文自动扩盘或执行旧三窗口方案。

2026-11-12，北京时间。本次已按新的“完成任务二”指令进行现场预检、全新部署、真实 L4 1h 冒烟及同输入 Python 完整比较；两天正式验收尚未完成，原因是实测容量模型超过现有共享盘余量。任务 3、4 未启动，没有删除任何原始档案，没有修改 VM 资源或启停独立 Spark 服务，没有提交、推送或 PR。

小型机器可读证据见 [task2_validation_20261112.json](task2_validation_20261112.json)。完整日志、采样、SQLite、Parquet 和失败比较目录均原位保留，不进入 Git。

## 预检与部署

本地仍为 main / `62dd2e53f52fc65f309535b1c2d57fa276684215`，未 fetch。原有未提交与忽略内容保留。此前沙箱内 SSH 的 WinError 10013 已通过用户要求的 `require_escalated` 审批流程解决，不是密钥损坏。

三台 SSH 使用现有私钥的 `-i` 参数和 `BatchMode=yes, StrictHostKeyChecking=yes`。身份与 IP 分别核实为 spark-master/.130、spark-worker-1/.129、spark-worker-2/.131，运行用户 lishuo、uid/gid 1000。两 Worker 的 NFS 源均为 `192.168.20.130:/data/cs5488`、nfs4；未发现已有 Spark 作业，专用 Master/Worker 服务均未运行。只读状态脚本对“未运行”返回 1；目录存在性检查对新路径返回 1，不代表 SSH 认证失败。

| 节点 | vCPU | 内存字节 | 本次角色 |
|---|---:|---:|---|
| Master | 2 | 5,620,944,896 | NFS 共享存储 |
| Worker 1 | 4 | 7,734,865,920 | L4、Python 参照和比较 |
| Worker 2 | 4 | 5,620,948,992 | 只读预检及新共享路径可访问性检查 |

Master 的 `/data/cs5488` 位于根分区 `/dev/sda2`（ext4、无 LVM），虚拟磁盘 `/dev/sda` 为 60G。最初可用 35,602,128,896 字节（33.16 GiB），本次验收后可用 34,230,763,520 字节（31.88 GiB）。Worker 1 本地 Spark scratch 位于另一台 VM 的根盘，不能把它的空闲量加到 NFS 共享盘容量中。

以下新路径在使用前确认不存在，并新建；没有覆盖旧部署或结果：

| 用途 | 路径 |
|---|---|
| 部署 | `/data/cs5488/releases/rolling_v1_20261112/` |
| 新共享输入 | `/data/cs5488/monthly_validation/rolling_v1_20261112/raw_shared/` |
| L4 冒烟 | `/data/cs5488/runs/rolling_v1_20261112_smoke_L4/` |
| Python 容量参照 | `/data/cs5488/runs/rolling_v1_20261112_smoke_python/` |
| 成功比较 | `/data/cs5488/monthly_validation/rolling_v1_20261112/comparison_smoke_python_L4_attempt02/` |
| 日志与小型证据 | `/data/cs5488/monthly_validation/rolling_v1_20261112/evidence/` |

源包为本地 `.deployment/rolling_v1_20261112_exec01.tar.gz`，SHA-256 `3939016fa9061f616065414d2246f570f6abff24cc1453f14197ec257c22e586`。部署前与部署后分别核对 50 份允许源文件的大小及哈希；收尾再次逐项核验部署文件。运行代码身份为 `b307ff8c73e8d05a11fd6825500b6cf9d7842299c997ad5bdaea2a4744b3d443`。保留旧源包、`/data/cs5488/project/` 和历史运行。

原专用 `spark-defaults.conf` 含历史 D4 参数，本次未修改它。使用新建的独立 `spark-conf/`、每个 case 独立 TMPDIR、事件日志目录和 Worker 1 本地 scratch；显式选择已有 Java 17。实际环境：Python 3.11.18、PySpark 3.5.7、PyArrow 26.0.1、SQLite 3.54.1、Java 17.0.20.1。

## 真实 1h 验收

实际来源为 UTC `[2024-01-16T00:00Z,2024-01-16T01:00Z)`，只有一个档案，cleanup=retain。没有按事件时间新增过滤。

- `2024-01-16-0.json.gz`：78,166,242 字节。
- 实际 SHA-256：`62fa17f986933b8692719ce00a8fa049aa528544a676096af629b3986aebfc95`，与 A 历史清单对应项一致。
- L4 与 Python 均为 212,804 条有效出现及最终事件；本档没有重复或冲突。
- L4 实际生效为 local[4]、Driver 4g、Shuffle=12、AQE=false、UTC、TIMESTAMP_MICROS。
- 应用 ID `local-1794483204703`；原始事件日志存在对应 ApplicationStart/ApplicationEnd，spark-worker-1 上有 540 个成功 TaskEnd。这是实际 L4 证据，不是 D4 或双 Worker 参与证据。
- 已验收文件大小/哈希复验通过；逐事件 13 字段、Arrow 类型、重复次数、日统计 CSV/Parquet、候选表内部重算、覆盖、输入哈希、重复/冲突证据均通过完整比较，共 19 个检查为 true，各类双向差异均为 0。

Python 参照串行复用本次已校验的同一档案，未重新下载或扩大输入范围。Python 与 Spark 共享最终 Python/SQLite 合并器，不能称为两套完全独立的全流程验证或全流程 Spark。由于真实 1h 没有重复或冲突，不能据此宣称真实跨批冲突已验收；已知答案的合成测试仍只是补充证据。

比较调度曾提前于 Python 运行完成而启动，比较器以 `Run is not complete` 正确拒绝、退出 1。原失败目录 `comparison_smoke_python_L4/` 保留；确认 Python 退出 0 后，在 `attempt02` 新目录重试通过。这是本次调度错误及恢复，不是任务四的受控故障验收，不计为成功比较或性能测量。

## 实测计时

| 阶段 | L4 秒数 | Python 秒数 |
|---|---:|---:|
| 下载校验 | 1778.744（新下载） | 1.174（缓存复核） |
| 原始检查 | 11.427 | 13.576 |
| 清洗导出 | 42.299 | 22.025 |
| 批次验收 | 14.245 | 13.778 |
| 全局去重 | 3.643 | 4.013 |
| 最终汇总导出 | 5.229 | 5.210 |
| 主入口端到端父计时 | 1855.966 | 60.211 |
| 外层启动至退出 | 1856.892 | 61.325 |

成功完整比较为 19.761 秒。L4 清洗阶段约 5,031 事件/秒；此值只对应本次单小时单次清洗，不包含下载或验收，也不作为重复性能实验的结论。全局合并父计时为 L4 8.896 秒、Python 9.256 秒，包含对应去重和汇总阶段；不能与子阶段重复相加。未执行清理，没有编造清理 0 秒。

本次新下载约耗时 29 分 39 秒，网络速度较慢但持续推进，无下载失败或重试。不能把它混入 Spark 清洗性能，或把 Python 缓存复核当作首次下载。

## 实测占用与旧重型两天容量模型（不作为现需求最低容量）

| 单小时实测组件 | 字节 |
|---|---:|
| 全部有效出现 Parquet 索引 | 21,191,232 |
| 局部清洗输出目录 | 54,695,136 |
| 批次验收 SQLite | 163,917,824 |
| 全局合并 SQLite | 177,405,952 |
| 最终事件 Parquet | 8,207,092 |
| L4 完整保留运行 | 428,739,438 |
| Python 完整保留运行 | 563,607,547 |
| 完整比较库及小型报告 | 290,616,987 |

外层每秒采样记录到 L4 本地 Spark scratch 峰值 118,776,358 字节；Python 专用 TMPDIR 可见文件峰值 37,452,614 字节；比较阶段也记录了每秒磁盘监控。Spark 临时文件在框架正常退出时自动释放，没有执行人工清理。采样不是瞬时峰值保证，SQLite 的匿名临时文件可能只能体现在文件系统空闲量中。

| 两天估算项目 | GiB |
|---|---:|
| 三份 Spark 完整运行（每份按 48 倍 1h） | 57.50 |
| 完整 Python 参照（48 倍） | 25.20 |
| 共享 48 档 raw（A 历史清单大小） | 4.59 |
| 三个 Python 对三窗口的完整比较库（48 倍） | 38.97 |
| 最小剩余空间阈值 | 2.00 |
| 合计 | **128.26** |

raw 的 48 档总大小 4,933,643,388 字节来自 A 历史清单，不能称为本次已下载或已核验 48 档。本次实际输入只有上述 1 档。按 A 历史两天有效出现数 10,885,522 对输出和比较库量级再校正，估算约 **136.25 GiB**。两种模型均为外推，未测得真实两天峰值；还需预留小时密度变化、SQLite 临时空间、失败尝试和系统余量。

建议开始正式验收前，Master 共享文件系统至少有 **200 GiB 可用**。当前只有 **31.88 GiB**，距建议值约差 **168 GiB**；正式 48 档下载、L4 6/12/24h 三窗口、两天 Python 参照及正式比较均未启动。不删除旧证据，不减少保留内容或对账字段来宣称通过。

## 旧存储调整建议（未执行，已撤销为任务前置条件）

推荐扩大 Master 现有虚拟磁盘：VMware 中由 60 GB 改为 **250 GB**，随后扩展 `/dev/sda2` 分区和 ext4 文件系统。这样保留 `/data/cs5488` 及 NFS 导出路径，Worker 不必扩盘。宿主 E 盘本次只读检查约有 434 GiB 可用。扩容后仍以实际 `df` 可用空间是否达到 200 GiB 为准。

1. 确认任务全部结束，正常关闭两 Worker，再正常关闭 Master；做关机备份。未由本次自动关机。
2. VMware Workstation 选择 Master → 编辑虚拟机设置 → 硬盘 → Utilities/实用工具 → Expand/扩展，目标设为 250 GB。若有快照或关联克隆导致不能扩展，保留现场另行处理，不删除快照。虚拟磁盘扩展后，还必须在客体中扩展分区和文件系统。[VMware 官方说明](https://knowledge.broadcom.com/external/article?legacyId=1004047)
3. 启动 Master，在 VM 控制台确认 `lsblk` 已显示扩大后的 `/dev/sda`，且现场仍为 `/dev/sda2`、ext4、挂载 `/`。然后由用户在控制台输入 sudo 密码，先预览，再执行：

```bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
sudo growpart -N /dev/sda 2
# 仅在预览显示目标与布局正确后：
sudo growpart /dev/sda 2
sudo resize2fs /dev/sda2
df -h /data/cs5488
```

`growpart -N` 是不写分区表的预览，正式命令扩展第 2 分区；`resize2fs` 扩展其 ext4 文件系统。这两个工具已存在，无需安装。[Ubuntu growpart 手册](https://manpages.ubuntu.com/manpages/resolute/man1/growpart.1.html)、[Ubuntu resize2fs 手册](https://manpages.ubuntu.com/manpages/tenacious/man8/resize2fs.8.html)

4. 启动两 Worker，重新只读检查各自 `findmnt -T /data/cs5488` 的源仍为 `192.168.20.130:/data/cs5488`，并检查实际可用空间。扩盘不意味着自动恢复任何旧后台任务。

以上保留旧容量调整建议及当时的停止原因，不构成新的扩容指令。当前没有本轮后台作业遗留；连续两天综合验收尚未完成。后续先依据最新需求修正验收矩阵和过程存储策略、重新计算容量，再决定是否需要扩容，不自动执行三窗口全量方案。
