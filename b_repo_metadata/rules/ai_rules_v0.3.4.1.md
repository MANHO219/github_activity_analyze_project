# AI 相关仓库判定规则 v0.3.4.1

- **规则版本：** `ai_rules_v0.3.4.1`（机器可读见 [ai_rules_v0.3.4.1.json](ai_rules_v0.3.4.1.json)）
- **上一版：** [`ai_rules_v0.3.4`](ai_rules_v0.3.4.md)
- **来源：** A 在 PR #5 的 review 中指出：只有安装步骤的 README 加一个空 Overview 标题就会被排除

## 问题

R12 的 `purpose_patterns.purpose_heading` 只要求出现 `## About` / `## Overview` 这类标题：

```text
(?im)^#{1,4}\s*(about|overview|description|introduction|what\s+is|features)\b
```

A 的复测：拿一份只有安装步骤的 README，原本是 `uncertain`，**只加一个空的 `## Overview` 标题就变成 `excluded`**。标题本身没有信息，规则却把“有标题”当成了“说明了项目用途”。

## 修复

新增 `readme_rules.non_ai.purpose_requires_body`（默认关闭，只在 v0.3.4.1 显式打开）：

- 只命中 `purpose_heading` 时，必须取到该标题下方、到下一个标题之前的段落，并且这段文字**真的有说明性内容**（默认 ≥ 40 个有效字符）；
- 代码块（``` / ~~~）、命令行（`npm`、`pip`、`git`、`docker`、`make` 等）、`$` 开头的行、空行、纯列表符号一律不计入正文；
- 链接、图片、HTML 标签按 `_meaningful_chars` 的既有逻辑剔除；
- 如果同时命中 `purpose_sentence`（“This project is a …”式句子），不受标题正文限制——那句本身就是用途说明。

配置：

```json
"purpose_requires_body": true,
"min_purpose_body_chars": 40
```

## 对照测试

| 场景 | 期望 |
|---|---|
| 安装步骤 README + 空 `## Overview` | `uncertain`（修复前是 `excluded`） |
| CoreELEC/xbmc：README 明确写 Kodi 影音中心 | `excluded` |
| v0.3.4 及更早版本 | 空标题仍可触发排除（版本隔离，不追溯修改） |

## 影响

本版标签与 v0.3.4 **完全相同**（两个 pilot 都是 0 条变化），因此没有另存 `repo_ai_labels_v0.3.4.1.csv`；`label_changes.csv` 记录 0 条即可复现这个结论。

重跑 pilot_01 / pilot_02，变化见各自的 `label_changes.csv`。凡是 R12 仅靠标题命中、且标题下方没有正文的仓库，会回退为 `uncertain`——这是把证据不足的排除撤回，不是新增排除。
