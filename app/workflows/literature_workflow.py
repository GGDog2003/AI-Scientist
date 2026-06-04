from __future__ import annotations  # 启用延后类型注解，便于类型提示中引用本地类。

from typing import Any  # 导入 Any，用于工作流状态字典类型标注。

from app.workflows.state_machine import ResearchStateMachine  # 导入正式状态机类，便于复用 app 目录下的节点逻辑。


def literature_node_names() -> list[str]:  # 返回文献调研阶段涉及的节点名称列表。
    return ["bootstrap_node", "student_literature_react_node"]  # 按顺序返回启动与文献调研节点名称。


def run_literature_stage(app: ResearchStateMachine, state: dict[str, Any]) -> dict[str, Any]:  # 执行文献调研阶段的核心节点。
    return app.student_literature_react_node(state)  # 直接复用正式状态机中的研究生文献调研节点逻辑。
