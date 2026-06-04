from __future__ import annotations  # 启用延后类型注解，便于未来扩展返回类型。

from dataclasses import dataclass  # 导入 dataclass，用于定义轻量写入服务对象。
from typing import Any  # 导入 Any，用于元数据字典的类型标注。

from app.schemas.workflow_state import ArtifactRecord  # 导入 app 目录下的工件记录模型，用于返回写入结果。
from app.tools.file_store import ArtifactManager  # 导入工件管理器，用于复用底层文件写入能力。


@dataclass(slots=True)  # 使用 dataclass 定义 Markdown 写入服务，并启用 slots 降低属性开销。
class MarkdownWriter:  # 封装面向 Markdown 文档的写入逻辑，使工具边界更清晰。
    artifact_manager: ArtifactManager  # 保存工件管理器实例，便于把 Markdown 落到工作区目录。

    def write(self, bucket: str, document_name: str, title: str, sections: list[tuple[str, str]], metadata: dict[str, Any] | None = None) -> ArtifactRecord:  # 写入一份 Markdown 文档并返回工件记录。
        return self.artifact_manager.write_markdown(bucket=bucket, document_name=document_name, title=title, sections=sections, metadata=metadata)  # 直接复用底层工件管理器写入能力。
