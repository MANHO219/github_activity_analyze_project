# 标签怎么交接：自动标签、人工复核与分析用标签

本页说明三张标签表的关系、区别，以及在“最终采用什么口径”确定之前，怎么给 C 一份可追溯、可回退的仓库标签表。

## 1. 三张表分别是什么

| 文件 | 谁产生 | 覆盖范围 | 含义 |
|---|---|---|---|
| `runs/pilot_01/repo_ai_labels.csv` | `label_repositories.py` + 规则 v0.3.5（README 辅助） | 全部 50 个仓库 | **自动标签**。规则读 API 快照计算，可重复生成；README 只补足 `uncertain`，并记录快照与哈希 |
| `runs/pilot_01/manual_review.csv` | `manual_review.py` + B 的 `reviews/pilot_01_decisions.json` | 33 个被抽中的仓库 | **人工判断**。B 看过 API 字段和 README 证据后给出的标签与理由，覆盖不完整 |
| `runs/pilot_01/repo_ai_labels_analysis.csv` | `build_analysis_labels.py` | 全部 50 个仓库 | **分析用标签**。把上面两张表按选定口径合并，一行一个仓库，同时保留自动值、人工值与最终值 |

三张表都保留，不互相覆盖。任何“最终采用”的调整都通过重新生成第三张表完成，前两张永远保持原样。

## 2. 自动标签与人工判断的区别

| 维度 | 自动标签 | 人工判断 |
|---|---|---|
| 依据 | 仓库 API 快照的 `description`、`topics`、`full_name` | API 字段 + README 前 4000 字符 + 仓库名与组织背景 |
| 覆盖 | 全部 50 个仓库 | 只覆盖被抽中的 33 个（included 全查、excluded 抽 5、uncertain 全查） |
| 可复现 | 是：同样的元数据 + 规则 → 同样的结果 | 否：依赖复核时的证据与判断，靠 `decisions.json` 留痕 |
| 版本 | 有 `rule_version` 与 `rule_id` | 有 `reviewer`、`reviewed_at_utc`、`human_reason` |
| 性质 | 规则输出，允许有误判 | 个案判断，不保证对未复核仓库成立 |

关键区别：**人工判断不是“更正确的自动标签”**。它只覆盖 33 个仓库，而且当时看的是 v0.1 的自动结果（`manual_review.csv` 里的 `ai_label_auto` 列是 v0.1 的值）。v0.2 与人工结论的对比是事后重算的，见 `label_comparison.json`。

另外两个容易混淆的点：

- `manual_review.csv` 的 `agrees_with_rule` 列是复核当时与 **v0.1** 的一致性，不是与 v0.2 的一致性；
- 人工复核使用 README，而自动规则不读 README。两者证据范围不同，所以“不一致”不等于“规则错”，可能是规则看不到的信息。
- `manual_review_summary.json` 把两个版本分开记录：`labels_rule_version` 是本次命令读取的标签版本（v0.2），`sheet_rule_version` 是生成清单时的版本（复用旧清单时记 `unknown_existing_sheet`），并用 `sheet_auto_labels_differ_from_current` 给出清单自动标签与当前标签的差异条数（本次 9 条）。人工一致率对应的是清单生成时的规则，不是当前规则。

## 3. 分析用标签怎么生成

```bash
cd b_repo_metadata
python scripts/build_analysis_labels.py --run-dir runs/pilot_01                 # 默认：人工优先
python scripts/build_analysis_labels.py --run-dir runs/pilot_01 --policy auto_only   # 只用自动标签
```

输出 `repo_ai_labels_analysis.csv`，字段：

| 字段 | 说明 |
|---|---|
| `repo_id` | 与 A 的事件表连接的主键 |
| `observed_repo_name` | 小时档案中的 `owner/repo` |
| `ai_label_auto` | 规则 v0.3.5 的自动标签 |
| `rule_id` / `reason_auto` | 自动标签的规则与理由 |
| `ai_label_manual` | 人工标签；没被复核的仓库为空 |
| `ai_label_final` | 按当前口径采用的标签 |
| `label_source` | `manual_review` 或 `auto_rule`，标明这一行最终值来自哪里 |
| `reason_human` | 人工判断的理由 |
| `policy` | 生成时使用的口径 |

两种口径的差别：

| 口径 | 规则 | 适用场景 | 当前结果（50 个仓库） |
|---|---|---|---|
| `manual_override`（已确认采用） | 有人工判断用人工，其余用自动 | 认可复核结论、同时接受未复核部分按规则走 | included 4 / excluded 38 / uncertain 8；来源：人工 33、自动 17 |
| `auto_only` | 全部用规则 v0.3.5 | 需要完全可复现、不接受人工个案判断 | included 4 / excluded 32 / uncertain 14 |

注意：默认口径下 included 为 4，其中 3 个“名称像 AI、描述为空、README 证明是 AI 项目”的仓库依赖人工判断（v0.3.5 规则也会用同一份 README 判为 included）。这部分提升不能在不同批次之间直接外推。

新口径对第一轮人工判断的影响检查见 `reviews/pilot_01_revision_check_v0.3.json`：没有需要改判的条目，第一轮 `pilot_01_decisions.json` 保持原样；如果以后要改判，另存修订文件，不覆盖第一轮记录。

## 4. 建议的交接方式

1. **给 C 的表里带上 `label_source`**，让分析能区分“规则判定”和“人工判定”；
2. **`uncertain` 单列，不并入 `excluded`**（已由 A 确认）：8 条存疑（404、ID 不一致、空仓库等）应保留原标签，说明没有足够信息；
3. 如果分析需要“只用可复现标签”，用 `auto_only` 版本，并在报告里说明口径；
4. 正式阶段（A 扩展时间窗、B 跑全量候选）时，人工只复核抽样，其余仍由规则决定——这样标签质量与可复现性能同时交代清楚。

## 5. 口径确认结果（2026-11-09）

| 问题 | 结论 |
|---|---|
| 最终标签口径 | **人工优先（`manual_override`）**，保留自动/人工/最终标签与来源 |
| `uncertain` 处理 | **单列保留，不并入 `excluded`** |
| AI 附加功能是否纳入 | **不纳入**；以 AI 为核心（含调用模型 API）纳入 |
| 弱信号是否直接排除 | **不排除**，维持 `uncertain` |
| 人工复核是否用 README | **允许**，优先描述缺失/名称命中/证据冲突，保存快照与依据 |
| 课程作业边界 | 学校课程、公开课、训练营同一标准，但需确认确实是作业 |
| 个人主页 | 同名 + 无描述 + 无 topics + 无语言 = 疑似，README 确认才排除 |

以上已落到 `ai_rules_v0.3` 起各版本与 `build_analysis_labels.py` 的默认参数；不需要重抓元数据，历史表继续保留。
