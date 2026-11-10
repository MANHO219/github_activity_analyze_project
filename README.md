# CS5488 小组项目：AI 相关 GitHub 仓库的生命周期

从 GH Archive 的公开事件中整理仓库活动，补仓库元数据与 AI 标签，再研究仓库生命周期。**当前已有一小时试跑结果、2024-01-15 全天 Python 活动汇总、B 的两批仓库标签试跑，以及 C 的第一版分析 Notebook。**

## 后续设想：2024 与 2026 年新建仓库的前 90 天

拟在 2024 年 4 月和 2026 年 4 月各选一批新建公开仓库，用相同的抽样方法、AI 标签口径和活动指标做对比。以每个仓库的 UTC 创建日为第 1 天，分别统计第 1–30、31–60、61–90 天的事件数和活跃天数，比较活动是集中在创建初期，还是在后续阶段持续发生。Agent 工具普及是研究背景，判断仓库实际使用了哪些工具需要额外证据。

**当前先验收 2024-01-15 的一天链路，并完成 D 的第一版并行实验。** A 提供固定输入和 Python 参照，B 完成标签交接，C 复跑 Notebook，D 按现有计划做三种配置的对比和全天 Spark 对账。

- **B 先收尾现有 PR 和试点标签。** 正式范围确定后，从两年的候选仓库中抽取未参与调规则的样本，用同一规则版本和人工复核口径做验证，分别记录元数据与标签覆盖情况。按 `repo_id` 向 C 交接创建时间、最终标签和标签来源。
- **C 先修订现有 Notebook，并用小样本验证同一套分析能切换年份。** 用已有的一天活动表和标签验证接入，再用跨日小样本检查 30 天分段及缺档处理。根据日期覆盖清单区分无公开活动与档案缺失。

一天链路和 D 第一版实验验收后，A 再确认两年各选 4 月第一周还是整月、样本量和数据交付安排。若选整月，源数据要覆盖到两年的 7 月 28 日 UTC 全天。长窗口的处理方式结合实际耗时和存储确定，Spark 批处理和 BigQuery 可作为候选，OpenMP 可作为附加实验评估。

## 第一次打开，按这个顺序看

| 想了解什么 | 入口 |
|---|---|
| 选题、分工、课程交付和研究边界 | [小组同步说明](CS5488_AI_Repository_Lifecycle_Project.md) |
| 数据从哪里来、哪个脚本处理、每个文件在哪 | [数据处理全解 HTML](a_data_pipeline/数据处理全解.html) |
| B 现在如何开始 | [B 接手指南](a_data_pipeline/B_接手指南.md) |
| B 的实现、跑法与试跑结果 | [B 阶段 README](b_repo_metadata/README.md)、[试跑结果](b_repo_metadata/RESULTS.md) |
| 自动标签 / 人工复核 / 分析用标签的区别 | [标签交接说明](b_repo_metadata/LABELS.md) |
| A 的实现和运行命令 | [数据管道 README](a_data_pipeline/README.md) |
| D 的单核、多核与虚拟机分布式实验，以及 A/D 分工边界 | [D 的实验计划](D_并行与分布式实验计划.md) |
| 实际样本与核对结果 | [样本交接记录](a_data_pipeline/runs/20240115_1hour_handoff/HANDOFF.md)、[验证摘要](a_data_pipeline/verification/RESULTS.md) |

HTML 请在下载或 clone 后，用本地浏览器打开；在 GitHub 文件页面也可以先下载。Markdown 说明可直接在 GitHub 阅读。仓库里的 HTML 已内嵌样本和源码，阅读主体内容不需要启动服务。

## B 可以立即使用的一小时试跑输入

打开[仓库候选清单](a_data_pipeline/runs/20240115_1hour_handoff/python/repo_candidates.csv)：69,768 个唯一仓库，每行一个 `repo_id`。第一轮先在自己电脑获取一个仓库，再固定一个小名单试跑；50 个是建议规模，AI 规则与最终字段由 A、B 确认。

B 的第一轮已完成并留在 [b_repo_metadata/](b_repo_metadata/)：50 个仓库的元数据、AI 标签（规则 v0.3）、33 条人工复核与按 `repo_id` 接回事件表的核对结果都可直接查看或重跑。规则从 v0.1 到 v0.3 的逐条变化都有记录（[v0.2→v0.3](b_repo_metadata/runs/pilot_01/label_changes.csv)、[v0.1→v0.2](b_repo_metadata/runs/pilot_01/label_changes_v0.1_to_v0.2.csv)），标签交接方式见 [LABELS.md](b_repo_metadata/LABELS.md)。

其他现成输入：[名称历史](a_data_pipeline/runs/20240115_1hour_handoff/python/repo_name_history.csv)、[事件预览](a_data_pipeline/runs/20240115_1hour_handoff/python/events_preview.csv)、[完整事件 Parquet](a_data_pipeline/runs/20240115_1hour_handoff/python/events_clean.parquet/)、[活动计数](a_data_pipeline/runs/20240115_1hour_handoff/python/repo_daily_counts.csv)。

## 目录怎么分

```text
仓库根目录/                         ← 对应原来的 group_project/
├── README.md                       ← 小组入口
├── CS5488_AI_Repository_Lifecycle_Project.md
├── A_启动任务_最小数据样本.md
├── D_并行与分布式实验计划.md         ← D 待实施的实验与交付要求
├── Project.pdf                     ← 课程项目要求
├── a_data_pipeline/
│   ├── B_接手指南.md
│   ├── 数据处理全解.html
│   ├── config/                     ← 输入范围与参数
│   ├── scripts/                    ← 命令入口
│   ├── gharchive_a/                ← 处理实现
│   ├── docs/                      ← 文档模板与证据快照
│   ├── verification/              ← 验证记录
│   ├── tests/                     ← 已有测试代码
│   ├── sample_data/                ← 一份精选的 24 小时仓库活动汇总表
│   ├── data/                      ← 原始下载，本地保留，Git 忽略
│   └── runs/                      ← 只提交一份精选交接结果
└── b_repo_metadata/                ← B：元数据、AI 标签、复核与接回事件表
    ├── README.md                   ← 跑法与字段说明
    ├── LABELS.md                   ← 自动、人工与分析用标签的交接口径
    ├── RESULTS.md                  ← pilot_01 结果与验收清单
    ├── config/                     ← 种子、分层规模、API 参数
    ├── rules/                      ← 当前 ai_rules_v0.2，保留 v0.1 供对比
    ├── bmeta/                      ← 抓取、规则、复核、接回的实现
    ├── scripts/                    ← 每个步骤一个命令入口
    ├── reviews/                    ← 人工判断与理由
    ├── tests/                      ← 51 项离线验证
    └── runs/                       ← debug_api_sample 与 pilot_01 结果
```

## 一小时试跑：快速熟悉管道

从 clone 后的仓库根目录运行：

```bash
cd a_data_pipeline
conda env create --file environment.yml
conda activate cs5488-data
python scripts/run_sample.py --with-spark
```

这条命令使用原来的**一小时默认样本**，下载并处理一个小时的数据，同时运行 Spark，适合熟悉目录和验证管道。需要联网和本机存储；此命令不会处理 24 小时。

## 24 小时扩展数据：现在能用什么，如何获取完整结果

2024-01-15 全天的 Python 处理已完成，全天 Spark 复算尚未完成。

- **可直接分析：** Git 中的 [`repo_daily_counts.csv`](a_data_pipeline/sample_data/20240115_24h/repo_daily_counts.csv) 按仓库、UTC 日期和事件类型汇总，共 1,340,785 行，合计 5,528,300 条事件。它是汇总表，不含逐条事件详情。
- **生成完整事件数据：** 原始 `.json.gz` 和全天逐条事件表没有放进 Git。环境已创建并激活后，在仓库根目录运行：

  ```bash
  cd a_data_pipeline
  conda activate cs5488-data
  python scripts/run_sample.py --date 2024-01-15 --hours 0-23 --run-dir runs/20240115_python
  ```

  这会下载并清洗这一天的 24 个小时档案，结果保存在本机。详细步骤见 [A 数据管道 README](a_data_pipeline/README.md)。
- **扩到一个月：** 当前脚本只有单日入口，没有日期范围批处理。月级扩展前需要实现批量调度、失败续跑、跨日 `event_id` 去重、按日分区和汇总校验；不能要求组员手动重复几十条命令或直接拼接每日结果。

全天数据的数量、质量检查和限制见[全天结果与交接](a_data_pipeline/verification/20240115_1day/README.md)。
