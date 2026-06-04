from __future__ import annotations  # 启用延后类型注解，便于后续类型标注扩展。

from typing import Any  # 导入 Any，用于工作流状态类型标注。

from app.workflows.state_machine import ResearchStateMachine  # 导入正式状态机类，便于复用 app 目录下的创新点节点逻辑。


def innovation_node_names() -> list[str]:  # 返回创新点讨论阶段涉及的节点名称列表。
    return ["student_innovation_react_node", "advisor_innovation_review_react_node"]  # 按阶段顺序返回研究生提交和导师审核节点。


def run_student_innovation_stage(app: ResearchStateMachine, state: dict[str, Any]) -> dict[str, Any]:  # 执行研究生创新点提案节点。
    return app.student_innovation_react_node(state)  # 直接复用正式状态机中的创新点提案逻辑。


def run_advisor_innovation_review_stage(app: ResearchStateMachine, state: dict[str, Any]) -> dict[str, Any]:  # 执行导师创新点审核节点。
    return app.advisor_innovation_review_react_node(state)  # 直接复用正式状态机中的导师审核逻辑。
