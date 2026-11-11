# D：单核、多核与双 Worker 实验

三小时双 Worker 参与验收和六小时三种配置各三次测量已完成。24 小时试跑及 Python 全天对账尚未执行。

- [六小时 Python 对账](results/python_spark_6h_20261111/README.md)：完整事件字段、日汇总键与计数全部一致。
- [六小时实验报告](六小时实验结果_20261111.md)：配置、原始耗时、加速比、吞吐、正确性和稳定性。
- [运行与复核说明](运行与复核说明.md)：提交命令、预热、有效 run ID 和复核方法。
- [提交说明](提交说明.md)：原仓库适配、提交范围及验证限制。
- [证据包说明](证据包说明.md)：原始日志、完整交付材料和校验值。
- [原始实验计划](../D_并行与分布式实验计划.md)。

scripts/ 与 configs/ 为本次实测使用的脚本与集群配置；results/ 为精选的计时、环境、有效配置、结果指纹和故障摘要。A 的共用适配代码位于 ../a_data_pipeline/gharchive_a/spark_clean.py。

配置中保留实测私网地址与 Ubuntu 项目路径，属于实验拓扑参数，不是通用安装默认值。在其他电脑上复现前，需要按节点调整并重新记录实际配置。SSH 密钥、Windows 本机路径和控制台登录步骤不随 Git 提交。

## Git 提交范围与完整日志获取

Git 只提交代码、配置、报告和精选小型记录，包括 JSON 核对结果、空差异示例以及简短执行日志。完整 Spark 事件日志、节点日志、压缩包、原始输入、逐事件输出和 SQLite 数据库不进入 Git。

完整日志包由 D 实验负责人通过小组交付渠道另行提供；请按以下文件名索取。具有实验机访问权限的成员也可从下列 Master 位置复制。**目前尚未上传 GitHub 附件，也没有公开下载链接；Master 是实验内网存储，仓库读权限不等于实验机访问权限。**

| 附件文件名 | 获取位置 | 大小（字节） | SHA-256 |
|---|---|---:|---|
| experiment_evidence_20261111.tar.gz | 实验 Master：`/data/cs5488/experiment_evidence_20261111.tar.gz`；或向 D 实验负责人索取 | 10,640,921 | `72a2c248fd30055e9cad12bbdc4b8b1f10bd019faa03cef8ccb1163f1529c7b2` |
| python_spark_6h_reconciliation_20261111.tar.gz | 实验 Master：`/data/cs5488/python_spark_6h_reconciliation_20261111.tar.gz`；或向 D 实验负责人索取 | 11,528 | `3214121668e34fc71d75d148bf7b5a4b8389b2de1d250cea93a5bdb311f1adbd` |
| 六小时实验交付包_20261111.zip | D 实验负责人本地项目 `d_parallel_experiments/`，单独索取 | 11,380,091 | `ee352bb7126093dbddcfd30547ffc293fbdbdc7b57482be3e740393c0f1df573` |

第一包含六小时原始控制台、Spark 事件及节点日志；第二包是后来追加的 Python 对账证据；第三包是对账之前的完整六小时交付快照，不能代替第二包。获取后使用 `sha256sum <文件名>`（Ubuntu）或 `Get-FileHash -Algorithm SHA256 <文件路径>`（PowerShell）核验。若后续上传附件，应在这里补充真实下载链接，不将文件系统路径写成公开链接。
