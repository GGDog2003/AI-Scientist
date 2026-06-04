from __future__ import annotations  # 启用延后类型注解，方便后续统一类型提示。

from typing import Any  # 导入 Any，用于工作流状态字典类型标注。

from app.workflows.state_machine import ResearchStateMachine  # 导入正式状态机类，便于复用 app 目录下的实验阶段逻辑。


def experiment_node_names() -> list[str]:  # 返回实验阶段涉及的节点名称列表。
    return ["student_experiment_design_react_node", "human_experiment_interrupt_node", "student_result_analysis_react_node"]  # 返回实验设计、人工执行、结果分析三个节点。


def run_experiment_design_stage(app: ResearchStateMachine, state: dict[str, Any]) -> dict[str, Any]:  # 执行实验设计节点。
    return app.student_experiment_design_react_node(state)  # 复用正式状态机中的实验设计逻辑。


def run_experiment_analysis_stage(app: ResearchStateMachine, state: dict[str, Any]) -> dict[str, Any]:  # 执行实验结果分析节点。
    return app.student_result_analysis_react_node(state)  # 复用正式状态机中的实验结果分析逻辑。
