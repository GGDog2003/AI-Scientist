from __future__ import annotations  # 启用延后类型注解，便于后续扩展返回类型。

from dataclasses import dataclass  # 导入 dataclass，用于定义轻量代码脚手架生成器。
from typing import Any  # 导入 Any，用于实验方案字典类型标注。

from app.schemas.workflow_state import ArtifactRecord  # 导入 app 目录下的工件记录模型，用于返回生成结果。
from app.tools.file_store import ArtifactManager  # 导入工件管理器，用于把代码脚手架写入工作区。


@dataclass(slots=True)  # 使用 dataclass 定义代码脚手架生成器，并启用 slots 降低属性存储开销。
class CodeScaffoldGenerator:  # 封装根据实验方案生成 Python 代码框架的能力。
    artifact_manager: ArtifactManager  # 保存工件管理器实例，便于生成文件时统一落盘。

    def generate(self, document_name: str, experiment_plan: dict[str, Any]) -> ArtifactRecord:  # 根据实验方案生成简单代码框架说明文档。
        sections = [  # 组织代码脚手架说明文档的章节内容。
            ("目标", f"根据实验目标生成代码框架：{experiment_plan.get('objective', '未提供目标')}"),  # 写入代码框架目标说明。
            ("推荐模块", "\n".join(f"- {item}" for item in experiment_plan.get("python_modules", [])) or "- train.py"),  # 写入建议生成的 Python 模块列表。
            ("实现步骤", "\n".join(f"{index}. {item}" for index, item in enumerate(experiment_plan.get("execution_steps", []), start=1)) or "1. 根据实验方案补充训练与评估代码。"),  # 写入实现步骤。
        ]  # 结束章节列表定义。
        return self.artifact_manager.write_markdown(bucket="experiment_plans", document_name=document_name, title="Python代码框架说明", sections=sections, metadata={"stage": "code_scaffold"})  # 通过工件管理器写出代码框架说明文档。
