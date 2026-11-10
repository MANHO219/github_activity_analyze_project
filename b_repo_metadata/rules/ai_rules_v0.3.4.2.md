# AI 相关仓库判定规则 v0.3.4.2

- **规则版本：** `ai_rules_v0.3.4.2`（机器可读见 [ai_rules_v0.3.4.2.json](ai_rules_v0.3.4.2.json)）
- **上一版：** [`ai_rules_v0.3.4.1`](ai_rules_v0.3.4.1.md)
- **来源：** A 复跑 #5 后指出：Overview 下只有英文安装说明时仍会被误排
- **范围：** 只补 R12，不改其他规则；这是 #5 分支上 R12 的收尾版本

## 1. 版本安排

`#5` 分支负责 R12 的用途判定，按补丁版本递进：

| 版本 | 内容 | 与其他版本的关系 |
|---|---|---|
| `v0.3.4` | PR #5 的基线（可选 AI 集成 + 课程覆盖） | 已推送 |
| `v0.3.4.1` | 第一次补 R12：只命中标题不算用途，标题下需有正文 | 补丁，不改 v0.3.4 |
| `v0.3.4.2` | 本次：英文安装说明不算“正文” | 补丁，只改 v0.3.4.1 的正文判定 |

`#8` 的 `v0.3.5`、`v0.3.6`、`v0.3.7` 都从 `v0.3.4` 派生，合并 `#5` 后通过 `v0.3.7` 继承 `v0.3.4.2` 的行为。版本号不严格线性，但每个文件独立、旧文件不改。

## 2. 问题

v0.3.4.1 判定“标题下方是否有说明正文”时，只排除了 shell 命令与代码块。A 的复测：

```markdown
## Overview

Install the package with pip:

pip install mytool

Then run the following command to start the service:

mytool --help
```

`Install the package with pip:` 和 `Then run the following command …` 是安装说明，却被当成正文，R12 于是把仓库判成 `excluded`。

## 3. 修复

`readme_rules.non_ai.ignore_install_lines`（默认关闭，只在 v0.3.4.2 打开）：

- `Install / Installation / Set up / Run / Execute / Launch / Build / Clone / Download / Configure / Usage / Quick start / Requirements / Prerequisites / Dependencies` 开头的行不计入正文；
- 含 `the following command(s)/step(s)` 的引导句不计入；
- `Then/Next/Finally + run/install/execute/…` 的过渡句不计入；
- 以冒号结尾且不超过 80 字符的引导句不计入（正文里的“以下是……”也按引导句处理）；
- 形如 `mytool --help` 的调用行不计入。

真正的用途说明（“Kodi is an award-winning media player…” 或 “A small set of helpers for handling dates…”）不受影响。

## 4. 对照测试

| 场景 | v0.3.4.1 | v0.3.4.2 |
|---|---|---|
| Overview + 英文安装说明 | excluded | **uncertain** |
| Overview 为空 | uncertain | uncertain |
| Overview 有真实用途说明 | excluded | excluded |
| CoreELEC/Kodi 式媒体中心 | excluded | excluded |

v0.3.4.1 的行为由“旧版本加载后不变”的用例锁住。

## 5. 重跑结果

pilot_01 / pilot_02 均 **0 条标签变化**：现有样本没有“Overview 只有安装说明”的仓库，这个 bug 只在构造样例上复现。测试 97 → 101 项。
