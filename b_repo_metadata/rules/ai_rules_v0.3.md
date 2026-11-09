# AI 相关仓库判定规则 v0.3

- **规则版本：** `ai_rules_v0.3`（机器可读版本见 [ai_rules_v0.3.json](ai_rules_v0.3.json)）
- **上一版：** [`ai_rules_v0.2`](ai_rules_v0.2.md)（标签保留在 `repo_ai_labels_v0.2.csv`）
- **状态：** 按 A 确认的五条口径实现（2026-11-09）
- **依据：** pilot_01 的 33 条人工复核 + A 对口径的书面确认

## 1. 五条口径与本版实现

| A 确认的口径 | v0.3 实现 | 规则 ID |
|---|---|---|
| 弱信号配非 AI 描述默认保留 `uncertain` | 裸 `ai`/`ml` 仍是弱信号；没有佐证词时只记 `uncertain`，不排除 | `R4b` / `R5c` |
| 只有附加 AI 功能、主体不是 AI 的项目不纳入；AI 为核心（含调用模型 API）可纳入 | 只在描述**明确把 AI 写成附加能力**时排除；以 AI 为核心的 API 应用仍纳入 | `R5d_ai_feature_only` |
| 允许读 README 辅助判断 | 只补足规则判为 `uncertain` 的仓库，优先描述缺失/名称命中/证据冲突；保存快照时间与哈希 | `R9` / `R10` / `R11` |
| 学校课程、公开课、训练营作业同一标准排除，但要确认确实是作业 | 强语义（final-project、openclassrooms、capstone）可直接判定；泛词（course、lab、hw）必须有描述佐证 | `R3b_coursework` |
| 个人主页增加“无语言”辅助条件，疑似不算排除 | 同名 + 无描述 + 无 topics + 无语言 = 疑似，记 `uncertain`；README 明确是个人主页才排除 | `R3c` → `R11` |

## 2. 判定顺序

先命中先返回：

| 顺序 | 规则 ID | 触发条件 | 输出 |
|---|---|---|---|
| 1 | `R1_metadata_unavailable` | 元数据取不到 | `uncertain` |
| 2 | `R2_api_id_mismatch` | API 返回的 id 与 repo_id 不一致 | `uncertain` |
| 3 | `R3b_coursework` | 强语义名称，或描述有明确作业语义，或泛词名称 + 描述佐证 | `excluded` |
| 4 | `R3c_profile_suspected` | 同名 + 无描述 + 无 topics + 无语言 | `uncertain` |
| 5 | `R3_resource_collection` | awesome、教程、链接合集等 | `excluded` |
| 6 | `R5d_ai_feature_only` | 描述明确写 AI 是附加功能 | `excluded` |
| 7 | `R4_topic_match` | 命中强 topic | `included` |
| 8 | `R5_description_match` | 描述命中强关键词 | `included` |
| 9 | `R5b_weak_signal_corroborated` | 弱信号 + 佐证词 | `included` |
| 10 | `R4b_weak_topic_only` | 只有弱 topic | `uncertain` |
| 11 | `R5c_weak_signal_only` | 只有弱描述 | `uncertain` |
| 12 | `R6_name_only_signal` | 只有名称像 AI | `uncertain` |
| 13 | `R7_insufficient_text_evidence` | 描述与 topics 都为空 | `uncertain` |
| 14 | `R8_no_ai_signal` | 有文本但无 AI 信号 | `excluded` |

第 3 步的课程规则刻意收紧：`course`、`lab`、`hw` 这类词单独出现时**不排除**，必须有“assignment/homework/final project/course materials”等描述佐证，或名称本身是 `final-project`、`openclassrooms`、`capstone`。

## 3. README 辅助判断

只作用于规则判为 `uncertain` 的仓库，顺序为：

1. README 命中个人主页特征（自我介绍、`about me`、`eu sou` 等）→ `excluded`（`R11_readme_profile`）；
2. README 命中明确的课程语境（`this is a repository for ... course`、`course materials`、`bootcamp` 等）→ `excluded`（`R10_readme_coursework`）；
3. README 命中 AI 技术证据（强关键词/弱词皆可）→ `included`（`R9_readme_ai`）；
4. 都没有 → 维持 `uncertain`，记录 `readme_evidence=no_signal`。

约束：

- 规则已给出的 `included`/`excluded` 不会被 README 覆盖（`test_readme_does_not_override_decided_labels`）；
- 每行记录 `readme_evidence`（`used` / `no_signal`）、`readme_sha256`、`readme_fetched_at_utc`；
- README 证据来自 `runs/pilot_01/manual_review_readmes.jsonl`（复核时抓取，含抓取时间与哈希），标注时用 `--readme-evidence` 指定；信息不足就继续存疑。

## 4. 与 v0.2 的对比（同一批 50 个仓库）

| 指标 | v0.2 | v0.3 |
|---|---:|---:|
| `included` | 1 | 4 |
| `excluded` | 30 | 30 |
| `uncertain` | 19 | 16 |
| 与人工在已判定行的一致 | 14/14 | 17/17 |
| 人工推翻 | 0 | 0 |

共 10 条变化：5 条标签变化 + 5 条仅理由变化。

- 3 条 `uncertain → included`：README 证明是 AI 项目（AWS 通话摘要示例、scikit-learn 卡路里预测、PrivateGPT 风格应用）；
- 1 条 `uncertain → excluded`：README 确认是 MLOps 课程资料；
- 1 条 `excluded → uncertain`：个人主页改为“疑似”，README 只有统计图片、没有文字证据，按口径保留存疑；
- 5 条仅理由变化：个人主页从 `R3c` 排除改为 `R11`（README 确认后排除）。

逐条记录见 `runs/pilot_01/label_changes.csv`。

注意：`17/17 = 100%` 只表示**当前复核样本中自动已判定的 17 条**与人工一致，不是整体分类准确率；人工复核只覆盖 33 个仓库，其余 17 个由规则决定。

## 5. 仍然存疑的 16 条

1. 8 条元数据缺失或空仓库（5 个 404、2 个 ID 不一致、1 个 README 也不存在）；
2. 1 条个人主页疑似但 README 无文字证据（`tannerhawkins/tannerhawkins` 只有统计图片）；
3. 1 条弱信号（GROWI：描述没写 AI，保留存疑）；
4. 6 条其他（游戏 mod、作品集网站、实验室主页、HCL 服务骨架、已改名的个人主页等），README 未给出 AI 或课程证据。

## 6. 版本管理

1. 复制 `ai_rules_v0.3.json` 为下一版，只改 JSON 与版本号；
2. 用同一批输入重跑 `label_repositories.py`，并保留上一版标签表；
3. 用 `compare_label_versions.py` 生成变化清单；
4. 旧规则、旧标签、旧复核判断都不覆盖；新口径若影响人工判断，另存修订版（本次检查见 `reviews/pilot_01_revision_check_v0.3.json`）。
