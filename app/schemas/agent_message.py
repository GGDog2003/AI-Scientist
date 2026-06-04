from pydantic import BaseModel  # 导入 Pydantic 基类，用于定义结构化消息模型。
from pydantic import Field  # 导入字段描述工具，用于给消息字段补充语义说明。


class AgentMessage(BaseModel):  # 定义 Agent 间传递的结构化消息模型。
    message_id: str = Field(description="消息唯一标识是什么。")  # 保存消息唯一 ID。
    from_agent: str = Field(description="消息由哪个角色发送。")  # 保存发送方角色。
    to_agent: str = Field(description="消息要发给哪个角色。")  # 保存接收方角色。
    stage: str = Field(description="消息处于哪个工作流阶段。")  # 保存工作流阶段名。
    artifact_type: str = Field(description="提交的工件类型是什么。")  # 保存工件类型。
    artifact_path: str = Field(description="提交工件的相对路径是什么。")  # 保存工件路径。
    summary: str = Field(description="消息摘要是什么。")  # 保存消息摘要。
    metadata: dict[str, object] = Field(default_factory=dict, description="附加元数据有哪些。")  # 保存挂起、恢复等附加信息。


__all__ = ["AgentMessage"]  # 暴露 AgentMessage 名称，供消息总线与工作流层引用。
