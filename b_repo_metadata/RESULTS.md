# B 第一轮试跑结果（pilot_01）

**运行时间：** 2026-11-02（UTC 05:02–05:35）
**环境：** Windows 11，Python 3.12.14，标准库 + pyarrow 26.0.0（仅用于读取 A 的 Parquet）
**规则版本：** `ai_rules_v0.1`（SHA-256 `28487599372518417e34a0092ec6c195a5379298d9349aa157bc84b7fbcbb522`）
**运行目录：** [`runs/pilot_01/`](runs/pilot_01/)，汇总见 [`run_summary.json`](runs/pilot_01/run_summary.json)

## 1. 本次数字

| 项目 | 实测结果 |
|---|---|
| A 的候选清单 | 69,768 行 / 69,768 个唯一 `repo_id`，SHA-256 `e11f5c20990233b45fa8fabe4e0eeeed401baceaaf6f108e1d2d3c6d463c0b09` |
| 首批名单 | 50 个：随机 40 + 名称关键词 10，种子 `5488`，SHA-256 `e9de060d26ded56bb841fe6a449bc409f55eb5a86125f279efa7bea170d3a9c8` |
| 元数据获取 | 43 `ok` + 2 `id_mismatch` + 5 `not_found` = 50；API 调用 50 次，pending 0 |
| AI 标签 | `included` 3 + `excluded` 22 + `uncertain` 25 = 50（唯一 `repo_id` 50 个） |
| 人工复核 | 33 条：included 3（全查）、excluded 5（抽样）、uncertain 25（全查） |
| 自动判定行的一致率 | 6 / 8（75%），2 条推翻 |
| 存疑行的复核结果 | 25 条中 17 条被人工判定（68%），8 条维持存疑 |
| 接回 A 的事件表 | 50/50 个试点仓库都能按 `repo_id` 匹配；197,313 条事件中 159 条属这 50 个仓库 |
| 离线测试 | 26 项通过 |

标签的规则分布：

| 规则 | 数量 | 含义 |
|---|---:|---|
| `R1_metadata_unavailable` | 5 | 404，无法获取元数据 |
| `R2_api_id_mismatch` | 2 | 同名仓库已换 ID |
| `R3_resource_collection` | 4 | awesome/教程/课程/链接合集 |
| `R4_topic_match` | 1 | topic 命中 |
| `R5_description_match` | 2 | 描述命中 |
| `R6_name_only_signal` | 3 | 只有名称像 AI |
| `R7_insufficient_text_evidence` | 15 | 描述与 topics 都为空 |
| `R8_no_ai_signal` | 18 | 有文本但无 AI 信号 |

## 2. 单仓库连通性样例

按指南第 2 节第 1 步，用 `apache/superset` 验证本机联网、依赖与读取方式：

- 请求：`GET https://api.github.com/repos/apache/superset`
- 返回：HTTP 200，`id=39464018`（与 A 的 `repo_id` 一致），`created_at=2015-07-21T18:55:34Z`
- 原始响应与核对结果：[`runs/debug_api_sample/api_sample_check.json`](runs/debug_api_sample/api_sample_check.json)、[`raw_api/39464018.json`](runs/debug_api_sample/raw_api/39464018.json)
- 该样例**不计入** 50 个试跑名单。

## 3. 关键案例

| 仓库 | 自动标签 | 人工标签 | 说明 |
|---|---|---|---|
| `Epigos-AI/epigos-python` | included | included | 计算机视觉平台 SDK，规则与人工一致 |
| `weseek/growi` | included | **excluded** | 团队协作 wiki，`ai` 只是附加功能的 topic |
| `ibm-developer-skills-network/oaqjp-final-project-emb-ai` | included | **excluded** | IBM 课程 final project，属课程作业 |
| `AWS ... real-time-summarizer` | uncertain | **included** | README 显示用 Cohere LLM + Transcribe 做通话摘要 |
| `JaishnavK/Python-Machine-Learning-Project` | uncertain | **included** | scikit-learn 卡路里预测项目（仓库已改名，ID 未变） |
| `AILEXGPT/nextjs-flask-starter` | uncertain | **included** | README 为 PrivateGPT 风格本地 LLM 文档问答 |
| `manifoldailearning/mlops-with-aws-datascientists` | uncertain | **excluded** | MLOps 课程配套仓库 |
| `bebill/Openclassrooms-P11_Kasa` | uncertain | **excluded** | Openclassrooms 课程作业 |
| 7 个 `owner/repo` 同名仓库 | uncertain | **excluded** | 个人主页 README，不是项目仓库 |

人工复核的完整对象、理由与一致率见 [`manual_review.csv`](runs/pilot_01/manual_review.csv)、[`manual_review_summary.json`](runs/pilot_01/manual_review_summary.json) 与判断源文件 [`reviews/pilot_01_decisions.json`](reviews/pilot_01_decisions.json)。

## 4. 按指南第 5 节的验收清单

| 完成条件 | 状态 | 证据 |
|---|---|---|
| 至少一个成功获取、返回 ID 与输入一致的样例 | ✅ | `apache/superset` → `39464018`，见 `runs/debug_api_sample/` |
| 首批名单、来源文件及其 SHA-256、选取方法、输入数量都有记录 | ✅ | `runs/pilot_01/selection.json`（69,768 行、种子 5488、两层抽样、输入/输出哈希） |
| 两张结果表覆盖首批每个 ID，主键唯一，失败与存疑保留 | ✅ | `run_summary.json` 的 `checks`：`metadata_ids_unique`、`labels_cover_metadata` 均为 true |
| 获取成功数 + 失败数 = 已处理仓库数；三种标签数量之和 = 结果仓库数；待处理项单列 | ✅ | 43+2+5=50；3+22+25=50；`fetch_summary.json` 的 `pending_repo_ids=[]` |
| 规则、标签理由和人工复核记录齐全；入选/排除各复核 5 个，不足时全查；存疑案例单独复核 | ✅ | `rules/ai_rules_v0.1.md`、每行 `reason`、`manual_review.csv`（included 3 全查、excluded 5、uncertain 25 全查） |
| 能按 `repo_id` 接回 A 的事件表；带标签的仓库表一仓库一行 | ✅ | `join_check.json`：50/50 命中，唯一性检查通过，覆盖 159 条事件 |
| 交回代码、运行命令和依赖；另一位组员能按说明重跑 | ✅ | `README.md` 的“怎么重跑”；26 项离线测试；重跑使用缓存，不重复请求 |

## 5. 复核发现与规则改进输入

自动判定行中 2 条被推翻，反映两类口径问题：

1. **裸 `ai`/`ml` 词元过强**：`weseek/growi` 仅因 topic 含 `ai` 被判入选，实际是协作 wiki。建议 v0.2 把单独出现的 `ai` 视为弱信号，需 topic 或描述中的强词佐证。
2. **课程作业未识别**：IBM 课程 final project 因描述含 `ai` 被判入选。建议增加课程/作业语境排除。

25 条存疑中 17 条被人工判定，集中在三类：

- **个人主页/作品集仓库（9 条）**：`owner/repo` 同名且无描述、无 topics。建议 v0.2 增加“非项目仓库”排除规则。
- **课程/资料仓库（2 条）**：MLOps 课程、Openclassrooms 作业。建议扩充课程排除关键词。
- **名称命中的真实 AI 项目（3 条）**：README 证明是 LLM/ML 项目，但 API 描述为空。建议名称命中后补抓 README 再判，而不是停在 uncertain。
- 其余 3 条为非 AI 工程（游戏 mod、游戏服务器代码、HCL 服务骨架），README 可明确排除。

8 条维持 `uncertain` 的记录：5 个 404、2 个 ID 不一致、1 个空仓库（README 也不存在）。这些不能靠文本规则解决，只能等仓库恢复可访问或在正式阶段用历史快照核对。

## 6. 未解决的问题

1. 规则 v0.1 的纳入/排除边界（尤其“仅集成 AI 功能”）尚未与 A 确认，当前口径偏宽。
2. 元数据是 2026-11-02 的快照，不等于 2024-01-15 的仓库状态；生命周期分析需要历史字段时，必须另行说明或取历史快照。
3. 50 个仓库是分层小样本，其中 10 个按名称过采样，不能据此估计 GitHub 整体 AI 仓库比例。
4. 事件覆盖仍只有 1 小时（197,313 条），试点仓库只覆盖其中 159 条事件，无法支持生命周期结论。
5. 人工复核使用了 README（记录在 `manual_review_readmes.jsonl`），而规则只看 API 字段；两种证据口径的差异已在报告中区分，但正式阶段应决定复核是否统一使用 README。

## 7. 复跑记录

```bash
cd b_repo_metadata
python scripts/build_pilot.py                 # 名单已冻结，重跑会拒绝覆盖
python scripts/fetch_metadata.py              # 使用 raw_api 缓存，0 次新请求
python scripts/label_repositories.py
python scripts/manual_review.py --run-dir runs/pilot_01 --decisions reviews/pilot_01_decisions.json
python scripts/join_check.py
python scripts/build_run_summary.py --run-dir runs/pilot_01
python -m unittest discover -s tests -v
```

各阶段的 `fetch_summary.json`、`label_summary.json`、`manual_review_summary.json`、`join_check.json` 与合并后的 `run_summary.json` 保留在同一运行目录，可与上表逐项对照。
