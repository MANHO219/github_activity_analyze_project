# B 第一轮试跑结果（pilot_01）

**首次运行：** 2026-11-02（UTC 05:02–05:35），规则 `ai_rules_v0.1`
**规则迭代：** 2026-11-02（UTC 08:00–08:40），规则 `ai_rules_v0.2`，同一批 50 个仓库重跑标签
**环境：** Windows 11，Python 3.12.14，标准库 + pyarrow 26.0.0（仅用于读取 A 的 Parquet）
**运行目录：** [`runs/pilot_01/`](runs/pilot_01/)，汇总见 [`run_summary.json`](runs/pilot_01/run_summary.json)

## 1. 本次数字

| 项目 | 实测结果 |
|---|---|
| A 的候选清单 | 69,768 行 / 69,768 个唯一 `repo_id`，SHA-256 `e11f5c20990233b45fa8fabe4e0eeeed401baceaaf6f108e1d2d3c6d463c0b09` |
| 首批名单 | 50 个：随机 40 + 名称关键词 10，种子 `5488`，SHA-256 `e9de060d26ded56bb841fe6a449bc409f55eb5a86125f279efa7bea170d3a9c8` |
| 元数据获取 | 43 `ok` + 2 `id_mismatch` + 5 `not_found` = 50；API 调用 50 次，pending 0 |
| AI 标签 v0.1 | `included` 3 + `excluded` 22 + `uncertain` 25 = 50 |
| AI 标签 v0.2（当前） | `included` 1 + `excluded` 30 + `uncertain` 19 = 50 |
| 人工复核 | 33 条：included 3（全查）、excluded 5（抽样）、uncertain 25（全查） |
| 与人工一致率（已判定行） | v0.1 6/8 = 75% → v0.2 14/14 = 100% |
| 接回 A 的事件表 | 50/50 个试点仓库按 `repo_id` 匹配；197,313 条事件中 159 条属这 50 个仓库 |
| 离线测试 | 44 项通过 |

v0.2 的规则分布：

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

- 缓存策略：**只复用 HTTP 200 的成功响应**；404、5xx、无效 JSON 会保留为证据但下次重新请求。
- 核对方式：把 `pilot_01` 的名单与 `raw_api/` 复制到临时目录重跑 `fetch_metadata.py`。
- 实测：43 个成功响应 + 2 个 ID 不一致命中缓存，5 个 404 重新请求，共 **5 次 API 调用**、0 个 pending。
- 需要复现失败快照时用 `--reuse-failed`，此时也命中缓存（0 次调用）。
- 记录：[`cache_retry_check.json`](runs/pilot_01/cache_retry_check.json)。

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
| 规则、标签理由和人工复核记录齐全；入选/排除各复核 5 个，不足时全查；存疑案例单独复核 | ✅ | 两版规则 JSON/MD、每行 `reason`、`manual_review.csv`（33 条） |
| 能按 `repo_id` 接回 A 的事件表；带标签的仓库表一仓库一行 | ✅ | `join_check.json`：50/50 命中，覆盖 159 条事件，唯一性检查通过 |
| 交回代码、运行命令和依赖；另一位组员能按说明重跑 | ✅ | `README.md` 的“怎么重跑”；44 项离线测试；缓存策略可复跑 |

## 8. 未解决与待确认

1. **规则口径**（今晚确认）：弱信号 + 非 AI 描述是否直接 `excluded`；仅集成 AI 功能是否纳入；README 能否作为规则输入；课程作业边界。见 `rules/ai_rules_v0.2.md` 第 6 节。
2. **标签口径**（今晚确认）：分析用标签采用 `manual_override` 还是 `auto_only`；`uncertain` 保留还是并入 `excluded`。见 `LABELS.md` 第 5 节。
3. 元数据是 2026-11-02 的快照，不等于 2024-01-15 的仓库状态。
4. 50 个仓库是分层小样本，不能估计 GitHub 整体 AI 仓库比例。
5. 事件覆盖仍只有 1 小时（197,313 条），试点仓库覆盖 159 条，无法支持生命周期结论。

## 9. 复跑记录

```bash
cd b_repo_metadata
python scripts/build_pilot.py                 # 名单已冻结，重跑会拒绝覆盖
python scripts/fetch_metadata.py              # 成功缓存命中；失败响应会重新请求
python scripts/label_repositories.py          # 默认 v0.2
python scripts/compare_label_versions.py --run-dir runs/pilot_01
python scripts/build_analysis_labels.py --run-dir runs/pilot_01
python scripts/manual_review.py --run-dir runs/pilot_01 --decisions reviews/pilot_01_decisions.json
python scripts/join_check.py
python scripts/build_run_summary.py --run-dir runs/pilot_01
python -m unittest discover -s tests -v
```

各阶段摘要（`fetch_summary.json`、`label_summary.json`、`label_comparison.json`、`label_analysis_summary.json`、`manual_review_summary.json`、`join_check.json`）与合并后的 `run_summary.json` 都在同一运行目录，可与上表逐项对照。
