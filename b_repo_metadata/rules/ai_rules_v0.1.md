# AI 相关仓库判定规则 v0.1

- **规则版本：** `ai_rules_v0.1`（机器可读版本见 [ai_rules_v0.1.json](ai_rules_v0.1.json)）
- **状态：** 草案，待 A、B 共同确认后冻结
- **提出者：** B；**确认者：** A + B（待定）
- **首次应用：** `runs/pilot_01`（2026-11-02，50 个仓库）

代码实现见 [`bmeta/rules.py`](../bmeta/rules.py)：规则内容只在 JSON 里维护，代码只负责按顺序执行并记录理由，避免文档与实现各说一套。

## 1. 判定对象与可见信息

- 判定单位是 A 的 `repo_id`（一个仓库一行），不是事件、不是用户名。
- v0.1 只读仓库 API 快照里的四个字段：`description`、`topics`、`full_name`（仓库名）、`language`/`archived`（只做记录，不参与判定）。
- 不读 README、不看代码内容、不请求仓库历史。人工复核可以读 README，但那是复核证据，不是规则输入。
- 快照时间是抓取时刻（本次为 2026-11-02），**不是** 2024-01-15 事件发生时的状态。

## 2. 纳入与排除的定义

| 类别 | 定义 | 输出 |
|---|---|---|
| 纳入 | topic 或描述表明仓库**核心用途**是 AI/机器学习：模型、训练或推理、数据集与评测、AI 应用、AI 工程工具 | `included` |
| 排除 | 元数据可读，但命中资料集合模式，或未命中任何 AI 信号 | `excluded` |
| 存疑 | 元数据缺失、ID 不一致，或只有名称像 AI、文本证据不足 | `uncertain` |

三条口径需要说清楚：

1. **`excluded` 是“本轮规则未命中”，不是“确定与 AI 无关”的断言。** 抽样审计只能说明规则在样本上的表现。
2. **资料集合一律排除**：awesome 列表、教程、课程作业、学习笔记、题库、链接合集等，即使描述里满是 AI 关键词。理由是这类仓库的生命周期由内容整理行为驱动，与“AI 项目是否持续开发”不是同一个研究对象。
3. **“仅集成 AI 功能”的项目 v0.1 暂不单独排除**：只要描述或 topic 明确声明 AI 能力就纳入。这条口径已知偏宽（`GROWI` 案例即由此误判），是否改为排除由 A、B 在 v0.2 决定。

## 3. 判定顺序

先命中先返回，后面的规则不再执行：

| 顺序 | 规则 ID | 触发条件 | 输出 |
|---|---|---|---|
| 1 | `R1_metadata_unavailable` | `fetch_status` 不是 `ok`/`ok_cached`（404、5xx、网络错误） | `uncertain` |
| 2 | `R2_api_id_mismatch` | API 返回的 `id` ≠ A 的 `repo_id`（同名仓库被改名或复用） | `uncertain` |
| 3 | `R3_resource_collection` | 仓库名或描述命中 awesome / 教程 / 课程作业 / 笔记 / 链接合集 | `excluded` |
| 4 | `R4_topic_match` | `topics` 精确命中 AI topic 词表（小写、整词） | `included` |
| 5 | `R5_description_match` | 描述命中 AI 关键词正则（英文整词 + 中文词） | `included` |
| 6 | `R6_name_only_signal` | 只有 `owner/repo` 名称像 AI，描述与 topics 都没有证据 | `uncertain` |
| 7 | `R7_insufficient_text_evidence` | 描述与 topics 同时为空 | `uncertain` |
| 8 | `R8_no_ai_signal` | 描述或 topics 有内容，但没有任何 AI 信号 | `excluded` |

顺序设计的原因：

- 元数据不可用或 ID 不一致时，任何文本判定都不可靠，所以排在最前；
- 资料集合排除优先于 AI 纳入，避免 `awesome-llm` 这类仓库因为关键词最多而被判为入选；
- topic 优先于描述：topic 是维护者主动声明的分类，噪声低于自然语言描述；
- 名称只作弱信号：`ML-project`、`chatbot-xxx` 可能是 AI，也可能是课程作业或演示仓库，必须人工确认；
- 描述与 topics 都为空时保留 `uncertain`，符合“当前信息不足不能直接判为非 AI”。

## 4. 关键词来源

**AI topics（整词匹配，节选）：** `machine-learning`、`deep-learning`、`llm`、`gpt`、`chatgpt`、`generative-ai`、`transformers`、`pytorch`、`tensorflow`、`computer-vision`、`nlp`、`rag`、`stable-diffusion`、`vector-database`、`llm-agents`、`mlops`、`openai`、`langchain`、`huggingface`、`whisper`、`yolo` 等，完整列表见 JSON 的 `ai_topic_terms`。

**描述关键词（正则，词边界）：** `machine learning`、`deep learning`、`artificial intelligence`、`neural network`、`large language model`、`LLM`、`GPT`、`chatgpt`、`diffusion model`、`transformer`、`pytorch`、`scikit-learn`、`reinforcement learning`、`retrieval augmented generation`、`fine-tuning`、`prompt engineering`、`embedding`、`object detection`、`speech recognition`、`text-to-speech`，以及中文的“机器学习 / 深度学习 / 人工智能 / 大模型 / 神经网络 / 自然语言处理 / 计算机视觉 / 强化学习 / 生成式 / 微调 / 向量数据库 / 智能体 / 模型训练”。

**资料集合模式：** `awesome`、`curated`、`a list of`、`collection of`、`tutorial`、`walkthrough`、`course`、`lecture`、`homework`、`assignment`、`study notes`、`cheat sheet`、`roadmap`、`interview questions`，以及中文的“教程 / 课程 / 作业 / 笔记 / 题库 / 大全 / 资料 / 入门指南 / 学习路线 / 面试题”；仓库名里 `awesome-`、`-notes`、`-course` 等也计入。

**名称弱信号：** `ai`、`ml`、`llm`、`gpt`、`openai`、`langchain`、`transformer`、`pytorch`、`tensorflow`、`nlp`、`computer-vision`、`neural`、`chatbot`、`mlops`、`whisper` 等。

## 5. 规则不做什么

- 不判断仓库质量、活跃度或是否值得研究；
- 不因为描述里出现一次 `AI` 就把整个组织/用户判为 AI；
- 不把 `archived`、星数、语言当作纳入条件（只记录，供 C 分析）；
- 不对 404 仓库做“已删除/已私有化”的推断，只记录无法获取；
- 不读 README 和代码：v0.1 刻意只用稳定、可批量获取的 API 字段，README 变化快且需要额外请求。

## 6. pilot_01 暴露的问题

50 个仓库的试跑与 33 条人工复核（含 README 证据）显示：

1. **裸 `ai` topic 过强**：`weseek/growi`（团队协作 wiki）因 topic 含 `ai` 被判 `included`，人工判为 `excluded`。
2. **课程作业没有被识别**：`ibm-developer-skills-network/...final-project-emb-ai` 被描述里的 `ai` 词元命中，人工判为课程作业 `excluded`。
3. **个人主页/作品集仓库缺一层排除**：15 个描述与 topics 为空的仓库里，多数是 `owner/repo` 同名的个人主页仓库；规则只能判 `uncertain`，人工用 README 改判为 `excluded`。
4. **名称命中需要二次证据**：`ML-project`（实为 scikit-learn 项目，应 `included`）与 `mlops-with-aws-datascientists`（实为课程仓库，应 `excluded`）都只能判 `uncertain`。

## 7. v0.2 候选（待 A、B 决定，未在 v0.1 生效）

| 候选改动 | 目的 | 需要的证据 |
|---|---|---|
| 裸 `ai`/`ml` 词元降权：单独出现时只记弱信号，需 topic 或描述中的强词佐证 | 消除 GROWI 类误判 | 复核中 2 个误判案例 |
| 增加非项目仓库排除：`owner/repo` 同名 + 无描述 + 无 topics + 无语言 → `excluded` | 减少个人主页仓库带来的 uncertain | 复核 8 个 profile 案例 |
| 增加课程/作业排除：名称或描述含 `course`、`final-project`、`openclassrooms`、`assignment` 等 | 处理课程作业边界 | IBM、Openclassrooms 2 个案例 |
| 名称命中后抓取 README 再判 | 用更多证据替代 uncertain | 3 个名称命中案例 |
| 规则版本与 API 快照时间写入每行标签 | 支持历史回溯 | 本版已记录 `metadata_fetched_at_utc` |

改动方式：复制 `ai_rules_v0.1.json` 为 `ai_rules_v0.2.json`，只改 JSON 与版本号，重跑 `label_repositories.py` 生成新的 `repo_ai_labels.csv`，旧表与新表都保留，便于对比标签漂移。
