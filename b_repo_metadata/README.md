# B 阶段：仓库元数据、AI 标签与人工复核

对应 [`../a_data_pipeline/B_接手指南.md`](../a_data_pipeline/B_接手指南.md) 的第一轮任务：**给 A 的仓库清单补充仓库 API 元数据 → 按规则打 AI 标签 → 人工复核 → 按 `repo_id` 接回事件表**。

本目录的产出是 `group_project/` 结构里的 `b_repo_metadata/`。所有结果都能从代码和原始响应重跑；仓库根目录对应 `group_project/`，因此事件表路径与 A 的交接目录直接对齐。

## 一分钟了解这次跑出了什么

| 项目 | 结果 |
|---|---|
| 试跑名单 | 50 个仓库：40 个随机抽样 + 10 个名称关键词过采样（固定种子 `5488`） |
| 元数据获取 | 43 个成功（ID 一致）、2 个 ID 不一致、5 个 404；共 50 次 API 调用 |
| AI 标签（规则 v0.2） | `included` 1、`excluded` 30、`uncertain` 19 |
| 与 v0.1 对比 | 9 条标签变化 + 2 条仅规则理由变化；与人工结论的一致率从 75% 提升到 100%，无回退 |
| 人工复核 | 33 条：included 全查 3、excluded 抽 5、uncertain 全查 25 |
| 分析用标签 | 默认“人工优先”口径下：included 4、excluded 38、uncertain 8（人工 33 行、自动 17 行） |
| 接回事件表 | 50/50 个试点仓库都能按 `repo_id` 匹配到 A 的 `events_clean.parquet`（197,313 条事件中 159 条属于这 50 个仓库） |
| 离线测试 | 50 项全部通过（不联网） |

详细数字、验收清单与遗留问题见 [RESULTS.md](RESULTS.md)；规则见 [rules/ai_rules_v0.2.md](rules/ai_rules_v0.2.md)；标签交接口径见 [LABELS.md](LABELS.md)。

## 交付物结构

```text
b_repo_metadata/
├── README.md                          ← 本页
├── RESULTS.md                         ← 本次试跑的数字、验收清单、遗留问题
├── LABELS.md                          ← 自动标签、人工复核、分析用标签的区别与生成方式
├── config/pilot.json                  ← 种子、分层规模、API 参数、当前规则文件
├── rules/
│   ├── ai_rules_v0.1.md / .json       ← 第一版规则（保留，用于对比）
│   └── ai_rules_v0.2.md / .json       ← 当前版本：弱信号、课程作业、个人主页识别
├── reviews/pilot_01_decisions.json    ← 人工判断与理由（B 写）
├── bmeta/                             ← 实现包（与 A 的 gharchive_a 对应）
│   ├── common.py                      ← 路径、CSV/JSON、UTC、run_summary 合并
│   ├── select.py                      ← 分层抽样与名称粗筛
│   ├── api.py                         ← GitHub REST 客户端（重试/限流/分类）
│   ├── fetch.py                       ← 抓取、缓存、续跑、失败记录
│   ├── rules.py                       ← 规则引擎（v1/v2 两代）
│   ├── label.py                       ← 标签表与标签摘要
│   ├── compare.py                     ← 规则版本对比与人工一致率
│   ├── handoff.py                     ← 自动标签 + 人工判断 → 分析用标签
│   ├── review.py                      ← 复核清单生成与人工判断合并
│   ├── evidence.py                    ← 复核用 README 证据
│   └── join.py                        ← 按 repo_id 接回事件表
├── scripts/                           ← 命令入口（每个步骤一个）
├── tests/test_b_pipeline.py           ← 50 项离线验证
└── runs/
    ├── debug_api_sample/              ← 单仓库连通性样例（apache/superset）
    └── pilot_01/
        ├── pilot_candidates.csv       ← 冻结的首批名单（含 sample_stratum）
        ├── selection.json             ← 选取方法、种子、输入/输出 SHA-256
        ├── raw_api/<repo_id>.json      ← 每个仓库的原始响应信封
        ├── repo_metadata.csv          ← 每仓库一行，失败行保留状态
        ├── repo_ai_labels.csv         ← 当前规则（v0.2）的标签
        ├── repo_ai_labels_v0.1.csv    ← v0.1 原始标签（保留）
        ├── label_changes.csv          ← v0.1 → v0.2 的逐条变化与原因
        ├── label_comparison.json      ← 混淆矩阵、人工一致率、改进/回退清单
        ├── repo_ai_labels_analysis.csv← 分析用标签（含来源与人工值）
        ├── label_analysis_summary.json
        ├── manual_review.csv          ← 33 条复核对象、人工结论与一致率
        ├── manual_review_readmes.jsonl← 复核时看过的 README 摘要与哈希
        ├── repo_labels_joined_events.csv
        ├── cache_retry_check.json     ← 失败缓存重试策略的核对记录
        ├── fetch_log.jsonl / fetch_summary.json / label_summary.json
        ├── join_check.json
        └── run_summary.json           ← 输入、版本、数量、检查与未解决问题
```

## 怎么重跑：先分清“复现”和“开新一轮”

依赖：Python 3.10+（只用标准库；读取 A 的 Parquet 需要 pyarrow）。以下命令都在 `b_repo_metadata/` 下执行。

### A. 复现本次成果（推荐；不覆盖已有复核记录）

```bash
# 1. 固定首批名单。已存在会拒绝覆盖，直接跳过即可
python scripts/build_pilot.py

# 2. 取元数据：token 通过环境变量读取，不写进任何文件
#    macOS/Linux: export GITHUB_TOKEN=...
#    Windows:     set GITHUB_TOKEN=...
python scripts/fetch_metadata.py

# 3. 按规则打标签（默认使用 config 里的 ai_rules_v0.2）
python scripts/label_repositories.py

# 4. 与上一版规则对比（需要旧标签表 repo_ai_labels_v0.1.csv）
python scripts/compare_label_versions.py --run-dir runs/pilot_01

# 5. 生成分析用标签（人工优先；可换 --policy auto_only）
python scripts/build_analysis_labels.py --run-dir runs/pilot_01

# 6. 合并已有复核记录（关键：带 --decisions，复用 runs/pilot_01 里现有的 33 行清单）
python scripts/manual_review.py --run-dir runs/pilot_01 \
    --decisions reviews/pilot_01_decisions.json

# 7. 接回 A 的事件表并核对；没有 pyarrow 时自动回退到候选表计数
python scripts/join_check.py

# 8. 汇总与验收检查
python scripts/build_run_summary.py --run-dir runs/pilot_01
```

第 6 步只读取已有清单、把判断写回去，不会因为当前规则是 v0.2 就重新抽样。

**不要**在这里先运行不带 `--decisions` 的 `manual_review.py`：那个命令是“生成新清单”，目标目录已有 `manual_review.csv` 时会直接报错退出（这是保护措施，加 `--force` 才会覆盖）。

### B. 创建新一轮复核清单（换输出目录，不动 pilot_01）

如果规则已更新、想按当前标签重新抽样核对，把清单写到新目录，输入显式指向已有运行目录：

```bash
python scripts/manual_review.py \
    --run-dir runs/pilot_02_review \
    --labels runs/pilot_01/repo_ai_labels.csv \
    --metadata runs/pilot_01/repo_metadata.csv
```

生成 `runs/pilot_02_review/manual_review.csv` 与摘要，`runs/pilot_01/` 不受影响。清单写完后把判断存成新的 decisions 文件，再用同一命令加 `--decisions` 合并；如果判断文件的 `repo_id` 不在清单里，脚本会报错并提示换目录。

只有明确要覆盖同一目录时才用 `--force` —— 它会丢掉该目录已有的复核记录。

### C. 单仓库样例与复核证据

单仓库连通性样例（指南要求的“先跑通 1 个仓库”，核对 `id=39464018`）：

```bash
python scripts/check_api_sample.py
```

复核用的 README 证据可重新抓取（可选，已有结果可直接复核）：

```bash
python scripts/fetch_readme_evidence.py --run-dir runs/pilot_01
```

不带 token 也能跑，但匿名配额是每小时 60 次；配额用尽时脚本会停在当前仓库之前并保留已完成结果，重新执行同一命令即可续跑。

## 缓存与重试（重要）

- **只有 HTTP 200 且响应体是合法 JSON 的成功响应会被复用**。404、5xx、无效 JSON、以及没有响应体的网络错误/超时，都会留在 `raw_api/` 作为证据，但下次运行**重新请求**，避免一次临时故障被永久缓存成“查不到”。
- 想复现某次失败快照（例如离线核对 404 名单），加 `--reuse-failed`：此时失败响应（含没有 JSON 响应体的网络错误）也命中缓存，`api_calls=0`，状态按缓存里的错误重建。
- 核对记录见 `runs/pilot_01/cache_retry_check.json`：在副本上重跑时，43 个成功响应命中缓存、2 个 ID 不一致命中缓存、5 个 404 重新请求，共 5 次 API 调用。
- 配额用尽时整批停在当前仓库之前，已抓取结果已写盘；重新执行同一命令即可续跑。

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

`repo_ai_labels.csv`：`repo_id`、`ai_label`、`reason`、`rule_version`、`rule_id`、`metadata_fetched_at_utc`、`labelled_at_utc`。`reason` 以规则 ID 开头，例如 `R5b_weak_signal_corroborated:weak=ai_token;corroboration=sdk_api`。

`repo_ai_labels_analysis.csv`：在自动标签基础上增加 `ai_label_manual`、`ai_label_final`、`label_source`、`policy`，用于交接给 C。字段与口径说明见 [LABELS.md](LABELS.md)。

`repo_labels_joined_events.csv`：每个试点仓库一行，含 `event_count` 与两个不同分母的占比：

- `event_share_of_source`：分母是事件表**全部事件**（197,313）；
- `event_share_of_pilot_events`：分母是**50 个试点仓库的事件总数**（159）。

## 处理约定

- **ID 一致性**：只有 API 返回 `id` 与 A 的 `repo_id` 相等时，才把响应内容当作该仓库的元数据；不一致时元数据列留空、状态写 `id_mismatch`。
- **失败不猜**：404 只记录“无法获取”，不推断为删除、私有化或非 AI；这类仓库的标签保持 `uncertain`。
- **快照语义**：描述、topics 是 2026-11-02 的状态，不是 2024-01-15 事件发生时的状态。
- **token 只走环境变量**：`config/pilot.json` 只写变量名 `GITHUB_TOKEN`，代码与运行产物都不落盘 token。

## 规则版本

- 当前规则 `ai_rules_v0.2`：裸 `ai`/`ml` 降为弱信号（需佐证词）、新增课程作业与个人主页识别。
- 上一版 `ai_rules_v0.1` 与它的标签表都保留；两版的逐条差异在 `label_changes.csv`，汇总在 `label_comparison.json`。
- 待统一确认的口径（弱信号是否直接排除、AI 附加功能是否纳入、README 能否作为规则输入等）列在 `rules/ai_rules_v0.2.md` 第 6 节，确认后再出 v0.3。

## 与 A、C 的接口

- 对 A：只用 `repo_id` 作为连接键；事件表里仓库名可能是历史名，不能用来 join。
- 对 C：优先使用 `repo_ai_labels_analysis.csv`，其中 `label_source` 标明每行是规则判定还是人工判定；`join_check.json` 记录本次试点覆盖的事件条数与未匹配情况。

## 测试

```bash
python -m unittest discover -s tests -v
```

测试覆盖名单抽样的确定性、v0.1/v0.2 规则各分支、抓取层的 200/404/ID 不一致/限流/失败缓存策略、复核合并的校验、版本对比与口径合并，以及接回事件表的计数与两个占比分母；全部离线，不需要 token。

## 已知限制

- 首批 50 个是分层样本（其中 10 个按名称过采样），**不能**用来估计整个 GitHub 的 AI 仓库比例。
- v0.2 仍有 19 个 `uncertain`：8 个元数据缺失/空仓库，11 个需要 README 才能判断，而规则不读 README。
- 事件覆盖只有 2024-01-15 UTC 00:00–01:00 这一个小时，生命周期分析要等 A 扩展时间窗后重跑。
- README 证据是复核辅助材料，会随时间变化；规则本身不依赖它。
