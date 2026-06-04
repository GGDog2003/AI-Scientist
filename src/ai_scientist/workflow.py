from __future__ import annotations  # 启用延后类型注解，便于在类中引用工作流状态类型。

from datetime import date  # 导入 date，用于在工件元数据中记录日期。
import json  # 导入 json，用于把状态或人工输入落盘。
from typing import Any  # 导入 Any，用于通用字典字段标注。
from typing import TypedDict  # 导入 TypedDict，用于定义 LangGraph 状态结构。
from uuid import uuid4  # 导入 uuid4，用于生成线程和恢复标识。

from langgraph.graph import END  # 导入 END 常量，用于声明工作流终点。
from langgraph.graph import START  # 导入 START 常量，用于声明工作流起点。
from langgraph.graph import StateGraph  # 导入 StateGraph，用于搭建 LangGraph 工作流。
from langgraph.types import interrupt  # 导入 interrupt，用于在人类实验阶段挂起等待。

from ai_scientist.agents import AdvisorAgent  # 导入导师 Agent，便于在节点中执行审核。
from ai_scientist.agents import ReviewerAgent  # 导入审稿人 Agent，便于在节点中执行盲审。
from ai_scientist.agents import StudentAgent  # 导入研究生 Agent，便于在节点中执行写作与设计。
from ai_scientist.config import AppSettings  # 导入项目配置，便于构建工作流对象。
from ai_scientist.schemas import AgentMessage  # 导入消息模型，便于记录提交流程。
from ai_scientist.schemas import ArtifactRecord  # 导入工件记录模型，便于在状态中保存工件历史。
from ai_scientist.schemas import ReviewDecision  # 导入审核决策枚举，便于做条件分支。
from ai_scientist.schemas import WorkflowStatus  # 导入工作流状态枚举，便于统一状态表达。
from ai_scientist.storage import ArtifactManager  # 导入工件管理器，便于持久化所有文档。
from ai_scientist.storage import MessageBus  # 导入消息总线，便于构造 submission / reply 消息。
from ai_scientist.tools import build_tools  # 导入工具构建函数，便于给 Agent 装配工具集。


class WorkflowState(TypedDict, total=False):  # 定义 LangGraph 共享状态，字段设计对应实现方案文档。
    thread_id: str  # 保存线程 ID，便于检查点恢复。
    topic: str  # 保存研究主题。
    domain: str  # 保存研究领域。
    paper_paths: list[str]  # 保存待阅读论文路径列表。
    workflow_status: str  # 保存当前工作流状态。
    current_stage: str  # 保存当前阶段名称。
    active_agent: str | None  # 保存当前活跃角色。
    waiting_for_agent: str | None  # 保存当前正在等待回复的角色。
    suspend_reason: str | None  # 保存挂起原因。
    submitted_artifact_path: str | None  # 保存最近一次提交的工件路径。
    submitted_artifact_type: str | None  # 保存最近一次提交的工件类型。
    resume_token: str | None  # 保存恢复标识。
    last_reply_message_id: str | None  # 保存最后一次回复消息 ID。
    conversation_round: int  # 保存总体往返轮次。
    innovation_review_round: int  # 保存创新点审核轮次。
    paper_review_round: int  # 保存论文二审轮次。
    blind_review_round: int  # 保存盲审轮次。
    literature_notes: list[dict[str, Any]]  # 保存结构化论文笔记。
    literature_report_path: str | None  # 保存文献调研报告路径。
    innovation_cards: list[dict[str, Any]]  # 保存候选创新点列表。
    approved_innovation: dict[str, Any] | None  # 保存已通过的创新点。
    innovation_report_path: str | None  # 保存创新点讨论文档路径。
    experiment_plan_path: str | None  # 保存实验设计方案路径。
    experiment_result_path: str | None  # 保存实验结果路径。
    result_analysis_path: str | None  # 保存实验结果分析路径。
    manuscript_path: str | None  # 保存当前论文路径。
    advisor_review_path: str | None  # 保存导师审稿意见路径。
    reviewer_review_path: str | None  # 保存审稿人意见路径。
    review_decision: str | None  # 保存最近一次审核决策。
    review_comments: list[str]  # 保存最近一次审核评论列表。
    artifacts: list[dict[str, Any]]  # 保存全部工件登记。
    messages_log: list[dict[str, Any]]  # 保存全部角色消息记录。
    human_result: dict[str, Any] | None  # 保存人工反馈的实验结果。
    final_summary: str | None  # 保存最终终稿总结。


class ResearchWorkflowApp:  # 定义整个科研多 Agent 系统的应用入口。
    def __init__(self, settings: AppSettings) -> None:  # 初始化应用对象。
        self.settings = settings  # 保存全局配置，便于整个应用复用。
        self.settings.ensure_workspace()  # 确保工作区目录在启动时已经创建完成。
        self.artifact_manager = ArtifactManager(settings.workspace_root)  # 创建工件管理器实例。
        self.artifact_manager.ensure_workspace()  # 再次确保工件目录齐全，增强健壮性。
        self.message_bus = MessageBus(self.artifact_manager)  # 创建消息总线实例。
        self.tools = build_tools(self.artifact_manager)  # 构建三类角色共享的工具集合。
        self.student_agent = StudentAgent(settings=settings, tools=self.tools)  # 创建研究生 Agent。
        self.advisor_agent = AdvisorAgent(settings=settings, tools=self.tools)  # 创建导师 Agent。
        self.reviewer_agent = ReviewerAgent(settings=settings, tools=self.tools)  # 创建审稿人 Agent。
        self.graph = self._build_graph()  # 编译 LangGraph 工作流图。

    def create_initial_state(self, topic: str, domain: str, paper_paths: list[str] | None = None, thread_id: str | None = None) -> WorkflowState:  # 构造启动工作流所需的初始状态。
        return WorkflowState(  # 返回完整的默认状态字典。
            thread_id=thread_id or uuid4().hex,  # 写入线程 ID，如无则自动生成。
            topic=topic,  # 写入研究主题。
            domain=domain,  # 写入研究领域。
            paper_paths=paper_paths or [],  # 写入论文路径列表，如无则给空列表。
            workflow_status=WorkflowStatus.running.value,  # 初始化工作流为运行中。
            current_stage="bootstrap",  # 初始化阶段为 bootstrap。
            active_agent="student",  # 默认先由研究生开始。
            waiting_for_agent=None,  # 初始没有等待的角色。
            suspend_reason=None,  # 初始没有挂起原因。
            submitted_artifact_path=None,  # 初始没有已提交工件。
            submitted_artifact_type=None,  # 初始没有提交工件类型。
            resume_token=None,  # 初始没有恢复令牌。
            last_reply_message_id=None,  # 初始没有回复消息。
            conversation_round=0,  # 初始化总体轮次为零。
            innovation_review_round=0,  # 初始化创新点审核轮次为零。
            paper_review_round=0,  # 初始化论文二审轮次为零。
            blind_review_round=0,  # 初始化盲审轮次为零。
            literature_notes=[],  # 初始化论文笔记列表为空。
            literature_report_path=None,  # 初始化文献报告路径为空。
            innovation_cards=[],  # 初始化创新点列表为空。
            approved_innovation=None,  # 初始化通过的创新点为空。
            innovation_report_path=None,  # 初始化创新点文档路径为空。
            experiment_plan_path=None,  # 初始化实验方案路径为空。
            experiment_result_path=None,  # 初始化实验结果路径为空。
            result_analysis_path=None,  # 初始化结果分析路径为空。
            manuscript_path=None,  # 初始化论文路径为空。
            advisor_review_path=None,  # 初始化导师意见路径为空。
            reviewer_review_path=None,  # 初始化审稿意见路径为空。
            review_decision=None,  # 初始化最近审核结论为空。
            review_comments=[],  # 初始化最近审核意见列表为空。
            artifacts=[],  # 初始化工件列表为空。
            messages_log=[],  # 初始化消息日志为空。
            human_result=None,  # 初始化人工实验结果为空。
            final_summary=None,  # 初始化最终总结为空。
        )  # 结束初始状态构造。

    def _register_artifact(self, state: WorkflowState, artifact: ArtifactRecord) -> dict[str, Any]:  # 把新工件加入状态中的工件列表。
        artifacts = list(state.get("artifacts", []))  # 复制当前工件列表，避免直接修改输入状态。
        artifacts.append(artifact.model_dump())  # 把新的工件对象序列化后追加到列表。
        return {"artifacts": artifacts}  # 返回工件列表更新。

    def _append_message(self, state: WorkflowState, message: AgentMessage) -> dict[str, Any]:  # 把新消息加入状态中的消息日志。
        messages = list(state.get("messages_log", []))  # 复制当前消息日志，避免原地修改。
        messages.append(message.model_dump())  # 把新消息序列化后写入日志。
        return {"messages_log": messages}  # 返回消息日志更新。

    def bootstrap_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义启动节点，用于准备目录和日志。
        payload = {"event": "bootstrap", "thread_id": state["thread_id"], "topic": state["topic"]}  # 组织一条启动日志内容。
        self.artifact_manager.append_log("workflow.jsonl", payload)  # 把启动日志写入工作流日志文件。
        return {"current_stage": "literature_research", "active_agent": "student"}  # 更新阶段并明确当前角色。

    def student_literature_react_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义研究生文献调研节点。
        synthesis = self.student_agent.summarize_literature({"topic": state["topic"], "domain": state["domain"], "paper_paths": state.get("paper_paths", [])})  # 调用研究生 Agent 生成文献汇总。
        artifact = self.artifact_manager.write_markdown(  # 把文献综述保存成 Markdown 工件。
            bucket="literature_reports",  # 指定工件目录桶。
            document_name="文献调研汇总报告",  # 指定文档名称。
            title="文献调研汇总报告",  # 指定 Markdown 主标题。
            sections=[  # 组织报告正文章节。
                ("研究趋势", synthesis.trend_summary),  # 写入趋势总结章节。
                ("潜在研究空白", "\n".join(f"- {item}" for item in synthesis.possible_gaps)),  # 写入研究空白章节。
                ("逐篇论文笔记", "\n\n".join(f"### {note.title}\n- 来源：{note.venue} {note.year}\n- 摘要：{note.summary}\n- 创新点：{'；'.join(note.innovation_points)}\n- 不足点：{'；'.join(note.limitations)}\n- 基座论文：{note.base_paper or '无'}\n- 相对提升：{'；'.join(note.improvements_over_base) or '无'}" for note in synthesis.notes)),  # 写入逐篇论文笔记。
            ],  # 结束章节列表。
            metadata={"title": "文献调研汇总报告", "version": "auto", "date": str(date.today()), "stage": "literature_summary", "author_agent": "StudentAgent", "review_status": "draft"},  # 写入文档元数据。
        )  # 完成文献综述工件写入。
        update = {  # 组织当前节点的状态更新。
            "literature_notes": [note.model_dump() for note in synthesis.notes],  # 写入结构化论文笔记列表。
            "literature_report_path": artifact.path,  # 写入文献报告路径。
            "current_stage": "innovation_proposal",  # 推进到创新点提案阶段。
            "active_agent": "student",  # 保持研究生为当前执行角色。
        }  # 结束更新字典构造。
        update.update(self._register_artifact(state, artifact))  # 把工件登记合并到状态更新中。
        return update  # 返回节点更新结果。

    def student_innovation_react_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义研究生创新点提案节点。
        proposal = self.student_agent.propose_innovations(  # 调用研究生 Agent 生成创新点提案。
            {  # 组织创新点提案上下文。
                "topic": state["topic"],  # 写入研究主题。
                "literature_notes": state.get("literature_notes", []),  # 写入结构化论文笔记。
                "advisor_comments": state.get("review_comments", []),  # 写入上一轮导师意见，便于打回后继续修改。
                "review_round": state.get("innovation_review_round", 0),  # 写入当前审核轮次。
            }  # 结束提案上下文字典。
        )  # 获得结构化创新点提案结果。
        artifact = self.artifact_manager.write_markdown(  # 将创新点提案保存成 Markdown 工件。
            bucket="innovation_meetings",  # 指定创新点讨论目录。
            document_name="创新点候选列表",  # 指定文档名称。
            title="创新点候选列表",  # 指定文档标题。
            sections=[  # 组织创新点文档章节。
                ("组会汇报摘要", proposal.meeting_brief),  # 写入组会摘要章节。
                ("候选创新点", "\n\n".join(f"### {card.name}\n- 动机：{card.motivation}\n- 类型：{card.novelty_type}\n- 预期收益：{card.expected_gain}\n- 风险：{'；'.join(card.risk_points)}\n- 证据：{'；'.join(card.evidence)}" for card in proposal.cards)),  # 写入创新点卡片列表。
                ("当前主推方向", proposal.selected_focus),  # 写入当前主推创新点。
            ],  # 结束章节列表。
            metadata={"title": "创新点候选列表", "version": "auto", "date": str(date.today()), "stage": "innovation_proposal", "author_agent": "StudentAgent", "review_status": "submitted"},  # 写入元数据。
        )  # 完成创新点文档写入。
        submission = self.message_bus.submission(  # 构造发给导师的提交消息。
            from_agent="student",  # 设置发送角色为研究生。
            to_agent="advisor",  # 设置接收角色为导师。
            stage="innovation_review",  # 设置消息阶段为创新点审核。
            artifact_type="innovation_card",  # 设置工件类型为创新点卡片。
            artifact_path=artifact.path,  # 写入创新点文档路径。
            summary="研究生已提交创新点候选方案，请导师审核。",  # 写入消息摘要。
        )  # 完成提交消息构造。
        update = {  # 组织节点更新。
            "innovation_cards": [card.model_dump() for card in proposal.cards],  # 保存结构化创新点卡片。
            "innovation_report_path": artifact.path,  # 保存创新点文档路径。
            "current_stage": "advisor_innovation_review",  # 推进到导师创新点审核阶段。
            "active_agent": None,  # 当前研究生提交后挂起，不再活跃。
            "waiting_for_agent": "advisor",  # 标记正在等待导师回复。
            "suspend_reason": "innovation_review",  # 标记挂起原因。
            "submitted_artifact_path": artifact.path,  # 记录最近提交的工件路径。
            "submitted_artifact_type": "innovation_card",  # 记录最近提交的工件类型。
            "resume_token": submission.metadata.get("resume_token"),  # 保存恢复令牌。
            "workflow_status": WorkflowStatus.suspended.value,  # 把工作流状态标记为挂起。
            "conversation_round": state.get("conversation_round", 0) + 1,  # 增加一次往返轮次。
        }  # 结束节点更新构造。
        update.update(self._register_artifact(state, artifact))  # 合并工件登记更新。
        update.update(self._append_message(state, submission))  # 合并消息日志更新。
        return update  # 返回节点更新结果。

    def advisor_innovation_review_react_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义导师创新点审核节点。
        review = self.advisor_agent.review_innovations(  # 调用导师 Agent 执行创新点审核。
            {  # 组织审核上下文。
                "topic": state["topic"],  # 写入研究主题。
                "proposal": {"cards": state.get("innovation_cards", [])},  # 写入研究生提交的创新点卡片。
                "review_round": state.get("innovation_review_round", 0),  # 写入当前审核轮次。
            }  # 结束审核上下文字典。
        )  # 获得结构化审核结果。
        artifact = self.artifact_manager.write_markdown(  # 保存导师反馈 Markdown 工件。
            bucket="innovation_meetings",  # 指定创新点目录桶。
            document_name="导师创新点反馈",  # 指定导师反馈文档名。
            title="导师创新点反馈",  # 指定文档标题。
            sections=[("审核结论", review.decision.value), ("逐条意见", "\n".join(f"- {item}" for item in review.comments))],  # 写入审核结论和意见。
            metadata={"title": "导师创新点反馈", "version": "auto", "date": str(date.today()), "stage": "innovation_review", "author_agent": "AdvisorAgent", "review_status": review.decision.value},  # 写入文档元数据。
        )  # 完成导师反馈写入。
        last_message = AgentMessage.model_validate(state["messages_log"][-1])  # 读取最近一条提交消息，并还原成结构化对象。
        reply = self.message_bus.reply(  # 构造导师发回研究生的回复消息。
            source_message=last_message,  # 指定原始提交消息。
            from_agent="advisor",  # 设置回复角色为导师。
            decision=review.decision.value,  # 写入导师审核结论。
            comments_path=artifact.path,  # 写入导师反馈文档路径。
            summary="导师已完成创新点审核。",  # 写入回复摘要。
        )  # 完成回复消息构造。
        approved = None  # 初始化通过的创新点为空。
        if review.approved_card_name:  # 判断导师是否明确批准了某个创新点。
            approved = next((card for card in state.get("innovation_cards", []) if card.get("name") == review.approved_card_name), None)  # 从创新点列表中匹配被批准项。
        update = {  # 组织状态更新。
            "review_decision": review.decision.value,  # 保存最近审核结论。
            "review_comments": review.comments,  # 保存最近审核意见。
            "advisor_review_path": artifact.path,  # 保存导师意见路径。
            "approved_innovation": approved,  # 保存批准的创新点。
            "waiting_for_agent": None,  # 导师已经完成回复，所以清空等待角色。
            "workflow_status": WorkflowStatus.running.value,  # 恢复工作流为运行中。
            "active_agent": "student",  # 把执行权切回研究生。
            "last_reply_message_id": reply.message_id,  # 保存最后一条回复消息 ID。
            "innovation_review_round": state.get("innovation_review_round", 0) + 1,  # 增加创新点审核轮次。
            "current_stage": "innovation_revision" if review.decision == ReviewDecision.revise else "experiment_design",  # 根据结论决定回到修改还是推进实验。
            "suspend_reason": None,  # 清空挂起原因。
        }  # 结束状态更新构造。
        update.update(self._register_artifact(state, artifact))  # 合并工件登记更新。
        update.update(self._append_message(state, reply))  # 合并消息日志更新。
        return update  # 返回节点更新结果。

    def student_experiment_design_react_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义研究生实验设计节点。
        plan = self.student_agent.design_experiment(  # 调用研究生 Agent 生成实验方案。
            {  # 组织实验设计上下文。
                "topic": state["topic"],  # 写入研究主题。
                "approved_innovation": state.get("approved_innovation"),  # 写入已批准的创新点。
                "domain": state["domain"],  # 写入研究领域。
            }  # 结束实验设计上下文。
        )  # 获得结构化实验方案。
        artifact = self.artifact_manager.write_markdown(  # 保存实验方案 Markdown 工件。
            bucket="experiment_plans",  # 指定实验方案目录。
            document_name="实验设计方案",  # 指定文档名称。
            title="实验设计方案",  # 指定标题。
            sections=[  # 组织实验方案章节。
                ("实验目标", plan.objective),  # 写入实验目标。
                ("数据集", "\n".join(f"- {item}" for item in plan.datasets)),  # 写入数据集列表。
                ("Baseline", "\n".join(f"- {item}" for item in plan.baselines)),  # 写入 baseline 列表。
                ("评价指标", "\n".join(f"- {item}" for item in plan.metrics)),  # 写入指标列表。
                ("消融实验", "\n".join(f"- {item}" for item in plan.ablations)),  # 写入消融实验列表。
                ("代码模块", "\n".join(f"- {item}" for item in plan.python_modules)),  # 写入建议代码模块。
                ("人工执行步骤", "\n".join(f"{index}. {item}" for index, item in enumerate(plan.execution_steps, start=1))),  # 写入人工执行步骤。
            ],  # 结束章节列表。
            metadata={"title": "实验设计方案", "version": "auto", "date": str(date.today()), "stage": "experiment_design", "author_agent": "StudentAgent", "review_status": "draft"},  # 写入元数据。
        )  # 完成实验方案工件写入。
        update = {  # 组织状态更新。
            "experiment_plan_path": artifact.path,  # 保存实验方案路径。
            "current_stage": "human_experiment",  # 推进到人工实验阶段。
            "active_agent": "human",  # 当前活跃方切换为人类用户。
            "waiting_for_agent": "human",  # 标记正在等待人工执行实验。
            "suspend_reason": "human_run_experiment",  # 标记挂起原因。
            "workflow_status": WorkflowStatus.suspended.value,  # 把工作流状态标记为挂起。
        }  # 结束更新字典构造。
        update.update(self._register_artifact(state, artifact))  # 合并工件登记更新。
        return update  # 返回节点更新结果。

    def human_experiment_interrupt_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义人工实验中断节点。
        result = interrupt(  # 触发 LangGraph 中断，等待人类用户恢复执行。
            {  # 构造发给外部调用方的中断负载。
                "type": "human_experiment_result_required",  # 指明这是人工实验结果输入请求。
                "thread_id": state["thread_id"],  # 写入线程 ID，便于客户端恢复。
                "plan_path": state.get("experiment_plan_path"),  # 写入实验方案路径，便于用户查看。
                "message": "请先手动运行实验，再通过 resume 传回 summary、metrics、optional notes。",  # 写入人类提示信息。
            }  # 结束中断负载构造。
        )  # 等待外部传回实验结果。
        normalized = result if isinstance(result, dict) else {"summary": str(result), "metrics": {}, "notes": ""}  # 把恢复输入统一规范成字典结构。
        json_artifact = self.artifact_manager.write_json("experiment_results", "实验原始结果", normalized)  # 先把原始实验结果保存成 JSON 工件。
        markdown_artifact = self.artifact_manager.write_markdown(  # 再把可读版本结果保存成 Markdown 工件。
            bucket="experiment_results",  # 指定实验结果目录。
            document_name="实验结果记录",  # 指定文档名称。
            title="实验结果记录",  # 指定文档标题。
            sections=[("结果摘要", normalized.get("summary", "")), ("指标", json.dumps(normalized.get("metrics", {}), ensure_ascii=False, indent=2)), ("附加说明", str(normalized.get("notes", "")))],  # 组织实验结果正文。
            metadata={"title": "实验结果记录", "version": "auto", "date": str(date.today()), "stage": "human_experiment", "author_agent": "HumanUser", "review_status": "confirmed"},  # 写入元数据。
        )  # 完成 Markdown 工件写入。
        update = {  # 组织状态更新。
            "human_result": normalized,  # 保存人工实验结果。
            "experiment_result_path": markdown_artifact.path,  # 保存 Markdown 实验结果路径。
            "current_stage": "result_analysis",  # 推进到结果分析阶段。
            "active_agent": "student",  # 执行权切回研究生。
            "waiting_for_agent": None,  # 清空等待角色。
            "suspend_reason": None,  # 清空挂起原因。
            "workflow_status": WorkflowStatus.running.value,  # 恢复工作流运行状态。
        }  # 结束状态更新构造。
        update.update(self._register_artifact(state, json_artifact))  # 合并 JSON 工件登记。
        update.update(self._register_artifact({"artifacts": update.get("artifacts", state.get("artifacts", []))}, markdown_artifact))  # 合并 Markdown 工件登记。
        return update  # 返回节点更新结果。

    def student_result_analysis_react_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义研究生结果分析节点。
        analysis = self.student_agent.analyze_results(  # 调用研究生 Agent 分析实验结果。
            {  # 组织结果分析上下文。
                "approved_innovation": state.get("approved_innovation"),  # 写入已通过创新点。
                "experiment_plan_path": state.get("experiment_plan_path"),  # 写入实验方案路径。
                "human_result": state.get("human_result"),  # 写入人工反馈结果。
            }  # 结束分析上下文字典。
        )  # 获得结构化结果分析。
        artifact = self.artifact_manager.write_markdown(  # 保存结果分析 Markdown 工件。
            bucket="experiment_results",  # 指定实验结果目录。
            document_name="实验结果解读与论文话术草案",  # 指定文档名称。
            title="实验结果解读与论文话术草案",  # 指定文档标题。
            sections=[  # 组织结果分析章节。
                ("结果总结", analysis.summary),  # 写入总体总结。
                ("关键发现", "\n".join(f"- {item}" for item in analysis.key_findings)),  # 写入关键发现。
                ("结论边界", "\n".join(f"- {item}" for item in analysis.claims_boundary)),  # 写入结论边界。
                ("论文叙事主线", "\n".join(f"{index}. {item}" for index, item in enumerate(analysis.paper_storyline, start=1))),  # 写入论文叙事主线。
            ],  # 结束章节列表。
            metadata={"title": "实验结果解读与论文话术草案", "version": "auto", "date": str(date.today()), "stage": "result_analysis", "author_agent": "StudentAgent", "review_status": "draft"},  # 写入元数据。
        )  # 完成结果分析工件写入。
        update = {  # 组织状态更新。
            "result_analysis_path": artifact.path,  # 保存结果分析路径。
            "current_stage": "manuscript_drafting",  # 推进到论文写作阶段。
            "active_agent": "student",  # 当前活跃角色仍为研究生。
        }  # 结束状态更新构造。
        update.update(self._register_artifact(state, artifact))  # 合并工件登记。
        return update  # 返回节点更新结果。

    def student_manuscript_react_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义研究生论文写作节点。
        draft = self.student_agent.draft_manuscript(  # 调用研究生 Agent 生成论文稿件。
            {  # 组织论文写作上下文。
                "topic": state["topic"],  # 写入研究主题。
                "approved_innovation": state.get("approved_innovation"),  # 写入已通过创新点。
                "result_analysis_path": state.get("result_analysis_path"),  # 写入结果分析路径。
                "review_comments": state.get("review_comments", []),  # 写入上一轮审稿意见。
                "stage": state.get("current_stage"),  # 写入当前阶段名称，便于区分初稿和返修。
            }  # 结束写作上下文构造。
        )  # 获得结构化论文草稿。
        artifact = self.artifact_manager.write_markdown(  # 保存论文 Markdown 工件。
            bucket="manuscripts",  # 指定论文目录。
            document_name="论文稿件",  # 指定文档名称。
            title=draft.title,  # 使用生成的标题作为文档标题。
            sections=[  # 组织论文章节。
                ("摘要", draft.abstract),  # 写入摘要。
                ("引言", draft.introduction),  # 写入引言。
                ("相关工作", draft.related_work),  # 写入相关工作。
                ("方法", draft.method),  # 写入方法章节。
                ("实验", draft.experiments),  # 写入实验章节。
                ("结论", draft.conclusion),  # 写入结论章节。
                ("参考文献", "\n".join(f"- {item}" for item in draft.references)),  # 写入参考文献。
                ("研究生自审", "\n".join(f"- {item}" for item in draft.self_review_notes)),  # 写入研究生自审记录。
            ],  # 结束章节列表。
            metadata={"title": draft.title, "version": "auto", "date": str(date.today()), "stage": "manuscript_drafting", "author_agent": "StudentAgent", "review_status": "submitted"},  # 写入元数据。
        )  # 完成论文工件写入。
        submission = self.message_bus.submission(  # 构造提交给导师的论文审核消息。
            from_agent="student",  # 设置发送角色为研究生。
            to_agent="advisor",  # 设置接收角色为导师。
            stage="paper_review",  # 设置当前阶段为论文二审。
            artifact_type="manuscript",  # 指定提交工件类型为论文。
            artifact_path=artifact.path,  # 写入论文路径。
            summary="研究生已提交论文稿件，请导师二审。",  # 写入提交摘要。
        )  # 完成提交消息构造。
        update = {  # 组织状态更新。
            "manuscript_path": artifact.path,  # 保存当前论文路径。
            "current_stage": "advisor_paper_review",  # 推进到导师二审阶段。
            "active_agent": None,  # 研究生提交后挂起。
            "waiting_for_agent": "advisor",  # 标记正在等待导师审核。
            "suspend_reason": "paper_review",  # 标记挂起原因。
            "submitted_artifact_path": artifact.path,  # 记录最近提交工件路径。
            "submitted_artifact_type": "manuscript",  # 记录最近提交工件类型。
            "resume_token": submission.metadata.get("resume_token"),  # 保存恢复令牌。
            "workflow_status": WorkflowStatus.suspended.value,  # 设置工作流为挂起状态。
            "conversation_round": state.get("conversation_round", 0) + 1,  # 增加总体对话轮次。
        }  # 结束状态更新构造。
        update.update(self._register_artifact(state, artifact))  # 合并工件登记更新。
        update.update(self._append_message(state, submission))  # 合并消息日志更新。
        return update  # 返回节点更新结果。

    def advisor_paper_review_react_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义导师论文二审节点。
        review = self.advisor_agent.review_manuscript(  # 调用导师 Agent 审核论文。
            {  # 组织导师审核上下文。
                "manuscript_path": state.get("manuscript_path"),  # 写入论文路径。
                "approved_innovation": state.get("approved_innovation"),  # 写入通过的创新点。
                "review_round": state.get("paper_review_round", 0),  # 写入当前论文二审轮次。
            }  # 结束审核上下文构造。
        )  # 获得结构化导师审核结果。
        artifact = self.artifact_manager.write_markdown(  # 保存导师论文审核意见。
            bucket="reviews",  # 指定审稿目录。
            document_name="导师审稿意见",  # 指定文档名称。
            title="导师审稿意见",  # 指定文档标题。
            sections=[  # 组织导师审稿意见章节。
                ("审核结论", review.decision.value),  # 写入审核结论。
                ("主要问题", "\n".join(f"- {item}" for item in review.major_issues) or "- 无"),  # 写入主要问题。
                ("次要问题", "\n".join(f"- {item}" for item in review.minor_issues) or "- 无"),  # 写入次要问题。
                ("必须修改", "\n".join(f"- {item}" for item in review.required_changes)),  # 写入必须修改项。
            ],  # 结束章节列表。
            metadata={"title": "导师审稿意见", "version": "auto", "date": str(date.today()), "stage": "advisor_paper_review", "author_agent": "AdvisorAgent", "review_status": review.decision.value},  # 写入元数据。
        )  # 完成导师意见写入。
        last_message = AgentMessage.model_validate(state["messages_log"][-1])  # 读取最近一条研究生提交论文消息。
        reply = self.message_bus.reply(  # 构造导师回复研究生的消息。
            source_message=last_message,  # 传入原始提交消息。
            from_agent="advisor",  # 设置回复角色为导师。
            decision=review.decision.value,  # 写入审核结论。
            comments_path=artifact.path,  # 写入意见文档路径。
            summary="导师已完成论文二审。",  # 写入回复摘要。
        )  # 完成回复消息构造。
        update = {  # 组织状态更新。
            "review_decision": review.decision.value,  # 保存最新审核结论。
            "review_comments": [*review.major_issues, *review.minor_issues, *review.required_changes],  # 保存最新审核意见集合。
            "advisor_review_path": artifact.path,  # 保存导师意见路径。
            "waiting_for_agent": None,  # 导师已完成回复，清空等待角色。
            "workflow_status": WorkflowStatus.running.value,  # 恢复工作流运行状态。
            "last_reply_message_id": reply.message_id,  # 保存最后回复消息 ID。
            "paper_review_round": state.get("paper_review_round", 0) + 1,  # 增加论文二审轮次。
            "current_stage": "manuscript_revision" if review.decision == ReviewDecision.revise else "reviewer_blind_review",  # 根据结论决定返修还是送盲审。
            "active_agent": "student" if review.decision == ReviewDecision.revise else "reviewer",  # 决定下一个执行角色。
            "suspend_reason": None,  # 清空挂起原因。
        }  # 结束状态更新构造。
        update.update(self._register_artifact(state, artifact))  # 合并工件登记更新。
        update.update(self._append_message(state, reply))  # 合并消息日志更新。
        return update  # 返回节点更新结果。

    def reviewer_blind_review_react_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义审稿人盲审节点。
        review = self.reviewer_agent.blind_review(  # 调用审稿人 Agent 执行盲审。
            {  # 组织盲审上下文。
                "manuscript_path": state.get("manuscript_path"),  # 写入论文路径。
                "review_round": state.get("blind_review_round", 0),  # 写入当前盲审轮次。
            }  # 结束盲审上下文。
        )  # 获得结构化盲审结果。
        artifact = self.artifact_manager.write_markdown(  # 保存盲审意见 Markdown 工件。
            bucket="reviews",  # 指定审稿目录。
            document_name="盲审意见",  # 指定文档名称。
            title="盲审意见",  # 指定文档标题。
            sections=[  # 组织盲审章节。
                ("审稿结论", review.decision.value),  # 写入最终结论。
                ("总体评价", review.summary),  # 写入总体评价。
                ("优点", "\n".join(f"- {item}" for item in review.strengths)),  # 写入优点。
                ("问题", "\n".join(f"- {item}" for item in review.weaknesses)),  # 写入问题。
                ("必须修改", "\n".join(f"- {item}" for item in review.required_changes)),  # 写入必须修改项。
                ("置信度", review.confidence),  # 写入置信度。
            ],  # 结束章节列表。
            metadata={"title": "盲审意见", "version": "auto", "date": str(date.today()), "stage": "reviewer_blind_review", "author_agent": "ReviewerAgent", "review_status": review.decision.value},  # 写入元数据。
        )  # 完成盲审工件写入。
        update = {  # 组织状态更新。
            "review_decision": review.decision.value,  # 保存盲审结论。
            "review_comments": [*review.weaknesses, *review.required_changes],  # 保存盲审问题与修改项。
            "reviewer_review_path": artifact.path,  # 保存盲审意见路径。
            "blind_review_round": state.get("blind_review_round", 0) + 1,  # 增加盲审轮次。
            "current_stage": "manuscript_revision" if review.decision in {ReviewDecision.major_revision, ReviewDecision.reject} else ("final_polish" if review.decision == ReviewDecision.minor_revision else "finalize"),  # 根据结论决定返修路径。
            "active_agent": "student" if review.decision in {ReviewDecision.major_revision, ReviewDecision.minor_revision, ReviewDecision.reject} else "system",  # 根据结论决定谁继续执行。
        }  # 结束状态更新构造。
        update.update(self._register_artifact(state, artifact))  # 合并工件登记更新。
        return update  # 返回节点更新结果。

    def student_final_revision_react_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义研究生终稿润色节点。
        draft = self.student_agent.draft_manuscript(  # 复用论文写作能力做最终小修。
            {  # 组织终稿润色上下文。
                "topic": state["topic"],  # 写入研究主题。
                "approved_innovation": state.get("approved_innovation"),  # 写入通过的创新点。
                "result_analysis_path": state.get("result_analysis_path"),  # 写入结果分析路径。
                "review_comments": state.get("review_comments", []),  # 写入盲审意见。
                "stage": "final_polish",  # 明确当前是终稿润色阶段。
            }  # 结束润色上下文。
        )  # 获得结构化终稿润色结果。
        artifact = self.artifact_manager.write_markdown(  # 保存终稿版本。
            bucket="manuscripts",  # 指定论文目录。
            document_name="论文终稿",  # 指定终稿文档名称。
            title=draft.title,  # 使用论文标题作为文档标题。
            sections=[("摘要", draft.abstract), ("引言", draft.introduction), ("相关工作", draft.related_work), ("方法", draft.method), ("实验", draft.experiments), ("结论", draft.conclusion), ("参考文献", "\n".join(f"- {item}" for item in draft.references)), ("最终自查", "\n".join(f"- {item}" for item in draft.self_review_notes))],  # 组织终稿章节。
            metadata={"title": draft.title, "version": "auto", "date": str(date.today()), "stage": "final_polish", "author_agent": "StudentAgent", "review_status": "final"},  # 写入元数据。
        )  # 完成终稿写入。
        update = {  # 组织状态更新。
            "manuscript_path": artifact.path,  # 更新最终论文路径。
            "current_stage": "finalize",  # 推进到最终收尾阶段。
            "active_agent": "system",  # 交给系统节点生成最终总结。
        }  # 结束状态更新构造。
        update.update(self._register_artifact(state, artifact))  # 合并工件登记更新。
        return update  # 返回节点更新结果。

    def finalize_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义最终收尾节点。
        final_summary = "\n".join(  # 组织最终工作流总结文本。
            [  # 构造最终总结的逐行内容。
                f"主题：{state['topic']}",  # 写入研究主题。
                f"领域：{state['domain']}",  # 写入研究领域。
                f"最终论文：{state.get('manuscript_path')}",  # 写入最终论文路径。
                f"导师意见：{state.get('advisor_review_path')}",  # 写入导师意见路径。
                f"盲审意见：{state.get('reviewer_review_path')}",  # 写入盲审意见路径。
                f"最终结论：{state.get('review_decision')}",  # 写入最终结论。
            ]  # 结束逐行内容。
        )  # 完成最终总结拼接。
        self.artifact_manager.append_log("workflow.jsonl", {"event": "completed", "thread_id": state["thread_id"], "final_decision": state.get("review_decision")})  # 写入完成日志。
        return {"workflow_status": WorkflowStatus.completed.value, "current_stage": "done", "active_agent": None, "waiting_for_agent": None, "final_summary": final_summary}  # 返回完成态更新。

    def innovation_router(self, state: WorkflowState) -> str:  # 根据导师创新点审核结果决定下一节点。
        return "student_innovation_react_node" if state.get("review_decision") == ReviewDecision.revise.value else "student_experiment_design_react_node"  # 打回则回研究生创新点节点，否则进入实验设计。

    def paper_router(self, state: WorkflowState) -> str:  # 根据导师论文审核结果决定下一节点。
        return "student_manuscript_react_node" if state.get("review_decision") == ReviewDecision.revise.value else "reviewer_blind_review_react_node"  # 打回则回论文写作节点，否则进入盲审。

    def blind_review_router(self, state: WorkflowState) -> str:  # 根据盲审结果决定下一节点。
        if state.get("review_decision") in {ReviewDecision.major_revision.value, ReviewDecision.reject.value}:  # 判断盲审是否为大修或拒稿。
            return "student_manuscript_react_node"  # 大修或拒稿时回到研究生论文返修节点。
        if state.get("review_decision") == ReviewDecision.minor_revision.value:  # 判断盲审是否为小修。
            return "student_final_revision_react_node"  # 小修时进入终稿润色节点。
        return "finalize_node"  # 接受时直接进入最终收尾节点。

    def _build_graph(self):  # 构建并编译 LangGraph 工作流图。
        builder = StateGraph(WorkflowState)  # 使用 WorkflowState 定义共享状态图。
        builder.add_node("bootstrap_node", self.bootstrap_node)  # 注册启动节点。
        builder.add_node("student_literature_react_node", self.student_literature_react_node)  # 注册文献调研节点。
        builder.add_node("student_innovation_react_node", self.student_innovation_react_node)  # 注册创新点提案节点。
        builder.add_node("advisor_innovation_review_react_node", self.advisor_innovation_review_react_node)  # 注册导师创新点审核节点。
        builder.add_node("student_experiment_design_react_node", self.student_experiment_design_react_node)  # 注册实验设计节点。
        builder.add_node("human_experiment_interrupt_node", self.human_experiment_interrupt_node)  # 注册人工实验中断节点。
        builder.add_node("student_result_analysis_react_node", self.student_result_analysis_react_node)  # 注册结果分析节点。
        builder.add_node("student_manuscript_react_node", self.student_manuscript_react_node)  # 注册论文写作节点。
        builder.add_node("advisor_paper_review_react_node", self.advisor_paper_review_react_node)  # 注册导师论文二审节点。
        builder.add_node("reviewer_blind_review_react_node", self.reviewer_blind_review_react_node)  # 注册盲审节点。
        builder.add_node("student_final_revision_react_node", self.student_final_revision_react_node)  # 注册终稿润色节点。
        builder.add_node("finalize_node", self.finalize_node)  # 注册最终收尾节点。
        builder.add_edge(START, "bootstrap_node")  # 把开始边连接到启动节点。
        builder.add_edge("bootstrap_node", "student_literature_react_node")  # 启动后先进入文献调研。
        builder.add_edge("student_literature_react_node", "student_innovation_react_node")  # 文献调研后进入创新点提案。
        builder.add_edge("student_innovation_react_node", "advisor_innovation_review_react_node")  # 创新点提交后进入导师审核。
        builder.add_conditional_edges("advisor_innovation_review_react_node", self.innovation_router, {"student_innovation_react_node": "student_innovation_react_node", "student_experiment_design_react_node": "student_experiment_design_react_node"})  # 根据导师意见在创新点返修和实验设计之间路由。
        builder.add_edge("student_experiment_design_react_node", "human_experiment_interrupt_node")  # 实验设计后进入人工实验中断。
        builder.add_edge("human_experiment_interrupt_node", "student_result_analysis_react_node")  # 人工恢复后进入结果分析。
        builder.add_edge("student_result_analysis_react_node", "student_manuscript_react_node")  # 结果分析后进入论文撰写。
        builder.add_edge("student_manuscript_react_node", "advisor_paper_review_react_node")  # 论文写完后进入导师二审。
        builder.add_conditional_edges("advisor_paper_review_react_node", self.paper_router, {"student_manuscript_react_node": "student_manuscript_react_node", "reviewer_blind_review_react_node": "reviewer_blind_review_react_node"})  # 根据导师意见在返修和盲审之间路由。
        builder.add_conditional_edges("reviewer_blind_review_react_node", self.blind_review_router, {"student_manuscript_react_node": "student_manuscript_react_node", "student_final_revision_react_node": "student_final_revision_react_node", "finalize_node": "finalize_node"})  # 根据盲审结果在大修、小修、接受之间路由。
        builder.add_edge("student_final_revision_react_node", "finalize_node")  # 小修终稿后进入最终收尾节点。
        builder.add_edge("finalize_node", END)  # 把收尾节点连接到工作流结束。
        return builder.compile(checkpointer=self.settings.build_checkpointer())  # 使用配置里的检查点构建并返回可执行图。
