from __future__ import annotations  # 启用延后类型注解，便于后续添加更细粒度类型提示。

from typing import Any  # 导入 Any，用于工作流状态类型标注。

from app.workflows.state_machine import ResearchStateMachine  # 导入正式状态机类，便于复用 app 目录下的论文阶段逻辑。


def paper_node_names() -> list[str]:  # 返回论文阶段涉及的节点名称列表。
    return ["student_manuscript_react_node", "advisor_paper_review_react_node", "reviewer_blind_review_react_node", "student_final_revision_react_node", "finalize_node"]  # 返回论文写作、导师二审、盲审、小修终稿和结束节点。


def run_student_paper_stage(app: ResearchStateMachine, state: dict[str, Any]) -> dict[str, Any]:  # 执行研究生论文写作节点。
    return app.student_manuscript_react_node(state)  # 复用正式状态机中的论文写作逻辑。


def run_advisor_paper_review_stage(app: ResearchStateMachine, state: dict[str, Any]) -> dict[str, Any]:  # 执行导师论文审核节点。
    return app.advisor_paper_review_react_node(state)  # 复用正式状态机中的导师论文二审逻辑。


def run_reviewer_blind_review_stage(app: ResearchStateMachine, state: dict[str, Any]) -> dict[str, Any]:  # 执行审稿人盲审节点。
    return app.reviewer_blind_review_react_node(state)  # 复用正式状态机中的审稿人盲审逻辑。
