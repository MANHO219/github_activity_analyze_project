# 任务四：两小时恢复、互斥与限定清理验收通过

2026-11-13。按用户要求，使用一条必要的真实 L4 恢复链路验证，不重复任务二/三的性能或完整对账。来源 UTC `[2024-01-16T00:00Z,02:00Z)`，两档共 **156,880,050 字节**；同一个 2h 批次用于验证同一清单部分删除。最终 **433,588 条事件**，完整覆盖两个来源小时。小型证据见 [JSON](task4_validation_20261113.json)。

| 验收项 | 真实结果 |
|---|---|
| NFS raw/output 互斥 | Master 持两把锁时，两个 Worker 对各锁均获取失败；释放后 Worker 1 可获取两锁 |
| Spark 中断、失败保留 | 实际 Spark 应用启动后，仅向本次子进程发 SIGINT；attempt-0001 及日志保留 |
| 输入复用 | 首次两档均 downloaded_verified；重跑均 cached_verified，禁止网络调用的断言未触发 |
| 部分清理恢复 | 首档真实 unlink 后、deleted 状态落盘前中断；磁盘日志为 deleting，第二档仍在。重跑接纳已写意图的缺失首档，再校验并删除第二档 |
| 最终合并恢复 | SQLite 已提交 10,000 条有效出现后中断；部分 attempt-0001 保留，另建 attempt-0002 完成，不伪装为原地续写 SQLite |
| 已验收跳过 | 重算批次与最终产物大小/哈希后跳过；禁止 Spark、下载及合并的断言未触发，两个验收标记哈希不变 |
| 损坏拒绝 | 只在独立副本修改已验收质量文件，退出 1 并报告 Accepted artifacts changed；原结果复验通过 |
| 最终交付 | 事件 13 字段和 Parquet 类型符合契约，事件 ID 唯一，日统计和候选表从全量事件重算一致，CSV/Parquet 一致；覆盖、质量摘要和全部有效出现索引保留 |

故障脚本在真实阶段边界暂停，再由父进程发送信号；下载、Spark、unlink、SQLite 写入均实际发生，没有替代输出。三个受控中断和损坏副本的退出 1 是预期负向结果，恢复运行与全跳过运行退出 0。脚本和完整日志保存在本轮 bootstrap/evidence，路径、命令和哈希在 JSON 中。

## 必要修复

最初锁预检失败：Master 使用本地 `flock` 持锁，Worker 1 仍可通过 NFS 获取同一文件的锁。此时尚未启动实际数据流水线或删除档案。NFS 客户端对 flock 的实现与服务端本地 flock 所在锁域不同，说明见 [Linux flock 手册](https://man7.org/linux/man-pages/man2/flock.2.html)。

`batch_support.exclusive_lock()` 的 POSIX 分支改用统一的 `fcntl.lockf` 记录锁；同进程重入在打开第二个描述符前拒绝，避免关闭描述符释放外层记录锁。只有 EACCES/EAGAIN 解释为占用，其他锁错误原样失败。新增进程级重入回归；本地专项通过，Linux 两项锁相关测试通过（0.337 秒），随后两 Worker 真实 NFS 验收通过。Windows 仍用 msvcrt。未改清洗、去重、冲突或合并规则。

## 目录、身份与清理边界

- 执行 release：`/data/cs5488/releases/rolling_v1_20261113_task4_lockfix01/`，新目录，52 个源文件逐一核验。
- 运行代码 SHA-256：`68d9b4051daf6343f78d934e1687f6586438e0bef16d0f28ad48c74419fe1217`；规则 `a-events-v1`。执行源包 SHA-256：`1d560a2c6bdf8b83fb913897517005cbcdb279849a26b9476a42c31809ab46dc`。
- 输出：`/data/cs5488/runs/rolling_v1_20261113_task4/`，最终位于 `merge/attempt-0002/result/`；run ID `9138330f26894da88a9cbe7c3e2f0cc1`。
- 证据及损坏副本：`/data/cs5488/monthly_validation/rolling_v1_20261113_task4/`。
- 唯一真实删除目录：`/data/cs5488/monthly_validation/rolling_v1_20261112/raw_cleanup/`，本轮确认不存在后新建并绑定 run ID；仅删除 **2024-01-16-0.json.gz、2024-01-16-1.json.gz**。逐文件核实下载归属、uid、路径、大小与 SHA-256；输入哈希与历史清单相同，详情在 JSON。

清单外 `unlisted_sentinel.json.gz`、所有 Parquet、索引、SQLite、失败尝试、部分合并及旧证据保留；原共享七档 SHA-256 前后一致。未启停集群服务，未改 VM、密钥、SSH 或代理配置。Worker 1 使用现有 Python 3.11.18 / PySpark 3.5.7 / PyArrow 26.0.1 / Java 17，local[4]、driver 4g；有效配置与资源记录在 JSON。

已有阶段计时保留：首次下载校验 26.298s；重跑缓存校验 2.203s、原始检查 24.920s、Spark 清洗导出 45.751s、批次验收 28.841s；成功全局去重 7.072s、最终汇总导出 10.546s。清理中断 0.288s，首次清理恢复 0.116s，后续复验分别 0.018s/0.016s。父计时、失败尝试、缓存和跳过独立保存，不重复相加。1s 采样下成功批次工作目录峰值 587,215,291 字节；短于采样间隔的失败合并峰值可能漏采。收尾共享盘余约 15.1 GiB，包括额外保留的损坏副本与最终复核库；不是两天容量模型。

本样本实际重复/冲突均为 0；跨批规则沿用任务二已通过的已知答案测试和七小时多批真实验证，本轮未重复。最终合并仍为 Python/SQLite。本次两小时恢复验收不等于连续两天综合验收，也无月级结论；连续两天与任务五整体汇总尚未执行。本轮没有提交、推送或 PR，所有现场保留，等待后续指令。
