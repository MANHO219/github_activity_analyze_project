# A 启动脚本验证结果

验证日期：2026-10-12。环境 `cs5488-data` 已创建，Python 3.11.17、PyArrow 25.0.0、PySpark 3.5.7、Java 17。

**推荐交接目录：** [本次样本的 HANDOFF.md](../runs/20240115_1hour_handoff/HANDOFF.md)。原始文件与各次试跑记录均保留；此目录包含统一 UTC Parquet 类型后的完整结果。

## 一个真实小时档案的结果

| 项目 | 实测结果 |
|---|---:|
| 输入文件 | `2024-01-15-0.json.gz` |
| 原始压缩大小 | 73,709,206 bytes，约 70.3 MiB |
| 非空原始事件 | 197,313 |
| 清洗后事件 | 197,313 |
| 清洗后唯一仓库 | 69,768 |
| 事件类型 | 15 |
| 仓库 × 日期 × 类型分组 | 84,692 |
| JSON 解析失败、关键字段无效 | 均为 0 |
| 内容一致的重复记录、冲突 ID | 均为 0 |
| 可选字段问题、时间不在文件标注小时内 | 均为 0 |
| Python / Spark 事件 ID、全部字段、日分组计数 | 一致，差异均为 0 |
| 两条路径的 Parquet / CSV 值 | 一致 |
| 两条路径的 Parquet 时间字段 | 均为 `timestamp[us, tz=UTC]` |

输入 SHA-256：`019cd01bb263573ae1d633fd965cdc9869fa5eefc31bd409376d10052ed7acd8`。

各阶段状态为 `completed`；计数核对和比较检查全部通过。依据文件：

- [输入清单](../runs/20240115_1hour_handoff/python/input_manifest.json)
- [质量摘要](../runs/20240115_1hour_handoff/python/quality_summary.json)
- [Python / Spark 比较结果](../runs/20240115_1hour_handoff/comparison/comparison_summary.json)
- [Parquet 类型与值核对](../runs/20240115_1hour_handoff/comparison/parquet_validation.json)
- [实际运行日志](real_sample_handoff_console.log)

这个档案的异常计数为 0，只说明该文件通过本轮规则；不代表其他小时没有问题，也不证明 GH Archive 捕获了全部 GitHub 活动。当前真实数据覆盖 1 小时，3 小时和 24 小时的命令已提供，尚未对这些范围跑真实数据。

## 异常场景验证

**8 项测试通过**，包括真实本地 Spark 运行。日志见 [fixture_tests_parquet.log](fixture_tests_parquet.log)。

已验证损坏压缩文件不会标记成功、缓存损坏会保留并报错、请求缺少小时必须明确允许、输出不会覆盖已有运行、空档案仍保留可读 schema，以及跨小时重复、完整 payload 冲突、可选字段缺失、无效 UTF-8、未知事件类型、UTC 日期、时间偏离和 Parquet 读回一致性。

构造样本有 8 条去重前有效记录：2 条内容一致的重复记录被移除，1 个冲突 ID 的 2 条记录留待复核，最终得到 4 条事件；两条实现得到同样结果。Python 与 Spark 共用字段校验规则，因此这里的已知预期结果测试补充了实现之间的比较。

这是数据管道的正确性验证。运行包含 SQLite/Parquet 导出和审计文件写入，耗时不应直接用于并行加速结论。
