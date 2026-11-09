# AI 相关仓库判定规则 v0.2

- **规则版本：** `ai_rules_v0.2`（机器可读版本见 [ai_rules_v0.2.json](ai_rules_v0.2.json)）
- **上一版：** [`ai_rules_v0.1`](ai_rules_v0.1.md)（保留，标签结果在 `repo_ai_labels_v0.1.csv`）
- **状态：** 草案，待 A、B 确认后冻结
- **依据：** pilot_01 的 33 条人工复核（2026-11-02）

v0.2 只做**能从复核结果明确推出**的改动：弱信号降级、课程作业识别、个人主页识别。涉及研究口径的问题（AI 附加功能是否纳入、弱信号是否直接排除、README 能否作为规则输入）列在第 6 节，等统一确认，不在代码里抢先实现。

## 1. 变更摘要

| 改动 | v0.1 | v0.2 | 依据案例 |
|---|---|---|---|
| 裸 `ai`/`ml` 信号 | topic 或描述命中即 `included` | 降为弱信号：需描述中的佐证词，否则 `uncertain` | `weseek/growi` 因 topic 含 `ai` 被误判为入选 |
| 课程作业 | 只有资源集合关键词，未单列 | 新增 `R3b_coursework`，从仓库名/描述识别课程、大作业、训练营、课程实验 | IBM 课程 final project、Openclassrooms P11、cs933 课程实验 |
| 个人主页仓库 | 描述与 topics 为空 → `uncertain` | 新增 `R3c_profile_repository`：`owner/repo` 同名且无描述无 topics → `excluded` | 6 个 profile README 仓库在复核中被人工排除 |
| AI 关键词表 | 单一词表 | 拆成 strong / weak 两组，另设佐证词表 | 区分“AI 是产品的核心”与“AI 只是标签” |
| 名称命中 | `uncertain` | 不变（`R6`） | 名称无法区分课程作业、个人项目与真实 AI 项目 |

## 2. 判定顺序

先命中先返回：

| 顺序 | 规则 ID | 触发条件 | 输出 |
|---|---|---|---|
| 1 | `R1_metadata_unavailable` | 元数据取不到（404、5xx、网络错误） | `uncertain` |
| 2 | `R2_api_id_mismatch` | API 返回 `id` ≠ A 的 `repo_id` | `uncertain` |
| 3 | `R3b_coursework` | 仓库名或描述命中课程/作业/训练营模式 | `excluded` |
| 4 | `R3c_profile_repository` | `owner/repo` 同名，且描述与 topics 都为空 | `excluded` |
| 5 | `R3_resource_collection` | awesome、教程、笔记、链接合集等资料集合 | `excluded` |
| 6 | `R4_topic_match` | topic 命中 **strong** 词表 | `included` |
| 7 | `R5_description_match` | 描述命中 **strong** 关键词 | `included` |
| 8 | `R5b_weak_signal_corroborated` | 只有弱信号，但描述含佐证词 | `included` |
| 9 | `R4b_weak_topic_only` | 只有裸 `ai`/`ml` topic，无佐证词 | `uncertain` |
| 10 | `R5c_weak_signal_only` | 只有裸 `ai`/`ml` 描述，无佐证词 | `uncertain` |
| 11 | `R6_name_only_signal` | 只有仓库名像 AI | `uncertain` |
| 12 | `R7_insufficient_text_evidence` | 描述与 topics 都为空 | `uncertain` |
| 13 | `R8_no_ai_signal` | 有文本但无任何 AI 信号 | `excluded` |

课程作业排在资料集合之前，是为了让理由写到更具体的规则上（`R3b` 而不是笼统的 `R3`）。

## 3. 弱信号与佐证词

**弱信号：** `ai`、`ml` 两个词（作为 topic 或描述中的整词）。它们太泛：既是研究对象的缩写，也是“AI 辅助功能”的营销词。

**佐证词**（描述中出现任一即可把弱信号升为 `included`）：`sdk`、`api`、`platform`、`framework`、`toolkit`、`engine`、`model`（含“模型”）、`training`/`train`/`inference`（含“训练”“推理”）、`dataset`（含“数据集”）、`vision`、`speech`、`detection`、`classification`、`segmentation`、`recognition`（含“视觉”“语音”）、`llm`、`gpt`、`chatgpt`、`prompt`、`agent`、`chat`、`embedding`、`rag`、`transformer`、`diffusion`、`openai`/`anthropic`/`huggingface`/`langchain`/`llama`/`mistral`、`benchmark`、`neural`、`research`、`copilot`、`assistant`、`chatbot`。

两个真实例子：

| 仓库 | 描述 | v0.2 判定 | 原因 |
|---|---|---|---|
| `Epigos-AI/epigos-python` | Epigos AI SDK for Python | `included` | 弱信号 `ai` + 佐证词 `sdk` |
| `weseek/growi` | Team collaboration software using markdown | `uncertain` | 只有 topic `ai`，描述里没有任何佐证词 |

## 4. 课程作业与个人主页

**课程作业（`R3b`）** 命中以下任一：

- 仓库名：`course`、`coursework`、`homework`、`assignment`、`capstone`、`bootcamp`、`udemy`、`coursera`、`udacity`；`final-project`、`openclassrooms`；`-lab`、`-lab2`、`-hw3` 这类结尾。
- 描述：`course(s)`、`coursework`、`homework`、`assignment(s)`、`final project`、`capstone`、`bootcamp`、`udemy`、`coursera`、`udacity`、`lesson`、`lecture`；中文“课程、作业、实验课、练习题、大作业”。

只命中真正表示教学的词：`lab` 只在名字以 `-lab`/`-lab2` 结尾时算，避免把 `lab-webpage`（实验室主页）误判为课程作业。

**个人主页（`R3c`）** 需同时满足：`owner/repo` 同名、描述为空、topics 为空。这是 GitHub profile README 的典型形态；仓库里没有项目内容，生命周期分析对它没有意义。

## 5. 与 v0.1 的对比（同一批 50 个仓库）

| 指标 | v0.1 | v0.2 |
|---|---:|---:|
| `included` | 3 | 1 |
| `excluded` | 22 | 30 |
| `uncertain` | 25 | 19 |
| 与人工判断在“已判定行”上的一致率 | 6/8 = 75% | 14/14 = 100% |
| 人工推翻（disagree） | 2 | 0 |
| 人工判定后仍有 8 条存疑（404/ID 不一致等） | 8 | 8 |

共 11 条变化：9 条标签变化、2 条仅规则理由变化。其中 8 条与人工结论由“不一致或存疑”变成一致，0 条回退。逐条记录见 `runs/pilot_01/label_changes.csv` 与 `label_comparison.json`。

仍然存疑的 19 条分三类：

1. 5 个 404 + 2 个 ID 不一致（元数据缺失，规则无法处理）；
2. 3 个名称命中且描述为空（`ML-project`、`PrivateGPT`、`MLOps 课程仓库`）——复核用 README 已判定，但规则不读 README；
3. 9 条其他（GROWI 弱信号、作品集网站、游戏 mod 等，人工已用 README 给出结论）。

## 6. 待统一确认的口径（影响 v0.3，不在 v0.2 生效）

1. **弱信号 + 非 AI 描述：改 `excluded` 还是维持 `uncertain`？** v0.2 保守地记 `uncertain`；`GROWI` 这类“有 AI 功能但主体不是 AI”的仓库，人工判为 `excluded`。
2. **“仅集成 AI 功能”的项目是否纳入？** 目前只要描述或 topic 明确声明 AI 能力就纳入；若决定排除，需要在 v0.3 增加“主体非 AI”的判定（难度较高，可能只能交给人工）。
3. **名称命中且描述为空时，是否允许抓 README 作为规则输入？** 当前规则只用 API 字段，README 仅作复核证据；若允许，规则会依赖可变内容，需要固定 README 快照时间。
4. **课程作业的边界：** 公开课/训练营作业（如 Openclassrooms、Coursera）是否与学校课程同等排除？v0.2 一律排除。
5. **个人主页仓库：** 是否只排除 `owner/repo` 同名且无语言、无描述的仓库（更严格），以免误伤同名但确有项目的仓库？v0.2 没有要求“无语言”。

## 7. 改规则的方式

1. 复制 `ai_rules_v0.2.json` 为 `ai_rules_v0.3.json`，只改 JSON 与 `version`/`changes_from_*`；
2. 用同一批输入重跑 `label_repositories.py --rules rules/ai_rules_v0.3.json`；
3. 用 `compare_label_versions.py` 生成变化清单；
4. 旧版本的 JSON 与标签表都保留，任何结论都能回溯到当时的规则。
