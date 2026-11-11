# AI 相关仓库判定规则 v0.3.4

- **规则版本：** `ai_rules_v0.3.4`（机器可读见 [ai_rules_v0.3.4.json](ai_rules_v0.3.4.json)）
- **上一版：** [`ai_rules_v0.3.3.1`](ai_rules_v0.3.3.1.md)
- **状态：** 按 A 的要求处理两个边界：可选 AI 集成、课程/训练营覆盖

## 1. 可选 AI 集成不纳入（R5d 扩充）

描述或 README 明确写 AI 只是可选集成时判 `excluded`，例如：

- “Calendar app with optional ChatGPT integration”
- “You can optionally integrate ChatGPT to draft events”
- “integrates with OpenAI” / “optional AI assistant”

新补充的措辞模式覆盖 `optional … ChatGPT`、`ChatGPT … optional`、`can integrate/connect/use … AI`。对照用例：以 ChatGPT 助手为核心的应用（“ChatGPT assistant that schedules your calendar”）仍判 `included`。

README 的可选集成检查在 AI 关键词纳入之前执行，避免 README 里出现 ChatGPT 就被当成核心能力。

## 2. 课程/训练营覆盖 included（R13_course_override）

README 明确说明仓库是**为课程或训练营制作**时，可以把自动标签从 `included` 覆盖为 `excluded`：

- 触发示例：“Made by X for the USC Viterbi Data Science Bootcamp”“course project”“课程作业”；
- 不触发：只提到作者参加过训练营（“attended a data science bootcamp”）、项目曾被用作教学示例（“used as a course example”）、受课程启发（“inspired by a course”）。

排除理由记录命中的证据模式，README 快照时间与哈希照常保存。

## 3. 版本隔离

两个新行为都只在规则文件显式配置时启用：`readme_rules.feature_only_patterns` 与 `readme_rules.course_override`。旧版本规则文件没有这些配置，行为不变；v0.3.2、v0.3.3、v0.3.3.1 都可以逐条复现。

## 4. 重跑结果

| 批次 | v0.3.3.1 | v0.3.4 | 变化 |
|---|---|---|---|
| pilot_01（50） | 4 / 32 / 14 | 4 / 32 / 14 | 0 条 |
| pilot_02（200） | 20 / 79 / 101 | 19 / 80 / 101 | 1 条：Etherscan-ML `included → excluded`（R13） |

pilot_02 分层：160 随机 2 / 71 / 87；40 关键词 17 / 9 / 14。分析用标签（人工优先）与自动标签的差异降为 **0**：13 条人工判断全部与自动结果一致。

pilot_02 里没有真实的可选 AI 集成样本，R5d 的新措辞由测试覆盖（日历可选集成 vs ChatGPT 助手核心）。

测试从 86 项增加到 93 项。
