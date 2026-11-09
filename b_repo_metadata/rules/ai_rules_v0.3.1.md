# AI 相关仓库判定规则 v0.3.1

- **规则版本：** `ai_rules_v0.3.1`（机器可读版本见 [ai_rules_v0.3.1.json](ai_rules_v0.3.1.json)）
- **上一版：** [`ai_rules_v0.3`](ai_rules_v0.3.md)（完整口径见该文档）
- **状态：** 按 A 对 v0.3 的两条反馈修正（2026-11-09）

v0.3.1 只改 README 辅助判断的两处，其他判定顺序、口径、规则 ID 全部沿用 v0.3。

## 1. README 判 AI：只认“核心证据”

v0.3 的实现只要 README 出现一次 `ai` 就纳入，A 指出这样会把“日历项目写以后打算加 AI”也算成 AI 项目。

v0.3.1 改成：

1. **先剔除未来意图行**：含 `plan / will / future / roadmap / coming soon / 计划 / 以后 / 打算 / 未来` 等字样的行不参与 AI 匹配；
2. **强证据直接纳入**：命中 `machine learning`、`llm`、`pytorch`、`transformer`、`computer vision` 等强关键词；
3. **弱证据要够多且有佐证**：只有 `ai`/`ml` 时，需在过滤后的文本中出现至少 3 次，且伴随 `model`、`chat`、`agent`、`api` 等佐证词，才判 `included`；
4. 否则维持 `uncertain`，写 `readme_evidence=no_signal`。

验证用例：

- “A calendar app. Roadmap: we plan to add AI features in 2027.” → `uncertain`；
- “A todo app. We use AI to sort tasks.”（仅一次弱词）→ `uncertain`；
- “AI assistant … The AI model … AI chat …”（三次弱词 + 佐证）→ `included`。

## 2. README 判个人主页：先确认“整篇像主页”

v0.3 只要 README 出现 `About me` / `Hi, I'm` 就排除，A 指出这会把机器学习项目里的作者介绍当成个人主页。

v0.3.1 改成两个条件同时满足才排除：

1. 规则本身已经判为个人主页疑似（`R3c_profile_suspected`：同名 + 无描述 + 无 topics + 无语言）；
2. README 有个人主页特征，且**没有**工程章节（`## Install`、`## Usage`、`## Features`、`## API`、代码块等）。

作者介绍出现在真实项目 README 里时，要么仓库名与 owner 不同（不会进入 `R3c`），要么有 Install/Usage 章节，都不会被误判为个人主页。

验证用例：

- `alice/alice` + “Hi, I'm Alice.\n## About me” → `excluded`（`R11_readme_profile`）；
- `bob/bob` + 同样自我介绍但含 Install/Usage → 维持 `uncertain`；
- `acme/ml-toolkit`（名称不像主页）+ 作者介绍 + Install/Usage → 正常走 AI 判断，`included`。

## 3. 用原快照重跑 pilot_01

用同一份 `repo_metadata.csv` 与 `manual_review_readmes.jsonl` 重跑 50 个仓库：

| 指标 | v0.3 | v0.3.1 |
|---|---:|---:|
| included | 4 | 4 |
| excluded | 30 | 30 |
| uncertain | 16 | 16 |
| 标签变化 | — | **0 条**（规则理由也无变化） |

50 个仓库里没有出现 A 说的两类误判样本，所以本次标签没有变化；两处修正由 7 项新测试覆盖（见 `tests/test_b_pipeline.py::RulesV31Tests`），并在后续 200 仓库扩大试跑中继续观察。

## 4. 与 v0.3 的关系

- 判定顺序、`R1`–`R11` 的编号与含义不变；
- 只有 `R9_readme_ai` 的证据门槛提高、`R11_readme_profile` 的触发条件收紧；
- 旧规则与旧标签全部保留，对比见 `runs/pilot_01/label_changes.csv`（v0.3 → v0.3.1）。
