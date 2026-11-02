# B 阶段：仓库元数据、AI 标签与人工复核

对应 [`../a_data_pipeline/B_接手指南.md`](../a_data_pipeline/B_接手指南.md) 的第一轮任务：**给 A 的仓库清单补充仓库 API 元数据 → 按规则打 AI 标签 → 人工复核 → 按 `repo_id` 接回事件表**。

本目录的产出是 `group_project/` 结构里的 `b_repo_metadata/`。所有结果都能从代码和原始响应重跑；仓库根目录对应 `group_project/`，因此事件表路径与 A 的交接目录直接对齐。

## 一分钟了解这次跑出了什么

| 项目 | 结果 |
|---|---|
| 试跑名单 | 50 个仓库：40 个随机抽样 + 10 个名称关键词过采样（固定种子 `5488`） |
| 元数据获取 | 43 个成功（ID 一致）、2 个 ID 不一致、5 个 404；共 50 次 API 调用 |
| AI 标签 | `included` 3、`excluded` 22、`uncertain` 25（规则 `ai_rules_v0.1`） |
| 人工复核 | 33 条：included 全查 3、excluded 抽 5、uncertain 全查 25；自动与人工在已判定行一致率 6/8 |
| 接回事件表 | 50/50 个试点仓库都能按 `repo_id` 匹配到 A 的 `events_clean.parquet`（197,313 条事件中 159 条属于这 50 个仓库） |
| 离线测试 | 26 项全部通过（不联网） |

详细数字、验收清单与未解决问题见 [RESULTS.md](RESULTS.md)；规则本身见 [rules/ai_rules_v0.1.md](rules/ai_rules_v0.1.md)。

## 交付物结构

```text
b_repo_metadata/
├── README.md                          ← 本页
├── RESULTS.md                         ← 本次试跑的数字、验收清单、遗留问题
├── config/pilot.json                  ← 种子、分层规模、API 参数、规则文件路径
├── rules/
│   ├── ai_rules_v0.1.md               ← 规则说明（人读）
│   └── ai_rules_v0.1.json             ← 规则实现（机读，改规则只改这里）
├── reviews/pilot_01_decisions.json    ← 人工判断与理由（B 写）
├── bmeta/                             ← 实现包（与 A 的 gharchive_a 对应）
│   ├── common.py                      ← 路径、CSV/JSON、UTC、run_summary 合并
│   ├── select.py                      ← 分层抽样与名称粗筛
│   ├── api.py                         ← GitHub REST 客户端（重试/限流/分类）
│   ├── fetch.py                       ← 抓取、缓存、续跑、失败记录
│   ├── rules.py                       ← 规则执行与理由生成
│   ├── label.py                       ← 标签表与标签摘要
│   ├── review.py                      ← 复核清单生成与人工判断合并
│   ├── evidence.py                    ← 复核用 README 证据
│   └── join.py                        ← 按 repo_id 接回事件表
├── scripts/                           ← 命令入口（每个步骤一个）
├── tests/test_b_pipeline.py           ← 26 项离线验证
└── runs/
    ├── debug_api_sample/              ← 单仓库连通性样例（apache/superset）
    │   ├── api_sample_check.json
    │   └── raw_api/39464018.json
    └── pilot_01/
        ├── pilot_candidates.csv       ← 冻结的首批名单（含 sample_stratum）
        ├── selection.json             ← 选取方法、种子、输入/输出 SHA-256
        ├── raw_api/<repo_id>.json      ← 每个仓库的原始响应信封
        ├── repo_metadata.csv          ← 每仓库一行，失败行保留状态
        ├── repo_ai_labels.csv         ← 每仓库一行的 AI 标签与理由
        ├── manual_review.csv          ← 33 条复核对象、人工结论与一致率
        ├── manual_review_readmes.jsonl← 复核时看过的 README 摘要与哈希
        ├── repo_labels_joined_events.csv
        ├── fetch_log.jsonl / fetch_summary.json / label_summary.json
        ├── join_check.json
        └── run_summary.json           ← 输入、版本、数量、检查与未解决问题
```

## 怎么重跑

依赖：Python 3.10+（只用标准库；读取 A 的 Parquet 需要 pyarrow）。在 `b_repo_metadata/` 下执行：

```bash
# 1. 固定首批名单（已存在时会拒绝覆盖，需要 --force）
python scripts/build_pilot.py

# 2. 取元数据：token 通过环境变量读取，不写进任何文件
#    macOS/Linux: export GITHUB_TOKEN=...
#    Windows:     set GITHUB_TOKEN=...
python scripts/fetch_metadata.py

# 3. 按规则打标签
python scripts/label_repositories.py

# 4. 人工复核：先生成清单，再合并判断（本仓库已包含完成的判断文件）
python scripts/manual_review.py --run-dir runs/pilot_01
python scripts/manual_review.py --run-dir runs/pilot_01 \
    --decisions reviews/pilot_01_decisions.json

# 5. 接回 A 的事件表并核对；没有 pyarrow 时自动回退到候选表计数
python scripts/join_check.py

# 6. 汇总与验收检查
python scripts/build_run_summary.py --run-dir runs/pilot_01
```

单仓库连通性样例（指南要求的“先跑通 1 个仓库”，核对 `id=39464018`）：

```bash
python scripts/check_api_sample.py
```

复核用的 README 证据可重新抓取（可选，已有结果可直接复核）：

```bash
python scripts/fetch_readme_evidence.py --run-dir runs/pilot_01
```

不带 token 也能跑，但匿名配额是每小时 60 次；配额用尽时脚本会停在当前仓库之前并保留已完成结果，重新执行同一命令即可续跑。

## 输出字段

`repo_metadata.csv`（与指南建议字段一致）：

| 字段 | 说明 |
|---|---|
| `repo_id` | A 的仓库主键，B 全程保留 |
| `observed_repo_name` | 小时档案里观察到的 `owner/repo` |
| `api_repo_id` | 仓库 API 返回的 `id`；与 `repo_id` 一致才采用元数据 |
| `current_full_name` | 抓取时的当前全名（可能已被改名） |
| `repo_created_at` | API 的 `created_at`，UTC；**不是** `first_observed_at` |
| `description` / `topics_json` / `language` / `archived` | 抓取时的快照；`topics_json` 是 JSON 数组文本 |
| `fetch_status` | `ok` / `ok_cached` / `not_found` / `id_mismatch` / `http_error` / `server_error` / `network_error` / `invalid_json` |
| `http_status` | 最近一次 HTTP 状态码 |
| `fetched_at_utc` | 获取成功时的时间；失败留空（失败时间在 `fetch_log.jsonl`） |

`repo_ai_labels.csv`：`repo_id`、`ai_label`（`included`/`excluded`/`uncertain`）、`reason`、`rule_version`、`rule_id`（便于统计）、`metadata_fetched_at_utc`、`labelled_at_utc`。`reason` 以规则 ID 开头，后面是命中的 topic/关键词/状态，例如 `R4_topic_match:topics=llm`。

## 处理约定

- **ID 一致性**：只有 API 返回 `id` 与 A 的 `repo_id` 相等时，才把响应内容当作该仓库的元数据；不一致时元数据列留空、状态写 `id_mismatch`。
- **失败不猜**：404 只记录“无法获取”，不推断为删除、私有化或非 AI；这类仓库的标签保持 `uncertain`。
- **快照语义**：描述、topics 是 2026-11-02 的状态，不是 2024-01-15 事件发生时的状态。
- **缓存优先**：`raw_api/` 有可用的原始响应时不再重复请求，重跑是幂等的；需要强制刷新时加 `--force-refresh`。
- **token 只走环境变量**：`config/pilot.json` 只写变量名 `GITHUB_TOKEN`，代码与运行产物都不落盘 token。

## 与 A、C 的接口

- 对 A：只用 `repo_id` 作为连接键；事件表里仓库名可能是历史名，不能用来 join。
- 对 C：`repo_ai_labels.csv` 一行一个仓库，可直接按 `repo_id` 合并到月度活动表；`join_check.json` 记录了本次试点覆盖的事件条数与未匹配情况。

## 测试

```bash
python -m unittest discover -s tests -v
```

测试覆盖名单抽样的确定性、规则各分支、抓取层的 200/404/ID 不一致/限流/缓存、复核合并的校验，以及接回事件表的计数与唯一性；全部离线，不需要 token。

## 已知限制

- 首批 50 个是分层样本（其中 10 个按名称过采样），**不能**用来估计整个 GitHub 的 AI 仓库比例。
- 规则 v0.1 未覆盖个人主页仓库、课程作业与“AI 只是附加功能”的边界，复核差异已记录，留给 v0.2。
- 事件覆盖只有 2024-01-15 UTC 00:00–01:00 这一个小时，生命周期分析要等 A 扩展时间窗后重跑。
- README 证据是复核辅助材料，会随时间变化；规则本身不依赖它。
