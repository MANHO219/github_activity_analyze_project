# B 阶段：仓库元数据、AI 标签与人工复核

对应 [`../a_data_pipeline/B_接手指南.md`](../a_data_pipeline/B_接手指南.md) 的第一轮任务：**给 A 的仓库清单补充仓库 API 元数据 → 按规则打 AI 标签 → 人工复核 → 按 `repo_id` 接回事件表**。

本目录的产出是 `group_project/` 结构里的 `b_repo_metadata/`。所有结果都能从代码和原始响应重跑；仓库根目录对应 `group_project/`，因此事件表路径与 A 的交接目录直接对齐。

## 一分钟了解这次跑出了什么

| 项目 | 结果 |
|---|---|
| 试跑名单 | pilot_01：50 个（40 随机 + 10 名称关键词）；pilot_02：200 个（160 随机 + 40 名称关键词，排除首轮 50） |
| 元数据获取 | pilot_01：43 成功 / 2 ID 不一致 / 5 个 404；pilot_02：163 成功 / 6 ID 不一致 / 31 个 404（各 200 次调用） |
| AI 标签（规则 v0.3.3.1） | pilot_01：`included` 4、`excluded` 32、`uncertain` 14；pilot_02：20 / 79 / 101 |
| pilot_02 分层分布 | 160 随机：3 / 70 / 87；40 关键词：17 / 9 / 14 |
| 与 v0.2 对比 | pilot_01：5 条标签变化 + 5 条仅理由变化；README 补足 3 个 AI 项目、1 个课程仓库 |
| v0.3.1 → v0.3.2 | pilot_01 0 条；pilot_02 2 条（修复 whisper 子串与中文边界） |
| v0.3.2 → v0.3.3 | pilot_01 6 条、pilot_02 22 条 `uncertain → excluded`（README 确认主体非 AI） |
| v0.3.3 → v0.3.3.1 | 4 条、17 条 `excluded → uncertain`（R12 要求用途说明、只对 R7 生效） |
| 与人工复核 | pilot_01 复核样本中自动已判定的 17 条全部与人工一致；只代表 33 条复核样本 |
| 人工复核 | pilot_01：33 条；pilot_02：抽查 13 条（included 3 / excluded 5 / uncertain 5） |
| 分析用标签 | pilot_01 人工优先：4 / 38 / 8（人工 33 行、自动 17 行） |
| 接回事件表 | pilot_01：50/50 命中，覆盖 159 / 197,313 条；pilot_02：200/200 命中，覆盖 1,072 / 5,528,300 条 |
| 离线测试 | 86 项全部通过（不联网） |

详细数字、验收清单与遗留问题见 [RESULTS.md](RESULTS.md)；当前规则见 [rules/ai_rules_v0.3.3.1.md](rules/ai_rules_v0.3.3.1.md)；标签交接口径见 [LABELS.md](LABELS.md)。

## 交付物结构

```text
b_repo_metadata/
├── README.md                          ← 本页
├── RESULTS.md                         ← 本次试跑的数字、验收清单、遗留问题
├── LABELS.md                          ← 自动标签、人工复核、分析用标签的区别与生成方式
├── config/pilot.json                  ← 种子、分层规模、API 参数、当前规则文件
├── rules/
│   ├── ai_rules_v0.1.md / .json       ← 第一版（保留，用于对比）
│   ├── ai_rules_v0.2.md / .json       ← 第二版（保留，用于对比）
│   ├── ai_rules_v0.3.md / .json       ← 第三版：五条口径、README 辅助
│   ├── ai_rules_v0.3.1.md / .json     ← 第四版：README 判 AI/个人主页收紧
│   ├── ai_rules_v0.3.2.md / .json     ← 第五版：名称词边界与中英相邻修复
│   ├── ai_rules_v0.3.3.md / .json     ← 第六版：README 确认主体非 AI
│   └── ai_rules_v0.3.3.1.md / .json   ← 当前版本：R12 需用途证据、旧版本不触发
├── reviews/pilot_01_decisions.json    ← 第一轮人工判断与理由（不覆盖）
├── reviews/pilot_01_revision_check_v0.3.json ← 新口径对旧判断的影响检查
├── bmeta/                             ← 实现包（与 A 的 gharchive_a 对应）
│   ├── common.py                      ← 路径、CSV/JSON、UTC、run_summary 合并
│   ├── select.py                      ← 分层抽样与名称粗筛
│   ├── api.py                         ← GitHub REST 客户端（重试/限流/分类）
│   ├── fetch.py                       ← 抓取、缓存、续跑、失败记录
│   ├── rules.py                       ← 规则引擎（v1/v2/v3，含中英/名称规范化）
│   ├── label.py                       ← 标签表与标签摘要
│   ├── compare.py                     ← 规则版本对比与人工一致率
│   ├── handoff.py                     ← 自动标签 + 人工判断 → 分析用标签
│   ├── review.py                      ← 复核清单生成与人工判断合并
│   ├── evidence.py                    ← 复核用 README 证据
│   └── join.py                        ← 按 repo_id 接回事件表
├── scripts/                           ← 命令入口（每个步骤一个）
├── tests/test_b_pipeline.py           ← 86 项离线验证
└── runs/
    ├── debug_api_sample/              ← 单仓库连通性样例（apache/superset）
    ├── pilot_01/                      ← 50 个仓库的首轮试跑
    │   ├── pilot_candidates.csv       ← 冻结的首批名单（含 sample_stratum）
    │   ├── selection.json             ← 选取方法、种子、输入/输出 SHA-256
    │   ├── raw_api/<repo_id>.json      ← 每个仓库的原始响应信封
    │   ├── repo_metadata.csv          ← 每仓库一行，失败行保留状态
    │   ├── repo_ai_labels.csv         ← 当前规则（v0.3.3）的标签
    │   ├── repo_ai_labels_v0.1…v0.3.2.csv ← 旧版标签（保留）
    │   ├── label_changes.csv          ← v0.3.1 → v0.3.2 的逐条变化
    │   ├── label_comparison.json      ← 混淆矩阵、人工一致率、改进/回退清单
    │   ├── repo_ai_labels_analysis.csv← 分析用标签（含来源与人工值）
    │   ├── manual_review.csv          ← 33 条复核对象、人工结论与一致率
    │   ├── manual_review_readmes.jsonl← 复核时看过的 README 摘要与哈希
    │   ├── repo_labels_joined_events.csv
    │   ├── cache_retry_check.json     ← 失败缓存重试策略的核对记录
    │   ├── fetch_log.jsonl / fetch_summary.json / label_summary.json
    │   ├── join_check.json
    │   └── run_summary.json           ← 输入、版本、数量、检查与未解决问题
    └── pilot_02/                      ← 200 个仓库的扩大试跑（160 随机 + 40 关键词）
        ├── pilot_candidates.csv       ← 排除首轮 50 后的抽样名单
        ├── selection.json             ← 输入 852,777 行、种子 5488、排除 50
        ├── raw_api/<repo_id>.json      ← 200 个仓库的原始响应
        ├── repo_metadata.csv / repo_ai_labels.csv
        ├── readme_evidence.jsonl      ← 200 个仓库的 README 快照（138 个可读）
        ├── label_changes.csv          ← v0.3.1 → v0.3.2 的 2 条变化
        ├── manual_review_pilot02.csv  ← 抽查 13 条的结论与备注
        ├── repo_labels_joined_events.csv
        ├── join_check.json
        └── pilot_02_summary.json      ← 抽样、API、标签、接回、核对汇总
```

## 怎么重跑：先分清“复现”和“开新一轮”

依赖：Python 3.10+（只用标准库；读取 A 的 Parquet 需要 pyarrow）。以下命令都在 `b_repo_metadata/` 下执行。

先把目的说清楚：`runs/pilot_01/manual_review.csv` 里的 33 条人工判断是在 **v0.1 自动标签**上做的。复现步骤要原样保留这批判断、只把判断合并回去，再用 `compare_label_versions.py` 把它与 **v0.2 自动标签**对比；**不是**基于 v0.2 重新抽样复核。想按新规则重新抽样时，用下面 B 节。

（旧版本 README 与已关闭的 PR #1 里曾把“生成清单”和“合并判断”两条命令连写，那会先按当前规则重算名单、再因 repo_id 不匹配而报错；以下流程已修正，以本页为准。）

### A. 复现本次成果（推荐；不覆盖已有复核记录）

```bash
# 1. 固定首批名单。已存在会拒绝覆盖，直接跳过即可
python scripts/build_pilot.py

# 2. 取元数据：token 通过环境变量读取，不写进任何文件
#    macOS/Linux: export GITHUB_TOKEN=...
#    Windows:     set GITHUB_TOKEN=...
python scripts/fetch_metadata.py

# 3. 按规则打标签（默认 ai_rules_v0.3；存在复核 README 证据时自动用于补足 uncertain）
python scripts/label_repositories.py

# 4. 与上一版规则对比（需要旧标签表 repo_ai_labels_v0.2.csv）
python scripts/compare_label_versions.py --run-dir runs/pilot_01 \
    --old runs/pilot_01/repo_ai_labels_v0.2.csv --new runs/pilot_01/repo_ai_labels.csv

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

第 6 步有三个约束：只读取已有清单、把判断写回去，不会因为当前规则是 v0.3 就重新抽样；清单必须已存在，**缺失时直接以退出码 5 报错，不会自动生成**（复现时若误删，先用 `git checkout -- runs/pilot_01/manual_review.csv` 取回）；它会把清单里的自动标签与当前标签做差异统计，写进摘要的 `sheet_auto_labels_differ_from_current`，提醒你人工一致率对应的是清单生成时的规则，而不是当前规则。

**不要**在这里先运行不带 `--decisions` 的 `manual_review.py`：那个命令是“生成新清单”，目标目录已有 `manual_review.csv` 时会直接报错退出（这是保护措施，加 `--force` 才会覆盖）。确实需要在缺清单时临时生成再合并，得显式加 `--allow-new-sheet`，摘要会标记这次是“生成后合并”，提示可能混轮次。

`manual_review_summary.json` 里版本字段分开记录：`labels_rule_version` 是本次读取的标签版本（v0.2），`sheet_rule_version` 是生成清单的版本（复用旧清单时记为 `unknown_existing_sheet`）。不要用后者之外的信息推断复核依据。

### B. 创建新一轮复核清单（换输出目录，不动 pilot_01）

如果规则已更新、想按当前标签重新抽样核对，把清单写到新目录，输入显式指向已有运行目录：

```bash
python scripts/manual_review.py \
    --run-dir runs/pilot_02_review \
    --labels runs/pilot_01/repo_ai_labels.csv \
    --metadata runs/pilot_01/repo_metadata.csv
```

生成 `runs/pilot_02_review/manual_review.csv` 与摘要，`runs/pilot_01/` 不受影响。清单写完后把判断存成新的 decisions 文件，再用同一命令加 `--decisions` 合并（这一次清单已存在，走的是合并模式）；如果判断文件的 `repo_id` 不在清单里，脚本会报错（退出码 4）并提示换目录。

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

## 扩大试跑 pilot_02（200 个仓库）

数据来自 A README 的全天生成命令：`python scripts/run_sample.py --date 2024-01-15 --hours 0-23 --run-dir runs/20240115_python`（在 `a_data_pipeline/` 下，约 52 分钟：下载 4.7 分钟、inspection 21.3 分钟、清洗导出 26.6 分钟）。结果 5,528,300 条事件、852,777 个仓库，与 A 的交接数量一致。

抽样：排除 pilot_01 的 50 个，从全天候选里用种子 5488 抽 160 个随机 + 40 个名称命中，共 200 个。命令：

```bash
python scripts/build_pilot.py --out-dir runs/pilot_02 \
    --candidates ../a_data_pipeline/runs/20240115_python/python/repo_candidates.csv \
    --exclude runs/pilot_01/pilot_candidates.csv \
    --random-size 160 --keyword-size 40 --seed 5488
python scripts/fetch_metadata.py --run-dir runs/pilot_02
python scripts/fetch_readme_evidence.py --run-dir runs/pilot_02 \
    --input runs/pilot_02/pilot_candidates.csv --out runs/pilot_02/readme_evidence.jsonl
python scripts/label_repositories.py --run-dir runs/pilot_02 \
    --readme-evidence runs/pilot_02/readme_evidence.jsonl
python scripts/join_check.py --run-dir runs/pilot_02 \
    --daily-csv ../a_data_pipeline/runs/20240115_python/python/repo_daily_counts.csv
```

结果（全部在 `runs/pilot_02/pilot_02_summary.json`）：

| 项目 | 结果 |
|---|---|
| 元数据 API | 200 次调用、163 成功、31 个 404、6 个 ID 不一致、120 秒 |
| README 证据 | 200 次请求、138 可读、62 无 README/404、128 秒 |
| 标签分布（160 随机） | included 3 / excluded 70 / uncertain 87 |
| 标签分布（40 关键词） | included 17 / excluded 9 / uncertain 14 |
| 接回全天活动表 | 200/200 命中，覆盖 1,072 / 5,528,300 条事件 |
| 全部 200 | included 20 / excluded 79 / uncertain 101（其中 5 条由 R12 排除） |
| 人工抽查 | 13 条：included 3、excluded 5、uncertain 5 |

抽查发现并修复了两处规则 bug（v0.3.2）：`Whispering-Origin-2D` 曾被当成 `whisper`（名称子串误判），中文“用Resnet101+GPT搭建…的AI”曾因 `\b` 在中文里失效被漏判。A 对两个边界案例给出判定：Etherscan-ML 按训练营项目人工排除（规则仍判 included，分析表按人工优先）；CoreELEC/xbmc 由 R12 自动排除。R12 在 v0.3.3.1 收紧为“README 必须说明项目用途、只对描述为空的仓库生效”，模板与只有安装说明的 README 不再排除。

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

`repo_ai_labels.csv`（v0.3）：`repo_id`、`ai_label`、`reason`、`rule_version`、`rule_id`、`metadata_fetched_at_utc`、`labelled_at_utc`，以及 README 辅助字段 `readme_evidence`（`used` / `no_signal` / 空）、`readme_sha256`、`readme_fetched_at_utc`。`reason` 以规则 ID 开头，例如 `R5b_weak_signal_corroborated:weak=ai_token;corroboration=sdk_api`，README 相关的一行形如 `R9_readme_ai:readme=llm,machine_learning`。

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

- 当前规则 `ai_rules_v0.3.3.1`：R12 要求 README 能说明项目用途（About/Overview 或“X is a …”），只对描述与 topics 都为空的仓库生效；模板、安装说明、名称或弱信号冲突都继续 uncertain。旧版规则文件没有 `readme_rules.non_ai` 时不会触发 R12。
- 各版本规则与标签表都保留；pilot_01 的 `label_changes.csv` 是 v0.3.2→v0.3.3（6 条），pilot_02 的是同版本对比（22 条）。
- 新口径对第一轮人工判断的影响检查见 `reviews/pilot_01_revision_check_v0.3.json`：无需改判，旧判断不覆盖。

## 与 A、C 的接口

- 对 A：只用 `repo_id` 作为连接键；事件表里仓库名可能是历史名，不能用来 join。
- 对 C：优先使用 `repo_ai_labels_analysis.csv`，其中 `label_source` 标明每行是规则判定还是人工判定；`join_check.json` 记录本次试点覆盖的事件条数与未匹配情况。

## 测试

```bash
python -m unittest discover -s tests -v
```

测试覆盖名单抽样的确定性与排除、v0.1/v0.2/v0.3/v0.3.1 规则各分支、README 辅助判断（强/弱证据、未来意图、个人主页与工程章节、补足但不覆盖）、抓取层的 200/404/ID 不一致/限流/失败缓存策略、复核合并的校验、版本对比与口径合并，以及接回事件表的计数与两个占比分母；全部离线，不需要 token。

## 已知限制

- 首批 50 个是分层样本（其中 10 个按名称过采样），**不能**用来估计整个 GitHub 的 AI 仓库比例。
- v0.3.1 仍有 16 个 `uncertain`：8 个元数据缺失/空仓库，其余是弱信号、个人主页无文字证据、README 也无判据的仓库。
- `17/17 = 100%` 只表示**当前复核样本中自动已判定的 17 条**与人工一致，不是整体分类准确率；复核只覆盖 33 个仓库。
- 事件覆盖只有 2024-01-15 UTC 00:00–01:00 这一个小时，生命周期分析要等 A 扩展时间窗后重跑。
- README 证据是复核与标注的辅助材料，会随时间变化；每行记录了快照时间与哈希，但 README 内容本身可能已变。
