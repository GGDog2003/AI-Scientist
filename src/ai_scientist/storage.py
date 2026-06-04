from __future__ import annotations  # 启用延后类型注解，便于在类方法中引用自身类型。

from dataclasses import dataclass  # 导入 dataclass，用于组织轻量存储服务。
from datetime import datetime  # 导入 datetime，用于生成日期版本号。
import json  # 导入 json，用于读写结构化工件。
from pathlib import Path  # 导入 Path，用于处理文件路径。
from typing import Any  # 导入 Any，用于通用序列化数据类型。
from uuid import uuid4  # 导入 uuid4，用于生成消息唯一标识。

from ai_scientist.schemas import AgentMessage  # 导入消息模型，便于统一构造 Agent 通信对象。
from ai_scientist.schemas import ArtifactRecord  # 导入工件模型，便于登记已生成文档。


@dataclass(slots=True)  # 定义工件管理器，并启用 slots 以减少运行时开销。
class ArtifactManager:  # 负责所有 markdown、json、日志等工件的持久化。
    workspace_root: Path  # 保存工作区根目录路径。

    def ensure_workspace(self) -> None:  # 确保工作区下的所有核心目录已经存在。
        self.workspace_root.mkdir(parents=True, exist_ok=True)  # 创建工作区根目录。
        for bucket in (  # 遍历所有约定目录。
            "papers",  # 论文目录。
            "parsed_papers",  # 解析结果目录。
            "literature_reports",  # 文献报告目录。
            "innovation_meetings",  # 创新点目录。
            "experiment_plans",  # 实验方案目录。
            "experiment_results",  # 实验结果目录。
            "manuscripts",  # 论文目录。
            "reviews",  # 审稿目录。
            "logs",  # 日志目录。
        ):  # 结束目录遍历。
            (self.workspace_root / bucket).mkdir(parents=True, exist_ok=True)  # 创建具体目录。

    def resolve(self, relative_path: str) -> Path:  # 把相对路径解析成工作区绝对路径。
        return (self.workspace_root / relative_path).resolve()  # 返回规范化绝对路径。

    def _next_versioned_name(self, bucket: str, document_name: str, suffix: str) -> str:  # 为指定目录和文档类型生成日期+版本文件名。
        date_prefix = datetime.now().strftime("%Y%m%d")  # 计算当天日期字符串。
        bucket_path = self.workspace_root / bucket  # 计算目录绝对路径。
        existing = sorted(bucket_path.glob(f"{date_prefix}_v*_{document_name}{suffix}"))  # 找出当天同名文档的历史版本。
        version = len(existing) + 1  # 根据已存在数量推导下一个版本号。
        return f"{date_prefix}_v{version}_{document_name}{suffix}"  # 返回完整文件名。

    def write_markdown(self, bucket: str, document_name: str, title: str, sections: list[tuple[str, str]], metadata: dict[str, Any] | None = None) -> ArtifactRecord:  # 生成并保存 Markdown 工件。
        filename = self._next_versioned_name(bucket, document_name, ".md")  # 生成版本化 Markdown 文件名。
        path = self.workspace_root / bucket / filename  # 计算目标输出路径。
        lines: list[str] = []  # 初始化 Markdown 行列表。
        if metadata:  # 判断是否需要写入 YAML 头。
            lines.append("---")  # 写入 YAML 起始分隔符。
            for key, value in metadata.items():  # 遍历元数据字典。
                if isinstance(value, list):  # 判断当前元数据是否是列表。
                    lines.append(f"{key}:")  # 先写入列表字段名。
                    for item in value:  # 遍历列表中的每个元素。
                        lines.append(f"  - {item}")  # 按 YAML 列表格式写入元素。
                else:  # 如果元数据不是列表，就直接写标量值。
                    lines.append(f"{key}: {value}")  # 写入简单键值对。
            lines.append("---")  # 写入 YAML 结束分隔符。
            lines.append("")  # 补一个空行，增强 Markdown 可读性。
        lines.append(f"# {title}")  # 写入文档主标题。
        lines.append("")  # 写入空行，分隔正文内容。
        for heading, body in sections:  # 遍历所有正文章节。
            lines.append(f"## {heading}")  # 写入二级标题。
            lines.append("")  # 写入空行，提升可读性。
            lines.append(body.strip())  # 写入章节主体内容。
            lines.append("")  # 在章节后补空行。
        path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")  # 将完整 Markdown 内容落盘到文件。
        return ArtifactRecord(bucket=bucket, path=str(path.relative_to(self.workspace_root)), title=title, stage=metadata.get("stage", "") if metadata else "")  # 返回工件登记对象。

    def write_json(self, bucket: str, document_name: str, payload: Any) -> ArtifactRecord:  # 生成并保存 JSON 工件。
        filename = self._next_versioned_name(bucket, document_name, ".json")  # 生成版本化 JSON 文件名。
        path = self.workspace_root / bucket / filename  # 计算 JSON 输出路径。
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")  # 把 JSON 数据美化后写入文件。
        return ArtifactRecord(bucket=bucket, path=str(path.relative_to(self.workspace_root)), title=document_name, stage="")  # 返回工件登记对象。

    def read_text(self, relative_or_absolute_path: str) -> str:  # 读取任意文本文件内容。
        path = Path(relative_or_absolute_path)  # 把输入路径转成 Path 对象。
        resolved = path if path.is_absolute() else self.workspace_root / path  # 根据是否绝对路径决定最终读取地址。
        return resolved.read_text(encoding="utf-8")  # 用 UTF-8 编码返回文本内容。

    def read_json(self, relative_or_absolute_path: str) -> Any:  # 读取任意 JSON 文件内容。
        return json.loads(self.read_text(relative_or_absolute_path))  # 先读文本，再反序列化为 Python 对象。

    def append_log(self, filename: str, payload: dict[str, Any]) -> Path:  # 向日志目录追加一条 JSONL 日志。
        path = self.workspace_root / "logs" / filename  # 计算日志文件路径。
        with path.open("a", encoding="utf-8") as file_handle:  # 以追加模式打开日志文件。
            file_handle.write(json.dumps(payload, ensure_ascii=False) + "\n")  # 把单条日志写成一行 JSON。
        return path  # 返回最终日志路径，便于上层追踪。


@dataclass(slots=True)  # 定义消息总线类，并启用 slots 以减少属性存储开销。
class MessageBus:  # 负责构造 Agent 间的 submission 和 reply 消息。
    artifact_manager: ArtifactManager  # 保存工件管理器，便于消息落日志时复用。

    def submission(self, from_agent: str, to_agent: str, stage: str, artifact_type: str, artifact_path: str, summary: str, resume_token: str | None = None) -> AgentMessage:  # 构造提交消息。
        token = resume_token or f"resume_{uuid4().hex}"  # 如果外部未传恢复标识，就自动生成一个。
        message = AgentMessage(  # 组装标准的提交消息对象。
            message_id=f"msg_{uuid4().hex}",  # 生成消息唯一 ID。
            from_agent=from_agent,  # 写入发送方角色。
            to_agent=to_agent,  # 写入接收方角色。
            stage=stage,  # 写入当前阶段名。
            artifact_type=artifact_type,  # 写入工件类型。
            artifact_path=artifact_path,  # 写入工件路径。
            summary=summary,  # 写入消息摘要。
            metadata={"requires_reply": True, "suspend_current_agent": True, "resume_token": token},  # 写入挂起与恢复相关元数据。
        )  # 结束消息对象组装。
        self.artifact_manager.append_log("messages.jsonl", message.model_dump())  # 把提交消息写入消息日志。
        return message  # 返回构造好的消息对象。

    def reply(self, source_message: AgentMessage, from_agent: str, decision: str, comments_path: str, summary: str) -> AgentMessage:  # 构造回复消息。
        message = AgentMessage(  # 组装标准的回复消息对象。
            message_id=f"msg_{uuid4().hex}",  # 生成新的消息唯一 ID。
            from_agent=from_agent,  # 写入发送回复的角色。
            to_agent=source_message.from_agent,  # 把回复发回原始发送方。
            stage=f"{source_message.stage}_reply",  # 把阶段名标记成回复阶段。
            artifact_type="review_reply",  # 固定标识为审核回复。
            artifact_path=comments_path,  # 写入审核意见文档路径。
            summary=summary,  # 写入回复摘要。
            metadata={"reply_to": source_message.message_id, "decision": decision, "resume_token": source_message.metadata.get("resume_token")},  # 写入关联消息和恢复标识。
        )  # 结束回复消息对象组装。
        self.artifact_manager.append_log("messages.jsonl", message.model_dump())  # 把回复消息写入消息日志。
        return message  # 返回构造好的回复消息对象。
