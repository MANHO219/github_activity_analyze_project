# A 样本运行交接

清洗后事件：197313；仓库：69768。

重复记录移除：0；冲突 ID：0；冲突记录暂排除：0。

本次覆盖：2024-01-15-0.json.gz。

交接优先读取 `python/quality_summary.json`、`python/events_preview.csv`、`python/repo_candidates.csv` 和 `python/events_clean.parquet/`（CSV-only 时用 CSV.gz）。

小时覆盖清单在 `python/input_manifest.json`；日计数仅覆盖已读取档案，不能补推未读取时段的活动。AI 分类与生命周期判断由后续阶段完成。

清洗前有效记录在 `python/working.sqlite3`，异常、重复和冲突记录另有文件；原始 payload 保存在原始小时档案。
