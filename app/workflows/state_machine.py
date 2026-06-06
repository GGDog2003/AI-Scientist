from __future__ import annotations

import json
from datetime import date
from datetime import datetime
from typing import Any
from uuid import uuid4

from langgraph.graph import END
from langgraph.graph import START
from langgraph.graph import StateGraph
from langgraph.types import interrupt

from app.agents.advisor_agent import AdvisorAgent
from app.agents.reviewer_agent import ReviewerAgent
from app.agents.student_agent import StudentAgent
from app.config import AppSettings
from app.config import build_thread_config
from app.schemas.agent_message import AgentMessage
from app.schemas.experiment_result import ExperimentGateDecision
from app.schemas.experiment_result import ExperimentGateReview
from app.schemas.manuscript_review import ReviewDecision
from app.schemas.workflow_state import ArtifactRecord
from app.schemas.workflow_state import WorkflowState
from app.schemas.workflow_state import WorkflowStatus
from app.tools import build_tools
from app.tools.file_store import ArtifactManager
from app.tools.message_bus import MessageBus


class ResearchStateMachine:
    def __init__(self, project_root: str | None = None, settings: AppSettings | None = None) -> None:
        self.settings = settings or AppSettings.from_env(project_root=project_root)
        self.settings.ensure_workspace()
        self.artifact_manager = ArtifactManager(self.settings.workspace_root)
        self.artifact_manager.ensure_workspace()
        self.message_bus = MessageBus(self.artifact_manager)
        self.tools = build_tools(self.artifact_manager)
        self.student_agent = StudentAgent(settings=self.settings, tools=self.tools)
        self.advisor_agent = AdvisorAgent(settings=self.settings, tools=self.tools)
        self.reviewer_agent = ReviewerAgent(settings=self.settings, tools=self.tools)
        self.graph = self._build_graph()

    def create_initial_state(
        self,
        topic: str,
        domain: str,
        paper_paths: list[str] | None = None,
        thread_id: str | None = None,
    ) -> WorkflowState:
        return WorkflowState(
            thread_id=thread_id or uuid4().hex,
            topic=topic,
            domain=domain,
            paper_paths=paper_paths or [],
            workflow_status=WorkflowStatus.running.value,
            current_stage="bootstrap",
            active_agent="student",
            waiting_for_agent=None,
            suspend_reason=None,
            submitted_artifact_path=None,
            submitted_artifact_type=None,
            resume_token=None,
            last_reply_message_id=None,
            conversation_round=0,
            innovation_review_round=0,
            paper_review_round=0,
            blind_review_round=0,
            literature_notes=[],
            literature_report_path=None,
            innovation_cards=[],
            approved_innovation=None,
            innovation_report_path=None,
            experiment_plan_path=None,
            experiment_result_path=None,
            result_analysis_path=None,
            manuscript_path=None,
            advisor_review_path=None,
            reviewer_review_path=None,
            review_decision=None,
            review_comments=[],
            artifacts=[],
            messages_log=[],
            human_result=None,
            final_summary=None,
        )

    def get_state(self, thread_id: str):
        return self.graph.get_state(build_thread_config(thread_id))

    def run_until_pause(self, input_value: Any, thread_id: str) -> tuple[Any, list[Any]]:
        # 供 GUI 和 CLI 共用的运行入口：持续执行到流程结束或命中中断点。
        config = build_thread_config(thread_id)
        interrupts: list[Any] = []
        for event in self.graph.stream(input_value, config=config):
            if "__interrupt__" in event:
                interrupts.extend(event["__interrupt__"])
        snapshot = self.graph.get_state(config)
        return snapshot, interrupts

    def _append_progress_event(
        self,
        state: WorkflowState,
        step_key: str,
        label: str,
        agent: str,
        status: str,
        artifact_path: str | None = None,
        detail: str | None = None,
    ) -> None:
        # 为 GUI 追加结构化进度日志，前端只需按同一个 step_key 取最新状态即可。
        self.artifact_manager.append_log(
            "progress.jsonl",
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "thread_id": state["thread_id"],
                "step_key": step_key,
                "label": label,
                "agent": agent,
                "status": status,
                "artifact_path": artifact_path,
                "detail": detail,
                "current_stage": state.get("current_stage"),
            },
        )

    def _mark_step_started(self, state: WorkflowState, step_key: str, label: str, agent: str) -> None:
        # 记录某一步已经开始执行，供前端显示旋转中的进度项。
        self._append_progress_event(state, step_key, label, agent, "running")

    def _mark_step_completed(
        self,
        state: WorkflowState,
        step_key: str,
        label: str,
        agent: str,
        artifact_path: str | None = None,
        detail: str | None = None,
    ) -> None:
        # 记录某一步已经完成，必要时附带可打开的产物路径。
        self._append_progress_event(state, step_key, label, agent, "completed", artifact_path, detail)

    def _mark_step_waiting(
        self,
        state: WorkflowState,
        step_key: str,
        label: str,
        agent: str,
        detail: str | None = None,
        artifact_path: str | None = None,
    ) -> None:
        # 记录某一步正在等待人工输入，供前端显示“导入实验结果”按钮。
        self._append_progress_event(state, step_key, label, agent, "waiting", artifact_path, detail)

    def _register_artifact(self, state: WorkflowState, artifact: ArtifactRecord) -> dict[str, Any]:
        artifacts = list(state.get("artifacts", []))
        artifacts.append(artifact.model_dump())
        return {"artifacts": artifacts}

    def _append_message(self, state: WorkflowState, message: AgentMessage) -> dict[str, Any]:
        messages = list(state.get("messages_log", []))
        messages.append(message.model_dump())
        return {"messages_log": messages}

    def _normalize_human_result(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            metrics = payload.get("metrics")
            if not isinstance(metrics, dict):
                payload = {**payload, "metrics": {}}
            return payload
        return {"summary": str(payload), "metrics": {}}

    def _coerce_float(self, value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return None
        return None

    def _find_metric(self, metrics: dict[str, Any], *keywords: str) -> float | None:
        for key, value in metrics.items():
            normalized_key = key.lower()
            if any(keyword in normalized_key for keyword in keywords):
                numeric_value = self._coerce_float(value)
                if numeric_value is not None:
                    return numeric_value
        return None

    def _pick_innovation(self, state: WorkflowState, approved_name: str | None = None) -> dict[str, Any] | None:
        cards = list(state.get("innovation_cards", []))
        if approved_name:
            for card in cards:
                if card.get("name") == approved_name:
                    return card
        return cards[0] if cards else None

    def _decide_experiment_gate_from_human_result(
        self,
        human_result: dict[str, Any] | None,
    ) -> tuple[ExperimentGateDecision, str]:
        human_result = human_result or {}
        metrics = human_result.get("metrics", {})
        summary = str(human_result.get("summary", "")).lower()
        psnr = self._find_metric(metrics, "psnr")
        ssim = self._find_metric(metrics, "ssim")
        if (psnr is not None and psnr >= 40.0) or (ssim is not None and ssim >= 0.995):
            return (
                ExperimentGateDecision.direct_to_writing,
                f"命中高收益阈值：PSNR={psnr}，SSIM={ssim}，按规则直接进入论文写作。",
            )
        if any(token in summary for token in ("顶刊级", "显著领先", "大幅领先", "明显优于", "far better", "sota")):
            return (
                ExperimentGateDecision.direct_to_writing,
                "人工实验总结包含显著领先信号，按规则直接进入论文写作。",
            )
        if (psnr is not None and psnr >= 34.0) or (ssim is not None and ssim >= 0.97):
            return (
                ExperimentGateDecision.minor_revision,
                f"命中中等收益阈值：PSNR={psnr}，SSIM={ssim}，按规则以小修方式进入论文写作。",
            )
        return (
            ExperimentGateDecision.major_revision,
            f"未命中放行阈值：PSNR={psnr}，SSIM={ssim}，按规则返回大修。",
        )

    def bootstrap_node(self, state: WorkflowState) -> dict[str, Any]:
        self._mark_step_started(state, "bootstrap", "初始化研究流程", "system")
        self.artifact_manager.append_log(
            "workflow.jsonl",
            {"event": "bootstrap", "thread_id": state["thread_id"], "topic": state["topic"]},
        )
        self._mark_step_completed(state, "bootstrap", "初始化研究流程", "system")
        return {"current_stage": "literature_research", "active_agent": "student"}

    def student_literature_react_node(self, state: WorkflowState) -> dict[str, Any]:
        self._mark_step_started(state, "literature_summary", "研究生正在阅读并整理文献", "student")
        synthesis = self.student_agent.summarize_literature(
            {"topic": state["topic"], "domain": state["domain"], "paper_paths": state.get("paper_paths", [])}
        )
        notes_section = "\n\n".join(
            [
                (
                    f"### {note.title}\n"
                    f"- 来源：{note.venue} {note.year}\n"
                    f"- 摘要：{note.summary}\n"
                    f"- 创新点：{'；'.join(note.innovation_points)}\n"
                    f"- 局限性：{'；'.join(note.limitations)}\n"
                    f"- 基座论文：{note.base_paper or '无'}\n"
                    f"- 相对改进：{'；'.join(note.improvements_over_base) or '无'}"
                )
                for note in synthesis.notes
            ]
        )
        artifact = self.artifact_manager.write_markdown(
            bucket="literature_reports",
            document_name="文献调研汇总报告",
            title="文献调研汇总报告",
            sections=[
                ("研究趋势", synthesis.trend_summary),
                ("潜在研究空白", "\n".join(f"- {item}" for item in synthesis.possible_gaps)),
                ("逐篇论文笔记", notes_section or "暂无。"),
            ],
            metadata={
                "title": "文献调研汇总报告",
                "version": "auto",
                "date": str(date.today()),
                "stage": "literature_summary",
                "author_agent": "StudentAgent",
                "review_status": "draft",
            },
        )
        update = {
            "literature_notes": [note.model_dump() for note in synthesis.notes],
            "literature_report_path": artifact.path,
            "current_stage": "innovation_proposal",
            "active_agent": "student",
        }
        update.update(self._register_artifact(state, artifact))
        self._mark_step_completed(
            state,
            "literature_summary",
            "研究生正在阅读并整理文献",
            "student",
            artifact.path,
        )
        return update

    def student_innovation_react_node(self, state: WorkflowState) -> dict[str, Any]:
        self._mark_step_started(state, "innovation_proposal", "研究生正在提出创新点方案", "student")
        proposal = self.student_agent.propose_innovations(
            {
                "topic": state["topic"],
                "domain": state["domain"],
                "literature_notes": state.get("literature_notes", []),
                "advisor_comments": state.get("review_comments", []),
                "review_round": state.get("innovation_review_round", 0),
            }
        )
        cards_section = "\n\n".join(
            [
                (
                    f"### {card.name}\n"
                    f"- 动机：{card.motivation}\n"
                    f"- 创新类型：{card.novelty_type}\n"
                    f"- 预期收益：{card.expected_gain}\n"
                    f"- 风险点：{'；'.join(card.risk_points)}\n"
                    f"- 证据依据：{'；'.join(card.evidence)}"
                )
                for card in proposal.cards
            ]
        )
        artifact = self.artifact_manager.write_markdown(
            bucket="innovation_meetings",
            document_name="创新点候选列表",
            title="创新点候选列表",
            sections=[
                ("组会汇报摘要", proposal.meeting_brief),
                ("候选创新点", cards_section or "暂无。"),
                ("当前主推方向", proposal.selected_focus),
            ],
            metadata={
                "title": "创新点候选列表",
                "version": "auto",
                "date": str(date.today()),
                "stage": "innovation_proposal",
                "author_agent": "StudentAgent",
                "review_status": "submitted",
            },
        )
        submission = self.message_bus.submission(
            from_agent="student",
            to_agent="advisor",
            stage="innovation_review",
            artifact_type="innovation_card",
            artifact_path=artifact.path,
            summary="研究生已提交创新点候选方案，请导师审核。",
        )
        update = {
            "innovation_cards": [card.model_dump() for card in proposal.cards],
            "innovation_report_path": artifact.path,
            "current_stage": "advisor_innovation_review",
            "active_agent": None,
            "waiting_for_agent": "advisor",
            "suspend_reason": "innovation_review",
            "submitted_artifact_path": artifact.path,
            "submitted_artifact_type": "innovation_card",
            "resume_token": submission.metadata.get("resume_token"),
            "workflow_status": WorkflowStatus.suspended.value,
            "conversation_round": state.get("conversation_round", 0) + 1,
        }
        update.update(self._register_artifact(state, artifact))
        update.update(self._append_message(state, submission))
        self._mark_step_completed(
            state,
            "innovation_proposal",
            "研究生正在提出创新点方案",
            "student",
            artifact.path,
        )
        return update

    def advisor_innovation_review_react_node(self, state: WorkflowState) -> dict[str, Any]:
        self._mark_step_started(state, "innovation_review", "导师正在审核创新点方案", "advisor")
        review = self.advisor_agent.review_innovations(
            {
                "topic": state["topic"],
                "proposal": {"cards": state.get("innovation_cards", [])},
                "review_round": state.get("innovation_review_round", 0),
            }
        )
        next_round = state.get("innovation_review_round", 0) + 1
        approved_innovation = self._pick_innovation(state, review.approved_card_name)
        forced_to_experiment = False
        if approved_innovation is None and next_round >= 3:
            approved_innovation = self._pick_innovation(state)
            forced_to_experiment = approved_innovation is not None
        comments = list(review.comments)
        if forced_to_experiment:
            comments.append("已达到导师创新点评审三轮上限，按当前首个候选方案直接进入实验验证。")
        artifact = self.artifact_manager.write_markdown(
            bucket="innovation_meetings",
            document_name="导师创新点反馈",
            title="导师创新点反馈",
            sections=[
                ("审核结论", review.decision.value),
                ("逐条意见", "\n".join(f"- {item}" for item in comments) or "- 无"),
                ("进入实验方案", json.dumps(approved_innovation, ensure_ascii=False, indent=2) if approved_innovation else "未确定"),
            ],
            metadata={
                "title": "导师创新点反馈",
                "version": "auto",
                "date": str(date.today()),
                "stage": "innovation_review",
                "author_agent": "AdvisorAgent",
                "review_status": review.decision.value,
            },
        )
        last_message = AgentMessage.model_validate(state["messages_log"][-1])
        reply = self.message_bus.reply(
            source_message=last_message,
            from_agent="advisor",
            decision=review.decision.value,
            comments_path=artifact.path,
            summary="导师已完成创新点审核。",
        )
        update = {
            "review_decision": review.decision.value,
            "review_comments": comments,
            "advisor_review_path": artifact.path,
            "approved_innovation": approved_innovation,
            "waiting_for_agent": None,
            "workflow_status": WorkflowStatus.running.value,
            "last_reply_message_id": reply.message_id,
            "innovation_review_round": next_round,
            "current_stage": "experiment_design"
            if approved_innovation
            else "innovation_revision",
            "active_agent": "student",
            "suspend_reason": None,
        }
        update.update(self._register_artifact(state, artifact))
        update.update(self._append_message(state, reply))
        self._mark_step_completed(
            state,
            "innovation_review",
            "导师正在审核创新点方案",
            "advisor",
            artifact.path,
            review.decision.value,
        )
        return update

    def student_experiment_design_react_node(self, state: WorkflowState) -> dict[str, Any]:
        self._mark_step_started(state, "experiment_design", "研究生正在设计实验方案", "student")
        approved_innovation = state.get("approved_innovation") or self._pick_innovation(state)
        plan = self.student_agent.design_experiment(
            {
                "topic": state["topic"],
                "approved_innovation": approved_innovation,
                "literature_notes": state.get("literature_notes", []),
                "review_comments": state.get("review_comments", []),
            }
        )
        artifact = self.artifact_manager.write_markdown(
            bucket="experiment_plans",
            document_name="实验设计方案",
            title="实验设计方案",
            sections=[
                ("实验目标", plan.objective),
                ("数据集", "\n".join(f"- {item}" for item in plan.datasets)),
                ("对比基线", "\n".join(f"- {item}" for item in plan.baselines)),
                ("评价指标", "\n".join(f"- {item}" for item in plan.metrics)),
                ("消融实验", "\n".join(f"- {item}" for item in plan.ablations)),
                ("代码模块", "\n".join(f"- {item}" for item in plan.python_modules)),
                ("执行步骤", "\n".join(f"- {item}" for item in plan.execution_steps)),
            ],
            metadata={
                "title": "实验设计方案",
                "version": "auto",
                "date": str(date.today()),
                "stage": "experiment_design",
                "author_agent": "StudentAgent",
                "review_status": "draft",
            },
        )
        update = {
            "approved_innovation": approved_innovation,
            "experiment_plan_path": artifact.path,
            "current_stage": "human_experiment",
            "active_agent": "student",
        }
        update.update(self._register_artifact(state, artifact))
        self._mark_step_completed(
            state,
            "experiment_design",
            "研究生正在设计实验方案",
            "student",
            artifact.path,
        )
        return update

    def human_experiment_interrupt_node(self, state: WorkflowState) -> dict[str, Any]:
        self._mark_step_waiting(
            state,
            "human_experiment",
            "等待人工导入实验结果",
            "human",
            "请导入实验结果 JSON 后继续流程",
            state.get("experiment_plan_path"),
        )
        human_payload = interrupt(
            {
                "stage": "human_experiment",
                "instruction": "请人工完成实验，并通过 resume 提交实验结果。",
                "expected_format": {
                    "summary": "一句话总结实验表现",
                    "metrics": {"PSNR": 0.0, "SSIM": 0.0},
                    "notes": ["可选：补充观察"],
                },
                "experiment_plan_path": state.get("experiment_plan_path"),
            }
        )
        normalized_result = self._normalize_human_result(human_payload)
        artifact = self.artifact_manager.write_json(
            bucket="experiment_results",
            document_name="人工实验结果",
            payload=normalized_result,
        )
        update = {
            "human_result": normalized_result,
            "experiment_result_path": artifact.path,
            "current_stage": "result_analysis",
            "active_agent": "student",
            "workflow_status": WorkflowStatus.running.value,
            "waiting_for_agent": None,
            "suspend_reason": None,
        }
        update.update(self._register_artifact(state, artifact))
        self._mark_step_completed(
            state,
            "human_experiment",
            "等待人工导入实验结果",
            "human",
            artifact.path,
        )
        return update

    def student_result_analysis_react_node(self, state: WorkflowState) -> dict[str, Any]:
        self._mark_step_started(state, "result_analysis", "研究生正在分析实验结果", "student")
        analysis = self.student_agent.analyze_results(
            {
                "topic": state["topic"],
                "approved_innovation": state.get("approved_innovation"),
                "experiment_plan_path": state.get("experiment_plan_path"),
                "human_result": state.get("human_result"),
            }
        )
        artifact = self.artifact_manager.write_markdown(
            bucket="experiment_results",
            document_name="实验结果分析",
            title="实验结果分析",
            sections=[
                ("整体总结", analysis.summary),
                ("关键发现", "\n".join(f"- {item}" for item in analysis.key_findings)),
                ("结论边界", "\n".join(f"- {item}" for item in analysis.claims_boundary)),
                ("论文叙事主线", "\n".join(f"- {item}" for item in analysis.paper_storyline)),
            ],
            metadata={
                "title": "实验结果分析",
                "version": "auto",
                "date": str(date.today()),
                "stage": "result_analysis",
                "author_agent": "StudentAgent",
                "review_status": "draft",
            },
        )
        update = {
            "result_analysis_path": artifact.path,
            "current_stage": "advisor_result_gate",
            "active_agent": "advisor",
        }
        update.update(self._register_artifact(state, artifact))
        self._mark_step_completed(
            state,
            "result_analysis",
            "研究生正在分析实验结果",
            "student",
            artifact.path,
        )
        return update

    def advisor_result_gate_react_node(self, state: WorkflowState) -> dict[str, Any]:
        self._mark_step_started(state, "advisor_result_gate", "导师正在根据实验结果决定是否放行", "advisor")
        forced_decision, decision_rationale = self._decide_experiment_gate_from_human_result(state.get("human_result"))
        review = self.advisor_agent.review_experiment_results(
            {
                "topic": state["topic"],
                "approved_innovation": state.get("approved_innovation"),
                "human_result": state.get("human_result"),
                "result_analysis_path": state.get("result_analysis_path"),
                "required_decision": forced_decision.value,
                "decision_rationale": decision_rationale,
            }
        )
        comments = list(review.comments) or ["请按既定分流结论整理证据链并推进下一阶段。"]
        if decision_rationale not in comments:
            comments.insert(0, decision_rationale)
        normalized_review = ExperimentGateReview(decision=forced_decision, comments=comments)
        artifact = self.artifact_manager.write_markdown(
            bucket="reviews",
            document_name="导师实验结果分流意见",
            title="导师实验结果分流意见",
            sections=[
                ("分流结论", normalized_review.decision.value),
                ("规则依据", decision_rationale),
                ("后续建议", "\n".join(f"- {item}" for item in normalized_review.comments)),
            ],
            metadata={
                "title": "导师实验结果分流意见",
                "version": "auto",
                "date": str(date.today()),
                "stage": "advisor_result_gate",
                "author_agent": "AdvisorAgent",
                "review_status": normalized_review.decision.value,
            },
        )
        next_stage = (
            "manuscript_drafting"
            if normalized_review.decision in {ExperimentGateDecision.direct_to_writing, ExperimentGateDecision.minor_revision}
            else "innovation_revision"
        )
        update = {
            "review_decision": normalized_review.decision.value,
            "review_comments": normalized_review.comments,
            "advisor_review_path": artifact.path,
            "current_stage": next_stage,
            "active_agent": "student",
        }
        update.update(self._register_artifact(state, artifact))
        self._mark_step_completed(
            state,
            "advisor_result_gate",
            "导师正在根据实验结果决定是否放行",
            "advisor",
            artifact.path,
            normalized_review.decision.value,
        )
        return update

    def student_manuscript_react_node(self, state: WorkflowState) -> dict[str, Any]:
        self._mark_step_started(state, "manuscript_drafting", "研究生正在撰写论文草稿", "student")
        draft = self.student_agent.draft_manuscript(
            {
                "topic": state["topic"],
                "domain": state["domain"],
                "approved_innovation": state.get("approved_innovation"),
                "literature_report_path": state.get("literature_report_path"),
                "result_analysis_path": state.get("result_analysis_path"),
                "experiment_result_path": state.get("experiment_result_path"),
                "review_comments": state.get("review_comments", []),
                "paper_review_round": state.get("paper_review_round", 0),
                "stage": state.get("current_stage"),
            }
        )
        artifact = self.artifact_manager.write_markdown(
            bucket="manuscripts",
            document_name="论文草稿",
            title=draft.title,
            sections=[
                ("摘要", draft.abstract),
                ("引言", draft.introduction),
                ("相关工作", draft.related_work),
                ("方法", draft.method),
                ("实验", draft.experiments),
                ("结论", draft.conclusion),
                ("参考文献", "\n".join(f"- {item}" for item in draft.references)),
                ("自审记录", "\n".join(f"- {item}" for item in draft.self_review_notes)),
            ],
            metadata={
                "title": draft.title,
                "version": "auto",
                "date": str(date.today()),
                "stage": "manuscript_drafting",
                "author_agent": "StudentAgent",
                "review_status": "submitted",
            },
        )
        submission = self.message_bus.submission(
            from_agent="student",
            to_agent="advisor",
            stage="paper_review",
            artifact_type="manuscript",
            artifact_path=artifact.path,
            summary="研究生已提交论文草稿，请导师审核。",
        )
        update = {
            "manuscript_path": artifact.path,
            "current_stage": "advisor_paper_review",
            "active_agent": None,
            "waiting_for_agent": "advisor",
            "suspend_reason": "paper_review",
            "submitted_artifact_path": artifact.path,
            "submitted_artifact_type": "manuscript",
            "resume_token": submission.metadata.get("resume_token"),
            "workflow_status": WorkflowStatus.suspended.value,
            "conversation_round": state.get("conversation_round", 0) + 1,
        }
        update.update(self._register_artifact(state, artifact))
        update.update(self._append_message(state, submission))
        self._mark_step_completed(
            state,
            "manuscript_drafting",
            "研究生正在撰写论文草稿",
            "student",
            artifact.path,
        )
        return update

    def advisor_paper_review_react_node(self, state: WorkflowState) -> dict[str, Any]:
        self._mark_step_started(state, "advisor_paper_review", "导师正在审核论文草稿", "advisor")
        review = self.advisor_agent.review_manuscript(
            {
                "manuscript_path": state.get("manuscript_path"),
                "approved_innovation": state.get("approved_innovation"),
                "result_analysis_path": state.get("result_analysis_path"),
                "review_round": state.get("paper_review_round", 0),
            }
        )
        artifact = self.artifact_manager.write_markdown(
            bucket="reviews",
            document_name="导师审稿意见",
            title="导师审稿意见",
            sections=[
                ("审核结论", review.decision.value),
                ("主要问题", "\n".join(f"- {item}" for item in review.major_issues) or "- 无"),
                ("次要问题", "\n".join(f"- {item}" for item in review.minor_issues) or "- 无"),
                ("必须修改", "\n".join(f"- {item}" for item in review.required_changes) or "- 无"),
            ],
            metadata={
                "title": "导师审稿意见",
                "version": "auto",
                "date": str(date.today()),
                "stage": "advisor_paper_review",
                "author_agent": "AdvisorAgent",
                "review_status": review.decision.value,
            },
        )
        last_message = AgentMessage.model_validate(state["messages_log"][-1])
        reply = self.message_bus.reply(
            source_message=last_message,
            from_agent="advisor",
            decision=review.decision.value,
            comments_path=artifact.path,
            summary="导师已完成论文审核。",
        )
        update = {
            "review_decision": review.decision.value,
            "review_comments": [*review.major_issues, *review.minor_issues, *review.required_changes],
            "advisor_review_path": artifact.path,
            "waiting_for_agent": None,
            "workflow_status": WorkflowStatus.running.value,
            "last_reply_message_id": reply.message_id,
            "paper_review_round": state.get("paper_review_round", 0) + 1,
            "current_stage": "manuscript_revision"
            if review.decision in {ReviewDecision.revise, ReviewDecision.major_revision}
            else "reviewer_blind_review",
            "active_agent": "student"
            if review.decision in {ReviewDecision.revise, ReviewDecision.major_revision}
            else "reviewer",
            "suspend_reason": None,
        }
        update.update(self._register_artifact(state, artifact))
        update.update(self._append_message(state, reply))
        self._mark_step_completed(
            state,
            "advisor_paper_review",
            "导师正在审核论文草稿",
            "advisor",
            artifact.path,
            review.decision.value,
        )
        return update

    def reviewer_blind_review_react_node(self, state: WorkflowState) -> dict[str, Any]:
        self._mark_step_started(state, "reviewer_blind_review", "审稿人正在盲审论文", "reviewer")
        review = self.reviewer_agent.blind_review(
            {"manuscript_path": state.get("manuscript_path"), "review_round": state.get("blind_review_round", 0)}
        )
        artifact = self.artifact_manager.write_markdown(
            bucket="reviews",
            document_name="盲审意见",
            title="盲审意见",
            sections=[
                ("审稿结论", review.decision.value),
                ("总体评价", review.summary),
                ("优点", "\n".join(f"- {item}" for item in review.strengths)),
                ("问题", "\n".join(f"- {item}" for item in review.weaknesses)),
                ("必须修改", "\n".join(f"- {item}" for item in review.required_changes)),
                ("置信度", review.confidence),
            ],
            metadata={
                "title": "盲审意见",
                "version": "auto",
                "date": str(date.today()),
                "stage": "reviewer_blind_review",
                "author_agent": "ReviewerAgent",
                "review_status": review.decision.value,
            },
        )
        update = {
            "review_decision": review.decision.value,
            "review_comments": [*review.weaknesses, *review.required_changes],
            "reviewer_review_path": artifact.path,
            "blind_review_round": state.get("blind_review_round", 0) + 1,
            "current_stage": "manuscript_revision"
            if review.decision in {ReviewDecision.major_revision, ReviewDecision.reject}
            else ("final_polish" if review.decision == ReviewDecision.minor_revision else "finalize"),
            "active_agent": "student"
            if review.decision in {ReviewDecision.major_revision, ReviewDecision.minor_revision, ReviewDecision.reject}
            else "system",
        }
        update.update(self._register_artifact(state, artifact))
        self._mark_step_completed(
            state,
            "reviewer_blind_review",
            "审稿人正在盲审论文",
            "reviewer",
            artifact.path,
            review.decision.value,
        )
        return update

    def student_final_revision_react_node(self, state: WorkflowState) -> dict[str, Any]:
        self._mark_step_started(state, "final_polish", "研究生正在润色最终论文", "student")
        draft = self.student_agent.draft_manuscript(
            {
                "topic": state["topic"],
                "domain": state["domain"],
                "approved_innovation": state.get("approved_innovation"),
                "result_analysis_path": state.get("result_analysis_path"),
                "review_comments": state.get("review_comments", []),
                "stage": "final_polish",
            }
        )
        artifact = self.artifact_manager.write_markdown(
            bucket="manuscripts",
            document_name="论文终稿",
            title=draft.title,
            sections=[
                ("摘要", draft.abstract),
                ("引言", draft.introduction),
                ("相关工作", draft.related_work),
                ("方法", draft.method),
                ("实验", draft.experiments),
                ("结论", draft.conclusion),
                ("参考文献", "\n".join(f"- {item}" for item in draft.references)),
                ("最终自查", "\n".join(f"- {item}" for item in draft.self_review_notes)),
            ],
            metadata={
                "title": draft.title,
                "version": "auto",
                "date": str(date.today()),
                "stage": "final_polish",
                "author_agent": "StudentAgent",
                "review_status": "final",
            },
        )
        update = {"manuscript_path": artifact.path, "current_stage": "finalize", "active_agent": "system"}
        update.update(self._register_artifact(state, artifact))
        self._mark_step_completed(state, "final_polish", "研究生正在润色最终论文", "student", artifact.path)
        return update

    def finalize_node(self, state: WorkflowState) -> dict[str, Any]:
        self._mark_step_started(state, "finalize", "系统正在整理最终结果", "system")
        final_summary = "\n".join(
            [
                f"主题：{state['topic']}",
                f"领域：{state['domain']}",
                f"最终论文：{state.get('manuscript_path')}",
                f"导师意见：{state.get('advisor_review_path')}",
                f"盲审意见：{state.get('reviewer_review_path')}",
                f"最终结论：{state.get('review_decision')}",
            ]
        )
        self.artifact_manager.append_log(
            "workflow.jsonl",
            {"event": "completed", "thread_id": state["thread_id"], "final_decision": state.get("review_decision")},
        )
        self._mark_step_completed(
            state,
            "finalize",
            "系统正在整理最终结果",
            "system",
            state.get("manuscript_path"),
            state.get("review_decision"),
        )
        return {
            "workflow_status": WorkflowStatus.completed.value,
            "current_stage": "done",
            "active_agent": None,
            "waiting_for_agent": None,
            "final_summary": final_summary,
        }

    def innovation_router(self, state: WorkflowState) -> str:
        if (
            state.get("review_decision") in {ReviewDecision.revise.value, ReviewDecision.major_revision.value}
            and state.get("innovation_review_round", 0) < 3
        ):
            return "student_innovation_react_node"
        return "student_experiment_design_react_node"

    def paper_router(self, state: WorkflowState) -> str:
        if (
            state.get("review_decision") in {ReviewDecision.revise.value, ReviewDecision.major_revision.value}
            and state.get("paper_review_round", 0) < 5
        ):
            return "student_manuscript_react_node"
        return "reviewer_blind_review_react_node"

    def blind_review_router(self, state: WorkflowState) -> str:
        if state.get("review_decision") == ReviewDecision.major_revision.value:
            return "student_manuscript_react_node"
        if state.get("review_decision") == ReviewDecision.reject.value:
            return "student_manuscript_react_node"
        if state.get("review_decision") == ReviewDecision.minor_revision.value:
            return "student_final_revision_react_node"
        return "finalize_node"

    def _build_graph(self):
        builder = StateGraph(WorkflowState)
        builder.add_node("bootstrap_node", self.bootstrap_node)
        builder.add_node("student_literature_react_node", self.student_literature_react_node)
        builder.add_node("student_innovation_react_node", self.student_innovation_react_node)
        builder.add_node("advisor_innovation_review_react_node", self.advisor_innovation_review_react_node)
        builder.add_node("student_experiment_design_react_node", self.student_experiment_design_react_node)
        builder.add_node("human_experiment_interrupt_node", self.human_experiment_interrupt_node)
        builder.add_node("student_result_analysis_react_node", self.student_result_analysis_react_node)
        builder.add_node("advisor_result_gate_react_node", self.advisor_result_gate_react_node)
        builder.add_node("student_manuscript_react_node", self.student_manuscript_react_node)
        builder.add_node("advisor_paper_review_react_node", self.advisor_paper_review_react_node)
        builder.add_node("reviewer_blind_review_react_node", self.reviewer_blind_review_react_node)
        builder.add_node("student_final_revision_react_node", self.student_final_revision_react_node)
        builder.add_node("finalize_node", self.finalize_node)
        builder.add_edge(START, "bootstrap_node")
        builder.add_edge("bootstrap_node", "student_literature_react_node")
        builder.add_edge("student_literature_react_node", "student_innovation_react_node")
        builder.add_edge("student_innovation_react_node", "advisor_innovation_review_react_node")
        builder.add_conditional_edges(
            "advisor_innovation_review_react_node",
            self.innovation_router,
            {
                "student_innovation_react_node": "student_innovation_react_node",
                "student_experiment_design_react_node": "student_experiment_design_react_node",
            },
        )
        builder.add_edge("student_experiment_design_react_node", "human_experiment_interrupt_node")
        builder.add_edge("human_experiment_interrupt_node", "student_result_analysis_react_node")
        builder.add_edge("student_result_analysis_react_node", "advisor_result_gate_react_node")
        builder.add_conditional_edges(
            "advisor_result_gate_react_node",
            lambda state: "student_manuscript_react_node"
            if state.get("current_stage") == "manuscript_drafting"
            else "student_innovation_react_node",
            {
                "student_manuscript_react_node": "student_manuscript_react_node",
                "student_innovation_react_node": "student_innovation_react_node",
            },
        )
        builder.add_edge("student_manuscript_react_node", "advisor_paper_review_react_node")
        builder.add_conditional_edges(
            "advisor_paper_review_react_node",
            self.paper_router,
            {
                "student_manuscript_react_node": "student_manuscript_react_node",
                "reviewer_blind_review_react_node": "reviewer_blind_review_react_node",
            },
        )
        builder.add_conditional_edges(
            "reviewer_blind_review_react_node",
            self.blind_review_router,
            {
                "student_manuscript_react_node": "student_manuscript_react_node",
                "student_final_revision_react_node": "student_final_revision_react_node",
                "finalize_node": "finalize_node",
            },
        )
        builder.add_edge("student_final_revision_react_node", "finalize_node")
        builder.add_edge("finalize_node", END)
        return builder.compile(checkpointer=self.settings.build_checkpointer())


__all__ = ["ResearchStateMachine"]
