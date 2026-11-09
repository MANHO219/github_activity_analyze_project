# pilot_02 误判抽查记录（v0.3.4 → v0.3.5）

- **日期：** 2026-11-09
- **范围：** `runs/pilot_02` 的全部 101 条 `uncertain` 与 80 条 `excluded`
- **依据：** 规则 v0.3.4 的标签、`readme_evidence.jsonl` 的 README 快照、`repo_metadata.csv` 的描述与 topics
- **结论：** 6 个仓库明确判错，改判后进入 v0.3.5；其余维持原标签

## 1. 怎么看的

1. 把 101 条 `uncertain` 按规则分组（R7 49、R1 31、R6 11、R2 6、R3c 4），逐条对照描述、topics 与 README 前 4000 字符；
2. 先筛“README 有正文但仍 `uncertain`”的 20 条，判断是证据不足还是规则漏判；
3. 再扫 80 条 `excluded`，用 AI 语义词表找“描述或 README 有 AI 线索却被排除”的候选，共 22 条，逐条核对；
4. 单独检查两个已知风险：R5d 的“可选 AI 集成”措辞、R13 的课程措辞。

## 2. 改判的 6 个（进入 v0.3.5）

| 仓库 | 旧 | 新 | 为什么是明确错误 |
|---|---|---|---|
| `pkeilbach/htwg-practical-nlp` | included | excluded | 描述“A practical course on NLP”，README 是课程准备与 Moodle 说明；属课程资料，不是 AI 项目 |
| `tomohideshibata/ChatGPT-related-papers` | included | excluded | README 首句“This is a list of ChatGPT-related papers.”，整篇是论文链接目录；属链接合集 |
| `Pepestar/Pepestar` | uncertain | excluded | `Bem vindo!` + `github-readme-stats` 卡片 + 社交链接，个人主页 |
| `gaurav-shrestha/gaurav-shrestha` | uncertain | excluded | typing 头图写 “Welcome to my Github Page”，正文全是社交链接 |
| `Speike-SHL/Speike-SHL` | uncertain | excluded | 只有贡献蛇 SVG，正文有效字符 0，个人主页 |
| `al3xback/fmentor-stats-preview-mocha-chai-expect` | uncertain | excluded | `chai-expect` 被 `ai[-_]` 命中；`chai` 是 JS 断言库，不是 AI |

## 3. 明确不改的（维持 uncertain）

这些仓库的 README 已经能看出“非 AI”，但**没有**放宽 R12 的用途门槛——它们的措辞不在 `purpose_patterns` 内，强行覆盖会把“AI 项目但没写关键词”的仓库一起误伤：

| 仓库 | 原因 |
|---|---|
| 4 个 `auto-green` 克隆（`keepgreen`、`nice`、`vigilant-spork`、`elmliuyong`） | README 是中文说明“自动保持提交常绿”，但句式不匹配 `purpose_patterns` |
| `nabsar-git/PHP` | PHP 学习笔记，非 AI，但同样没有“X is a …”式用途句 |
| `MiSArch/wishlist` | `# Wishlist service for MiSArch`，标题即用途，但模式要求 “is a … service” |
| `project-ncl/pnc-api-types-ts` | “TypeScript based types used in PNC project”，用途句不匹配 |
| 5 个 CRA / Next.js / Vite 模板仓库 | README 是脚手架默认文档，`template_patterns` 已阻止排除，维持 `uncertain` 是正确行为 |

## 4. 两个已知风险的实测

- **R5d（可选 AI 集成）：** 对 200 条 README 做 `optional … AI/ChatGPT/OpenAI/LLM` 双向扫描，命中 **0**。pilot_02 没有真实样本，不能据此调整措辞。
- **R13（课程覆盖）：** included 里只有 `pkeilbach/htwg-practical-nlp` 命中课程词，已由 R3b 的描述规则覆盖，不涉及 R13 的 README 覆盖逻辑。

## 5. 一个故意没改的冲突

`ItsCryptic/ItsCryptic` 的 README 是一段 JS 对象：“Hi, I'm Kevin… I'm some developer from the United States”。它属于 13 条人工复核样本，人工记录是 `uncertain`，理由写明“README 是个人主页式自我介绍，但用代码块展示，未触发主页确认；偏保守”。

R11 的 `project_sections` 含裸 ` ``` `，任何带代码块的 README 都会被当成“有工程章节”，所以规则确实确认不了。但按「人工优先、口径不确定先问 A」的约定，本轮**没有**去掉这个条件；否则自动标签会与人工记录直接冲突。

建议：A 确认后，把 `engineering_section` 尾部的 `| ``` ` 去掉，这类仓库即可自动确认。

## 6. 复现

```bash
cd b_repo_metadata
python -m unittest discover -s tests
python scripts/label_repositories.py --run-dir runs/pilot_02 --readme-evidence runs/pilot_02/readme_evidence.jsonl
python scripts/compare_label_versions.py --run-dir runs/pilot_02 \
    --old runs/pilot_02/repo_ai_labels_v0.3.4.csv --new runs/pilot_02/repo_ai_labels.csv \
    --review runs/pilot_02/manual_review_pilot02.csv
```

## 7. A review 追加（2026-11-09）

A 复测了 v0.3.5 新增的三个排除条件，各找到一个“讨论该主题就被排除”的反例：

| 反例 | v0.3.5 的误判 | v0.3.6 的处理 |
|---|---|---|
| ML 工具的描述里推荐一门 `course on deployment` | 当成课程资料（R3b） | `course on` 只认描述开头的自述课程 |
| 用 LLM 总结 `ChatGPT-related papers` 的工具 | 当成论文清单（R3） | `paper_list` 只认整段描述或“list of papers” |
| 满足疑似主页条件的 ML 工具 + GitHub 统计卡 | 当成个人主页（R11） | 统计卡须“无 AI 强证据 + 正文 <200 字符”才确认 |

同一轮 review 还确认了两件事：

1. `ItsCryptic/ItsCryptic` 的代码块是个人自我介绍，**可人工判为 excluded**——已记入 `runs/pilot_02/manual_revisions.csv`，自动规则仍保持 uncertain；
2. **不要**直接取消代码块限制：A 复测发现那样会让“带统计卡 + 真实安装命令”的 AI 项目也被判成主页，通用规则继续细化。

另外，A 复测 R12 时发现“安装步骤 + 空 Overview 标题”会被误排除，已在 v0.3.4.1（PR #5）修掉：标题下方必须有说明正文。
