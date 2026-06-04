from __future__ import annotations  # 启用延后类型注解，便于在类型提示中引用 Pydantic 模型。

from dataclasses import dataclass  # 导入 dataclass，用于定义工件索引服务。

from app.schemas.workflow_state import ArtifactRecord  # 导入 app 目录下的工件记录模型，便于构建结构化索引。


@dataclass(slots=True)  # 使用 dataclass 定义工件索引器，并启用 slots 优化属性存储。
class ArtifactIndex:  # 保存项目运行中产出的结构化工件列表，便于按阶段和目录检索。
    artifacts: list[ArtifactRecord]  # 保存全部工件记录对象列表。

    def add(self, artifact: ArtifactRecord) -> None:  # 向索引中追加一条工件记录。
        self.artifacts.append(artifact)  # 把新工件对象追加到列表末尾。

    def by_bucket(self, bucket: str) -> list[ArtifactRecord]:  # 根据目录桶筛选工件记录。
        return [artifact for artifact in self.artifacts if artifact.bucket == bucket]  # 返回属于目标目录桶的全部工件。

    def by_stage(self, stage: str) -> list[ArtifactRecord]:  # 根据工作流阶段筛选工件记录。
        return [artifact for artifact in self.artifacts if artifact.stage == stage]  # 返回属于目标阶段的全部工件。
