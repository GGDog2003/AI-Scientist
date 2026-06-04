from __future__ import annotations  # 启用延后类型注解，便于在 dataclass 中引用 Path 等类型。

from dataclasses import dataclass  # 导入 dataclass，用于定义轻量配置对象。
import os  # 导入 os，用于读取环境变量。
from pathlib import Path  # 导入 Path，用于统一处理项目路径。
import sqlite3  # 导入 sqlite3，用于创建 SQLite 持久化连接。
from typing import Any  # 导入 Any，用于描述通用返回类型。

from langgraph.checkpoint.memory import InMemorySaver  # 导入内存检查点实现，用于临时调试模式。
from langgraph.checkpoint.sqlite import SqliteSaver  # 导入 SQLite 检查点实现，用于持久化工作流状态。


@dataclass(slots=True)  # 使用 dataclass 定义应用配置，并启用 slots 降低属性访问开销。
class AppSettings:  # 保存整个项目运行需要的基础配置。
    project_root: Path  # 保存项目根目录路径。
    workspace_root: Path  # 保存工作区根目录路径。
    checkpoint_db: Path  # 保存 LangGraph 检查点数据库路径。
    model_name: str  # 保存模型名称。
    model_provider: str | None  # 保存模型提供商名称。
    model_source: str  # 保存模型配置来自哪个环境变量，便于启动时打印排查信息。
    temperature: float  # 保存模型温度参数。
    use_stub_agent: bool  # 保存是否启用本地 stub 模式。
    has_any_key: bool  # 保存当前环境中是否至少存在一个可用的大模型密钥。

    @classmethod  # 提供从环境变量直接构建配置对象的能力。
    def from_env(cls, project_root: str | Path | None = None) -> "AppSettings":  # 从环境变量和项目路径加载配置。
        resolved_project_root = Path(project_root or Path.cwd()).resolve()  # 解析项目根目录，默认使用当前工作目录。
        workspace_root = resolved_project_root / "workspace1"  # 计算工作区目录路径。
        checkpoint_db = Path(os.getenv("AI_SCIENTIST_CHECKPOINT_DB", workspace_root / "checkpoints.sqlite")).resolve()  # 读取或生成默认检查点数据库路径。

        if os.getenv("AI_SCIENTIST_MODEL"):  # 优先读取项目自身约定的模型配置环境变量。
            raw_model_name = os.getenv("AI_SCIENTIST_MODEL", "openai:gpt-4.1-mini")  # 读取 provider:model 形式的模型配置。
            model_source = "AI_SCIENTIST_MODEL"  # 记录模型配置来源，便于后续输出调试信息。
        elif os.getenv("OPENAI_MODEL_NAME"):  # 兼容用户常见的 OpenAI 风格模型名称变量。
            raw_model_name = f"openai:{os.getenv('OPENAI_MODEL_NAME')}"  # 自动补上 openai provider 前缀，避免继续落回默认模型。
            model_source = "OPENAI_MODEL_NAME"  # 记录模型配置来源，便于用户确认本次已读取到这个变量。
        else:  # 如果没有任何显式模型配置，就继续使用默认模型。
            raw_model_name = "openai:gpt-4.1-mini"  # 默认回退到项目内置的 OpenAI 模型名。
            model_source = "default"  # 记录当前使用的是默认值，而不是用户显式配置。

        if ":" in raw_model_name:  # 判断模型名称是否带有 provider:model 前缀。
            model_provider, model_name = raw_model_name.split(":", 1)  # 拆分提供商和模型名，便于 LangChain 初始化。
        else:  # 如果没有显式提供 provider，则让 LangChain 后续自行推断。
            model_provider, model_name = None, raw_model_name  # 只保留模型名，并把提供商置空。

        explicit_stub = os.getenv("AI_SCIENTIST_USE_STUB")  # 读取是否显式要求启用 stub。
        has_any_key = any(os.getenv(name) for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"))  # 判断常见模型密钥是否存在。
        use_stub_agent = explicit_stub.lower() == "true" if explicit_stub else False  # 只有用户显式要求时才启用 stub，避免默认静默走假流程。

        return cls(  # 返回构造好的配置对象。
            project_root=resolved_project_root,  # 写入项目根目录。
            workspace_root=workspace_root,  # 写入工作区目录。
            checkpoint_db=checkpoint_db,  # 写入检查点数据库路径。
            model_name=model_name,  # 写入模型名称。
            model_provider=model_provider,  # 写入模型提供商名称。
            model_source=model_source,  # 写入模型配置来源。
            temperature=float(os.getenv("AI_SCIENTIST_TEMPERATURE", "0")),  # 写入温度参数，默认更稳定。
            use_stub_agent=use_stub_agent,  # 写入是否启用 stub。
            has_any_key=has_any_key,  # 写入当前是否检测到可用模型密钥。
        )  # 完成配置对象创建。

    def ensure_workspace(self) -> None:  # 确保工作区和核心目录全部存在。
        self.workspace_root.mkdir(parents=True, exist_ok=True)  # 创建工作区根目录。
        for bucket in (  # 遍历全部核心目录名称。
            "papers",  # 论文原文目录。
            "parsed_papers",  # 论文解析结果目录。
            "literature_reports",  # 文献报告目录。
            "innovation_meetings",  # 创新点讨论目录。
            "experiment_plans",  # 实验方案目录。
            "experiment_results",  # 实验结果目录。
            "manuscripts",  # 论文版本目录。
            "reviews",  # 审稿意见目录。
            "logs",  # 日志目录。
        ):  # 结束目录遍历。
            (self.workspace_root / bucket).mkdir(parents=True, exist_ok=True)  # 创建对应目录。
        self.checkpoint_db.parent.mkdir(parents=True, exist_ok=True)  # 创建检查点数据库父目录。

    def build_checkpointer(self) -> Any:  # 构建 LangGraph 需要的检查点对象。
        if str(self.checkpoint_db).lower() == ":memory:":  # 判断是否显式要求使用内存检查点。
            return InMemorySaver()  # 返回内存检查点实现。
        connection = sqlite3.connect(self.checkpoint_db, check_same_thread=False)  # 创建 SQLite 连接，并允许跨线程访问。
        return SqliteSaver(connection)  # 用 SQLite Saver 包装连接后返回。

    def _validate_api_keys(self) -> None:  # 校验当前环境中的模型密钥是否看起来像真实可用的 ASCII 字符串。
        for env_name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):  # 遍历当前支持的常见模型密钥环境变量。
            value = os.getenv(env_name)  # 读取当前环境变量的原始值，便于逐个校验。
            if not value:  # 如果当前变量未设置，就跳过它，继续检查下一个变量。
                continue  # 未设置不是格式错误，只表示当前不使用这个提供商。
            try:  # 开始校验该密钥是否可被安全编码为 ASCII 请求头。
                value.encode("ascii")  # 把密钥编码成 ASCII，若失败通常表示用户填了中文占位文本。
            except UnicodeEncodeError as exc:  # 捕获非 ASCII 密钥错误，并返回更清晰的解释。
                raise RuntimeError(f"{env_name} 包含非 ASCII 字符，当前值看起来不是实际 API Key，而是中文占位文本或非法字符。请替换成平台签发的真实 key。") from exc  # 直接告诉用户问题就在密钥内容本身。
            normalized = value.strip()  # 去掉前后空白，便于识别常见占位词和空值。
            if not normalized:  # 判断去掉空白后是否已经为空。
                raise RuntimeError(f"{env_name} 当前为空字符串，请设置成真实 API Key。")  # 空字符串说明变量虽然存在，但并不能用于实际调用。
            placeholder_tokens = ("your", "token", "key", "apikey", "api_key", "example", "test", "demo", "placeholder")  # 定义常见英文占位词集合，用于识别假值。
            lowered = normalized.lower()  # 统一转成小写，便于无视大小写匹配占位文本。
            if any(token in lowered for token in placeholder_tokens) and not normalized.startswith("sk-"):  # 判断该值是否更像占位文本而不是实际 key。
                raise RuntimeError(f"{env_name} 当前值看起来像占位文本，而不是真实 API Key。请不要直接复制示例文字，改成平台签发的真实 key。")  # 对常见英文占位字符串给出明确提示。

    def validate_runtime(self) -> None:  # 校验当前运行模式是否满足真实大模型执行的前置条件。
        if self.use_stub_agent:  # 判断当前是否显式启用了 stub 模式。
            return  # 如果用户明确要求 stub，就允许继续运行离线调试流程。
        if not self.has_any_key:  # 判断当前环境中是否完全没有任何可用模型密钥。
            raise RuntimeError("当前未检测到大模型 API Key，系统不会再默认静默回退到 stub。请先设置 OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY，或显式设置 AI_SCIENTIST_USE_STUB=true。")  # 没有密钥且未显式启用 stub 时，直接报错提醒用户配置环境。
        self._validate_api_keys()  # 在确认存在密钥后，继续校验密钥内容是否合法，避免把中文占位文本发到底层 HTTP 客户端。

    def runtime_mode_label(self) -> str:  # 返回当前运行模式的文本标签，便于命令行打印。
        if self.use_stub_agent:  # 判断当前是否显式启用了 stub。
            return "stub"  # 返回 stub 标签，表示只跑本地假数据流程。
        return f"llm({self.model_provider + ':' if self.model_provider else ''}{self.model_name})"  # 返回真实模型标签，表示将调用外部大模型。


def build_thread_config(thread_id: str) -> dict[str, dict[str, str]]:  # 构建 LangGraph 标准线程配置结构。
    return {"configurable": {"thread_id": thread_id}}  # 返回标准 configurable 配置字典。
