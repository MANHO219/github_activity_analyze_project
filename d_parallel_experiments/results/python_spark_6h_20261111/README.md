# 六小时 Spark 与 Python 对账结果

2026-11-11：**对账通过。** Python 参照由 Master 使用仓库原有 Python 清洗逻辑、同一批 2024-01-15 UTC 0–5 时档案重新生成；不是组员全天 Parquet 的切片，也不是新一轮 Spark 实验。

| 检查 | 结果 |
|---|---|
| 输入六文件大小与 SHA-256 | 全部匹配发布清单 |
| 处理代码 | Master 部署文件哈希与本地代码一致 |
| Python / Spark 事件数 | 各 1,177,282 |
| 双方事件 ID 唯一性 | 通过 |
| 双向缺失/多出事件 ID | 0 / 0 |
| 完整事件行双向差异 | 0 / 0 |
| 13 个事件字段 | 每个字段不一致数均为 0 |
| Python 重算 / Spark 重算 / Spark 导出日汇总分组 | 各 347,774 |
| 日汇总键双向差异 | 0 / 0 |
| 日汇总键及计数双向差异 | 0 / 0 |
| 双方日汇总与各自事件守恒 | 通过 |
| 双方 CSV / Parquet 完整内容、类型 | 通过 |
| A 原有对账程序 | 19 项检查通过 |
| 新增 Parquet 字段及日汇总核对 | 18 项检查通过 |

13 个字段为 event_id、event_type、event_time、repo_id、repo_name、actor_id、actor_login、event_date、source_file、source_line、source_hour、time_outside_file_hour、optional_field_issues；没有忽略来源字段、空值、时间或异常标记。

## 直接对账范围与九次结果的关系

直接核对 `d4stable_6h_r1` 的完整 CSV、Parquet 和日汇总。当前 Spark 输出重新计算的完整有序事件 CSV、日汇总、候选表和名称历史 SHA-256 与六小时原始证据一致。本地保存的历史指纹也独立核验匹配。

此前九次 L1/L4/D4 正式测量的完整输出指纹一致，因此本次直接对账结合原九次指纹证据，可支持三种模式输出与 Python 一致。**没有将其表述为重新对九次输出逐次执行 Python 明细对账。**

## 执行与保存

Master 上 `/data/cs5488/runs/python_6h_reconcile_20261111_01/` 保存完整 Python 输出、SQLite 比较数据库、差异示例和状态。脚本与控制台日志在 `/data/cs5488/reconciliation_tools_20261111/`。没有启动 Worker 或 Spark 服务，没有修改旧实验输出。

Python 清洗记录为 119.379 秒。这是本次单次生成参照的耗时，不纳入原九次 Spark 性能表，也不作为经过三次测量的 Python 性能基线。

本目录精选证据：

- [执行状态](reconciliation_status.json)、[输入哈希](input_hash_verification.json)、[处理代码哈希](code_sha256.json)。
- [原有对账结果](original_comparison/comparison_summary.json)、[Parquet 与 CSV 核对](original_comparison/parquet_validation.json)。
- [完整字段与日汇总结果](field_comparison/comparison_summary.json)、[旧 Spark 指纹复验](spark_fingerprint_reverification.json)。
- execution/ 保存实际运行脚本、代码哈希清单和控制台日志；两个 comparison 子目录保存双向差异示例，零差异文件为空数据集。

证据归档 `python_spark_6h_reconciliation_20261111.tar.gz` 已从 Master 下载到 Windows，两端 SHA-256 相同：

`3214121668e34fc71d75d148bf7b5a4b8389b2de1d250cea93a5bdb311f1adbd`

归档包含小型报告、差异示例及执行记录，不含大型逐事件输出和 SQLite 数据库。24 小时 Spark 试跑与组员全天参照对账仍未执行。
