# 基于 hello-agents 规范的科研多 Agent 实现细节

## 1. 目标定义

本系统目标是实现一个面向科研工作的多 Agent 协作系统，覆盖文献调研、创新点筛选、实验设计、代码生成、论文撰写、导师审核、审稿人盲审等完整流程。

系统内包含三个核心子 Agent：

- `StudentAgent`：对应研究生，负责读文献、提创新点、设计实验、生成代码、撰写论文、自审。
- `AdvisorAgent`：对应导师，负责创新点把关、实验结果评估、论文二轮审核。
- `ReviewerAgent`：对应审稿人，负责第三方盲审与审稿结论输出。

按照 `hello-agents` 的实现思路，系统应满足以下约束：

- Agent 角色职责单一，不把所有能力混在一个超大 Prompt 中。
- 对外暴露统一输入输出接口，便于编排和替换模型。
- 工具能力独立封装，Agent 通过工具调用完成 PDF 解析、文档生成、代码落盘、消息传递等操作。
- 采用状态驱动工作流，而不是无边界自由对话。
- 重要中间产物全部文档化、可追踪、可回滚。
- 允许人在关键节点介入，防止“自动化科研”脱离真实实验结果。

## 2. 推荐目录结构

```text
AI-Scientist/
├─ app/
│  ├─ agents/
│  │  ├─ base_agent.py
│  │  ├─ student_agent.py
│  │  ├─ advisor_agent.py
│  │  └─ reviewer_agent.py
│  ├─ workflows/
│  │  ├─ state_machine.py
│  │  ├─ literature_workflow.py
│  │  ├─ innovation_workflow.py
│  │  ├─ experiment_workflow.py
│  │  └─ paper_workflow.py
│  ├─ tools/
│  │  ├─ pdf_parser.py
│  │  ├─ paper_search.py
│  │  ├─ markdown_writer.py
│  │  ├─ code_generator.py
│  │  ├─ file_store.py
│  │  └─ message_bus.py
│  ├─ memory/
│  │  ├─ session_memory.py
│  │  ├─ vector_memory.py
│  │  └─ artifact_index.py
│  ├─ schemas/
│  │  ├─ agent_message.py
│  │  ├─ paper_note.py
│  │  ├─ innovation_card.py
│  │  ├─ experiment_plan.py
│  │  ├─ experiment_result.py
│  │  ├─ manuscript_review.py
│  │  └─ workflow_state.py
│  ├─ prompts/
│  │  ├─ student/
│  │  ├─ advisor/
│  │  └─ reviewer/
│  └─ main.py
├─ workspace/
│  ├─ papers/
│  ├─ parsed_papers/
│  ├─ literature_reports/
│  ├─ innovation_meetings/
│  ├─ experiment_plans/
│  ├─ experiment_results/
│  ├─ manuscripts/
│  ├─ reviews/
│  └─ logs/
└─ 实现方式/
```

这套结构符合 `hello-agents` 里常见的“Agent 层、Tool 层、Workflow 层、Schema 层、Memory 层”拆分方式，后续扩展新角色时不会破坏主流程。

## 2.1 首选技术栈

你这类科研多 Agent 系统，首选技术栈建议明确为 `LangChain + LangGraph`。

推荐组合如下：

- Agent 与工具抽象：`LangChain`
- 多 Agent 状态编排：`LangGraph`
- 结构化输出：`Pydantic`
- 文档生成与工件管理：`Markdown + YAML Front Matter`
- 向量检索：`LangChain VectorStore` 接口
- 长期记忆与状态持久化：`LangGraph Checkpointer + 本地文件索引`
- PDF 解析：独立 Parser Tool，再通过 `LangChain Tool` 暴露给 Agent

这样选型的原因：

- `LangChain` 适合封装 Prompt、Tool、结构化输出、检索链路。
- `LangGraph` 适合实现多角色、多阶段、可中断恢复的科研工作流。
- 两者组合后，既能保留 `hello-agents` 的分层思路，也能快速落成可运行工程。

## 2.2 推荐范式：Plan-and-Solve 外壳 + ReAct 内核

这套科研多 Agent 系统，不建议做成“全局纯 ReAct”，更适合做成混合范式：

- 系统全局编排使用 `Plan-and-Solve`
- 单个 Agent 内部执行使用 `ReAct`

原因如下：

- 科研流程天然是长链路、多阶段、强状态约束任务，适合先规划再执行。
- 单个角色在处理局部任务时，又需要边思考边查资料边调工具，这更适合 `ReAct`。
- 研究生、导师、审稿人之间存在大量“提交 -> 审核 -> 打回 -> 重做”的回环，这适合由 `LangGraph` 控制状态跳转，而不是靠自由对话维持。

因此，推荐你把系统理解为：

`Plan-and-Solve` 负责控制“什么时候做什么、谁来做、是否通过、打回给谁”，`ReAct` 负责控制“当前这个角色如何调用工具完成本轮任务”。

## 3. 核心抽象设计

## 3.1 BaseAgent 抽象

三个角色都继承统一的 `BaseAgent`，保证交互协议一致。

建议统一接口：

```python
class BaseAgent:
    def __init__(self, name, role, model, tools, memory, prompt_template):
        pass

    def run(self, task_input: dict, context: dict) -> dict:
        pass

    def think(self, task_input: dict, context: dict) -> dict:
        pass

    def act(self, plan: dict) -> dict:
        pass

    def review(self, artifact: dict, review_rules: dict) -> dict:
        pass
```

这样做的好处：

- 上层工作流不需要关心具体是研究生、导师还是审稿人。
- 后续可以替换不同大模型，只要保持协议一致即可。
- 便于对各 Agent 的输出做统一校验与日志记录。

## 3.2 Tool 抽象

工具必须从 Prompt 中剥离，否则复杂科研流程很快会失控。

建议每个工具都遵循以下模式：

```python
class BaseTool:
    name: str
    description: str

    def invoke(self, **kwargs) -> dict:
        pass
```

重点工具如下：

- `PaperSearchTool`：检索目标方向论文元数据。
- `PdfParserTool`：解析 PDF 文本、章节、公式、图表标题、参考文献。
- `PaperRelationTool`：判断论文是否属于基于基座论文的改进工作。
- `MarkdownWriterTool`：生成并保存 Markdown 报告。
- `CodeScaffoldTool`：生成 Python 实验代码框架。
- `ArtifactStoreTool`：保存与读取中间产物。
- `MessageBusTool`：完成 Agent 间消息传递。
- `HumanFeedbackTool`：等待人类输入实验结果或人工修改意见。

## 3.3 Schema 约束

`hello-agents` 的一个关键思想是让 Agent 输出结构化结果，而不是只返回自然语言。

建议核心数据结构如下：

- `PaperNote`
  - `paper_id`
  - `title`
  - `venue`
  - `year`
  - `summary`
  - `innovation_points`
  - `limitations`
  - `base_paper`
  - `improvements_over_base`
- `InnovationCard`
  - `name`
  - `motivation`
  - `novelty_type`
  - `related_work_overlap`
  - `feasibility`
  - `expected_gain`
  - `advisor_feedback`
  - `status`
- `ExperimentPlan`
  - `task_name`
  - `dataset`
  - `baseline_methods`
  - `proposed_method`
  - `metrics`
  - `ablation_design`
  - `compute_budget`
  - `python_modules`
- `ExperimentResult`
  - `run_id`
  - `metrics`
  - `comparison_tables`
  - `error_cases`
  - `human_confirmed`
- `ManuscriptReview`
  - `reviewer_role`
  - `decision`
  - `major_issues`
  - `minor_issues`
  - `revision_requests`

有了这些 Schema，系统才能稳定地把“读文献”流转到“提创新点”，再流转到“写论文”和“审稿”。

如果使用 `LangChain`，建议这些 Schema 直接定义为 `Pydantic` 模型，并通过结构化输出能力约束 Agent 返回值，而不是依赖自然语言后处理。

## 4. 三个 Agent 的实现细节

## 4.1 StudentAgent

`StudentAgent` 不是一个纯聊天机器人，而是一个有阶段目标的执行型 Agent。

在实现上，`StudentAgent` 建议采用 `ReAct Agent` 形态。

### 文献阅读职责

- 输入研究方向、关键词、顶会顶刊范围、论文列表。
- 调用 `PaperSearchTool` 和 `PdfParserTool`。
- 对每篇论文产出结构化 `PaperNote`。
- 如果识别到该论文是“基于某基座论文的改良”，则自动补读基座论文，再生成“改进点对比”。

这里很适合 `ReAct`：

- `Thought`：先判断该论文是否需要补读基座论文
- `Action`：调用 PDF 解析、检索、关系识别工具
- `Observation`：获取论文结构化信息
- `Thought`：总结创新点与不足点
- `Action`：写入 `PaperNote`

### 创新点生成职责

- 在累计阅读满 10 篇论文后，汇总所有 `PaperNote`。
- 输出《文献调研汇总报告.md》。
- 自动提炼 3 到 5 个 `InnovationCard`。
- 每个创新点都必须包含：
  - 新颖性来源
  - 与已有工作的差异
  - 可能提升的指标
  - 风险点
  - 是否需要更多实验支撑

这一段也建议保留 `ReAct` 风格，让 `StudentAgent` 在发现证据不足时继续回查文献，而不是一次性硬输出创新点。

### 组会汇报职责

- 将候选创新点发给 `AdvisorAgent`。
- 接收导师修改意见。
- 根据意见更新 `InnovationCard`。
- 只有 `status=approved` 的创新点，才允许进入实验阶段。

这里的关键不是研究生自己无限循环，而是：

- `StudentAgent` 节点内部用 `ReAct` 迭代思考与修改
- 节点之间由 `LangGraph` 判断“通过 / 打回 / 再修改”

### 实验设计职责

- 生成《实验设计方案.md》。
- 输出实验环境、依赖、训练/验证/测试划分、评价指标、对照组、消融实验、复现实验步骤。
- 若领域为人工智能相关，调用 `CodeScaffoldTool` 生成 Python 项目框架。
- 代码输出必须与实验方案一一对应，避免“代码写了但实验设计文档没有定义”的情况。

### 论文撰写职责

- 人类反馈实验结果后，先生成《实验结果解读与论文话术草案.md》。
- 再基于真实结果撰写论文。
- 必须显式禁止以下行为：
  - 编造结果
  - 编造数据集划分
  - 编造超参数
  - 编造引用
  - 夸大结论

### 自审职责

- 每个论文版本完成后，先调用自身 `review()` 执行第一轮自审。
- 自审清单应包括：
  - 创新点是否与方法章节一致
  - 实验表格是否与真实结果一致
  - 引文是否真实存在
  - 结论是否超出证据范围

## 4.2 AdvisorAgent

`AdvisorAgent` 是质量门禁角色，不负责替学生直接做完全部工作。

`AdvisorAgent` 也建议做成 `ReAct Agent`，但它的工具权限和上下文范围要比研究生更受限。

### 创新点审核

- 判断创新点属于：
  - 基于基座论文的结构改进
  - 新损失函数/训练策略
  - 多模块组合创新
  - 任务迁移或范式创新
- 检查是否可能属于低价值增量。
- 检查是否与近年工作高度重复。
- 给出“通过 / 退回修改 / 建议放弃”三类结论。

导师节点的 `ReAct` 模式可以是：

- `Thought`：判断当前创新点属于哪类创新
- `Action`：检索相关工作、读取组会材料、读取文献总结
- `Observation`：得到重合度、可行性、风险信息
- `Thought`：形成审核判断
- `Action`：输出结构化审核意见

### 实验结果审核

- 审查是否有充分 baseline。
- 审查是否有消融实验。
- 审查评价指标是否覆盖任务核心目标。
- 审查结果是否稳定，是否需要多次运行求均值和方差。
- 审查是否存在：
  - 对照组缺失
  - 参数设置不公平
  - 数据泄露
  - 只挑最好结果汇报

### 论文二审

- 按学术论文标准检查章节完整性。
- 重点看方法描述是否准确。
- 检查实验分析是否真正支撑创新点。
- 检查语言是否存在模糊表述、跳步推理、结论过度泛化。
- 审核通过后才进入 `ReviewerAgent` 三审。

如果发现证据链不完整，导师节点可以继续回查实验方案、实验结果、论文对应章节，这也是典型的局部 `ReAct`。

## 4.3 ReviewerAgent

`ReviewerAgent` 应模拟顶会 / 顶刊审稿人，不继承导师视角。

`ReviewerAgent` 同样建议采用 `ReAct`，但必须严格限制输入来源，只允许读取论文正文、图表、实验结果附件、参考文献等“盲审可见材料”。

### 审稿风格要求

- 只依据论文文本与附带材料判断，不读取内部讨论历史。
- 以匿名第三方视角给出结论。
- 输出要尖锐，但必须具体且可修改。

### 审稿维度

- 创新性：是否只是已有模块拼接，是否真有原创贡献。
- 科学性：实验设计是否充分，是否有泄露、偏置、不公平对比。
- 写作质量：逻辑是否清晰，图表是否自解释，术语是否规范。
- 学术规范：引用是否准确，是否有夸大陈述。

审稿人的 `ReAct` 重点不在生成内容，而在逐条质疑、核查、回证据、再下结论。

### 结论格式

- `accept`
- `minor_revision`
- `major_revision`
- `reject`

同时输出：

- `summary`
- `strengths`
- `weaknesses`
- `required_changes`
- `confidence`

## 5. 多 Agent 协作工作流设计

## 5.1 总体状态机

建议采用状态机驱动，而不是纯链式调用。

```text
INIT
-> LITERATURE_READING
-> LITERATURE_SUMMARY
-> INNOVATION_PROPOSAL
-> ADVISOR_REVIEW_INNOVATION
-> INNOVATION_REVISION
-> EXPERIMENT_DESIGN
-> HUMAN_RUN_EXPERIMENT
-> RESULT_ANALYSIS
-> MANUSCRIPT_DRAFTING
-> STUDENT_SELF_REVIEW
-> ADVISOR_PAPER_REVIEW
-> REVIEWER_BLIND_REVIEW
-> REVISION_LOOP
-> FINAL_MANUSCRIPT
-> DONE
```

`hello-agents` 风格更适合这种“显式状态 + 显式转移条件”的实现方式，原因如下：

- 易于中断恢复。
- 易于插入人工确认。
- 易于记录每一步产物。
- 易于避免模型跳步骤。

这里可以明确理解为：

- 状态机层是 `Plan-and-Solve`
- 每个状态节点内部是 `ReAct`

也就是“图外控流程，图内做推理”。

如果使用 `LangGraph`，这里建议直接把每个阶段实现为一个图节点，每次节点执行后更新共享状态 `ResearchWorkflowState`。

推荐节点映射如下：

- `literature_reading_node`
- `literature_summary_node`
- `innovation_proposal_node`
- `advisor_review_innovation_node`
- `innovation_revision_node`
- `experiment_design_node`
- `human_feedback_node`
- `result_analysis_node`
- `manuscript_drafting_node`
- `student_self_review_node`
- `advisor_paper_review_node`
- `reviewer_blind_review_node`
- `revision_router_node`
- `finalize_node`

如果进一步按混合范式落地，建议改成更明确的角色化节点命名：

- `student_literature_react_node`
- `student_innovation_react_node`
- `advisor_innovation_review_react_node`
- `student_experiment_design_react_node`
- `student_result_analysis_react_node`
- `student_manuscript_react_node`
- `advisor_paper_review_react_node`
- `reviewer_blind_review_react_node`
- `revision_router_node`
- `finalize_node`

推荐状态字段如下：

- `topic`
- `paper_list`
- `paper_notes`
- `literature_report_path`
- `innovation_cards`
- `approved_innovation`
- `experiment_plan_path`
- `experiment_result_path`
- `manuscript_path`
- `advisor_review_path`
- `reviewer_review_path`
- `revision_round`
- `next_action`

## 5.2 各阶段输入输出

### 阶段 1：文献调研

- 输入：研究方向、关键词、论文来源、论文数量要求。
- 执行者：`StudentAgent`
- 工具：`PaperSearchTool`、`PdfParserTool`
- 输出：
  - `PaperNote` x 10
  - `文献调研汇总报告.md`

### 阶段 2：创新点讨论

- 输入：文献汇总报告、候选创新点。
- 执行者：`StudentAgent` + `AdvisorAgent`
- 输出：
  - `创新点候选列表.md`
  - `组会纪要.md`
  - 已批准的 `InnovationCard`

这一阶段最典型的循环模式是：

`StudentAgent(ReAct)` 产出创新点 -> `AdvisorAgent(ReAct)` 审核 -> 若打回则回到 `StudentAgent(ReAct)` 继续检索与修改 -> 再提交导师

### 阶段 3：实验设计

- 输入：已批准创新点。
- 执行者：`StudentAgent`
- 输出：
  - `实验设计方案.md`
  - Python 实验代码框架

### 阶段 4：人工执行实验

- 输入：实验设计方案、代码框架。
- 执行者：人类用户
- 输出：
  - 原始实验日志
  - 指标结果
  - 图表

这里必须保留人工节点，不能让 Agent 自己伪造“已跑实验”。

### 阶段 5：结果分析与论文写作

- 输入：真实实验结果。
- 执行者：`StudentAgent`
- 输出：
  - `实验结果解读与论文话术草案.md`
  - 论文初稿

### 阶段 6：导师二审

- 输入：论文初稿。
- 执行者：`AdvisorAgent`
- 输出：
  - `导师审稿意见.md`
  - 修改后论文版本

这里同样是：

`StudentAgent(ReAct)` 撰写/修改论文 -> `AdvisorAgent(ReAct)` 二审 -> 若打回则继续回到研究生节点

### 阶段 7：审稿人三审

- 输入：导师通过的论文版本。
- 执行者：`ReviewerAgent`
- 输出：
  - `盲审意见.md`
  - 审稿结论

这里是：

`ReviewerAgent(ReAct)` 输出三审意见 -> 若 `major_revision` / `reject`，返回研究生节点继续修改 -> 再进导师二审

## 5.3 打回与回环机制

你的场景不是线性流程，而是强回环流程，所以要在方案里明确写死回环机制。

建议回环规则如下：

- 创新点不通过
  - `advisor_innovation_review_react_node` -> `student_innovation_react_node`
- 实验设计不通过
  - `advisor_innovation_review_react_node` 或实验审核节点 -> `student_experiment_design_react_node`
- 论文二审不通过
  - `advisor_paper_review_react_node` -> `student_manuscript_react_node`
- 三审大修或拒稿
  - `reviewer_blind_review_react_node` -> `student_manuscript_react_node`
  - 修改后重新进入 `advisor_paper_review_react_node`

建议每次打回都生成以下状态字段：

- `review_round`
- `review_decision`
- `review_comments`
- `revision_requirements`
- `revision_target_node`

这样后续无论是恢复执行还是查看历史，都会非常清晰。

## 5.4 提交后挂起、收到回复再恢复

你这个多 Agent 系统还有一个非常关键的执行语义：

- 当前角色如果需要把产物提交给别的角色审核
- 当前角色必须立刻挂起
- 直到对方角色处理完成并返回结果
- 当前角色才能基于返回结果继续执行

这不是普通的函数串行调用，更像“提交任务 -> 挂起等待 -> 收到回执 -> 恢复执行”的协作流程。

例如：

- `StudentAgent` 写完创新点
- 提交给 `AdvisorAgent`
- `StudentAgent` 进入挂起状态
- `AdvisorAgent` 审核并返回“通过”或“打回修改”
- `StudentAgent` 恢复执行
  - 如果打回，则继续修改创新点
  - 如果通过，则进入实验设计

导师和审稿人的流程也是同样逻辑：

- 导师把论文提交给审稿人后，导师当前轮次也应挂起等待
- 审稿人返回盲审结果后，导师或研究生再继续后续修改流程

因此，系统应该把“角色切换”建模成显式的挂起与恢复，而不是让一个 Agent 在内部模拟另一个 Agent 的回复。

建议增加以下状态字段：

- `active_agent`
- `waiting_for_agent`
- `suspend_reason`
- `submitted_artifact_path`
- `submitted_artifact_type`
- `resume_token`
- `last_reply_message_id`
- `conversation_round`

建议状态含义如下：

- `active_agent`
  - 当前允许继续执行的角色
- `waiting_for_agent`
  - 当前正在等待哪个角色返回
- `suspend_reason`
  - 因为什么提交动作进入挂起
- `submitted_artifact_path`
  - 本轮提交出去的文档或工件路径
- `resume_token`
  - 用于恢复当前挂起任务的关联标识

推荐的挂起状态示意：

```json
{
  "active_agent": "student",
  "waiting_for_agent": "advisor",
  "suspend_reason": "innovation_review",
  "submitted_artifact_type": "innovation_card",
  "submitted_artifact_path": "workspace1/innovation_meetings/20260604_v2_创新点候选列表.md",
  "workflow_status": "suspended"
}
```

收到导师返回结果后的恢复状态示意：

```json
{
  "active_agent": "student",
  "waiting_for_agent": null,
  "suspend_reason": null,
  "last_reply_message_id": "msg_102",
  "review_decision": "revise",
  "workflow_status": "running"
}
```

从工作流角度，这意味着：

- 提交动作会触发“当前节点结束”
- 系统把控制权转交给目标角色节点
- 目标角色完成后写回结构化结果
- Router 根据返回结果恢复原角色，或者切换到下一阶段

这套机制必须写进方案，因为它决定了你的系统不是单纯的线性 Agent 链，而是带有显式等待语义的多角色协作图。

### 阶段 8：返修闭环

- 若结论为 `major_revision` 或 `reject`：
  - 返回 `StudentAgent`
  - 修改后重新进入导师二审
- 若结论为 `minor_revision` 或 `accept`：
  - 完成终稿整理

## 6. Agent 间消息传递机制

建议不要直接让一个 Agent 把完整自然语言历史原封不动发给另一个 Agent，而是采用结构化消息总线。

推荐消息结构：

```json
{
  "message_id": "msg_001",
  "from_agent": "student",
  "to_agent": "advisor",
  "stage": "innovation_review",
  "artifact_type": "innovation_card",
  "artifact_path": "workspace1/innovation_meetings/20260604_v1_创新点候选列表.md",
  "summary": "候选创新点共4个，请评估新颖性与可行性",
  "metadata": {
    "topic": "图像分割",
    "requires_reply": true,
    "suspend_current_agent": true,
    "resume_token": "resume_001"
  }
}
```

这样设计有三个好处：

- 可追踪每次协作的输入输出。
- 可直接把文档路径作为上下文，而不是塞入超长 Prompt。
- 可支持异步执行和失败重试。

除此之外，还建议把消息分成两类：

- `submission_message`
  - 当前角色提交工件给其他角色，并触发自身挂起
- `reply_message`
  - 被调用角色返回审核意见、是否通过、修改要求，并触发对方恢复执行

推荐 `reply_message` 结构：

```json
{
  "message_id": "msg_002",
  "reply_to": "msg_001",
  "from_agent": "advisor",
  "to_agent": "student",
  "stage": "innovation_review_reply",
  "decision": "revise",
  "comments_path": "workspace1/innovation_meetings/20260604_v1_导师反馈.md",
  "resume_token": "resume_001"
}
```

系统收到 `reply_message` 后，应执行以下动作：

- 校验 `resume_token` 是否匹配当前挂起任务
- 将 `waiting_for_agent` 清空
- 把 `active_agent` 切回原角色
- 把 `decision`、`comments_path` 写入工作流状态
- Router 决定是回到修改节点，还是进入下一阶段

这样，整个系统就会具备真正的“提交-等待-恢复”协作语义。

## 6.1 挂起/恢复的 LangGraph 落地方式

如果用 `LangGraph` 实现，建议把“挂起与恢复”视为正常状态转移，而不是异常逻辑。

推荐理解方式：

- 角色节点执行到“提交他人审核”时，不继续深入
- 只产出一条 `submission_message` 和一个 `suspended` 状态
- 图的控制权转到目标角色节点
- 目标角色返回 `reply_message` 后，再由 Router 恢复原角色节点

推荐节点流转示意：

```text
student_innovation_react_node
-> advisor_innovation_review_react_node
-> innovation_reply_router
-> student_innovation_react_node   (打回)
-> student_experiment_design_react_node   (通过)
```

论文审核阶段同理：

```text
student_manuscript_react_node
-> advisor_paper_review_react_node
-> advisor_reply_router
-> student_manuscript_react_node   (打回)
-> reviewer_blind_review_react_node   (通过)
```

盲审阶段同理：

```text
reviewer_blind_review_react_node
-> reviewer_reply_router
-> student_manuscript_react_node   (大修/拒稿)
-> finalize_node   (小修完成/接受)
```

这里最重要的不是“谁调用了谁”，而是：

- 谁当前在执行
- 谁正在等待别人
- 谁的结果会决定恢复到哪个节点

这三个信息必须进入工作流状态，而不能只留在自然语言上下文里。

## 7. 记忆与上下文设计

为了满足“支持上下文记忆和多轮对话”，建议把记忆拆成三层。

### 7.1 会话记忆

- 保存本轮任务状态。
- 适合存放当前阶段目标、最近一次反馈、当前版本号。

### 7.2 长期项目记忆

- 保存论文笔记、创新点历史、实验历史、审稿历史。
- 可使用向量数据库或本地嵌入索引。

### 7.3 工件索引记忆

- 不只记“说过什么”，更记“生成过什么文档”。
- 核心是文件路径、版本号、摘要、标签、阶段归属。

科研场景里，工件记忆通常比聊天记忆更重要，因为最终协作依赖的是文档与结果物，而不是闲聊上下文。

## 8. PDF 解析能力设计

用户明确要求支持论文 PDF 解析，因此这一层必须单独实现。

建议分为四步：

### 第一步：文本抽取

- 提取标题、作者、摘要、正文、章节、参考文献。

### 第二步：版面识别

- 标记图、表、公式、算法框。

### 第三步：语义切分

- 将论文切分为摘要、引言、方法、实验、结论等逻辑块。

### 第四步：信息抽取

- 抽取创新点句子。
- 抽取不足点句子。
- 抽取 baseline 名称、数据集、指标、消融实验设计。

建议输出 `parsed_papers/*.json`，而不是只保留原始纯文本，便于后续复用。

## 9. Python 代码生成功能设计

用户要求人工智能领域生成 Python 实验代码，因此代码生成模块应受实验方案约束。

建议生成内容包括：

- `train.py`
- `eval.py`
- `models/`
- `datasets/`
- `configs/`
- `README.md`

生成规则：

- 代码框架只根据已批准创新点和实验方案生成。
- 每个配置项都在实验方案中有来源。
- 不允许生成与论文写作不一致的虚假实验模块。
- 必须生成足够清晰的注释，便于人工继续补全与运行。

为了和你的仓库规范一致，后续如果真正生成 Python 代码，建议采用逐行注释风格。

## 10. 人类干预接口设计

这个系统不能完全封闭自动运行，必须保留人工接管点。

建议至少设置以下人工确认节点：

- 论文列表确认
- 候选创新点确认
- 导师通过后的最终创新点确认
- 实验设计确认
- 实验执行结果录入
- 论文终稿确认

推荐接口形式：

- CLI 输入
- Web 表单
- Markdown 文档回填

最实用的落地方式是“Agent 生成 Markdown -> 人类修改 Markdown -> 系统重新读取”，因为这最符合科研写作习惯。

## 11. 文档与版本管理规范

用户已经定义文档按 `日期_版本号_文档名称.md` 保存，这里建议进一步细化。

### 目录建议

- `workspace/literature_reports/`
- `workspace/innovation_meetings/`
- `workspace/experiment_plans/`
- `workspace/experiment_results/`
- `workspace/manuscripts/`
- `workspace/reviews/`

### 文件命名示例

- `20260604_v1_文献调研汇总报告.md`
- `20260605_v2_创新点候选列表.md`
- `20260607_v1_实验设计方案.md`
- `20260610_v3_论文初稿.md`
- `20260611_v1_导师审稿意见.md`
- `20260612_v1_盲审意见.md`

### 元数据建议

每份 Markdown 头部增加：

```yaml
---
title: 文献调研汇总报告
version: v1
date: 2026-06-04
stage: literature_summary
author_agent: StudentAgent
review_status: draft
related_artifacts:
  - papers/xxx.pdf
---
```

这样做便于后续自动检索与版本追踪。

## 12. 推荐工作流编排方式

如果按 `hello-agents` 的范式落地，建议采用“Planner + State Machine + Tool Executor”的组合，而不是只写一个无限循环 Agent。

推荐编排分层：

- `Planner`
  - 决定当前阶段目标
  - 选择下一个状态
- `Executor`
  - 调用指定 Agent
  - 调用指定 Tool
- `StateStore`
  - 持久化工作流状态
- `ArtifactManager`
  - 保存阶段产物

如果首选 `LangGraph`，则可以把这四层进一步映射成：

- `Planner`：由条件边和 Router Node 承担
- `Executor`：由 Node 内部调用 `LangChain Agent / Runnable / Tool`
- `StateStore`：由 `LangGraph` 状态对象和 Checkpointer 承担
- `ArtifactManager`：由你自定义的文件工件管理模块承担

如果再结合混合范式，可以进一步理解成：

- `Plan-and-Solve`
  - 由 `LangGraph` 的图结构、状态对象、条件边承担
- `ReAct`
  - 由每个角色节点内部的 `LangChain Agent` 承担

工作流伪代码示例：

```python
while state != "DONE":
    current_task = planner.next(state, context)
    result = executor.run(current_task)
    artifact_manager.save(result)
    state = transition(current_state=state, result=result)
```

这种设计对科研场景尤其重要，因为流程长、工件多、人工反馈频繁。

建议优先使用 `StateGraph`，而不是把所有逻辑塞进单个 ReAct Agent。因为你的需求本质上是“多阶段科研流程系统”，不是“单轮工具调用机器人”。

推荐伪代码：

```python
def student_innovation_react_node(state):
    # 研究生在本节点内部用 ReAct 调工具、查文献、改创新点
    result = student_react_agent.invoke(state)
    return {"innovation_cards": result["innovation_cards"]}


def advisor_innovation_review_react_node(state):
    # 导师在本节点内部用 ReAct 审核创新点并决定是否打回
    review = advisor_react_agent.invoke(state)
    return {
        "review_decision": review["decision"],
        "review_comments": review["comments"],
    }


def innovation_router(state):
    if state["review_decision"] == "approved":
        return "student_experiment_design_react_node"
    return "student_innovation_react_node"
```

## 13. 质量控制与安全约束

科研 Agent 最需要防的不是代码报错，而是学术失真。

因此必须加入硬性约束：

- 未经人类确认的实验结果，不得写入论文结论。
- 无法验证的引用，不得自动写入参考文献。
- 未完成对照实验时，不得宣称方法全面优于现有方法。
- 审稿人结论不得读取导师内部意见，避免角色串味。
- 每一轮改稿都要保留历史版本，不能覆盖。

建议额外增加一个 `IntegrityChecker`：

- 检查结果表是否来自真实实验文件。
- 检查引用是否可在文献库中找到。
- 检查论文中出现的数字是否能在实验结果记录中追溯。

## 14. 最小可行版本实现建议

如果你准备先做第一版，建议不要一开始就追求全自动。

### 第一阶段 MVP

- 支持单领域论文列表导入
- 支持 10 篇论文 PDF 解析
- 支持 `StudentAgent` 生成论文笔记
- 支持生成文献调研汇总报告
- 支持 `StudentAgent` 与 `AdvisorAgent` 创新点往返评审
- 支持生成实验设计方案
- 支持人工录入实验结果
- 支持生成论文初稿
- 支持导师二审与审稿人三审

### 第二阶段增强

- 接入向量检索
- 接入论文关系图谱
- 自动识别基座论文
- 自动生成图表描述
- 支持多轮返修自动追踪

### 第三阶段增强

- 支持多个研究方向并行项目
- 支持多模型协同
- 支持 Web 界面
- 支持论文模板切换

## 15. 你这个需求最适合的技术路线

如果以 Python 为主实现，推荐路线如下：

- Agent 框架层：`LangChain`
- 工作流编排层：`LangGraph`
- 模型调用层：统一封装 `LangChain Chat Model`
- 状态编排层：`LangGraph StateGraph + Router`
- 文档层：`Markdown + YAML Front Matter`
- 记忆层：`LangChain Retriever + VectorStore`，配合本地工件索引
- 持久化层：`LangGraph Checkpointer + workspace 文件系统`
- 工具层：PDF 解析、文件存储、消息总线、代码模板生成，并统一包装成 `LangChain Tool`

更具体的模块建议如下：

- `StudentAgent`
  - 用 `LangChain ReAct Agent` 封装提示词、结构化输出、工具调用
- `AdvisorAgent`
  - 用 `LangChain ReAct Agent` 封装审核链，输出标准化审查结果
- `ReviewerAgent`
  - 用 `LangChain ReAct Agent` 封装盲审链，严格限制输入上下文
- `ResearchWorkflow`
  - 用 `LangGraph` 组织三类 Agent 的调用顺序和返修分支，整体遵循 `Plan-and-Solve`
- `MemoryManager`
  - 用 `LangChain` 的检索接口接向量库或本地索引
- `ArtifactManager`
  - 独立管理 Markdown、实验记录、评审记录的落盘和版本号

推荐的依赖方向：

- `langchain`
- `langgraph`
- `pydantic`
- `langchain-text-splitters`
- `langchain-community`
- 向量库按你的部署偏好选择 `faiss-cpu`、`chroma` 或其他后端

如果后续你要做第一版代码骨架，我建议直接按 `LangGraph + Pydantic State + LangChain Tools` 起手，这样最贴近你现在这份需求。

再进一步，建议直接按下面这个组合起手：

- `LangGraph StateGraph`
- `Pydantic Workflow State`
- `Student/Advisor/Reviewer ReAct Agents`
- `Router Nodes`
- `Artifact Persistence`

这会比“一个超级大 Agent + 很长 Prompt”稳定得多，也更符合你当前这个需要多轮打回和多人协作的科研场景。

原因是你的目标不是做一个“会聊天的科研助手”，而是做一个“可追踪、可审计、可协作”的科研工作流系统。

## 16. 落地建议总结

要让这个科研 Agent 真正可用，核心不是把三个角色 Prompt 写长，而是把下面五件事做好：

- 角色边界清晰。
- 工作流状态明确。
- 工具调用独立。
- 文档工件可追踪。
- 人类实验结果强制介入。

只要这五点落稳，这个系统就会比较符合 `hello-agents` 的规范，也更适合后续继续扩展成真正可运行的科研多 Agent 平台。

## 17. 入口与 PDF 输入约定

- 默认启动入口使用仓库根目录脚本，即 `python main.py start ...`。
- 安装后的 `ai-scientist ...` 仍然保留为等价可选入口，但不作为主文档默认示例。
- 文献输入主方式为 `--paper-dir <论文目录>`，而不是在 `options` 中逐个输入 PDF 文件。
- 系统启动后自动遍历目录下全部 `.pdf` 文件，并按文件名顺序逐篇解析。
- `--paper-path` 仅作为补充参数保留，用于目录之外临时追加单篇 PDF。
- 这套输入约定更符合批量读论文场景，也更贴合“先准备论文目录，再让研究生 Agent 批处理”的 hello-agents 工程化方式。
