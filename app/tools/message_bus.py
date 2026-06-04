from __future__ import annotations  # 启用延后类型注解，便于在方法签名中引用本地类型。

from dataclasses import dataclass  # 导入 dataclass，用于定义轻量消息总线。
from uuid import uuid4  # 导入 uuid4，用于生成消息 ID 和恢复标识。

from app.schemas.agent_message import AgentMessage  # 导入 Agent 消息模型，用于统一提交与回复协议。
from app.tools.file_store import ArtifactManager  # 导入工件管理器，用于把消息写入日志。


@dataclass(slots=True)  # 使用 dataclass 定义消息总线，并启用 slots 降低属性开销。
class MessageBus:  # 负责构造 submission 和 reply 两类结构化消息。
    artifact_manager: ArtifactManager  # 保存工件管理器，用于复用日志写入能力。

    def submission(self, from_agent: str, to_agent: str, stage: str, artifact_type: str, artifact_path: str, summary: str, resume_token: str | None = None) -> AgentMessage:  # 构造提交通知消息。
        token = resume_token or f"resume_{uuid4().hex}"  # 如果外部未提供恢复标识，则自动生成一个。
        message = AgentMessage(  # 组装标准提交消息对象。
            message_id=f"msg_{uuid4().hex}",  # 生成消息唯一 ID。
            from_agent=from_agent,  # 写入发送方角色。
            to_agent=to_agent,  # 写入接收方角色。
            stage=stage,  # 写入工作流阶段名。
            artifact_type=artifact_type,  # 写入提交工件类型。
            artifact_path=artifact_path,  # 写入提交工件路径。
            summary=summary,  # 写入消息摘要。
            metadata={"requires_reply": True, "suspend_current_agent": True, "resume_token": token},  # 写入挂起与恢复相关元数据。
        )  # 完成提交消息对象组装。
        self.artifact_manager.append_log("messages.jsonl", message.model_dump())  # 把消息写入日志。
        return message  # 返回构造好的消息对象。

    def reply(self, source_message: AgentMessage, from_agent: str, decision: str, comments_path: str, summary: str) -> AgentMessage:  # 构造回复消息。
        message = AgentMessage(  # 组装标准回复消息对象。
            message_id=f"msg_{uuid4().hex}",  # 生成新的消息唯一 ID。
            from_agent=from_agent,  # 写入发送回复的角色。
            to_agent=source_message.from_agent,  # 回复发回原始发送方。
            stage=f"{source_message.stage}_reply",  # 标记成对应阶段的回复消息。
            artifact_type="review_reply",  # 固定标识为审核回复。
            artifact_path=comments_path,  # 写入审核意见文档路径。
            summary=summary,  # 写入回复摘要。
            metadata={"reply_to": source_message.message_id, "decision": decision, "resume_token": source_message.metadata.get("resume_token")},  # 写入关联消息和恢复令牌。
        )  # 完成回复消息对象组装。
        self.artifact_manager.append_log("messages.jsonl", message.model_dump())  # 把回复消息写入日志。
        return message  # 返回构造好的回复消息对象。


__all__ = ["MessageBus"]  # 显式声明对外暴露的类型，方便工作流层统一引用。
