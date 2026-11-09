# AI 相关仓库判定规则 v0.3.5

- **规则版本：** `ai_rules_v0.3.5`（机器可读见 [ai_rules_v0.3.5.json](ai_rules_v0.3.5.json)）
- **上一版：** [`ai_rules_v0.3.4`](ai_rules_v0.3.4.md)
- **状态：** 对 pilot_02 的 101 条 `uncertain` 与 80 条 `excluded` 做误判抽查后，只修 6 个明确判错的仓库（4 处判据）
- **原则：** 不放宽证据门槛，不为了让 `uncertain` 变少而扩大排除范围

## 1. 这版没有改什么

先划清边界，避免误读成“又放宽了一轮”：

- **R12（README 确认主体非 AI）不动。** 200 字符阈值与 `purpose_patterns` 全部保持 v0.3.4 原样。抽查里确实有一批 README 已写明用途、规则却没认出来的仓库（`auto-green` 克隆 4 个、`nabsar-git/PHP`、`MiSArch/wishlist`、`project-ncl/pnc-api-types-ts`），它们**继续维持 `uncertain`**，交给 LLM 试验与人工判断，不在这里加宽正则。
- **R5d（可选 AI 集成）不动。** 生成 v0.3.5 前对 pilot_02 全部 200 条 README 做过措辞扫描，`optional … AI/ChatGPT/OpenAI/LLM` 命中数为 **0**，仍然只有测试覆盖，没有真实样本。
- **R13（课程覆盖）不动。** 覆盖仍要求“为课程/训练营制作”的明确语义；本轮只补了描述侧的 `course on/about`（走 R3b，不涉及 R13 的覆盖逻辑）。
- **R11 的代码围栏问题不动**，原因见第 6 节。

## 2. R3 资源合集：补充论文清单

`resource_collection_patterns` 新增 `paper_list`：

```text
\b[\w.+-]+[-\s]related\s+papers?\b|\bpapers?\s+list\b|\blist\s+of\s+papers?\b
```

`tomohideshibata/ChatGPT-related-papers` 的描述是 “ChatGPT-related papers”，README 第一句是 “This is a list of ChatGPT-related papers.”，整篇是论文链接目录。按已确认口径「链接合集一律排除」，v0.3.4 却因为描述里带 ChatGPT 被判 `included`，属于**明确误纳入**。

只匹配“论文清单”这一种表述，不扩大到 `papers` 单词本身——`Official implementation of the paper …` 这类实现仓库不能被误伤（有对照测试）。

## 3. R3b 课程作业：补充 “course on/about”

`coursework_description_patterns` 新增 `course_on`：

```text
\bcourses?\s+(on|about)\b
```

`pkeilbach/htwg-practical-nlp` 的描述是 “A practical course on natural language processing @ HTWG Konstanz.”，README 开头是 “Welcome to the course **Practical Natural Language Processing** at HTWG Konstanz.”，正文是课程准备事项与 Moodle 说明。它是**课程资料本身**，不是 AI 项目。

v0.3.4 的课程模式要求 `course assignment/project/work/material` 这类“课程的产物”，漏掉了“课程本身”这种自述。新增模式只认 `course on/about`，不认单独的 `course` 单词（“model serving for online courses” 仍判 included，有对照测试）。

## 4. R11 个人主页：补充组件级措辞

`profile_patterns` 新增 `readme_profile_widget`：

```text
github-readme-stats|github-contribution-grid|readme-typing-svg|bem\s+vindo|welcome[+\s]+to[+\s]+my[+\s]+(github|profile)
```

抽查里的三条个人主页 README 都没有传统自我介绍句式，但都有个人主页专属组件：

- `Pepestar/Pepestar`：`### Bem vindo!` + `github-readme-stats` 卡片 + 社交链接；
- `gaurav-shrestha/gaurav-shrestha`：`readme-typing-svg` 头图，文案在 URL 里（`Welcome+to+my+Github+Page`）；
- `Speike-SHL/Speike-SHL`：只有贡献蛇 SVG（`github-contribution-grid-snake`），正文有效字符为 0。

这三类组件几乎只出现在个人主页仓库；配合 R11 原有的前置条件（规则已判 `R3c_profile_suspected`：owner 与 repo 同名 + 无描述 + 无 topics + 无语言），误伤面很小。

## 5. 名称信号：修复 `ai` 词元边界

`name_signal_patterns` 的第一条原来是：

```text
(^|[/_.-])ai($|[/_.-])|ai[-_]|[-_]ai
```

后两个分支没有左/右边界，`chai-expect` 会命中 `ai[-_]`，把 JS 断言库 `chai` 当成 AI 名称信号（与 v0.3.2 修的 `whispering` 同类问题）。改为：

```text
(^|[/_.-])ai([-_.]|$)
```

`ai-tool`、`open-ai`、`foo-ai` 仍然命中；`chai`、`trail`、`email` 不再命中。

## 6. 已知限制：代码围栏仍被当成“工程章节”（待 A 确认）

R11 的 `project_sections` 里含裸的 ` ``` `，因此**任何带代码块的 README 都不会被确认为个人主页**。`ItsCryptic/ItsCryptic` 就是这种情况：README 是一段 JS 对象，写着 “Hi, I'm Kevin… I'm some developer from the United States”。

这一条**本轮没有改**，两个原因：

1. 它在 pilot_02 的 13 条人工复核里，人工记录是 `uncertain`，理由写明“README 是个人主页式自我介绍，但用代码块展示，未触发主页确认；偏保守”；
2. 按项目约定「人工优先，遇到不确定的口径先问 A」，规则不应单方面推翻人工记录。

要改的话，把 `engineering_section` 尾部的 `| ``` ` 去掉即可，R11 会立刻确认这类仓库；建议由 A 确认后再进 v0.3.6。

## 7. 重跑结果

| 批次 | v0.3.4 | v0.3.5 | 变化 |
|---|---|---|---|
| pilot_01（50） | 4 / 32 / 14 | 4 / 32 / 14 | 0 条 |
| pilot_02（200） | 19 / 80 / 101 | 17 / 86 / 97 | 6 条 |

pilot_02 的 6 条明细：

| 仓库 | 旧 | 新 | 规则 |
|---|---|---|---|
| `pkeilbach/htwg-practical-nlp` | included | excluded | R3b（`course on`） |
| `tomohideshibata/ChatGPT-related-papers` | included | excluded | R3（论文清单） |
| `Pepestar/Pepestar` | uncertain | excluded | R11（`Bem vindo` + 统计卡） |
| `gaurav-shrestha/gaurav-shrestha` | uncertain | excluded | R11（typing 头图） |
| `Speike-SHL/Speike-SHL` | uncertain | excluded | R11（贡献蛇） |
| `al3xback/fmentor-stats-preview-mocha-chai-expect` | uncertain | excluded | R8（`chai` 不再命中名称信号） |

分层分布（pilot_02）：160 随机 2 / 75 / 83；40 关键词 15 / 11 / 14。

人工一致率没有变化：

- pilot_01：19 条已判定行全部一致，0 条人工推翻，6 条由人工补判，8 条两边都存疑；
- pilot_02：13 条抽查里 9 条一致、0 条不一致、4 条两边都存疑——**自动与人工差异仍为 0**（6 条变化都不在复核样本里）。

## 8. 版本隔离

四处判据改动全部落在 v0.3.5 的 JSON 里，旧版本文件一个字节都没动。加载 v0.3.4 及更早的规则后行为不变：

- 旧文件没有 `paper_list` / `course_on` / `readme_profile_widget` 条目；
- 旧文件的 `project_sections` 与 `name_signal_patterns` 保持原样。

`python -m unittest discover -s tests` 里有专门的“旧版本加载后不触发新行为”对照用例。

## 9. 仍然存在的风险

1. **R5d 无真实样本**：pilot_02 扫描结果为 0 条，不能证明新措辞在真实数据上可靠。
2. **R12 判决能力有限**：README 已写明非 AI、但措辞不在 `purpose_patterns` 内的仓库仍是 `uncertain`；这是刻意保留，不是漏改。
3. **R13 只覆盖 README 侧**，描述侧的课程语义由 R3b 承担；“欢迎来到本课程”式 README 仍可能漏判。
4. **代码围栏问题待 A 确认**（第 6 节）。
5. **个人主页组件模式可能误伤**：极少数项目 README 会用 typing 头图做装饰；R11 前置条件已把大部分项目排除在外。
