# B 接手指南：给仓库补信息，再判断是否属于研究对象

**你接手的是已经整理好的仓库清单。第一轮目标：跑通“获取仓库信息 → 按规则打标签 → 人工复核 → 按 repo_id 接回 A 的数据”。**

更新：2026-11-02。当前输入来自 2024-01-15 UTC 00:00–01:00 的一个小时档案；这是流程原型，正式研究还要扩大观察范围。

> **B 已完成第一轮（pilot_01，2026-11-02）**：实现、跑法与字段说明见 [b_repo_metadata/README.md](../b_repo_metadata/README.md)，结果与验收清单见 [RESULTS.md](../b_repo_metadata/RESULTS.md)，标签交接方式见 [LABELS.md](../b_repo_metadata/LABELS.md)。AI 规则已迭代到 v0.3（按 A 确认的五条口径：弱信号维持存疑、AI 附加功能排除、README 辅助、课程与个人主页收紧），同一批 50 个仓库的标签变化与人工一致率对比都保留在运行目录。本指南继续作为任务定义与验收口径，第 5 节的完成条件已逐条核对。

## 1. 从哪个文件开始？

以下文件已经存在，路径从 `a_data_pipeline/` 开始：

```text
a_data_pipeline/
├── B_接手指南.md                         ← 先读本页
├── 数据处理全解.html                     ← 查数据来源、字段和处理过程
└── runs/
    └── 20240115_1hour_handoff/
        └── python/
            ├── repo_candidates.csv      ← B 的主要输入；每行一个仓库
            ├── repo_name_history.csv    ← 同一 ID 观察到过哪些名称
            ├── events_preview.csv      ← 用来理解事件表的 100 行预览
            └── events_clean.parquet/   ← 完整事件表；以后按 repo_id 连接标签
```

直接打开[仓库清单](runs/20240115_1hour_handoff/python/repo_candidates.csv)。它有 **69,768 行、69,768 个唯一 repo_id，仓库名称均非空**；这些仓库包含各种主题，AI 标签目前待补。A 已完成从事件中提取唯一仓库这一步。

| 输入列 | B 怎样理解和使用 |
|---|---|
| `repo_id` | 仓库主键；交回结果和连接事件表都用它 |
| `repo_name` | 小时档案中观察到的 `owner/repo` 名称；用来尝试请求 API |
| `first_observed_at`、`last_observed_at` | 这个小时样本内首见、末见的事件时间 |
| `event_count` | 这个仓库在本小时样本中有多少条事件 |
| `observed_name_count` | 本样本中同一 ID 出现过多少个不同名称 |

**仓库创建时间要从仓库 API 补充。** `first_observed_at` 和事件的 `created_at` 都不能代替它。样本中有 **60 个仓库 ID 出现过多个名称**，可查[名称历史](runs/20240115_1hour_handoff/python/repo_name_history.csv)；多个名称的具体原因还需核实。

## 2. 第一轮具体做什么？

下面的 **50 个仓库是建议的试跑规模**，A、B 可以调整并记录；完整的 69,768 行清单留作后续扩展输入。

1. **先跑通 1 个仓库。** 用 `GET /repos/{owner}/{repo}`，保存真实返回内容。可从样本里的 `apache/superset` 开始，核对返回 `id` 是否等于输入 `repo_id=39464018`。这一步验证 B 自己电脑的联网、依赖和读取方式；此示例没有预先指定 AI 标签。
2. **固定首批名单。** 从候选清单选 50 个，保存为 `pilot_candidates.csv`，记录选取方法；随机抽样时记录种子，例如 `5488`。API 调试样例若不在这 50 个中，单独标为调试记录。首批名单用于跑通流程，不能据此直接估计整个 GitHub 的 AI 仓库比例。
3. **获取仓库信息。** 至少保存 API 的 `id`、`full_name`、`created_at`、`description`、`topics`、`language`、`archived`，以及获取时间和状态。原始 JSON 另存，后续可以回查。
4. **提出 AI 判定规则初稿。** 写明纳入/排除范围、topic 与描述关键词及匹配方法，再与 A 确认版本。传统机器学习、教程/课程作业、资料集合、仅集成 AI 功能的项目是否纳入，都要明确。每个判断保存理由。
5. **人工复核并接回 A 的表。** 查看部分入选、排除和存疑仓库，记录人工判断与自动规则的差异。最后用 `repo_id` 连接回 A 的事件表，检查每条事件最多匹配一条仓库标签。

B 这一轮主要使用 **Python、CSV/JSON 和 HTTP 请求**。在 HTML 中优先阅读“04 三张分析用表”和“08 后续组员”，需要查细节时再回看 A 的处理步骤。

## 3. 最后交回什么？

下面是 **B 接手后要创建的建议结构**。2026-11-02 已由 B 实现在 [`b_repo_metadata/`](../b_repo_metadata/)（见其 README 与 RESULTS）；实际目录另含实现包 `bmeta/`、`config/`、`tests/` 与复核证据，字段与本表一致。路径从 `group_project/` 开始：

```text
group_project/
└── b_repo_metadata/                       ← B 创建
    ├── scripts/fetch_metadata.py          ← 获取、缓存、记录失败的代码
    ├── scripts/label_repositories.py      ← 应用标签规则的代码
    ├── rules/ai_rules_v0.1.md             ← 第一版规则及适用范围
    └── runs/pilot_01/
        ├── pilot_candidates.csv          ← 冻结的首批输入名单
        ├── raw_api/                      ← 原始响应，按 repo_id 保存
        ├── repo_metadata.csv             ← 每个输入仓库一行，包含失败状态
        ├── repo_ai_labels.csv            ← 每个输入仓库一行，包含存疑标签
        ├── manual_review.csv             ← 人工复核对象、结论和理由
        └── run_summary.json              ← 输入、版本、获取/标签数量及未解决问题
```

**建议的第一版输出字段，A、B 试跑后确认并固定：**

| 输出 | 字段与约定 |
|---|---|
| `repo_metadata.csv` | `repo_id`、`observed_repo_name`、`api_repo_id`、`current_full_name`、`repo_created_at`、`description`、`topics_json`、`language`、`archived`、`fetch_status`、`http_status`、`fetched_at_utc` |
| `repo_ai_labels.csv` | `repo_id`、`ai_label`、`reason`、`rule_version`、`metadata_fetched_at_utc`、`labelled_at_utc` |

- `repo_id` 始终保留 A 的 ID；`api_repo_id` 单独保存 API 返回的 ID。只有二者匹配时，才把返回信息认作同一仓库的元数据。
- `repo_created_at` 对应仓库 API 的 `created_at`。时间统一 UTC；`topics_json` 用 JSON 数组文本保存，例如 `[]`。
- `ai_label` 使用 `included` / `excluded` / `uncertain`。每行都要有理由及规则版本。
- 获取失败或 ID 不匹配时，元数据缺失项留空、状态写清，AI 标签先记 `uncertain`。当前信息不足不能直接判为非 AI。
- `fetched_at_utc` 在成功获取时填写。取回的描述、topics 等是获取时的快照，不能直接当作 2024 年事件发生时的仓库状态。

## 4. 哪些地方需要特别留意？

- 名称可能变化或被重新使用。请求遇到重定向应跟随，并核对返回 ID；可回查 A 的名称历史。404 只记录无法获取，暂不自行判定为删除或私有化。
- 首批采用串行请求并缓存响应；根据响应中的配额和重试信息暂停、续跑。网络失败、限流、HTTP 错误与正常空字段分别记录。若使用 Token，通过环境变量读取，分享代码时保留变量名即可。
- 这里的研究对象来自 A 的样本。用于调试规则的额外已知 AI 仓库须单独记录，加入正式研究对象时需要说明纳入依据及事件覆盖。
- AI 规则由 B 提出、A+B 确认；此指南中的试跑规模与字段是交接建议，正式研究范围尚未冻结。

API 字段和公开仓库读取方式见 [GitHub Repository API](https://docs.github.com/en/rest/repos/repos#get-a-repository)。重定向、错误与限流处理见 [GitHub 官方使用建议](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)。

## 5. 第一轮怎样算完成？

以下为 pilot_01（2026-11-02）的核对结果，证据文件见 [b_repo_metadata/RESULTS.md](../b_repo_metadata/RESULTS.md)：

- [x] 至少有一个在 B 电脑上成功获取、返回 ID 与输入一致的真实样例。→ `apache/superset` 返回 `id=39464018`，见 `b_repo_metadata/runs/debug_api_sample/`。
- [x] 首批名单、来源文件及其 SHA-256、选取方法、输入数量都有记录。→ `runs/pilot_01/selection.json`（69,768 行、种子 5488、随机 40 + 关键词 10）。
- [x] 两张结果表覆盖首批每个 ID，主键唯一；获取失败和存疑记录保留。→ 50 个唯一 ID；43 ok + 2 id 不一致 + 5 个 404 均保留状态。
- [x] 获取成功数 + 失败数 = 已处理仓库数；三种标签数量之和 = 结果仓库数；待处理项单列。→ 43+2+5=50；3+22+25=50；`pending_repo_ids` 为空。
- [x] 规则、标签理由和人工复核记录齐全。建议入选/排除各复核 5 个，不足时全查；某类未出现时写明本轮未覆盖该类，存疑案例单独复核。→ included 仅 3 个全查、excluded 抽 5、uncertain 25 个全查，共 33 条，理由逐条记录。
- [x] 能按 `repo_id` 接回 A 的事件表；带标签的仓库表保持一仓库一行。→ `join_check.json`：50/50 命中，197,313 条事件中 159 条被覆盖，唯一性检查通过。
- [x] 交回代码、运行命令和所需依赖；另一位组员能按说明重跑这批名单。待处理请求或未解决的联网问题仍需完成后再验收。→ `b_repo_metadata/README.md` 给出完整命令，26 项离线测试通过，缓存可让重跑不产生新请求。

**完成这一轮后，B 才扩展批量获取和规则复核；A 同时继续扩展事件数据。最终交给 C 的是带创建时间、AI 标签、理由和获取状态的仓库表，以及对应覆盖范围内的事件数据。**
