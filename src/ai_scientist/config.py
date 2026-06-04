from __future__ import annotations  # 启用延后类型注解，减少前向引用限制。

from dataclasses import dataclass  # 导入 dataclass，便于定义轻量配置对象。
import os  # 导入 os，用于读取环境变量。
from pathlib import Path  # 导入 Path，用于做路径拼接和解析。
import sqlite3  # 导入 sqlite3，用于创建 SQLite 连接。
from typing import Any  # 导入 Any，用于配置字典类型标注。

from langgraph.checkpoint.memory import InMemorySaver  # 导入内存检查点，便于调试模式使用。
from langgraph.checkpoint.sqlite import SqliteSaver  # 导入 SQLite 检查点，便于持久化工作流。


@dataclass(slots=True)  # 使用 dataclass 定义配置对象，并启用 slots 降低属性开销。
class AppSettings:  # 定义整个项目运行所需的核心配置。
    project_root: Path  # 保存项目根目录路径，便于统一定位文件。
    workspace_root: Path  # 保存工作区目录路径，便于生成科研工件。
    checkpoint_db: Path  # 保存检查点数据库路径，便于 LangGraph 持久化。
    model_name: str  # 保存模型名称，便于初始化 LangChain 模型。
    model_provider: str | None  # 保存模型提供商名称，便于兼容多家模型接口。
    temperature: float  # 保存模型温度参数，控制生成随机性。
    use_stub_agent: bool  # 保存是否启用本地桩代理，便于离线调试。

    @classmethod  # 声明类方法，便于直接从环境变量创建配置对象。
    def from_env(cls, project_root: str | Path | None = None) -> "AppSettings":  # 从环境变量中加载配置。
        resolved_project_root = Path(project_root or Path.cwd()).resolve()  # 解析项目根目录，默认取当前工作目录。
        workspace_root = resolved_project_root / "workspace1"  # 计算工作区目录路径，统一放置运行产物。
        checkpoint_db = Path(os.getenv("AI_SCIENTIST_CHECKPOINT_DB", workspace_root / "checkpoints.sqlite")).resolve()  # 读取检查点数据库路径，默认放到 workspace1 下。
        raw_model_name = os.getenv("AI_SCIENTIST_MODEL", "openai:gpt-4.1-mini")  # 读取模型名称，默认使用 OpenAI 兼容格式。
        if ":" in raw_model_name:  # 判断模型名称是否带有 provider:model 前缀格式。
            model_provider, model_name = raw_model_name.split(":", 1)  # 拆分提供商和模型名，便于后续初始化。
        else:  # 如果没有显式前缀，则保持提供商为空。
            model_provider, model_name = None, raw_model_name  # 记录仅模型名的情况，兼容 LangChain 默认推断。
        explicit_stub = os.getenv("AI_SCIENTIST_USE_STUB")  # 读取是否显式启用 stub 模式。
        has_any_key = any(os.getenv(name) for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"))  # 判断是否存在常见模型密钥。
        use_stub_agent = explicit_stub.lower() == "true" if explicit_stub else not has_any_key  # 优先使用显式配置，否则在无密钥时启用 stub。
        return cls(  # 返回组装好的配置对象。
            project_root=resolved_project_root,  # 写入项目根目录。
            workspace_root=workspace_root,  # 写入工作区目录。
            checkpoint_db=checkpoint_db,  # 写入检查点数据库路径。
            model_name=model_name,  # 写入模型名。
            model_provider=model_provider,  # 写入模型提供商。
            temperature=float(os.getenv("AI_SCIENTIST_TEMPERATURE", "0")),  # 写入温度参数，默认更稳定。
            use_stub_agent=use_stub_agent,  # 写入是否启用 stub。
        )  # 结束配置对象创建。

    def ensure_workspace(self) -> None:  # 确保所有核心目录存在，避免后续写文件失败。
        self.workspace_root.mkdir(parents=True, exist_ok=True)  # 创建工作区目录，支持多层级递归创建。
        for bucket in (  # 遍历所有需要的工件目录名称。
            "papers",  # 论文原文目录。
            "parsed_papers",  # 论文解析结果目录。
            "literature_reports",  # 文献调研报告目录。
            "innovation_meetings",  # 创新点讨论与组会目录。
            "experiment_plans",  # 实验设计方案目录。
            "experiment_results",  # 实验结果目录。
            "manuscripts",  # 论文版本目录。
            "reviews",  # 审稿意见目录。
            "logs",  # 运行日志目录。
        ):  # 结束目录名称遍历。
            (self.workspace_root / bucket).mkdir(parents=True, exist_ok=True)  # 创建对应工件目录，保证可写。
        self.checkpoint_db.parent.mkdir(parents=True, exist_ok=True)  # 创建检查点数据库父目录，避免 SQLite 打开失败。

    def build_checkpointer(self) -> Any:  # 构建 LangGraph 所需的检查点对象。
        if str(self.checkpoint_db).lower() == ":memory:":  # 判断是否显式要求使用纯内存检查点。
            return InMemorySaver()  # 返回内存检查点，适合临时测试。
        connection = sqlite3.connect(self.checkpoint_db, check_same_thread=False)  # 创建 SQLite 连接，并允许跨线程访问。
        return SqliteSaver(connection)  # 使用 SQLite Saver 包装连接，供 LangGraph 持久化使用。


def build_thread_config(thread_id: str) -> dict[str, dict[str, str]]:  # 构建 LangGraph 线程配置，便于持久化恢复。
    return {"configurable": {"thread_id": thread_id}}  # 返回标准的 configurable 结构。
