from __future__ import annotations  # 启用延后类型注解，便于在类和函数签名中引用本地类型。

from datetime import date  # 导入 date，用于给 Markdown 工件写入日期元数据。
import json  # 导入 json，用于把实验结果或状态落盘为结构化文本。
from typing import Any  # 导入 Any，用于通用字典字段类型标注。
from uuid import uuid4  # 导入 uuid4，用于生成 thread_id 和恢复标识。

from langgraph.graph import END  # 导入 END 常量，用于声明图终点。
from langgraph.graph import START  # 导入 START 常量，用于声明图起点。
from langgraph.graph import StateGraph  # 导入 StateGraph，用于构建 LangGraph 工作流。
from langgraph.types import interrupt  # 导入 interrupt，用于在人工实验阶段挂起等待。

from app.agents.advisor_agent import AdvisorAgent  # 导入导师 Agent，便于在节点中执行审核。
from app.agents.reviewer_agent import ReviewerAgent  # 导入审稿人 Agent，便于在节点中执行盲审。
from app.agents.student_agent import StudentAgent  # 导入研究生 Agent，便于在节点中执行写作与设计。
from app.config import AppSettings  # 导入项目配置对象，便于构建底层运行环境。
from app.config import build_thread_config  # 导入线程配置构造函数，便于外部读取状态。
from app.schemas.agent_message import AgentMessage  # 导入 Agent 消息模型，便于记录提交流程。
from app.schemas.manuscript_review import ReviewDecision  # 导入审核决策枚举，便于条件分支路由。
from app.schemas.workflow_state import ArtifactRecord  # 导入工件记录模型，便于登记工件。
from app.schemas.workflow_state import WorkflowState  # 导入共享状态 TypedDict，作为 LangGraph 状态定义。
from app.schemas.workflow_state import WorkflowStatus  # 导入工作流状态枚举，统一描述运行态。
from app.tools import build_tools  # 导入工具构造函数，便于给角色 Agent 装配工具。
from app.tools.file_store import ArtifactManager  # 导入工件管理器，便于持久化各种文档。
from app.tools.message_bus import MessageBus  # 导入消息总线，便于构造 submission / reply 消息。


class ResearchStateMachine:  # 定义整个科研多 Agent 系统的正式状态机入口。
    def __init__(self, project_root: str | None = None, settings: AppSettings | None = None) -> None:  # 初始化状态机，并创建底层依赖对象。
        self.settings = settings or AppSettings.from_env(project_root=project_root)  # 优先复用外部传入配置，否则从环境变量加载配置。
        self.settings.ensure_workspace()  # 确保工作区目录和检查点父目录已经存在。
        self.artifact_manager = ArtifactManager(self.settings.workspace_root)  # 创建工件管理器实例。
        self.artifact_manager.ensure_workspace()  # 再次确保工件目录齐全，增强健壮性。
        self.message_bus = MessageBus(self.artifact_manager)  # 创建消息总线实例。
        self.tools = build_tools(self.artifact_manager)  # 构建三类角色共享的工具列表。
        self.student_agent = StudentAgent(settings=self.settings, tools=self.tools)  # 创建研究生 Agent。
        self.advisor_agent = AdvisorAgent(settings=self.settings, tools=self.tools)  # 创建导师 Agent。
        self.reviewer_agent = ReviewerAgent(settings=self.settings, tools=self.tools)  # 创建审稿人 Agent。
        self.graph = self._build_graph()  # 编译 LangGraph 工作流图。

    def create_initial_state(self, topic: str, domain: str, paper_paths: list[str] | None = None, thread_id: str | None = None) -> WorkflowState:  # 构造启动工作流需要的初始状态。
        return WorkflowState(  # 返回完整的初始共享状态字典。
            thread_id=thread_id or uuid4().hex,  # 写入线程 ID，如无则自动生成。
            topic=topic,  # 写入研究主题。
            domain=domain,  # 写入研究领域。
            paper_paths=paper_paths or [],  # 写入待阅读论文路径列表。
            workflow_status=WorkflowStatus.running.value,  # 初始化工作流为运行中。
            current_stage="bootstrap",  # 初始化阶段为 bootstrap。
            active_agent="student",  # 默认由研究生开始执行。
            waiting_for_agent=None,  # 初始没有等待中的角色。
            suspend_reason=None,  # 初始没有挂起原因。
            submitted_artifact_path=None,  # 初始没有最近一次提交工件路径。
            submitted_artifact_type=None,  # 初始没有最近一次提交工件类型。
            resume_token=None,  # 初始没有恢复令牌。
            last_reply_message_id=None,  # 初始没有回复消息 ID。
            conversation_round=0,  # 初始化总体来回轮次为零。
            innovation_review_round=0,  # 初始化创新点审核轮次为零。
            paper_review_round=0,  # 初始化论文二审轮次为零。
            blind_review_round=0,  # 初始化盲审轮次为零。
            literature_notes=[],  # 初始化论文笔记列表为空。
            literature_report_path=None,  # 初始化文献调研报告路径为空。
            innovation_cards=[],  # 初始化创新点卡片列表为空。
            approved_innovation=None,  # 初始化已通过创新点为空。
            innovation_report_path=None,  # 初始化创新点文档路径为空。
            experiment_plan_path=None,  # 初始化实验方案路径为空。
            experiment_result_path=None,  # 初始化实验结果路径为空。
            result_analysis_path=None,  # 初始化结果分析文档路径为空。
            manuscript_path=None,  # 初始化论文路径为空。
            advisor_review_path=None,  # 初始化导师意见路径为空。
            reviewer_review_path=None,  # 初始化审稿人意见路径为空。
            review_decision=None,  # 初始化最近一次审核结论为空。
            review_comments=[],  # 初始化最近一次审核意见列表为空。
            artifacts=[],  # 初始化工件登记列表为空。
            messages_log=[],  # 初始化消息日志为空。
            human_result=None,  # 初始化人工实验结果为空。
            final_summary=None,  # 初始化最终总结为空。
        )  # 结束初始状态构造。

    def get_state(self, thread_id: str):  # 根据线程 ID 读取当前工作流状态快照。
        return self.graph.get_state(build_thread_config(thread_id))  # 使用标准线程配置读取指定线程状态。

    def _register_artifact(self, state: WorkflowState, artifact: ArtifactRecord) -> dict[str, Any]:  # 把新工件追加到状态中的工件列表。
        artifacts = list(state.get("artifacts", []))  # 复制当前工件列表，避免原地修改输入状态。
        artifacts.append(artifact.model_dump())  # 把新工件序列化后追加到列表。
        return {"artifacts": artifacts}  # 返回工件列表更新结果。

    def _append_message(self, state: WorkflowState, message: AgentMessage) -> dict[str, Any]:  # 把新消息追加到状态中的消息日志。
        messages = list(state.get("messages_log", []))  # 复制当前消息日志，避免原地修改输入状态。
        messages.append(message.model_dump())  # 把新消息序列化后追加到列表。
        return {"messages_log": messages}  # 返回消息日志更新结果。

    def bootstrap_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义启动节点，用于记录线程启动日志。
        payload = {"event": "bootstrap", "thread_id": state["thread_id"], "topic": state["topic"]}  # 构造一条工作流启动日志负载。
        self.artifact_manager.append_log("workflow.jsonl", payload)  # 把启动日志写入工作流日志文件。
        return {"current_stage": "literature_research", "active_agent": "student"}  # 推进到文献调研阶段，并保持研究生为当前角色。

    def student_literature_react_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义研究生文献调研节点。
        synthesis = self.student_agent.summarize_literature({"topic": state["topic"], "domain": state["domain"], "paper_paths": state.get("paper_paths", [])})  # 调用研究生 Agent 生成文献调研汇总。
        artifact = self.artifact_manager.write_markdown(  # 将文献综述保存为 Markdown 工件。
            bucket="literature_reports",  # 指定输出目录桶为文献报告。
            document_name="文献调研汇总报告",  # 指定文档名称。
            title="文献调研汇总报告",  # 指定 Markdown 主标题。
            sections=[  # 组织文献报告的正文分节。
                ("研究趋势", synthesis.trend_summary),  # 写入研究趋势章节。
                ("潜在研究空白", "\n".join(f"- {item}" for item in synthesis.possible_gaps)),  # 写入潜在研究空白章节。
                ("逐篇论文笔记", "\n\n".join(f"### {note.title}\n- 来源：{note.venue} {note.year}\n- 摘要：{note.summary}\n- 创新点：{'；'.join(note.innovation_points)}\n- 不足点：{'；'.join(note.limitations)}\n- 基座论文：{note.base_paper or '无'}\n- 相对提升：{'；'.join(note.improvements_over_base) or '无'}" for note in synthesis.notes)),  # 写入逐篇论文笔记章节。
            ],  # 结束报告分节列表。
            metadata={"title": "文献调研汇总报告", "version": "auto", "date": str(date.today()), "stage": "literature_summary", "author_agent": "StudentAgent", "review_status": "draft"},  # 写入文档元数据。
        )  # 完成文献综述工件写入。
        update = {  # 组织当前节点的状态更新。
            "literature_notes": [note.model_dump() for note in synthesis.notes],  # 保存结构化论文笔记列表。
            "literature_report_path": artifact.path,  # 保存文献调研报告路径。
            "current_stage": "innovation_proposal",  # 推进到创新点提案阶段。
            "active_agent": "student",  # 保持研究生为当前执行角色。
        }  # 结束更新字典构造。
        update.update(self._register_artifact(state, artifact))  # 合并工件登记更新。
        return update  # 返回节点更新结果。

    def student_innovation_react_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义研究生创新点提案节点。
        proposal = self.student_agent.propose_innovations(  # 调用研究生 Agent 生成创新点提案。
            {  # 组织创新点提案上下文。
                "topic": state["topic"],  # 写入研究主题。
                "literature_notes": state.get("literature_notes", []),  # 写入结构化论文笔记列表。
                "advisor_comments": state.get("review_comments", []),  # 写入上一轮导师意见，便于被打回后继续修改。
                "review_round": state.get("innovation_review_round", 0),  # 写入当前审核轮次。
            }  # 结束创新点上下文构造。
        )  # 获得结构化创新点提案结果。
        artifact = self.artifact_manager.write_markdown(  # 将创新点提案保存为 Markdown 工件。
            bucket="innovation_meetings",  # 指定输出目录桶为创新点讨论目录。
            document_name="创新点候选列表",  # 指定文档名称。
            title="创新点候选列表",  # 指定 Markdown 主标题。
            sections=[  # 组织创新点文档分节。
                ("组会汇报摘要", proposal.meeting_brief),  # 写入组会汇报摘要。
                ("候选创新点", "\n\n".join(f"### {card.name}\n- 动机：{card.motivation}\n- 类型：{card.novelty_type}\n- 预期收益：{card.expected_gain}\n- 风险：{'；'.join(card.risk_points)}\n- 证据：{'；'.join(card.evidence)}" for card in proposal.cards)),  # 写入创新点卡片列表。
                ("当前主推方向", proposal.selected_focus),  # 写入当前主推创新点。
            ],  # 结束文档分节列表。
            metadata={"title": "创新点候选列表", "version": "auto", "date": str(date.today()), "stage": "innovation_proposal", "author_agent": "StudentAgent", "review_status": "submitted"},  # 写入文档元数据。
        )  # 完成创新点文档写入。
        submission = self.message_bus.submission(  # 构造发给导师的提交消息。
            from_agent="student",  # 设置发送角色为研究生。
            to_agent="advisor",  # 设置接收角色为导师。
            stage="innovation_review",  # 标记当前阶段为创新点审核。
            artifact_type="innovation_card",  # 标记提交工件类型为创新点卡片。
            artifact_path=artifact.path,  # 写入创新点文档路径。
            summary="研究生已提交创新点候选方案，请导师审核。",  # 写入消息摘要。
        )  # 完成提交消息构造。
        update = {  # 组织节点状态更新。
            "innovation_cards": [card.model_dump() for card in proposal.cards],  # 保存结构化创新点卡片。
            "innovation_report_path": artifact.path,  # 保存创新点文档路径。
            "current_stage": "advisor_innovation_review",  # 推进到导师创新点审核阶段。
            "active_agent": None,  # 研究生提交后挂起，不再处于活跃执行状态。
            "waiting_for_agent": "advisor",  # 标记正在等待导师回复。
            "suspend_reason": "innovation_review",  # 标记挂起原因是创新点审核。
            "submitted_artifact_path": artifact.path,  # 记录最近提交工件路径。
            "submitted_artifact_type": "innovation_card",  # 记录最近提交工件类型。
            "resume_token": submission.metadata.get("resume_token"),  # 保存恢复令牌。
            "workflow_status": WorkflowStatus.suspended.value,  # 把工作流状态标记为挂起。
            "conversation_round": state.get("conversation_round", 0) + 1,  # 增加总体来回轮次。
        }  # 结束节点更新构造。
        update.update(self._register_artifact(state, artifact))  # 合并工件登记更新。
        update.update(self._append_message(state, submission))  # 合并消息日志更新。
        return update  # 返回节点更新结果。

    def advisor_innovation_review_react_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义导师创新点审核节点。
        review = self.advisor_agent.review_innovations(  # 调用导师 Agent 审核创新点提案。
            {  # 组织导师审核上下文。
                "topic": state["topic"],  # 写入研究主题。
                "proposal": {"cards": state.get("innovation_cards", [])},  # 写入研究生提交的创新点卡片。
                "review_round": state.get("innovation_review_round", 0),  # 写入当前审核轮次。
            }  # 结束审核上下文。
        )  # 获得结构化导师审核结果。
        artifact = self.artifact_manager.write_markdown(  # 保存导师反馈 Markdown 文档。
            bucket="innovation_meetings",  # 指定输出目录桶为创新点讨论目录。
            document_name="导师创新点反馈",  # 指定文档名称。
            title="导师创新点反馈",  # 指定文档标题。
            sections=[("审核结论", review.decision.value), ("逐条意见", "\n".join(f"- {item}" for item in review.comments))],  # 组织审核结论和逐条意见。
            metadata={"title": "导师创新点反馈", "version": "auto", "date": str(date.today()), "stage": "innovation_review", "author_agent": "AdvisorAgent", "review_status": review.decision.value},  # 写入文档元数据。
        )  # 完成导师反馈写入。
        last_message = AgentMessage.model_validate(state["messages_log"][-1])  # 读取最近一条提交消息，并还原成结构化对象。
        reply = self.message_bus.reply(  # 构造导师返回给研究生的回复消息。
            source_message=last_message,  # 绑定原始提交消息。
            from_agent="advisor",  # 设置回复角色为导师。
            decision=review.decision.value,  # 写入导师审核结论。
            comments_path=artifact.path,  # 写入导师反馈文档路径。
            summary="导师已完成创新点审核。",  # 写入回复摘要。
        )  # 完成回复消息构造。
        approved = None  # 初始化通过的创新点为空。
        if review.approved_card_name:  # 判断导师是否明确通过了某个创新点。
            approved = next((card for card in state.get("innovation_cards", []) if card.get("name") == review.approved_card_name), None)  # 从创新点卡片列表中匹配被通过项。
        update = {  # 组织状态更新。
            "review_decision": review.decision.value,  # 保存最近审核结论。
            "review_comments": review.comments,  # 保存最近审核意见。
            "advisor_review_path": artifact.path,  # 保存导师反馈路径。
            "approved_innovation": approved,  # 保存已通过创新点。
            "waiting_for_agent": None,  # 导师已完成回复，清空等待角色。
            "workflow_status": WorkflowStatus.running.value,  # 恢复工作流为运行中。
            "active_agent": "student",  # 把控制权交还给研究生。
            "last_reply_message_id": reply.message_id,  # 保存最后一条回复消息 ID。
            "innovation_review_round": state.get("innovation_review_round", 0) + 1,  # 增加创新点审核轮次。
            "current_stage": "innovation_revision" if review.decision == ReviewDecision.revise else "experiment_design",  # 根据审核结论决定返修还是进入实验阶段。
            "suspend_reason": None,  # 清空挂起原因。
        }  # 结束状态更新构造。
        update.update(self._register_artifact(state, artifact))  # 合并工件登记更新。
        update.update(self._append_message(state, reply))  # 合并消息日志更新。
        return update  # 返回节点更新结果。

    def student_experiment_design_react_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义研究生实验设计节点。
        plan = self.student_agent.design_experiment(  # 调用研究生 Agent 生成实验方案。
            {  # 组织实验设计上下文。
                "topic": state["topic"],  # 写入研究主题。
                "approved_innovation": state.get("approved_innovation"),  # 写入已通过的创新点。
                "domain": state["domain"],  # 写入研究领域。
            }  # 结束实验设计上下文。
        )  # 获得结构化实验方案。
        artifact = self.artifact_manager.write_markdown(  # 将实验方案保存为 Markdown 工件。
            bucket="experiment_plans",  # 指定输出目录桶为实验方案目录。
            document_name="实验设计方案",  # 指定文档名称。
            title="实验设计方案",  # 指定 Markdown 主标题。
            sections=[  # 组织实验方案正文分节。
                ("实验目标", plan.objective),  # 写入实验目标。
                ("数据集", "\n".join(f"- {item}" for item in plan.datasets)),  # 写入数据集列表。
                ("Baseline", "\n".join(f"- {item}" for item in plan.baselines)),  # 写入 baseline 列表。
                ("评价指标", "\n".join(f"- {item}" for item in plan.metrics)),  # 写入评价指标列表。
                ("消融实验", "\n".join(f"- {item}" for item in plan.ablations)),  # 写入消融实验列表。
                ("代码模块", "\n".join(f"- {item}" for item in plan.python_modules)),  # 写入建议代码模块列表。
                ("人工执行步骤", "\n".join(f"{index}. {item}" for index, item in enumerate(plan.execution_steps, start=1))),  # 写入人工执行步骤列表。
            ],  # 结束实验方案分节列表。
            metadata={"title": "实验设计方案", "version": "auto", "date": str(date.today()), "stage": "experiment_design", "author_agent": "StudentAgent", "review_status": "draft"},  # 写入文档元数据。
        )  # 完成实验方案工件写入。
        update = {  # 组织状态更新。
            "experiment_plan_path": artifact.path,  # 保存实验方案路径。
            "current_stage": "human_experiment",  # 推进到人工实验阶段。
            "active_agent": "human",  # 当前活跃方切换为人类用户。
            "waiting_for_agent": "human",  # 标记当前正在等待人工执行实验。
            "suspend_reason": "human_run_experiment",  # 标记挂起原因是人工实验执行。
            "workflow_status": WorkflowStatus.suspended.value,  # 把工作流状态标记为挂起。
        }  # 结束状态更新构造。
        update.update(self._register_artifact(state, artifact))  # 合并工件登记更新。
        return update  # 返回节点更新结果。

    def human_experiment_interrupt_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义人工实验挂起节点。
        result = interrupt(  # 触发 LangGraph 中断，等待外部传回实验结果。
            {  # 构造发给外部调用方的中断负载。
                "type": "human_experiment_result_required",  # 标记这是人工实验结果请求。
                "thread_id": state["thread_id"],  # 写入线程 ID，便于后续 resume。
                "plan_path": state.get("experiment_plan_path"),  # 写入实验方案路径，便于用户查看。
                "message": "请先手动运行实验，再通过 resume 传回 summary、metrics、optional notes。",  # 写入人工提示信息。
            }  # 结束中断负载构造。
        )  # 等待外部恢复执行时提供实验结果。
        normalized = result if isinstance(result, dict) else {"summary": str(result), "metrics": {}, "notes": ""}  # 把恢复输入统一规范成字典结构。
        json_artifact = self.artifact_manager.write_json("experiment_results", "实验原始结果", normalized)  # 先把原始实验结果保存成 JSON 工件。
        markdown_artifact = self.artifact_manager.write_markdown(  # 再把可读版实验结果保存成 Markdown 工件。
            bucket="experiment_results",  # 指定输出目录桶为实验结果目录。
            document_name="实验结果记录",  # 指定文档名称。
            title="实验结果记录",  # 指定 Markdown 主标题。
            sections=[("结果摘要", normalized.get("summary", "")), ("指标", json.dumps(normalized.get("metrics", {}), ensure_ascii=False, indent=2)), ("附加说明", str(normalized.get("notes", "")))],  # 组织实验结果正文分节。
            metadata={"title": "实验结果记录", "version": "auto", "date": str(date.today()), "stage": "human_experiment", "author_agent": "HumanUser", "review_status": "confirmed"},  # 写入文档元数据。
        )  # 完成 Markdown 实验结果写入。
        artifacts = list(state.get("artifacts", []))  # 复制当前工件列表，便于一次性追加两个工件。
        artifacts.append(json_artifact.model_dump())  # 追加 JSON 工件记录。
        artifacts.append(markdown_artifact.model_dump())  # 追加 Markdown 工件记录。
        return {  # 返回人工实验节点的状态更新。
            "human_result": normalized,  # 保存人工实验结果。
            "experiment_result_path": markdown_artifact.path,  # 保存 Markdown 结果文档路径。
            "current_stage": "result_analysis",  # 推进到结果分析阶段。
            "active_agent": "student",  # 把执行权交还给研究生。
            "waiting_for_agent": None,  # 清空等待角色。
            "suspend_reason": None,  # 清空挂起原因。
            "workflow_status": WorkflowStatus.running.value,  # 恢复工作流为运行中。
            "artifacts": artifacts,  # 写回包含两个新工件的工件列表。
        }  # 结束状态更新返回。

    def student_result_analysis_react_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义研究生实验结果分析节点。
        analysis = self.student_agent.analyze_results(  # 调用研究生 Agent 分析实验结果。
            {  # 组织结果分析上下文。
                "approved_innovation": state.get("approved_innovation"),  # 写入已通过创新点。
                "experiment_plan_path": state.get("experiment_plan_path"),  # 写入实验方案路径。
                "human_result": state.get("human_result"),  # 写入人工反馈结果。
            }  # 结束结果分析上下文。
        )  # 获得结构化结果分析。
        artifact = self.artifact_manager.write_markdown(  # 保存实验结果解读与论文话术草案。
            bucket="experiment_results",  # 指定输出目录桶为实验结果目录。
            document_name="实验结果解读与论文话术草案",  # 指定文档名称。
            title="实验结果解读与论文话术草案",  # 指定 Markdown 主标题。
            sections=[  # 组织结果分析正文分节。
                ("结果总结", analysis.summary),  # 写入结果总结章节。
                ("关键发现", "\n".join(f"- {item}" for item in analysis.key_findings)),  # 写入关键发现章节。
                ("结论边界", "\n".join(f"- {item}" for item in analysis.claims_boundary)),  # 写入结论边界章节。
                ("论文叙事主线", "\n".join(f"{index}. {item}" for index, item in enumerate(analysis.paper_storyline, start=1))),  # 写入论文叙事主线章节。
            ],  # 结束结果分析分节列表。
            metadata={"title": "实验结果解读与论文话术草案", "version": "auto", "date": str(date.today()), "stage": "result_analysis", "author_agent": "StudentAgent", "review_status": "draft"},  # 写入文档元数据。
        )  # 完成结果分析工件写入。
        update = {  # 组织状态更新。
            "result_analysis_path": artifact.path,  # 保存结果分析文档路径。
            "current_stage": "manuscript_drafting",  # 推进到论文写作阶段。
            "active_agent": "student",  # 保持研究生为当前执行角色。
        }  # 结束状态更新构造。
        update.update(self._register_artifact(state, artifact))  # 合并工件登记更新。
        return update  # 返回节点更新结果。

    def student_manuscript_react_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义研究生论文写作节点。
        draft = self.student_agent.draft_manuscript(  # 调用研究生 Agent 生成论文草稿。
            {  # 组织论文写作上下文。
                "topic": state["topic"],  # 写入研究主题。
                "approved_innovation": state.get("approved_innovation"),  # 写入已通过创新点。
                "result_analysis_path": state.get("result_analysis_path"),  # 写入结果分析文档路径。
                "review_comments": state.get("review_comments", []),  # 写入上一轮审核意见，便于返修时继续修改。
                "stage": state.get("current_stage"),  # 写入当前阶段名，便于区分初稿与返修稿。
            }  # 结束论文写作上下文。
        )  # 获得结构化论文草稿。
        artifact = self.artifact_manager.write_markdown(  # 保存论文 Markdown 工件。
            bucket="manuscripts",  # 指定输出目录桶为论文目录。
            document_name="论文稿件",  # 指定文档名称。
            title=draft.title,  # 使用模型生成的论文标题作为文档标题。
            sections=[  # 组织论文章节。
                ("摘要", draft.abstract),  # 写入摘要章节。
                ("引言", draft.introduction),  # 写入引言章节。
                ("相关工作", draft.related_work),  # 写入相关工作章节。
                ("方法", draft.method),  # 写入方法章节。
                ("实验", draft.experiments),  # 写入实验章节。
                ("结论", draft.conclusion),  # 写入结论章节。
                ("参考文献", "\n".join(f"- {item}" for item in draft.references)),  # 写入参考文献列表。
                ("研究生自审", "\n".join(f"- {item}" for item in draft.self_review_notes)),  # 写入研究生自审记录。
            ],  # 结束论文章节列表。
            metadata={"title": draft.title, "version": "auto", "date": str(date.today()), "stage": "manuscript_drafting", "author_agent": "StudentAgent", "review_status": "submitted"},  # 写入文档元数据。
        )  # 完成论文工件写入。
        submission = self.message_bus.submission(  # 构造提交给导师的论文审核消息。
            from_agent="student",  # 设置发送角色为研究生。
            to_agent="advisor",  # 设置接收角色为导师。
            stage="paper_review",  # 标记当前阶段为论文二审。
            artifact_type="manuscript",  # 标记提交工件类型为论文。
            artifact_path=artifact.path,  # 写入论文路径。
            summary="研究生已提交论文稿件，请导师二审。",  # 写入消息摘要。
        )  # 完成提交消息构造。
        update = {  # 组织状态更新。
            "manuscript_path": artifact.path,  # 保存当前论文路径。
            "current_stage": "advisor_paper_review",  # 推进到导师二审阶段。
            "active_agent": None,  # 研究生提交后挂起。
            "waiting_for_agent": "advisor",  # 标记当前正在等待导师回复。
            "suspend_reason": "paper_review",  # 标记挂起原因是论文二审。
            "submitted_artifact_path": artifact.path,  # 记录最近一次提交工件路径。
            "submitted_artifact_type": "manuscript",  # 记录最近一次提交工件类型。
            "resume_token": submission.metadata.get("resume_token"),  # 保存恢复令牌。
            "workflow_status": WorkflowStatus.suspended.value,  # 把工作流标记为挂起。
            "conversation_round": state.get("conversation_round", 0) + 1,  # 增加总体来回轮次。
        }  # 结束状态更新构造。
        update.update(self._register_artifact(state, artifact))  # 合并工件登记更新。
        update.update(self._append_message(state, submission))  # 合并消息日志更新。
        return update  # 返回节点更新结果。

    def advisor_paper_review_react_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义导师论文二审节点。
        review = self.advisor_agent.review_manuscript(  # 调用导师 Agent 审核论文。
            {  # 组织导师审核上下文。
                "manuscript_path": state.get("manuscript_path"),  # 写入论文路径。
                "approved_innovation": state.get("approved_innovation"),  # 写入已通过创新点。
                "review_round": state.get("paper_review_round", 0),  # 写入当前导师审核轮次。
            }  # 结束导师审核上下文。
        )  # 获得结构化导师审核结果。
        artifact = self.artifact_manager.write_markdown(  # 保存导师审稿意见文档。
            bucket="reviews",  # 指定输出目录桶为审稿意见目录。
            document_name="导师审稿意见",  # 指定文档名称。
            title="导师审稿意见",  # 指定 Markdown 主标题。
            sections=[  # 组织导师审稿正文分节。
                ("审核结论", review.decision.value),  # 写入审核结论章节。
                ("主要问题", "\n".join(f"- {item}" for item in review.major_issues) or "- 无"),  # 写入主要问题章节。
                ("次要问题", "\n".join(f"- {item}" for item in review.minor_issues) or "- 无"),  # 写入次要问题章节。
                ("必须修改", "\n".join(f"- {item}" for item in review.required_changes)),  # 写入必须修改章节。
            ],  # 结束正文分节列表。
            metadata={"title": "导师审稿意见", "version": "auto", "date": str(date.today()), "stage": "advisor_paper_review", "author_agent": "AdvisorAgent", "review_status": review.decision.value},  # 写入文档元数据。
        )  # 完成导师意见写入。
        last_message = AgentMessage.model_validate(state["messages_log"][-1])  # 读取最近一条研究生提交论文的消息，并还原成结构化对象。
        reply = self.message_bus.reply(  # 构造导师返回给研究生的回复消息。
            source_message=last_message,  # 绑定原始提交消息。
            from_agent="advisor",  # 设置回复角色为导师。
            decision=review.decision.value,  # 写入导师审核结论。
            comments_path=artifact.path,  # 写入导师反馈文档路径。
            summary="导师已完成论文二审。",  # 写入回复摘要。
        )  # 完成导师回复消息构造。
        update = {  # 组织状态更新。
            "review_decision": review.decision.value,  # 保存最新审核结论。
            "review_comments": [*review.major_issues, *review.minor_issues, *review.required_changes],  # 保存导师提出的全部问题和修改项。
            "advisor_review_path": artifact.path,  # 保存导师反馈路径。
            "waiting_for_agent": None,  # 导师已完成回复，清空等待角色。
            "workflow_status": WorkflowStatus.running.value,  # 恢复工作流为运行中。
            "last_reply_message_id": reply.message_id,  # 保存最后一条回复消息 ID。
            "paper_review_round": state.get("paper_review_round", 0) + 1,  # 增加导师审核轮次。
            "current_stage": "manuscript_revision" if review.decision == ReviewDecision.revise else "reviewer_blind_review",  # 根据审核结论决定返修还是进入盲审。
            "active_agent": "student" if review.decision == ReviewDecision.revise else "reviewer",  # 根据审核结论决定下一个活跃角色。
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
            bucket="reviews",  # 指定输出目录桶为审稿意见目录。
            document_name="盲审意见",  # 指定文档名称。
            title="盲审意见",  # 指定 Markdown 主标题。
            sections=[  # 组织盲审文档正文分节。
                ("审稿结论", review.decision.value),  # 写入审稿结论章节。
                ("总体评价", review.summary),  # 写入总体评价章节。
                ("优点", "\n".join(f"- {item}" for item in review.strengths)),  # 写入优点章节。
                ("问题", "\n".join(f"- {item}" for item in review.weaknesses)),  # 写入问题章节。
                ("必须修改", "\n".join(f"- {item}" for item in review.required_changes)),  # 写入必须修改章节。
                ("置信度", review.confidence),  # 写入置信度章节。
            ],  # 结束文档分节列表。
            metadata={"title": "盲审意见", "version": "auto", "date": str(date.today()), "stage": "reviewer_blind_review", "author_agent": "ReviewerAgent", "review_status": review.decision.value},  # 写入文档元数据。
        )  # 完成盲审意见写入。
        update = {  # 组织状态更新。
            "review_decision": review.decision.value,  # 保存盲审结论。
            "review_comments": [*review.weaknesses, *review.required_changes],  # 保存盲审问题与修改项。
            "reviewer_review_path": artifact.path,  # 保存盲审意见路径。
            "blind_review_round": state.get("blind_review_round", 0) + 1,  # 增加盲审轮次。
            "current_stage": "manuscript_revision" if review.decision in {ReviewDecision.major_revision, ReviewDecision.reject} else ("final_polish" if review.decision == ReviewDecision.minor_revision else "finalize"),  # 根据盲审结论决定返修路径。
            "active_agent": "student" if review.decision in {ReviewDecision.major_revision, ReviewDecision.minor_revision, ReviewDecision.reject} else "system",  # 根据盲审结论决定下一个活跃角色。
        }  # 结束状态更新构造。
        update.update(self._register_artifact(state, artifact))  # 合并工件登记更新。
        return update  # 返回节点更新结果。

    def student_final_revision_react_node(self, state: WorkflowState) -> dict[str, Any]:  # 定义研究生终稿润色节点。
        draft = self.student_agent.draft_manuscript(  # 复用论文写作能力做最终小修改稿。
            {  # 组织终稿润色上下文。
                "topic": state["topic"],  # 写入研究主题。
                "approved_innovation": state.get("approved_innovation"),  # 写入已通过创新点。
                "result_analysis_path": state.get("result_analysis_path"),  # 写入结果分析路径。
                "review_comments": state.get("review_comments", []),  # 写入盲审意见，便于小修。
                "stage": "final_polish",  # 明确当前是终稿润色阶段。
            }  # 结束润色上下文。
        )  # 获得结构化终稿润色结果。
        artifact = self.artifact_manager.write_markdown(  # 保存终稿版本。
            bucket="manuscripts",  # 指定输出目录桶为论文目录。
            document_name="论文终稿",  # 指定终稿文档名称。
            title=draft.title,  # 使用论文标题作为文档标题。
            sections=[("摘要", draft.abstract), ("引言", draft.introduction), ("相关工作", draft.related_work), ("方法", draft.method), ("实验", draft.experiments), ("结论", draft.conclusion), ("参考文献", "\n".join(f"- {item}" for item in draft.references)), ("最终自查", "\n".join(f"- {item}" for item in draft.self_review_notes))],  # 组织终稿章节列表。
            metadata={"title": draft.title, "version": "auto", "date": str(date.today()), "stage": "final_polish", "author_agent": "StudentAgent", "review_status": "final"},  # 写入文档元数据。
        )  # 完成终稿工件写入。
        update = {  # 组织状态更新。
            "manuscript_path": artifact.path,  # 更新最终论文路径。
            "current_stage": "finalize",  # 推进到最终收尾阶段。
            "active_agent": "system",  # 把执行权交给系统收尾节点。
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
        self.artifact_manager.append_log("workflow.jsonl", {"event": "completed", "thread_id": state["thread_id"], "final_decision": state.get("review_decision")})  # 写入工作流完成日志。
        return {"workflow_status": WorkflowStatus.completed.value, "current_stage": "done", "active_agent": None, "waiting_for_agent": None, "final_summary": final_summary}  # 返回完成态更新。

    def innovation_router(self, state: WorkflowState) -> str:  # 根据导师创新点审核结论决定下一节点。
        return "student_innovation_react_node" if state.get("review_decision") == ReviewDecision.revise.value else "student_experiment_design_react_node"  # 打回则回创新点提案节点，否则进入实验设计节点。

    def paper_router(self, state: WorkflowState) -> str:  # 根据导师论文二审结论决定下一节点。
        return "student_manuscript_react_node" if state.get("review_decision") == ReviewDecision.revise.value else "reviewer_blind_review_react_node"  # 打回则回论文写作节点，否则进入盲审节点。

    def blind_review_router(self, state: WorkflowState) -> str:  # 根据盲审结论决定下一节点。
        if state.get("review_decision") in {ReviewDecision.major_revision.value, ReviewDecision.reject.value}:  # 判断盲审是否为大修或拒稿。
            return "student_manuscript_react_node"  # 大修或拒稿时回到研究生论文返修节点。
        if state.get("review_decision") == ReviewDecision.minor_revision.value:  # 判断盲审是否为小修。
            return "student_final_revision_react_node"  # 小修时进入终稿润色节点。
        return "finalize_node"  # 接受时直接进入最终收尾节点。

    def _build_graph(self):  # 构建并编译 LangGraph 工作流图。
        builder = StateGraph(WorkflowState)  # 使用 WorkflowState 作为共享状态定义创建图。
        builder.add_node("bootstrap_node", self.bootstrap_node)  # 注册启动节点。
        builder.add_node("student_literature_react_node", self.student_literature_react_node)  # 注册文献调研节点。
        builder.add_node("student_innovation_react_node", self.student_innovation_react_node)  # 注册创新点提案节点。
        builder.add_node("advisor_innovation_review_react_node", self.advisor_innovation_review_react_node)  # 注册导师创新点审核节点。
        builder.add_node("student_experiment_design_react_node", self.student_experiment_design_react_node)  # 注册实验设计节点。
        builder.add_node("human_experiment_interrupt_node", self.human_experiment_interrupt_node)  # 注册人工实验挂起节点。
        builder.add_node("student_result_analysis_react_node", self.student_result_analysis_react_node)  # 注册结果分析节点。
        builder.add_node("student_manuscript_react_node", self.student_manuscript_react_node)  # 注册论文写作节点。
        builder.add_node("advisor_paper_review_react_node", self.advisor_paper_review_react_node)  # 注册导师论文二审节点。
        builder.add_node("reviewer_blind_review_react_node", self.reviewer_blind_review_react_node)  # 注册审稿人盲审节点。
        builder.add_node("student_final_revision_react_node", self.student_final_revision_react_node)  # 注册终稿润色节点。
        builder.add_node("finalize_node", self.finalize_node)  # 注册最终收尾节点。
        builder.add_edge(START, "bootstrap_node")  # 把图起点连接到启动节点。
        builder.add_edge("bootstrap_node", "student_literature_react_node")  # 启动后进入文献调研阶段。
        builder.add_edge("student_literature_react_node", "student_innovation_react_node")  # 文献调研后进入创新点提案阶段。
        builder.add_edge("student_innovation_react_node", "advisor_innovation_review_react_node")  # 创新点提交后进入导师审核阶段。
        builder.add_conditional_edges("advisor_innovation_review_react_node", self.innovation_router, {"student_innovation_react_node": "student_innovation_react_node", "student_experiment_design_react_node": "student_experiment_design_react_node"})  # 根据导师审核结果在创新点返修和实验设计之间路由。
        builder.add_edge("student_experiment_design_react_node", "human_experiment_interrupt_node")  # 实验设计后进入人工实验挂起阶段。
        builder.add_edge("human_experiment_interrupt_node", "student_result_analysis_react_node")  # 人工恢复后进入实验结果分析阶段。
        builder.add_edge("student_result_analysis_react_node", "student_manuscript_react_node")  # 结果分析后进入论文写作阶段。
        builder.add_edge("student_manuscript_react_node", "advisor_paper_review_react_node")  # 论文稿件提交后进入导师二审阶段。
        builder.add_conditional_edges("advisor_paper_review_react_node", self.paper_router, {"student_manuscript_react_node": "student_manuscript_react_node", "reviewer_blind_review_react_node": "reviewer_blind_review_react_node"})  # 根据导师意见在论文返修和盲审之间路由。
        builder.add_conditional_edges("reviewer_blind_review_react_node", self.blind_review_router, {"student_manuscript_react_node": "student_manuscript_react_node", "student_final_revision_react_node": "student_final_revision_react_node", "finalize_node": "finalize_node"})  # 根据盲审结果在大修、小修、接受之间路由。
        builder.add_edge("student_final_revision_react_node", "finalize_node")  # 小修终稿后进入最终收尾节点。
        builder.add_edge("finalize_node", END)  # 把收尾节点连接到图终点。
        return builder.compile(checkpointer=self.settings.build_checkpointer())  # 使用配置中的检查点编译并返回可执行图。


__all__ = ["ResearchStateMachine"]  # 暴露正式状态机类，供 CLI 和外部脚本创建工作流实例。
