# AI 相关仓库判定规则 v0.3.3

- **规则版本：** `ai_rules_v0.3.3`（机器可读见 [ai_rules_v0.3.3.json](ai_rules_v0.3.3.json)）
- **上一版：** [`ai_rules_v0.3.2`](ai_rules_v0.3.2.md)
- **状态：** 按 A 对两个边界案例的判定，新增 README 确认“主体非 AI”的排除规则

## 1. 新增 R12_readme_non_ai

当规则判为 `uncertain`、且 README 满足以下全部条件时，判 `excluded`：

1. 去掉链接、图片、HTML 标签后，有效正文至少 200 个字符（只有标题、徽章或链接列表不算）；
2. 去掉“计划/以后/roadmap”等未来意图行后，完全没有 AI 强证据或弱证据（`ai`/`ml` 出现 0 次）；
3. 没有命中课程作业或个人主页证据（这两类会先由 R10/R11 处理）。

理由写 `readme_chars=<有效字符数>;no_ai_evidence`，README 快照时间与哈希照常记录。

边界行为：

- CoreELEC/xbmc（Kodi 影音中心）→ `excluded`，这是本规则的测试案例；
- 只有 `# feliix` 这类短 README → 维持 `uncertain`；
- 长 README 但只有“以后打算加 AI”的未来计划 → 计划行被剔除后按非 AI 项目排除；
- AI 项目（README 有 PyTorch、neural network 等）→ `included`，不受影响。

## 2. 两个边界案例的处理

| 仓库 | A 的判定 | 规则侧结果 |
|---|---|---|
| `elyselam/Etherscan-ML` | 人工 `excluded`：README 明确为 USC Viterbi Data Science Bootcamp 制作，按训练营项目排除 | 规则仍为 `included`（描述/topic 直接命中机器学习）；分析用标签按人工优先取 `excluded`，规则缺口记录在案 |
| `CoreELEC/xbmc` | 人工 `excluded`：README 明确核心功能是影音播放与管理 | v0.3.3 由 `R12_readme_non_ai` 自动排除，与人工一致 |

Etherscan-ML 的缺口说明：课程/训练营证据只作用于 `uncertain`，而这个仓库的描述直接命中强 AI 词，规则在课程证据之前就判了 `included`。是否允许 README 课程证据覆盖 `included` 需要 A 决定，v0.3.3 未改。

## 3. 重跑结果

| 批次 | v0.3.2 | v0.3.3 | 变化 |
|---|---|---|---|
| pilot_01（50） | 4 / 30 / 16 | 4 / 36 / 10 | 6 条 `uncertain → excluded` |
| pilot_02（200） | 20 / 74 / 106 | 20 / 96 / 84 | 22 条 `uncertain → excluded` |

pilot_01 的人工优先分析标签与自动标签差异从 8 条降到 2 条；pilot_02 的 13 条复核里只有 Etherscan-ML 一条需要人工覆盖。

测试从 76 项增加到 80 项。
