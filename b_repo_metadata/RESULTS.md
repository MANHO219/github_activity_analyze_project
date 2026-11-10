# B 试跑结果（pilot_01 / pilot_02）

**首次运行：** 2026-11-02（UTC 05:02–05:35），规则 `ai_rules_v0.1`
**规则迭代：** 2026-11-02（UTC 08:00–08:40），规则 `ai_rules_v0.2`，同一批 50 个仓库重跑标签
**口径确认后更新：** 2026-11-09，规则 `ai_rules_v0.3`（A 确认五条口径），同一批 50 个仓库重跑
**反馈修正：** 2026-11-09，规则 `ai_rules_v0.3.1`（README 判 AI / 个人主页收紧），同批重跑 0 条标签变化
**边界案例：** 2026-11-09，规则 `ai_rules_v0.3.3`（README 确认主体非 AI），pilot_01 6 条、pilot_02 22 条 uncertain → excluded
**收紧 R12：** 2026-11-09，规则 `ai_rules_v0.3.3.1`（需用途证据、只对 R7、旧版本不触发），pilot_01 4 条、pilot_02 17 条回退为 uncertain
**可选 AI 集成与课程覆盖：** 2026-11-09，规则 `ai_rules_v0.3.4`，pilot_01 0 条、pilot_02 1 条（Etherscan-ML 由 R13 排除）
**误判抽查：** 2026-11-09，规则 `ai_rules_v0.3.5`（论文清单、course on、个人主页组件、名称边界），pilot_01 0 条、pilot_02 6 条
**R12 补全：** 2026-11-09，规则 `ai_rules_v0.3.4.1`（用途标题需正文），pilot_01 0 条、pilot_02 0 条
**A review 收紧：** 2026-11-10，规则 `ai_rules_v0.3.6`（三个新增条件收紧到仓库自身用途），pilot_01 0 条、pilot_02 0 条
**R12 收尾：** 2026-11-10，规则 `ai_rules_v0.3.4.2`（英文安装说明不算正文），pilot_01 0 条、pilot_02 0 条
**论文清单再收紧：** 2026-11-10，规则 `ai_rules_v0.3.7`（a list of 锚定整段），pilot_01 0 条、pilot_02 0 条
**环境：** Windows 11，Python 3.12.14（v0.3.4 及以前）/ 3.13.14（v0.3.5 重跑），标准库 + pyarrow 26.0.0（仅用于读取 A 的 Parquet）
**运行目录：** [`runs/pilot_01/`](runs/pilot_01/)，汇总见 [`run_summary.json`](runs/pilot_01/run_summary.json)

## 0. 当前状态：v0.3.7（论文清单再收紧 + R12 收尾）

对 pilot_02 的 101 条 `uncertain` 与 80 条 `excluded` 逐条复查后，只把 6 个**明确判错**的仓库改判；A 复测又发现三处“讨论该主题就被排除”的误伤，v0.3.6 收紧。

| 仓库 | v0.3.4 | v0.3.5 | 依据 |
|---|---|---|---|
| `pkeilbach/htwg-practical-nlp` | included | excluded | 描述与 README 都是“某课程”，属课程资料 |
| `tomohideshibata/ChatGPT-related-papers` | included | excluded | README 首句“This is a list of … papers”，属链接合集 |
| `Pepestar/Pepestar` | uncertain | excluded | `Bem vindo` + GitHub 统计卡，个人主页 |
| `gaurav-shrestha/gaurav-shrestha` | uncertain | excluded | typing 头图写 “Welcome to my Github Page” |
| `Speike-SHL/Speike-SHL` | uncertain | excluded | 只有贡献蛇 SVG，个人主页 |
| `al3xback/fmentor-stats-preview-mocha-chai-expect` | uncertain | excluded | `chai` 被误当 `ai` 名称信号 |

| 指标 | v0.2 | v0.3 | v0.3.3.1 | v0.3.6（当前） |
|---|---:|---:|---:|---:|
| `included` | 1 | 4 | 4 | 4 |
| `excluded` | 30 | 30 | 32 | 32 |
| `uncertain` | 19 | 16 | 14 | 14 |
| 与人工在已判定行的一致 | 14/14 | 17/17 | 19/19 | 19/19 |
| 人工推翻 | 0 | 0 | 0 | 0 |
| 人工优先与自动的差异 | 11 | 8 | 6 | 6 |

pilot_01 的 50 个仓库在 v0.3.4 → v0.3.6 之间**0 条标签变化、0 条理由变化**：这批样本里没有课程资料、论文清单、个人主页组件或 `chai` 类名称。

A 的复测集中在三个新增条件：推荐 `course on deployment` 的 ML 工具、总结 `ChatGPT-related papers` 的工具、带统计卡的 ML 工具，在 v0.3.5 下都会被误排；v0.3.6 分别加了对照测试，规则改为判断“仓库本身的用途”。同时 R12 也补了“标题下方必须有正文”，空 `## Overview` + 安装步骤不再排除。

注意：**19/19 = 100% 只代表复核样本中自动已判定的 19 条**与人工一致，不是整体分类准确率；人工复核只覆盖 33 个仓库。

规则说明见 [`rules/ai_rules_v0.3.7.md`](rules/ai_rules_v0.3.7.md)、[`rules/ai_rules_v0.3.4.2.md`](rules/ai_rules_v0.3.4.2.md)；抽查过程、改判依据与“维持 uncertain”的清单见 [`reviews/pilot_02_rule_review_v0.3.5.md`](reviews/pilot_02_rule_review_v0.3.5.md)。以下第 1–9 节保留早期过程记录，数字与表格以本节为准。

## 0.2 扩大试跑 pilot_02（200 个仓库）

2026-11-09 用 A README 的 24 小时命令重建全天数据（52 分钟，5,528,300 事件 / 852,777 仓库，与 A 的交接数量一致），排除 pilot_01 的 50 个后，用种子 5488 抽 160 随机 + 40 名称命中。

| 项目 | 结果 |
|---|---|
| 元数据 API | 200 次调用：163 成功、31 个 404、6 个 ID 不一致，120 秒 |
| README 证据 | 200 次请求：138 个有响应（134 个有正文）、62 个无 README 或 404，128 秒 |
| 标签（160 随机） | included 2 / excluded 75 / uncertain 83 |
| 标签（40 关键词） | included 15 / excluded 11 / uncertain 14 |
| 全部 200（自动） | included 17 / excluded 86 / uncertain 97（5 条由 R12、1 条由 R13、5 条由 R11 排除） |
| 全部 200（最终，人工优先） | included 17 / excluded 87 / uncertain 96（含 A 对 ItsCryptic 的一条人工修订） |
| 接回全天活动表 | 200/200 命中，覆盖 1,072 / 5,528,300 条事件；按最终标签 excluded 394 / included 109 / uncertain 569 |
| 人工抽查 | 13 条（included 3、excluded 5、uncertain 5） |

抽查发现并修复两处规则 bug（v0.3.2）：`Whispering-Origin-2D` 被子串当成 `whisper`；中文“用Resnet101+GPT搭建…的AI”因 `\b` 在中文里失效被漏判。A 判定两个边界案例：Etherscan-ML 按训练营项目排除，CoreELEC/xbmc 按 README 主体非 AI 排除。v0.3.3.1 收紧 R12（需用途说明、只对 R7）；v0.3.4 新增 R13 课程覆盖，Etherscan-ML 由规则自动 excluded，13 条人工复核与自动标签差异为 0。明细见 `runs/pilot_02/manual_review_pilot02.csv` 与 `pilot_02_summary.json`。

v0.3.5 的 6 条变化全部来自 101 条 `uncertain` 与 80 条 `excluded` 的人工复查，没有一条落在 13 条复核样本里。A 另对 `ItsCryptic/ItsCryptic` 做了一条人工修订（代码块内容是自我介绍 → 个人主页），记在 `runs/pilot_02/manual_revisions.csv`，不覆盖原复核表；最终标签因此是 17 / 87 / 96。接回表已按最终标签重跑，覆盖的 1,072 条事件不变，只是重新分到了 excluded。

## 1. 本次数字

| 项目 | 实测结果 |
|---|---|
| A 的候选清单 | 69,768 行 / 69,768 个唯一 `repo_id`，SHA-256 `e11f5c20990233b45fa8fabe4e0eeeed401baceaaf6f108e1d2d3c6d463c0b09` |
| 首批名单 | 50 个：随机 40 + 名称关键词 10，种子 `5488`，SHA-256 `e9de060d26ded56bb841fe6a449bc409f55eb5a86125f279efa7bea170d3a9c8` |
| 元数据获取 | 43 `ok` + 2 `id_mismatch` + 5 `not_found` = 50；API 调用 50 次，pending 0 |
| AI 标签 v0.1 | `included` 3 + `excluded` 22 + `uncertain` 25 = 50 |
| AI 标签 v0.2 | `included` 1 + `excluded` 30 + `uncertain` 19 = 50 |
| AI 标签 v0.3.7（当前） | `included` 4 + `excluded` 32 + `uncertain` 14 = 50 |
| 人工复核 | 33 条：included 3（全查）、excluded 5（抽样）、uncertain 25（全查） |
| 与人工一致率（已判定行） | v0.1 6/8 = 75% → v0.2 14/14 → v0.3 17/17 → v0.3.6 19/19 |
| 接回 A 的事件表 | 50/50 个试点仓库按 `repo_id` 匹配；197,313 条事件中 159 条属这 50 个仓库 |
| 离线测试 | 134 项通过 |

v0.2 的规则分布（历史记录）：

| 规则 | 数量 | 含义 |
|---|---:|---|
| `R1_metadata_unavailable` | 5 | 404，无法获取元数据 |
| `R2_api_id_mismatch` | 2 | 同名仓库已换 ID |
| `R3_resource_collection` | 3 | awesome/教程/链接合集 |
| `R3b_coursework` | 3 | 课程作业（IBM final project、Openclassrooms、cs933-lab） |
| `R3c_profile_repository` | 6 | 个人主页仓库 |
| `R4b_weak_topic_only` | 1 | 只有裸 `ai` topic，无佐证 |
| `R5b_weak_signal_corroborated` | 1 | 弱信号 + 佐证词（Epigos AI SDK） |
| `R6_name_only_signal` | 3 | 只有名称像 AI |
| `R7_insufficient_text_evidence` | 8 | 描述与 topics 都为空 |
| `R8_no_ai_signal` | 18 | 有文本但无 AI 信号 |

## 2. 规则 v0.1 → v0.2 的对比

同一批 50 个仓库、同一份元数据快照，只改规则：

| 指标 | v0.1 | v0.2 |
|---|---:|---:|
| `included` | 3 | 1 |
| `excluded` | 22 | 30 |
| `uncertain` | 25 | 19 |
| 与人工判断一致（已判定行） | 6/8 (75%) | 14/14 (100%) |
| 人工推翻（disagree） | 2 | 0 |
| 人工判定后仍存疑 | 8 | 8 |

混淆矩阵（旧 → 新）：

| v0.1 \ v0.2 | included | excluded | uncertain |
|---|---:|---:|---:|
| included (3) | 1 | 1 | 1 |
| excluded (22) | 0 | 22 | 0 |
| uncertain (25) | 0 | 7 | 18 |

共 11 条变化：9 条标签变化、2 条仅规则理由变化。8 条由“不一致/存疑”变成与人工一致，0 条回退：

| 仓库 | v0.1 | v0.2 | 原因 |
|---|---|---|---|
| `ibm-developer-skills-network/oaqjp-final-project-emb-ai` | included | excluded | 新增课程作业规则，从名称识别 `final-project` |
| `weseek/growi` | included | uncertain | 裸 `ai` topic 降为弱信号，描述里没有佐证词 |
| 6 个 `owner/repo` 同名仓库 | uncertain | excluded | 新增个人主页仓库规则 |
| `bebill/Openclassrooms-P11_Kasa` | uncertain | excluded | 名称命中 Openclassrooms 课程作业 |
| `Epigos-AI/epigos-python` | included | included | 标签不变，理由改为“弱信号 + sdk 佐证” |
| `Xanonymous-GitHub/cs933-lab` | excluded | excluded | 标签不变，理由改由更具体的课程规则记录 |

逐条记录：[`label_changes.csv`](runs/pilot_01/label_changes.csv)；汇总与人工对照：[`label_comparison.json`](runs/pilot_01/label_comparison.json)。

v0.2 仍存疑的 19 条分三类：

1. **8 条元数据缺失/空仓库**：5 个 404、2 个 ID 不一致、1 个 README 也不存在的空仓库；
2. **3 条名称像 AI 但描述为空**：`ML-project`（实为 scikit-learn 项目）、`PrivateGPT` 风格仓库、MLOps 课程仓库——README 能判定，但规则不读 README；
3. **8 条其他**：GROWI（AI 附加功能边界）、游戏 mod/游戏服务器代码、个人作品集、实验室主页、HCL 服务骨架、名称已被改掉的个人主页仓库（`mattdotjar/matthewmatheus`）。

## 3. 标签交接

三张表的分工与生成方式见 [LABELS.md](LABELS.md)。当前结果：

| 表 | 覆盖 | 结果 |
|---|---|---|
| `repo_ai_labels.csv`（自动，v0.2） | 50 | included 1 / excluded 30 / uncertain 19 |
| `manual_review.csv`（人工判断） | 33 | 与 v0.1 复核时记录的判断，不覆盖自动表 |
| `repo_ai_labels_analysis.csv`（默认人工优先） | 50 | included 4 / excluded 38 / uncertain 8；来源：人工 33、自动 17 |

默认口径 `manual_override`：有复核的仓库用人工标签，其余用规则标签；`label_source` 标明每行来源。改用 `--policy auto_only` 可得到纯规则版本。最终采用哪种口径待今晚确认。

## 4. API 失败后的重跑行为

- 缓存策略：**只复用 HTTP 200 且响应体为合法 JSON 的成功响应**；404、5xx、无效 JSON，以及没有响应体的网络错误/超时，都会保留为证据但下次重新请求。
- 核对方式：把 `pilot_01` 的名单与 `raw_api/` 复制到临时目录重跑 `fetch_metadata.py`。
- 实测：43 个成功响应 + 2 个 ID 不一致命中缓存，5 个 404 重新请求，共 **5 次 API 调用**、0 个 pending。
- 需要复现失败快照时用 `--reuse-failed`：失败响应（含没有 JSON 响应体的网络错误）也命中缓存，0 次调用；状态按缓存里的错误重建（`network_error` / `server_error` / `not_found`）。
- 记录：[`cache_retry_check.json`](runs/pilot_01/cache_retry_check.json)，另有 50 项离线测试覆盖这些分支。

## 5. 事件占比的口径

`repo_labels_joined_events.csv` 里现在有两个明确命名的列：

| 字段 | 分母 | 本次示例 |
|---|---|---|
| `event_share_of_source` | 事件表全部事件 197,313 条 | 仓库有 3 条事件 → 0.000015 |
| `event_share_of_pilot_events` | 50 个试点仓库的事件总数 159 条 | 同一仓库 → 0.018868 |

原字段 `event_share_of_pilot` 名字有歧义，已拆成上面两列；`join_check.json` 也记录了 `events_covered_share_of_source`（159/197,313 ≈ 0.08%）。v0.1 的旧表保留为 `repo_labels_joined_events_v0.1.csv`。

## 6. 单仓库连通性样例

按指南第 2 节第 1 步，用 `apache/superset` 验证本机联网、依赖与读取方式：

- 请求：`GET https://api.github.com/repos/apache/superset`
- 返回：HTTP 200，`id=39464018`（与 A 的 `repo_id` 一致），`created_at=2015-07-21T18:55:34Z`
- 原始响应与核对结果：[`runs/debug_api_sample/api_sample_check.json`](runs/debug_api_sample/api_sample_check.json)、[`raw_api/39464018.json`](runs/debug_api_sample/raw_api/39464018.json)
- 该样例**不计入** 50 个试跑名单。

## 7. 按指南第 5 节的验收清单

第一轮（v0.1）已全部满足，v0.2 迭代后依旧成立：

| 完成条件 | 状态 | 证据 |
|---|---|---|
| 至少一个成功获取、返回 ID 与输入一致的样例 | ✅ | `apache/superset` → `39464018`，见 `runs/debug_api_sample/` |
| 首批名单、来源文件及其 SHA-256、选取方法、输入数量都有记录 | ✅ | `runs/pilot_01/selection.json` |
| 两张结果表覆盖首批每个 ID，主键唯一，失败与存疑保留 | ✅ | `run_summary.json` 的 `checks` 全部为 true |
| 获取成功数 + 失败数 = 已处理仓库数；三种标签数量之和 = 结果仓库数；待处理项单列 | ✅ | 43+2+5=50；1+30+19=50；`pending_repo_ids` 为空 |
| 规则、标签理由和人工复核记录齐全；入选/排除各复核 5 个，不足时全查；存疑案例单独复核 | ✅ | 三版规则 JSON/MD、每行 `reason`、`manual_review.csv`（33 条） |
| 能按 `repo_id` 接回 A 的事件表；带标签的仓库表一仓库一行 | ✅ | `join_check.json`：50/50 命中，覆盖 159 条事件，唯一性检查通过 |
| 交回代码、运行命令和依赖；另一位组员能按说明重跑 | ✅ | `README.md` 的“怎么重跑”分成复现与开新一轮两种；134 项离线测试；缓存策略可复跑 |

## 8. 未解决与待确认

1. **规则口径：已由 A 确认并落到 v0.3**（弱信号维持存疑、只附加 AI 功能排除、README 可辅助、课程需确认语义、个人主页先记疑似）。
2. **标签口径：已确认**——交接给 C 采用人工优先，保留自动/人工/最终标签与来源，`uncertain` 单列不并入 `excluded`；见 `LABELS.md`。
3. 元数据是 2026-11-02 的快照，不等于 2024-01-15 的仓库状态。
4. 50 个仓库是分层小样本，不能估计 GitHub 整体 AI 仓库比例；19/19 只是复核样本内的一致率。
5. 事件覆盖仍只有 1 小时（197,313 条），试点仓库覆盖 159 条，无法支持生命周期结论。
6. 后续计划：用 LLM API 辅助判断 `uncertain`，单独 PR、先做小试验；模型与预算由组内确定。
7. R5d 的“可选 AI 集成”措辞目前只有测试覆盖：v0.3.5 生成前扫描 pilot_02 全部 200 条 README，`optional … AI/ChatGPT/OpenAI/LLM` 命中 0 条；扩量后需要专门抽样验证。
8. R12 的 200 字符阈值与 `purpose_patterns` 仍是启发式，**未放宽**：`auto-green` 克隆、`MiSArch/wishlist` 等 README 已写明非 AI 的仓库仍是 `uncertain`，留给 LLM 试验与人工判断。A 指出的“空标题即排除”已在 v0.3.4.1 修掉。
9. R11 仍把任意代码围栏当作“工程章节”。A 明确：`ItsCryptic/ItsCryptic` 可人工判为 excluded，已记入 `manual_revisions.csv`；通用规则暂不放开——A 复测发现直接取消限制会让带统计卡和真实安装命令的 AI 项目也被判成主页。
10. `readme_evidence.jsonl` 里有 2 条空 README 记录（`srecops/srecops`、`cyx2016/agent`）的 `readme_chars` 是历史错误信封的长度，v0.3.5 已修抓取代码并在加载时跳过这类文本，但旧文件未回写；下次抓取会自动修正。
11. 接回表改用最终标签：`join_check.py` 默认读取 `repo_ai_labels_analysis.csv`；pilot_02 已按此重跑，pilot_01 没有标签变化，保留原来基于 parquet 的记录。

## 9. 复跑记录

复现本次成果（不碰已有复核记录；`manual_review.py` 只合并判断，不复用时会报错保护）：

```bash
cd b_repo_metadata
python scripts/build_pilot.py                 # 名单已冻结，重跑会拒绝覆盖
python scripts/fetch_metadata.py              # 成功缓存命中；失败响应会重新请求
python scripts/label_repositories.py          # 默认 v0.3，自动使用复核 README 证据
python scripts/compare_label_versions.py --run-dir runs/pilot_01 \
    --old runs/pilot_01/repo_ai_labels_v0.2.csv --new runs/pilot_01/repo_ai_labels.csv
python scripts/build_analysis_labels.py --run-dir runs/pilot_01
python scripts/manual_review.py --run-dir runs/pilot_01 --decisions reviews/pilot_01_decisions.json
python scripts/join_check.py
python scripts/build_run_summary.py --run-dir runs/pilot_01
python -m unittest discover -s tests -v
```

要按当前规则重新抽样复核时，换输出目录并显式指向已有输入（不会覆盖 `runs/pilot_01/`）：

```bash
python scripts/manual_review.py --run-dir runs/pilot_02_review \
    --labels runs/pilot_01/repo_ai_labels.csv \
    --metadata runs/pilot_01/repo_metadata.csv
```

复核流程的保护已验证：

- 按上面的复现顺序重跑后，`manual_review.csv` 与仓库中的版本逐字节一致（SHA-256 `07a92c95515dc159db39b91f34535cd7620506f2bf316f937ec6f2469514a693`）；
- 误跑不带 `--decisions` 的 `manual_review.py` 会以退出码 3 拒绝覆盖，文件不变；
- 清单被删时带 `--decisions` 会以退出码 5 拒绝自动生成清单，不会把旧判断混进按新规则临时生成的名单；确实需要生成后合并时要显式加 `--allow-new-sheet`；
- 把旧判断文件合并到另一轮清单时会以退出码 4 报错，并列出不在清单中的 `repo_id`；
- 摘要区分 `labels_rule_version`（本次读取的标签版本，v0.2）与 `sheet_rule_version`（复用旧清单时为 `unknown_existing_sheet`），并记录清单自动标签与当前标签的差异：本次 9 条，与 v0.1→v0.2 的标签变化一致。人工一致率（6/8、17 条 resolve）是对**清单生成时的 v0.1 标签**算的；v0.2 与人工的对比见 `label_comparison.json`。

各阶段摘要（`fetch_summary.json`、`label_summary.json`、`label_comparison.json`、`label_analysis_summary.json`、`manual_review_summary.json`、`join_check.json`）与合并后的 `run_summary.json` 都在同一运行目录，可与上表逐项对照。
