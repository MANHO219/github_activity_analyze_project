# CS5488 选题同步：AI 相关 GitHub 仓库的生命周期


## 选题是什么？

研究 **AI 相关 GitHub 仓库创建后，头一年会出现哪些公开活动轨迹**：有的可能开头很热闹，之后安静下来；有的可能逐渐形成持续的开发和协作。我们会用 GH Archive 的公开事件画出仓库活动时间线，再归纳常见模式。

建议英文题目：**From Hype to Sustainability: Lifecycle Patterns of AI-Related GitHub Repositories**

当前判断：和 CS5488 的并行计算、数据处理要求很契合；前序讨论给出的契合度估计是 8.5–9/10。这个方向有相邻研究，不能说“从没人做过”；项目重点应放在 AI 仓库的筛选规则和创建后生命周期上。最大难点是定义“AI 相关”，以及确认事件档案是否完整。

## 查到哪些类似项目？

- **CS5488：** [Parallel Color Quantization](https://github.com/YongzeYang/Parallel-Color-Quantization) 用 Hadoop、Spark 和并行 k-means 处理图像像素。它和我们都展示并行处理，但研究问题不同。此前看的课程选题还包括房价、NBA、IMDb、汇率、航班、气候和 Twitter 等。目前公开检索没找到 CS5488 的 GH Archive + AI 仓库生命周期同题项目；这不排除私人或未公开的项目。
- **GH Archive 工程项目：** [Git-Influencer](https://github.com/chuqiaoshen/Git-Influencer) 用 GH Archive、HDFS、Spark、Airflow 和 GraphX 找 GitHub 网络中的影响者；[Zoomcamp 数据管道](https://github.com/linhpham-ldp/github-data-pipeline) 把 GH Archive 接到 BigQuery、dbt 和 dashboard。它们说明 GH Archive 管道本身并不新；我们的重点要放在仓库生命周期分析。
- **学术研究：** [AI 论文仓库维护研究](https://arxiv.org/abs/1903.01555) 关注 AI 论文配套代码及其维护问题；[学术 AI 仓库人气研究](https://doi.org/10.1007/s10664-020-09916-6) 比较仓库受欢迎程度和工程特征；[开源仓库维护停止研究](https://arxiv.org/abs/2507.21678) 研究一般仓库的维护停止。它们都与本题相邻，但研究对象或重点不同。

## 数据拿得到吗？有一条真实 API 样本

**事件数据：** [GH Archive](https://www.gharchive.org/) 按小时提供压缩 JSON，记录事件类型、时间、仓库和 actor；不同事件的 `payload` 结构会不同。历史批量事件用 GH Archive 更合适：GitHub REST Events API 只提供近 30 天、最多 300 条时间线事件。

**仓库元数据：** Repository API 可以补仓库的创建时间、描述、topic、语言和当前人气指标。我实际请求了公开仓库 [huggingface/transformers 的 API](https://api.github.com/repos/huggingface/transformers)，取回的部分字段如下（2026-09-28 查询）：

```json
{
  "id": 155220641,
  "full_name": "huggingface/transformers",
  "created_at": "2018-10-29T13:56:00Z",
  "pushed_at": "2026-09-27T22:59:44Z",
  "language": "Python",
  "topics": ["deep-learning", "llm", "machine-learning", "transformer"],
  "stargazers_count": 166733,
  "forks_count": 34696,
  "archived": false
}
```

这说明公开仓库的 `GET /repos/{owner}/{repo}` 确实能返回我们想用的字段；读取公开仓库无需认证，匿名 REST API 限额是每小时 60 次，详见 [GitHub Repository API 文档](https://docs.github.com/en/rest/repos/repos) 和[限额说明](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)。示例是当前快照，不能当作历史数据。这个接口需要先知道仓库名，也不会自动列出所有 AI 仓库。

可复现请求：

```bash
curl -sS -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/huggingface/transformers
```

**访问限制：** 在线请求成功返回了真实 JSON；但从当前工作区的 Python 环境直连时遇到 DNS 错误。因此 API 有真实公开数据已确认，组员的运行环境是否能直接联网还要再试。也还没有验证 AI 仓库发现和大批量 API 抓取。

### 试跑与筛选建议

1. 先处理 1 天，再扩到 1 周，检查字段、缺档、事件量、文件大小和 Spark 能否读取。
2. 前序讨论暂建议试跑 **2022-01 至 2025-04**，理论上约有 29,184 个小时档案时段（假设每小时都有文件）。之前提到 2025-05 之后可能有覆盖异常，但尚未核实；先做覆盖检查再定时间窗。
3. 用 topics、description 和固定关键词筛 AI 仓库，例如 `machine-learning`、`deep-learning`、`llm`、`generative-ai`、`transformers`、`rag`；随机抽样人工复核分类。当前 metadata 可能与仓库过去的状态不同。
4. 生命周期分析只纳入有完整 12 个月观察期的仓库；没有观察到公开事件表示“数据中没看到活动”，不等于仓库已废弃。

## 为什么符合大数据课程？

- **Volume：** 多年 × 每小时的事件数据；用实测文件数、事件数和大小说明规模。
- **Variety：** Push、PR、Issue、Fork、Watch、Release 等事件结构不同，还有描述、topic、语言等元数据。
- **Velocity：** GitHub 活动持续发生，GH Archive 按小时归档；项目可以批处理，不必实现实时流。
- **Veracity：** 检查缺档、异常事件量、schema 变化、机器人活动和 AI 标签误差。
- **Value：** 观察 AI 开源项目是否持续维护，以及哪些早期活动与后续活跃相关。

**并行计算怎么体现：** 一天有约 24 个独立小时文件。Spark 可以让多个 worker 同时处理不同文件，各自筛选和计数，再合并结果；这里是多个文件之间并行，不是把单个 `.json.gz` 文件切开。实际是否提速，要用同一批数据比较 `local[1]`、`local[2]`、`local[4]` 的运行时间；这些配置是在一台机器上使用不同数量的 worker 线程。

## A、B 前期工作安排（先做出可交接的小样本）

**A 的第一轮执行清单：** [A 的启动任务：跑通最小事件数据样本](A_启动任务_最小数据样本.md)，从一个小时文件开始，按读取、清洗、核对、导出的顺序推进。

**A 脚本已实现并验证一个真实小时样本：** [运行与交接说明](a_data_pipeline/README.md)。样本有 197,313 条事件，Python 与 Spark 结果一致；原始数据、质量统计及异常/重复分类文件均保留。

**组员完整了解数据处理：** [数据处理全解（HTML）](a_data_pipeline/数据处理全解.html)，按原始输入、脚本操作、字段变化、过程文件、分析用表和后续实验串联；[简短 Markdown 介绍](a_data_pipeline/数据说明_给组员.md) 也保留。

**B 的直接入口：** [B 接手指南](a_data_pipeline/B_接手指南.md)。唯一仓库清单已由 A 生成，B 从现成输入开始，先验证一个仓库，再固定一批小名单完成元数据、标签与复核流程。

前期不等全量数据处理完成才开工。A、B 先用一个小样本把数据格式和筛选规则定下来；C、D 拿到第一版交付物后即可并行做分析原型和 Spark 实验。以下按阶段安排，具体日期由组内按截止时间倒排。

### 阶段 1：共同定规则（半天左右）

- **A**：选一个 GH Archive 小时文件作为试跑输入，记录日期、下载地址、文件大小和读取方式。
- **B**：提出 AI 相关仓库的纳入规则和关键词初稿；说明哪些类型算、哪些不算。
- **A + B**：共同定一个小试跑范围（例如 1 天）和统一仓库标识（优先使用 `repo_id`，同时保留 `owner/repo` 名称）。

**交付物：** 一页数据字段约定，明确事件表和仓库表的主键、时间字段及筛选规则版本。

### 阶段 2：小样本先交接（约 1–2 天）

**A：事件数据读取与初步清洗**

1. 下载并读取选定日期的 GH Archive `.json.gz` 文件，统计文件是否可读、事件总数和事件类型数量。
2. 提取共同字段：事件时间、事件类型、仓库名称/ID、actor；不急着展开所有事件特有的 `payload`。
3. 处理明显无效记录，统一时间格式和仓库标识；保留原始文件，不覆盖原始数据。
4. 导出一份小样本事件表（CSV 或 Parquet）和字段说明，让 C 能开始按仓库、日期计数。

**A 交付：** 原始文件清单、清洗脚本/Notebook、事件表样例、字段说明、文件与事件计数、已知限制。

**B：仓库候选清单与标签抽查**

1. 接收 A 已生成的 `repo_candidates.csv` 唯一仓库清单，固定本轮试跑名单并记录选取方法。
2. 对候选仓库使用预先约定的 topic、描述和关键词规则标记 AI 相关；用 GitHub Repository API 补充创建时间、描述、topic、语言等可用字段。
3. 人工抽查一批“命中”和“未命中”仓库，记录误判例子，调整规则并保存版本。
4. 给仓库清单增加明确标签（如 `included` / `excluded` / `uncertain`）和筛选理由；不要只留下最终入选名单。

**B 交付：** 仓库候选表、API 获取脚本/请求记录、AI 标签规则、抽查记录与未解决问题。API 的匿名限额和运行环境联网情况先小批量验证，不在规则未稳定时直接批量抓取。

### 阶段 3：交接后扩展正式数据（约 2–4 天，可并行）

- **A** 扩展 GH Archive 时间范围，做小时文件覆盖检查、解析统计和稳定的批处理流程；与 B 固定事件表字段后，按日期或仓库聚合并输出正式数据。
- **B** 在 A 提供的完整候选仓库上应用冻结的筛选规则，补齐必要元数据并复核抽样；为生命周期分析筛出创建时间和观察期足够的仓库。
- **A + B** 对正式交付做一次核对：事件记录能否匹配仓库清单、未匹配比例、缺失字段、重复记录和标签抽查结果。

**正式交接给 C、D：** 一份稳定字段的事件数据、一份带标签及筛选理由的仓库表、字段/规则说明、数据质量摘要和可复跑脚本。C 可据此生成仓库月度活动表；D 可据此测试同一任务在不同 Spark 并行度下的运行时间。

### 分工边界与减负办法

- A 负责“事件档案怎样可靠读入并变成可分析记录”；B 负责“哪些仓库属于研究对象，以及这个判断有多可靠”。
- B 不需要一开始就抓全 GitHub 的 AI 仓库；先从 GH Archive 样本出现的仓库中筛选，避免 API 限额和候选规模失控。
- A、B 的交付字段在试跑后尽早冻结。若完整数据量超出时间或算力预算，先缩短日期范围或采用分层抽样，保证 C、D 有稳定数据可继续。
- 第一版交接是原型输入，不代表最终结论；等正式时间范围和仓库名单确定后，C、D 应重跑分析并在报告中说明筛选和数据覆盖限制。

## 四人分工与课程交付

估计总工作量 **60–100 人时**，即每人约 **15–25 小时**。建议每人都有技术、分析和写作任务：

- **A 数据处理：** 下载、覆盖检查、Spark 解析和清洗。
- **B 仓库筛选：** AI 定义、metadata 获取、人工抽查标签。
- **C 生命周期分析：** 仓库月度活动表、轨迹图和聚类。
- **D 并行实验与整合：** Spark 运行时间比较、图表及展示整合。

小组共同完成三个问题：AI 仓库活动趋势如何？创建后头一年有哪些轨迹？早期活动与第 12 个月仍活跃是否相关？非 AI 仓库可做匹配对照，时间紧时先不加。

根据 [课程 Project.pdf](Project.pdf)：3–4 人组；报告至少 10 页；报告占 70%、展示占 30%；展示 5 分钟加 1 分钟 Q&A，每位成员都要发言；提交报告、幻灯片、数据集/链接等。实际日期以 Canvas 为准。

## 初步工作流与技术栈

```text
确定 AI 仓库清单 + GH Archive 小时事件
        ↓
Python 下载和覆盖检查
        ↓
PySpark 解析、筛选、清洗、聚合
        ↓
仓库 × 年龄月份活动表（Parquet）
        ↓
生命周期分析、图表、并行性能比较
```

- **获取：** GH Archive + GitHub Repository API
- **存储/处理：** JSON.gz → HDFS（课程环境可用时）→ PySpark → Parquet
- **分析/作图：** PySpark、pandas、scikit-learn（可选 K-means）、Python 或 R
- **并行实验：** 相同任务比较 Spark 不同并行度，记录环境和实测运行时间，不预设加速结果。

## 组会时需要定的事

1. AI 仓库范围和关键词怎么定？
2. 试跑后选哪段数据，是否排除覆盖异常时段？
3. “持续活跃”用什么指标定义？
4. 要不要增加非 AI 对照组？
