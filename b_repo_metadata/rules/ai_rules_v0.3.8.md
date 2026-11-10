# AI 相关仓库判定规则 v0.3.8

- **规则版本：** `ai_rules_v0.3.8`（机器可读见 [ai_rules_v0.3.8.json](ai_rules_v0.3.8.json)）
- **上一版：** [`ai_rules_v0.3.7`](ai_rules_v0.3.7.md)
- **来源：** A 第三次复验 #8：论文合集应按“仓库的主要用途”判定，不能只看到 curated / collection of 就排除
- **基线：** 已合并 #5 的 `v0.3.4.3`，继承 R12 的列表标记剥离

## 1. 问题

v0.3.7 把 `paper_list` 收紧到整段，但 `curated_list` 仍是“命中即排除”：

```text
\bcurated\b | ^\s*a\s+list\s+of\b | \bcollection\s+of\b | \blinks?\s+(to|for)\b
```

于是下面这类描述会被误排：

> An LLM tool that summarizes a collection of papers

这是**处理论文的工具**，不是论文合集。同一个工具的另一种写法
（`summarizes a list of papers`）在 v0.3.7 已经能纳入，两种写法结果不一致。

## 2. 判定口径：看仓库主要提供什么

资源词分成两档，配置在 `resource_collection_patterns[].strength`：

| 档位 | 模式 | 含义 |
|---|---|---|
| `strong` | `awesome`、`tutorial`、`learning_notes`、`roadmap`、`zh_resource`、`paper_list` | 名字或描述本身就是资料集合 |
| `weak` | `curated`、`collection_of`、`links_to`、`list_of_inline` | 只是线索，可能是“提到”，也可能是“就是” |

判定顺序（`resource_collection.require_primary_purpose = true` 时生效）：

1. **strong 命中** → 排除；但描述里明确写着 `a tool / a CLI / a library` 时算冲突，改判 `uncertain`；
2. **weak 命中且描述开头就是清单**（`list_lead_patterns`：`A curated list of …`、`Curated links for …`）→ 排除；
3. **weak 命中且有工具语义**（`tool_signal_patterns`：声明式工具名词 + 处理动词）→ 不算合集，按工具的核心功能继续判断；
4. **weak 命中但没有任何用途说明** → `uncertain`，不自动排除。

工具动词只收明确的处理动作（summarize / convert / extract / analyze / search / filter / parse …）。
`build` / `create` / `generate` 太通用（`building blocks`、`generative AI`），不参与判定。

## 3. 验收用例

| 描述 | 结果 |
|---|---|
| `An LLM tool that summarizes a list of papers` | `included` |
| `An LLM tool that summarizes a collection of papers` | `included` |
| `A curated list of LLM papers.` | `excluded`（`R3_resource_collection`） |
| `A collection of papers about LLMs` | `excluded` |
| `ChatGPT-related papers.` | `excluded` |
| `Curated links for Microsoft related events` | `excluded` |
| `A collection of reusable … VHDL building blocks.` | `excluded` |
| `My notes and a curated collection of links about LLMs` | `uncertain`（`R3c_resource_mention_only`） |
| `A tutorial on building LLM apps` | `excluded`（教程仍是资料，不因 build 降级） |
| `An LLM tool that summarizes a collection of papers`（v0.3.7） | `excluded`（版本隔离） |

## 4. 继承 R12 的列表标记剥离

A 复测：安装说明写成 `1. Download…`、`2. Add…`、`3. Run…` 后仍被判为 `excluded`。
原因是编号让行首变成了 `1.`，绕过了指令行判断。v0.3.4.3 起先剥掉 Markdown 列表标记
（有序 `1.` / `1)`、无序 `- * +`、checkbox），再判断正文：

- `readme_rules.non_ai.strip_list_markers: true` 显式开启，旧版本行为不变；
- 纯安装步骤 → `uncertain`；
- 编号列表但每行确实在说明用途 → 仍 `excluded`（`R12_readme_non_ai`）。

## 5. 影响

| 样本 | v0.3.7 → v0.3.8 |
|---|---|
| pilot_01（50） | 0 条变化，仍 4 / 32 / 14 |
| pilot_02（200） | 0 条变化，仍 17 / 86 / 97 |

两个 pilot 里没有“工具 + 合集词”的描述，所以本轮只靠对照测试验证；这也说明
该问题只在 A 构造的反例上出现，不影响已交付标签。

## 6. 已知限制

- **README 侧的清单证据还没接入**：描述为空、只有 README 写 “a list of papers” 的仓库仍是 `uncertain`。
- `strong` 与工具语义的“冲突”只看声明式工具名词；`A tool for …`、`A CLI for …` 能识别，
  纯动词描述（`Summarizes papers`）不会触发冲突。
- 中文清单表述（`资料`、`大全` 等）仍在 `strong` 档，未做“工具 vs 清单”的冲突判定。
