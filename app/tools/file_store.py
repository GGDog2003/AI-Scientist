from __future__ import annotations  # 启用延后类型注解，便于方法签名中引用 Path 和 ArtifactRecord。

from dataclasses import dataclass  # 导入 dataclass，用于定义轻量工件管理器。
from datetime import datetime  # 导入 datetime，用于生成日期版本号。
import json  # 导入 json，用于写入结构化工件和日志。
from pathlib import Path  # 导入 Path，用于统一处理文件路径。
from typing import Any  # 导入 Any，用于通用负载类型标注。

from app.schemas.workflow_state import ArtifactRecord  # 导入工件记录模型，用于返回结构化写入结果。


@dataclass(slots=True)  # 使用 dataclass 定义工件管理器，并启用 slots 降低属性开销。
class ArtifactManager:  # 负责 Markdown、JSON、日志等工件的持久化。
    workspace_root: Path  # 保存工作区根目录路径。

    def ensure_workspace(self) -> None:  # 确保工作区下的全部核心目录已经存在。
        self.workspace_root.mkdir(parents=True, exist_ok=True)  # 创建工作区根目录。
        for bucket in (  # 遍历需要的全部目录桶名称。
            "papers",  # 论文原文目录。
            "parsed_papers",  # 论文解析目录。
            "literature_reports",  # 文献报告目录。
            "innovation_meetings",  # 创新点讨论目录。
            "experiment_plans",  # 实验方案目录。
            "experiment_results",  # 实验结果目录。
            "manuscripts",  # 论文目录。
            "reviews",  # 审稿目录。
            "logs",  # 日志目录。
        ):  # 结束目录遍历。
            (self.workspace_root / bucket).mkdir(parents=True, exist_ok=True)  # 创建对应的目录。

    def resolve(self, relative_path: str) -> Path:  # 把工作区相对路径解析成绝对路径。
        return (self.workspace_root / relative_path).resolve()  # 返回规范化的绝对路径对象。

    def _next_versioned_name(self, bucket: str, document_name: str, suffix: str) -> str:  # 生成日期_版本_文档名格式的文件名。
        date_prefix = datetime.now().strftime("%Y%m%d")  # 计算当天日期前缀。
        bucket_path = self.workspace_root / bucket  # 计算目录桶的绝对路径。
        existing = sorted(bucket_path.glob(f"{date_prefix}_v*_{document_name}{suffix}"))  # 找出当天同名文档的历史版本。
        version = len(existing) + 1  # 以历史数量推导下一个版本号。
        return f"{date_prefix}_v{version}_{document_name}{suffix}"  # 返回完整的版本化文件名。

    def write_markdown(self, bucket: str, document_name: str, title: str, sections: list[tuple[str, str]], metadata: dict[str, Any] | None = None) -> ArtifactRecord:  # 写入 Markdown 工件并返回结构化记录。
        filename = self._next_versioned_name(bucket, document_name, ".md")  # 生成版本化 Markdown 文件名。
        path = self.workspace_root / bucket / filename  # 计算 Markdown 输出路径。
        lines: list[str] = []  # 初始化 Markdown 行列表。
        if metadata:  # 判断是否需要写入 YAML 头部元数据。
            lines.append("---")  # 写入 YAML 起始分隔符。
            for key, value in metadata.items():  # 遍历元数据字典。
                if isinstance(value, list):  # 判断是否是列表字段。
                    lines.append(f"{key}:")  # 先写入列表字段名。
                    for item in value:  # 遍历列表中的每个元素。
                        lines.append(f"  - {item}")  # 以 YAML 列表格式写入元素。
                else:  # 如果不是列表字段，则按标量写入。
                    lines.append(f"{key}: {value}")  # 写入简单键值对。
            lines.append("---")  # 写入 YAML 结束分隔符。
            lines.append("")  # 写入空行，增强 Markdown 可读性。
        lines.append(f"# {title}")  # 写入主标题。
        lines.append("")  # 写入空行，分隔正文内容。
        for heading, body in sections:  # 遍历全部正文分节。
            lines.append(f"## {heading}")  # 写入二级标题。
            lines.append("")  # 写入空行，提升可读性。
            lines.append(body.strip())  # 写入章节正文。
            lines.append("")  # 在章节尾部补空行。
        path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")  # 将完整 Markdown 内容落盘到文件。
        return ArtifactRecord(bucket=bucket, path=str(path.relative_to(self.workspace_root)), title=title, stage=metadata.get("stage", "") if metadata else "")  # 返回结构化工件记录。

    def write_json(self, bucket: str, document_name: str, payload: Any) -> ArtifactRecord:  # 写入 JSON 工件并返回结构化记录。
        filename = self._next_versioned_name(bucket, document_name, ".json")  # 生成版本化 JSON 文件名。
        path = self.workspace_root / bucket / filename  # 计算 JSON 输出路径。
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")  # 将 JSON 负载美化后写入文件。
        return ArtifactRecord(bucket=bucket, path=str(path.relative_to(self.workspace_root)), title=document_name, stage="")  # 返回结构化工件记录。

    def read_text(self, relative_or_absolute_path: str) -> str:  # 读取任意文本工件内容。
        path = Path(relative_or_absolute_path)  # 把输入路径转成 Path 对象。
        resolved = path if path.is_absolute() else self.workspace_root / path  # 根据绝对路径或相对路径决定最终读取地址。
        return resolved.read_text(encoding="utf-8")  # 以 UTF-8 返回文本内容。

    def read_json(self, relative_or_absolute_path: str) -> Any:  # 读取任意 JSON 工件内容。
        return json.loads(self.read_text(relative_or_absolute_path))  # 先读取文本，再反序列化成 Python 对象。

    def append_log(self, filename: str, payload: dict[str, Any]) -> Path:  # 向日志目录追加一条 JSONL 日志。
        path = self.workspace_root / "logs" / filename  # 计算日志文件路径。
        with path.open("a", encoding="utf-8") as file_handle:  # 以追加模式打开日志文件。
            file_handle.write(json.dumps(payload, ensure_ascii=False) + "\n")  # 把单条日志写成一行 JSON。
        return path  # 返回最终日志文件路径。


__all__ = ["ArtifactManager"]  # 显式声明对外暴露的类型，方便其他模块引用。
