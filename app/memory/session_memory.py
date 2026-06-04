from __future__ import annotations  # 启用延后类型注解，便于类型提示中引用标准集合类型。

from dataclasses import dataclass  # 导入 dataclass，用于定义轻量会话内存服务。
from typing import Any  # 导入 Any，用于状态字典值的类型标注。


@dataclass(slots=True)  # 使用 dataclass 定义会话记忆存储，并启用 slots 降低属性开销。
class SessionMemoryStore:  # 封装线程级别的轻量会话记忆能力。
    sessions: dict[str, dict[str, Any]]  # 保存 thread_id 到状态字典的映射关系。

    def get(self, thread_id: str) -> dict[str, Any] | None:  # 根据线程 ID 获取最近一次缓存状态。
        return self.sessions.get(thread_id)  # 返回命中的状态字典，如不存在则返回 None。

    def set(self, thread_id: str, state: dict[str, Any]) -> None:  # 保存指定线程的最新状态。
        self.sessions[thread_id] = state  # 直接用线程 ID 覆盖写入状态字典。
