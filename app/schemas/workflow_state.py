from enum import Enum  # 导入枚举基类，用于定义工作流状态常量。
from typing import Any  # 导入 Any，用于状态字典字段类型标注。
from typing import TypedDict  # 导入 TypedDict，用于定义共享状态结构。

from pydantic import BaseModel  # 导入 Pydantic 基类，用于定义工件记录模型。
from pydantic import Field  # 导入字段描述工具，用于补充字段语义。


class WorkflowStatus(str, Enum):  # 定义工作流状态枚举。
    running = "running"  # 表示工作流正在运行。
    suspended = "suspended"  # 表示工作流已挂起等待外部输入。
    completed = "completed"  # 表示工作流全部执行完毕。


class ArtifactRecord(BaseModel):  # 定义工件登记模型。
    bucket: str = Field(description="工件属于哪个目录桶。")  # 保存目录桶名称。
    path: str = Field(description="工件相对工作区的路径是什么。")  # 保存工件路径。
    title: str = Field(description="工件标题是什么。")  # 保存工件标题。
    stage: str = Field(description="工件属于哪个工作流阶段。")  # 保存工作流阶段名。


class WorkflowState(TypedDict, total=False):  # 定义整个科研多 Agent 系统的共享状态结构。
    thread_id: str  # 保存工作流线程 ID。
    topic: str  # 保存研究主题。
    domain: str  # 保存研究领域。
    paper_paths: list[str]  # 保存论文路径列表。
    workflow_status: str  # 保存当前工作流状态。
    current_stage: str  # 保存当前阶段名称。
    active_agent: str | None  # 保存当前活跃角色。
    waiting_for_agent: str | None  # 保存正在等待回复的角色。
    suspend_reason: str | None  # 保存挂起原因。
    submitted_artifact_path: str | None  # 保存最近提交工件路径。
    submitted_artifact_type: str | None  # 保存最近提交工件类型。
    resume_token: str | None  # 保存恢复令牌。
    last_reply_message_id: str | None  # 保存最后一条回复消息 ID。
    conversation_round: int  # 保存总体往返轮次。
    innovation_review_round: int  # 保存创新点审核轮次。
    paper_review_round: int  # 保存论文二审轮次。
    blind_review_round: int  # 保存盲审轮次。
    literature_notes: list[dict[str, Any]]  # 保存结构化论文笔记列表。
    literature_report_path: str | None  # 保存文献调研报告路径。
    innovation_cards: list[dict[str, Any]]  # 保存候选创新点卡片列表。
    approved_innovation: dict[str, Any] | None  # 保存已通过的创新点。
    innovation_report_path: str | None  # 保存创新点候选文档路径。
    experiment_plan_path: str | None  # 保存实验设计方案路径。
    experiment_result_path: str | None  # 保存实验结果路径。
    result_analysis_path: str | None  # 保存结果分析路径。
    manuscript_path: str | None  # 保存当前论文路径。
    advisor_review_path: str | None  # 保存导师审核意见路径。
    reviewer_review_path: str | None  # 保存审稿人意见路径。
    review_decision: str | None  # 保存最近一次审核结论。
    review_comments: list[str]  # 保存最近一次审核意见列表。
    artifacts: list[dict[str, Any]]  # 保存工作流中生成的全部工件。
    messages_log: list[dict[str, Any]]  # 保存角色通信消息日志。
    human_result: dict[str, Any] | None  # 保存人类反馈的实验结果。
    final_summary: str | None  # 保存最终总结内容。

__all__ = ["ArtifactRecord", "WorkflowStatus", "WorkflowState"]  # 暴露工作流状态相关模型，供状态机和内存层引用。
