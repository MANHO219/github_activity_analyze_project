# AI 相关仓库判定规则 v0.3.6

- **规则版本：** `ai_rules_v0.3.6`（机器可读见 [ai_rules_v0.3.6.json](ai_rules_v0.3.6.json)）
- **上一版：** [`ai_rules_v0.3.5`](ai_rules_v0.3.5.md)
- **来源：** A 对 PR #8 的 review——三个新增排除条件都能被“讨论该主题”的仓库误触发
- **原则：** 规则判断的是**仓库本身的用途**，不是描述里提到了什么词

## 1. `course on` 只在自述为课程时生效

v0.3.5 的正则 `\bcourses?\s+(on|about)\b` 不区分主语，A 的反例：

> 机器学习工具的描述只是推荐一门 course on deployment，会被当成课程资料。

v0.3.6 改为开头锚定，只认“这个仓库就是课程”：

```text
^\s*(this\s+is\s+)?(a|an)\s+(practical\s+|online\s+|hands-on\s+|introductory\s+|university\s+|graduate\s+)?course\s+on\b
|^\s*course\s+on\b
```

- `A practical course on natural language processing` → 仍排除（`pkeilbach/htwg-practical-nlp`）
- `An MLOps toolkit for model deployment. See the course on deployment for background.` → 不再排除

## 2. `paper_list` 只认“整段就是清单”

v0.3.5 的 `\b[\w.+-]+[-\s]related\s+papers?\b` 会匹配描述里的任意位置，A 的反例：

> 用 LLM 总结 ChatGPT-related papers 的工具，会被当成论文清单。

v0.3.6 只保留两种形态：

```text
\b(list|collection)\s+of\s+[\w\s.,+-]{0,40}?papers?\b
|^\s*[\w.+-]+[-\s]related\s+papers?[.\s]*$
```

- 描述整段就是 `ChatGPT-related papers` → 仍排除（`tomohideshibata/ChatGPT-related-papers`）
- `An LLM tool that summarizes ChatGPT-related papers` → 不再排除

## 3. 统计卡只在“没有 AI 证据且正文极短”时确认主页

v0.3.5 把 `github-readme-stats|github-contribution-grid|readme-typing-svg|bem vindo|…` 直接放进 `profile_patterns`，A 的反例：

> 满足疑似主页条件的仓库，README 明明写的是机器学习工具，加一张 GitHub 统计卡也会被判成个人主页。

v0.3.6 把这组组件证据拆到 `readme_rules.profile_widget_patterns`，并加两道前置条件：

1. README 里**没有 AI 强证据**（`ai_strong_patterns` 一条都不命中）；
2. README 的有效正文 **< 200 字符**（`profile_widget_max_meaningful_chars`）。

两条同时满足，才把组件当作主页证据。`profile_patterns` 只保留 v0.3.4 的自我介绍句式（`Hi, I'm …`、`About me`、`github profile` 等）；`Bem vindo` 属于组件表，不在这一组。

- `Pepestar`、`gaurav-shrestha`、`Speike-SHL`：没有 AI 证据、正文极短 → 仍排除
- ML 工具 + 统计卡 → 不再排除，继续走 README 的 AI 证据判定

## 4. 对照测试

| 场景 | v0.3.5 | v0.3.6 |
|---|---|---|
| 描述里推荐 `course on deployment` 的 MLOps 工具 | excluded（R3b） | included |
| 自述 `A practical course on NLP` | excluded | excluded |
| 用 LLM 总结 `ChatGPT-related papers` 的工具 | excluded（R3） | included |
| 描述整段是 `ChatGPT-related papers` | excluded | excluded |
| ML 工具 + GitHub 统计卡 | excluded（R11） | included |
| 个人主页 + 统计卡（无 AI、正文极短） | excluded | excluded |

v0.3.5 的行为由“旧版本加载后不变”的对照用例锁住。

## 5. 重跑结果

| 批次 | v0.3.5 | v0.3.6 | 变化 |
|---|---|---|---|
| pilot_01（50） | 4 / 32 / 14 | 4 / 32 / 14 | 0 条 |
| pilot_02（200） | 17 / 86 / 97 | 17 / 86 / 97 | 0 条 |

pilot_02 的 6 条改判全部保留：`pkeilbach/htwg-practical-nlp`、`tomohideshibata/ChatGPT-related-papers`、`Pepestar/Pepestar`、`gaurav-shrestha/gaurav-shrestha`、`Speike-SHL/Speike-SHL`、`al3xback/fmentor-…-chai-expect`。三个收紧条件在现有样本里没有触发新的回退——样本中没有“推荐课程”“总结论文”“ML 工具带统计卡”的仓库。

## 6. 仍然存在的风险

1. R5d 的“可选 AI 集成”仍无真实样本。
2. R12 的 `purpose_patterns` 未放宽。
3. R11 的代码围栏限制仍在，`ItsCryptic/ItsCryptic` 由人工修订处理。
4. `course_on` 依赖描述以课程开头；如果作者把课程信息写在第二句，仍可能漏判——这是为了避免误伤刻意做的取舍。
