# AI 相关仓库判定规则 v0.3.7

- **规则版本：** `ai_rules_v0.3.7`（机器可读见 [ai_rules_v0.3.7.json](ai_rules_v0.3.7.json)）
- **上一版：** [`ai_rules_v0.3.6`](ai_rules_v0.3.6.md)
- **来源：** A 复跑 #8 后指出：用 LLM 总结论文列表的工具仍被当成论文清单
- **基线：** 已合并 #5 的 `v0.3.4.2`，继承 R12 的英文安装说明过滤

## 1. 问题

v0.3.6 的 `paper_list` 虽然要求整段表述，但 `curated_list` 里的 `\ba\s+list\s+of\b` 没有锚定，描述里只要出现 “a list of papers” 就会命中：

> A tool that uses an LLM to summarize a list of papers.

这是**用 LLM 总结论文的工具**，不是论文清单，却被判 `excluded`。

## 2. 修复

两处都收紧到“整段描述就是清单”：

```text
paper_list:
^\s*(?:a\s+|an\s+|the\s+)?(?:curated\s+|awesome\s+|comprehensive\s+)?
(?:list|collection)\s+of\s+[\w\s.,'+-]{0,60}?papers?
(?:\s+(?:about|on|for)\s+[\w\s.,'+-]{0,40})?[.\s]*$
|^\s*[\w.+-]+[-\s]related\s+papers?[.\s]*$

curated_list:
\bcurated\b|^\s*a\s+list\s+of\b|\bcollection\s+of\b|\blinks?\s+(to|for)\b
```

- `A curated list of LLM papers.` → 仍排除
- `A list of papers about large language models.` → 仍排除
- `ChatGPT-related papers.` → 仍排除
- `A tool that uses an LLM to summarize a list of papers.` → 不再排除

## 3. 继承 R12 收尾

v0.3.7 的 `readme_rules.non_ai` 同时打开：

- `purpose_requires_body: true`（v0.3.4.1）
- `min_purpose_body_chars: 40`
- `ignore_install_lines: true`（v0.3.4.2）

所以“Overview 下只有英文安装说明”在本版仍是 `uncertain`，有对照测试。

## 4. 对照测试

| 场景 | v0.3.6 | v0.3.7 |
|---|---|---|
| 用 LLM 总结 “a list of papers” 的工具 | excluded | included |
| `A curated list of LLM papers.` | excluded | excluded |
| `A list of papers about LLMs.` | excluded | excluded |
| `ChatGPT-related papers.` | excluded | excluded |
| Overview + 英文安装说明 | excluded | uncertain |

v0.3.6 的行为由“旧版本加载后不变”的用例锁住。

## 5. 重跑结果

pilot_01 / pilot_02 均 **0 条标签变化**：样本里没有“用 LLM 总结论文列表”的仓库。测试 101（#5）→ 134（含合并后的全部用例）。

接回表按最终标签重跑：200/200、1,072 条不变，分布 excluded 394 / included 109 / uncertain 569。
