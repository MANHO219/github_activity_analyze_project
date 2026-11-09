# AI 相关仓库判定规则 v0.3.2

- **规则版本：** `ai_rules_v0.3.2`（机器可读见 [ai_rules_v0.3.2.json](ai_rules_v0.3.2.json)）
- **上一版：** [`ai_rules_v0.3.1`](ai_rules_v0.3.1.md)
- **状态：** 200 仓库扩大试跑中人工核对发现的两处匹配 bug 修复

v0.3.2 只修词边界，不改判定顺序与口径。

## 1. 名称匹配：camelCase 拆分 + 词边界

`ResnetGPT` 这类 camelCase 名称之前匹配不到 `gpt`，而 `Whispering-Origin-2D` 又会把 `whispering` 当成 `whisper`。现在名称先拆成 `resnet-gpt`、`whispering-origin-2-d`，再按整词匹配。

- `someone/ResnetGPT` → 命中 `gpt`，名称信号成立；
- `someone/Whispering-Origin-2D` → 不命中 `whisper`，按普通仓库处理。

个人主页判定仍用**原始** owner/repo 比较是否同名，避免拆分后把 `PauloHenriqueJr/paulohenriquejr` 拆成两段。

## 2. 中英相邻：插入空格后再匹配

中文是 Unicode 单词字符，`\b` 在“的AI”“GPT搭建”这类位置不生效，导致真正的中文 AI 项目被漏判。现在匹配前在中文与英文/数字相邻处插入空格：

- “用Resnet101+GPT搭建一个玩王者荣耀的AI” → 命中 `gpt`，判 `included`；
- “一个用AI做模型训练的平台” → 弱词 `ai` + 佐证词“模型/训练”，判 `included`。

## 3. 重跑结果

| 批次 | v0.3.1 | v0.3.2 | 变化 |
|---|---|---|---|
| pilot_01（50） | 4 / 30 / 16 | 4 / 30 / 16 | 0 条 |
| pilot_02（200） | 20 / 73 / 107 | 20 / 74 / 106 | 2 条（1 标签 + 1 理由） |

- pilot_02 的变化：`Whispering-Origin-2D` 由 `uncertain` 改判 `excluded`（不再误当 whisper）；`ResnetGPT` 仍是 `included`，但理由从 README 变为描述直接命中 `GPT`。

测试从 71 项增加到 76 项，覆盖 camelCase、中文相邻、whisper 子串、个人主页同名比较。
