# 验证记录

## HTML 数据说明

[数据处理全解](../数据处理全解.html) 依据已完成样本与当前源码生成；原始档案 SHA-256 已核对，包内源码哈希与样本记录一致。初版页面的浏览检查包括 13 个字段、3 条真实事件切换、58 项文件分类、源码定位、68 个本地链接，以及 390/320 像素布局。初版记录在 [data_guide_ui.json](data_guide_ui.json)，截图为本目录的 `data_guide_*.png`。

2026-10-13 增加目录树、原始结构图、汇总图，以及两张可缩放和点击的文件关系图。更新版在当前 664 × 841 浏览器视图中检查：页面没有横向溢出，目录树覆盖 58 项数据/运行产物和 29 项相关代码/配置/说明；文件搜索、分片展开、就地定位、图谱节点定位及 125% 缩放均可使用，浏览器没有脚本错误。生成结果的 47 个 DOM ID 无重复，34 个文件定位链接均指向真实存在的路径。原始数据与包内处理代码保持本次样本的哈希。

更新版浏览记录在 [data_guide_graph_ui.json](data_guide_graph_ui.json)，截图为 `data_guide_file_graph.jpg`、`data_guide_cleaning_graph.jpg`、`data_guide_directory_tree.jpg` 和 `data_guide_aggregation.jpg`。更新版未重新检查 390/320 像素视图，初版窄屏结果不能作为新图谱的视觉验证。

这部分只验证说明页面；下方记录验证数据处理脚本。

### 2026-11-02：B 的第一轮接手入口

新增 [B 接手指南](../B_接手指南.md)，HTML 第 08 节包含可独立阅读的启动卡。实际输入有 69,768 个唯一仓库 ID、名称均非空，其中 60 个 ID 出现多个观察名称。生成后的 HTML 有 48 个唯一 DOM ID、37 个有效文件定位目标；目录树含 58 项数据/运行产物和 30 项代码/配置/说明。

已查看启动卡排版，检查输入节点定位、交付字段展开及浏览器错误日志；HTML 和指南的本地 HTTP 请求均返回 200。记录见 [b_handoff_20261102.json](b_handoff_20261102.json)，截图为 `b_handoff_20261102.jpg`。B 本机的联网、获取代码、AI 规则和实际标签待 B 完成；这次没有组织真实组员试读。

## 数据管道

异常场景测试命令：`RUN_SPARK_TESTS=1 python -m unittest discover -s tests -v`。

真实样本为 `2024-01-15-0.json.gz`，交接版执行命令：`python scripts/run_sample.py --with-spark --run-dir runs/20240115_1hour_handoff`。

交接版运行输出保存在 `real_sample_handoff_console.log`；测试日志在 `fixture_tests_parquet.log`。早期日志和运行目录也保留。各阶段参数、环境、质量计数与比较结果保存在对应运行目录。结果汇总见 [RESULTS.md](RESULTS.md)。
