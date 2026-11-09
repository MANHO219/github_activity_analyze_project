# AI 相关仓库判定规则 v0.3.3.1

- **规则版本：** `ai_rules_v0.3.3.1`（机器可读见 [ai_rules_v0.3.3.1.json](ai_rules_v0.3.3.1.json)）
- **上一版：** [`ai_rules_v0.3.3`](ai_rules_v0.3.3.md)
- **状态：** 按 A 的复测反馈收紧 R12，并修复版本隔离问题

## 1. R12 收紧：必须说明项目用途

v0.3.3 的 R12 只要 README 正文够长、没有 AI 词就排除，A 用“只有安装说明的长 README”复测时被直接排除；真实样本里 `LDingLDing/langchain-js` 的名称有 AI 线索、README 是通用 Next.js 模板，也被判成 excluded。

v0.3.3.1 增加三个门槛：

1. **必须能说明主要用途**：README 要有 `About`/`Overview`/`Description` 等章节，或“X is a …”式说明，或中文“本项目/这是一个/主要功能”。只有安装步骤、模板脚手架、徽章链接的 README 不算；
2. **只对 R7 生效**：即描述与 topics 都为空。名称命中（R6）或弱信号（R4b/R5c）属于冲突证据，继续 `uncertain`；
3. **模板识别**：`bootstrapped with`、`create-next-app`、`starter template`、`boilerplate` 等模板文本出现时，不排除。

排除理由会写 `purpose=<命中的用途模式>;readme_chars=<有效字符>`，便于复核依据。

## 2. R12 只在配置了它的版本启用

v0.3.3 之前引擎把 R12 当成默认规则，导致用 `--rules ai_rules_v0.3.2.json` 重跑时仍然触发 R12，两批分别有 6 条和 22 条与存档不一致。

现在只有规则文件的 `readme_rules.non_ai` 存在时才启用 R12；v0.3.2 及更早版本没有这个配置，加载后不会触发。实测：

- 用 v0.3.2 重跑 pilot_01 / pilot_02，与存档标签 **0 差异**；
- 用 v0.3.3 重跑，与存档标签 **0 差异**（保留旧版的宽松 R12 行为，便于版本对比）。

## 3. 重跑结果

| 批次 | v0.3.3 | v0.3.3.1 | 变化 |
|---|---|---|---|
| pilot_01（50） | 4 / 36 / 10 | 4 / 32 / 14 | 4 条 excluded → uncertain |
| pilot_02（200） | 20 / 96 / 84 | 20 / 79 / 101 | 17 条 excluded → uncertain |

- `LDingLDing/langchain-js` 恢复为 `uncertain`（R6 名称命中，README 是模板）；
- `CoreELEC/xbmc` 仍由 R12 自动排除（README 有用途说明，无 AI 证据）；
- pilot_02 的 R12 命中从 22 条降到 5 条，pilot_01 从 6 条降到 2 条。

测试从 80 项增加到 86 项，覆盖旧版本不触发 R12、只有安装说明、模板 README、名称/弱信号冲突、用途说明排除等情况。
