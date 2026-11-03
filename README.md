# CS5488 小组项目：AI 相关 GitHub 仓库的生命周期

从 GH Archive 的公开事件中整理仓库活动，补仓库元数据与 AI 标签，再研究仓库的生命周期。**当前完成一个真实小时的数据管道与正确性验证，以及 B 的 50 仓库元数据/标签试跑（pilot_01）；正式观察期与生命周期结论待完成。**

2024-01-15 的全天 Python 数据处理已完成；全天 Spark 复算暂未完成。样本数量、交接包和限制见 [全天结果与交接](a_data_pipeline/verification/20240115_1day/README.md)。

## 第一次打开，按这个顺序看

| 想了解什么 | 入口 |
|---|---|
| 选题、分工、课程交付和研究边界 | [小组同步说明](CS5488_AI_Repository_Lifecycle_Project.md) |
| 数据从哪里来、哪个脚本处理、每个文件在哪 | [数据处理全解 HTML](a_data_pipeline/数据处理全解.html) |
| B 现在如何开始 | [B 接手指南](a_data_pipeline/B_接手指南.md) |
| B 的实现、跑法与试跑结果 | [B 阶段 README](b_repo_metadata/README.md)、[试跑结果](b_repo_metadata/RESULTS.md) |
| A 的实现和运行命令 | [数据管道 README](a_data_pipeline/README.md) |
| 实际样本与核对结果 | [样本交接记录](a_data_pipeline/runs/20240115_1hour_handoff/HANDOFF.md)、[验证摘要](a_data_pipeline/verification/RESULTS.md) |

HTML 请在下载或 clone 后，用本地浏览器打开；在 GitHub 文件页面也可以先下载。Markdown 说明可直接在 GitHub 阅读。仓库里的 HTML 已内嵌样本和源码，阅读主体内容不需要启动服务。

## B 可以立即使用的输入

打开[仓库候选清单](a_data_pipeline/runs/20240115_1hour_handoff/python/repo_candidates.csv)：69,768 个唯一仓库，每行一个 `repo_id`。第一轮先在自己电脑获取一个仓库，再固定一个小名单试跑；50 个是建议规模，AI 规则与最终字段由 A、B 确认。

B 的第一轮已完成并留在 [b_repo_metadata/](b_repo_metadata/)：50 个仓库的元数据、AI 标签、33 条人工复核与按 `repo_id` 接回事件表的核对结果都可直接查看或重跑，规则草案见 [ai_rules_v0.1](b_repo_metadata/rules/ai_rules_v0.1.md)。

其他现成输入：[名称历史](a_data_pipeline/runs/20240115_1hour_handoff/python/repo_name_history.csv)、[事件预览](a_data_pipeline/runs/20240115_1hour_handoff/python/events_preview.csv)、[完整事件 Parquet](a_data_pipeline/runs/20240115_1hour_handoff/python/events_clean.parquet/)、[活动计数](a_data_pipeline/runs/20240115_1hour_handoff/python/repo_daily_counts.csv)。

## 目录怎么分

```text
仓库根目录/                         ← 对应原来的 group_project/
├── README.md                       ← 小组入口
├── CS5488_AI_Repository_Lifecycle_Project.md
├── A_启动任务_最小数据样本.md
├── Project.pdf                     ← 课程项目要求
├── tools/prepare_github_share.py    ← 生成可分享副本
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
    ├── RESULTS.md                  ← pilot_01 结果与验收清单
    ├── config/                     ← 种子、分层规模、API 参数
    ├── rules/                      ← ai_rules_v0.1（.md 说明 + .json 实现）
    ├── bmeta/                      ← 抓取、规则、复核、接回的实现
    ├── scripts/                    ← 每个步骤一个命令入口
    ├── reviews/                    ← 人工判断与理由
    ├── tests/                      ← 26 项离线验证
    └── runs/                       ← debug_api_sample 与 pilot_01 结果
```

## 先复跑一小时试跑样本

从 clone 后的仓库根目录运行：

```bash
cd a_data_pipeline
conda env create --file environment.yml
conda activate cs5488-data
python scripts/run_sample.py --with-spark
```

会下载/校验原始小时档案，并创建新的运行目录。需要联网及本机足够的存储；配置和数据覆盖见管道 README。组员使用已提交的 CSV 时可以直接开始，运行完整 Spark 管道是另一项工作。

上面这条命令使用原来的**一小时默认样本**并运行 Spark；它不会把样本扩展到 24 小时。Git 中的一天汇总表可直接用于初步分析，见[汇总表文件](a_data_pipeline/sample_data/20240115_24h/repo_daily_counts.csv)。若要在本机生成完整一天的逐条事件数据，或继续增加日期，请按 [A README「获取更长时间的数据」](a_data_pipeline/README.md#获取更长时间的数据) 操作；该流程默认跑 Python，不要求先跑 Spark。

## 哪些内容在 GitHub，哪些在本地

仓库包含代码、环境文件、说明、验证记录，以及 `20240115_1hour_handoff` 中的一小时 Python 样本。另有一份 24 小时汇总表：[`repo_daily_counts.csv`](a_data_pipeline/sample_data/20240115_24h/repo_daily_counts.csv)，按 `repo_id × UTC 日期 × event_type` 统计，共 1,340,785 行，约 48 MB，适合组员直接开始做汇总分析。它不是逐条事件表。

完整的 24 小时逐条事件表、原始 `.json.gz`、SQLite 中间数据库、Spark 复算输出、旧试跑目录和缓存由 `.gitignore` 排除。本机原件继续保留。需要这些完整数据时，可按 A 的说明下载原始档案并重新运行；需要回查完整 payload 或过程数据库时，也可联系 A。HTML 中指向未提交产物的文件链接，需要拿到对应本地文件后才可打开。

重新生成完整 HTML 需要原始档案与完整交接运行（包括未提交的 SQLite 等文件）。clone 后可直接阅读已有 HTML；新电脑若要重新生成，可先复跑样本，再给 `scripts/build_data_guide.py` 指定新运行目录。

## 准备上传

建议用一个小组私有仓库，并邀请组员加入。`Project.pdf` 是课程资料；若准备公开仓库，先确定它和其他课程材料是否适合公开。

在本目录执行下面命令，可生成只包含 Git 未忽略文件的分享压缩包：

```bash
python tools/prepare_github_share.py
```

压缩包默认生成在本目录的上一级，解压得到独立的 `group_project_github_ready/` 分享目录。**上传这个分享目录里的项目文件**；把 ZIP 本身上传到代码仓库，不会自动展开成目录。使用 GitHub Desktop 或命令行提交时，先检查待提交清单：应包含 B 的输入 CSV，且不含 `data/raw`、SQLite 和旧运行。

仓库根目录就是本页所在目录；上传分享版时可将这一层的内容放在仓库根目录，避免额外嵌套一个 `group_project/group_project/`。
