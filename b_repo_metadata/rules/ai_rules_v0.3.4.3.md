# AI 相关仓库判定规则 v0.3.4.3

- **规则版本：** `ai_rules_v0.3.4.3`（机器可读见 [ai_rules_v0.3.4.3.json](ai_rules_v0.3.4.3.json)）
- **上一版：** [`ai_rules_v0.3.4.2`](ai_rules_v0.3.4.2.md)
- **来源：** A 复跑 #5 后指出：安装说明写成编号列表后仍会被误排
- **范围：** 只补 R12，不改其他规则；这是 #5 分支上 R12 的第三版补丁

## 1. 版本安排

`#5` 分支负责 R12 的用途判定，按补丁版本递进：

| 版本 | 内容 | 与其他版本的关系 |
|---|---|---|
| `v0.3.4` | PR #5 的基线（可选 AI 集成 + 课程覆盖） | 已推送 |
| `v0.3.4.1` | 第一次补 R12：只命中标题不算用途，标题下需有正文 | 补丁，不改 v0.3.4 |
| `v0.3.4.2` | 第二次补 R12：英文安装说明不算正文 | 补丁，只改正文判定 |
| `v0.3.4.3` | 本次：编号列表先剥标记，再判正文 | 补丁，只改正文判定 |

`#8` 的 `v0.3.5`–`v0.3.8` 从 `v0.3.4` 派生，合并 `#5` 后通过 `v0.3.8` 继承 `v0.3.4.3` 的行为。版本号不严格线性，但每个文件独立、旧文件不改。

## 2. 问题

v0.3.4.2 的指令行判断按行首匹配。A 的复测把同样的安装说明写成编号列表：

```markdown
## Overview

1. Download the release archive for your platform
2. Add the extracted folder to your PATH
3. Run mytool --serve to start the service
```

行首变成了 `1.`，`Download / Add / Run` 都不在行首，指令行判断全部失效，四行被当成正文，
R12 于是把仓库判成 `excluded`。

## 3. 修复

`readme_rules.non_ai.strip_list_markers`（默认关闭，只在 v0.3.4.3 打开）：

判断正文前先剥掉 Markdown 列表标记，最多剥两层（`1. - item`）：

- 有序：`1.`、`1)`、`(1)`；
- 无序：`-`、`*`、`+`；
- checkbox：`- [ ]`、`- [x]`。

剥完再走 v0.3.4.2 的指令行判断，并补充 `Copy / Move / Add / Open / Extract / Edit / Select / Choose / Click / Navigate` 等步骤动词。

## 4. 对照测试

| 场景 | v0.3.4.2 | v0.3.4.3 |
|---|---|---|
| 编号安装步骤（Download / Add / Run / Open） | excluded | **uncertain** |
| 无序列表安装步骤 | excluded | **uncertain** |
| 编号列表但每行在说明用途 | excluded | excluded |
| CoreELEC/Kodi 式媒体中心 | excluded | excluded |

v0.3.4.2 的行为由“旧版本加载后不变”的用例锁住。

## 5. 重跑结果

pilot_01 / pilot_02 均 **0 条标签变化**：现有样本没有编号列表形式的安装说明，
这个 bug 只在构造样例上复现。测试 101 → 107 项。
