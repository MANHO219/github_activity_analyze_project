# B 的 PR 复验与下一轮任务

核对了远端 [PR #5](https://github.com/MANHO219/github_activity_analyze_project/pull/5) 的 `7692078` 和 [PR #8](https://github.com/MANHO219/github_activity_analyze_project/pull/8) 的 `c0944d4`。在临时目录离线复跑，分别通过 97 和 123 项测试。建议先完成下面的修改，按 #5、#8 的依赖顺序复验和合并。

## PR #5 的 R12 用途判定

按此前约定，#5 这轮验收聚焦 v0.3.3.1 的 R12 用途证据和旧版本隔离。提交把 R12 修复放进了 v0.3.4.1，默认版本也随之更新。请在 PR 里明确 v0.3.4 那批改动的合并安排。如果 #5 保持此前范围，就把 R12 修复放在 v0.3.3.1 的基线上独立交付。

原来的「空 Overview 加安装命令」已保持 `uncertain`，Kodi 影音中心仍是 `excluded`。两批试点在 v0.3.4.1 的标签分别为 4/32/14 和 19/80/101，逐仓库与 v0.3.4 相同。现在还有一个边界，标题下有足够长的**英文安装说明**时，程序仍会当作项目用途。例如：

> ## Overview
> Download the release archive and extract its contents into a new folder. Add the executable to your system path before opening a terminal. Follow the installation guide to configure your environment and verify that the setup completed successfully.

这段只有操作步骤，预期继续存疑。请补这条对照测试，验证明确说明项目用途的 README 仍能按 R12 判定。 [当前规则说明](https://github.com/MANHO219/github_activity_analyze_project/blob/7692078/b_repo_metadata/rules/ai_rules_v0.3.4.1.md#L17)

## PR #8 的规则与交接

已复现三个原反例的修复，涉及工具描述提到课程、用 LLM 处理相关论文、AI 工具放统计卡。pilot_02 的自动标签是 17 入选、86 排除、97 存疑。人工优先后是 17/87/96，`ItsCryptic/ItsCryptic` 的人工修订正确反映在最终表和活动接回表。重跑接回得到 200/200 个仓库、1,072 条事件，按入选、排除、存疑分别为 109、394、569 条。 [接回摘要](https://github.com/MANHO219/github_activity_analyze_project/blob/c0944d4/b_repo_metadata/runs/pilot_02/join_check.json)

1. 论文合集的规则仍会误排描述为 “An LLM tool that summarizes a list of ChatGPT papers.” 的仓库。请用这句和一个真正的论文清单做对照，检查程序能区分仓库提供的工具与工具处理的内容。 [论文规则](https://github.com/MANHO219/github_activity_analyze_project/blob/c0944d4/b_repo_metadata/rules/ai_rules_v0.3.6.json#L371)
2. 修 README 的离线重跑步骤。从只有已提交的元数据、README 和复核快照的目录开始，依次生成自动标签、合并人工复核和修订生成分析用表，再接回活动。当前说明跳过了生成分析用标签这一步。实测接回会退回自动标签，检查全部通过，但事件分布变为 109/387/576。pilot_02 生成分析用表时显式传入 `manual_review_pilot02.csv` 和 `manual_revisions.csv`。接回时明确传入 `repo_ai_labels_analysis.csv`，使用仓库中已共享的 `a_data_pipeline/sample_data/20240115_24h/repo_daily_counts.csv`。摘要要写清输入和实际用的标签字段。 [当前 README 命令](https://github.com/MANHO219/github_activity_analyze_project/blob/c0944d4/b_repo_metadata/README.md#L188)
3. 同步核对 `--labels` 的列选择。当前只看文件名是否以 `_analysis.csv` 结尾。同一份最终标签表换成 `custom.csv` 后会读错列并报错。按表头或显式参数选择字段，方便 C 和后续不同批次使用。 [标签列选择](https://github.com/MANHO219/github_activity_analyze_project/blob/c0944d4/b_repo_metadata/scripts/join_check.py#L50)

两个 PR 的标签摘要还有相同的 SHA-256 问题。每个 PR 的两批试点各有三项，即规则、元数据和标签表。摘要值与 CRLF 换行的内容一致，Git 提交中的文件使用 LF。请按最终入库的文件字节更新摘要，并在干净检出上复核。#8 已包含 #5 的 R12 修复，等 #5 范围确定并收尾后，把 #8 更新到对应基线。

## 合并后的验证

保留 50 和 200 仓库的试跑，作为流程验证和调规则的记录。规则定稿后，从 A 后续提供的候选仓库中抽一批没参与调规则的仓库。先独立人工判定，再对照自动标签。按抽样来源和标签类别记录复核分母、误纳入、漏掉的 AI 仓库、因证据缺失继续存疑的数量和典型案例。若进入 2024、2026 两个观察窗口，采用相同的规则、抽样与人工判定口径，分别报告两批的元数据与标签覆盖。

LLM 是可选的小对照。先挑仍是 `uncertain` 且有可核对描述或 README 的仓库，保留人工独立判定。对比正确补判数、新增误判、耗时与调用费用，再决定是否采用。标签来源可追溯，并保留自动、人工和 LLM 各自的结果。

最终给 C 的是一仓库一行的分析用标签表，附创建时间或对应元数据、最终标签、标签来源、缺失状态和规则版本。验收时一起交复核明细与一页结果说明。
