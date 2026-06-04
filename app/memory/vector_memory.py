from __future__ import annotations  # 启用延后类型注解，便于类型提示中引用本地类。

from dataclasses import dataclass  # 导入 dataclass，用于定义简易向量记忆服务。


@dataclass(slots=True)  # 使用 dataclass 定义简化版向量记忆，并启用 slots 降低开销。
class SimpleVectorMemory:  # 提供一个不依赖真实向量数据库的最小可用占位实现。
    documents: list[tuple[str, str]]  # 保存文档 ID 与文本内容的二元组列表。

    def add(self, document_id: str, text: str) -> None:  # 把一份文本加入内存索引。
        self.documents.append((document_id, text))  # 直接把文档标识和文本追加到列表中。

    def search(self, query: str, top_k: int = 5) -> list[str]:  # 使用最简单的关键词包含逻辑模拟检索接口。
        lowered = query.lower()  # 把查询词转换成小写，便于做大小写无关匹配。
        matches = [document_id for document_id, text in self.documents if lowered in text.lower()]  # 收集包含查询词的文档 ID。
        return matches[:top_k]  # 返回前 top_k 个命中文档 ID。
