from __future__ import annotations  # 启用延后类型注解，便于函数签名中引用 ArtifactManager。

from pathlib import Path  # 导入 Path，用于统一处理文件路径。

from langchain.tools import tool  # 导入 LangChain tool 装饰器，用于把函数包装成 Agent 工具。

from app.tools.code_generator import CodeScaffoldGenerator  # 导出代码脚手架生成器。
from app.tools.file_store import ArtifactManager  # 导出文件存储与工件管理器。
from app.tools.markdown_writer import MarkdownWriter  # 导出 Markdown 写入器。
from app.tools.message_bus import MessageBus  # 导出消息总线。
from app.tools.paper_search import search_workspace_files  # 导出工作区论文搜索函数。
from app.tools.pdf_parser import parse_pdf_text  # 导出 PDF 解析函数。


def build_tools(artifact_manager: ArtifactManager) -> list:  # 根据当前工作区构建可供 Agent 使用的 LangChain 工具列表。
    @tool  # 把读取工件函数注册成 LangChain 工具。
    def read_artifact(path: str) -> str:  # 定义读取文本工件内容的工具函数。
        """读取工作区中的文本工件内容。"""  # 描述工具用途，便于模型理解调用场景。
        return artifact_manager.read_text(path)  # 使用工件管理器返回目标文件内容。

    @tool  # 把列目录函数注册成 LangChain 工具。
    def list_bucket_files(bucket: str) -> str:  # 定义列出目录内容的工具函数。
        """列出工作区某个目录桶下的全部文件。"""  # 描述工具用途，便于模型快速定位上下文。
        bucket_path = artifact_manager.workspace_root / bucket  # 计算目标目录路径。
        if not bucket_path.exists():  # 判断目录是否存在。
            return f"bucket not found: {bucket}"  # 返回目录不存在提示。
        return "\n".join(str(path.relative_to(artifact_manager.workspace_root)) for path in sorted(bucket_path.rglob("*")) if path.is_file())  # 返回目录下全部文件相对路径。

    @tool  # 把 PDF 解析函数注册成 LangChain 工具。
    def parse_pdf_file(path: str) -> str:  # 定义解析 PDF 文件文本的工具函数。
        """读取并抽取 PDF 论文文本。"""  # 描述工具用途，帮助研究生 Agent 读论文。
        candidate = Path(path)  # 把输入路径转成 Path 对象。
        resolved = candidate if candidate.is_absolute() else artifact_manager.workspace_root / candidate  # 根据路径是否绝对决定最终读取地址。
        return parse_pdf_text(resolved)  # 调用 PDF 解析函数返回整篇文本。

    @tool  # 把工作区搜索函数注册成 LangChain 工具。
    def search_workspace(query: str, bucket: str = "workspace1") -> str:  # 定义在工作区内全文粗搜的工具函数。
        """在工作区文本文件中搜索关键词。"""  # 描述工具用途，帮助 Agent 回查已有工件。
        root = artifact_manager.workspace_root if bucket == "workspace1" else artifact_manager.workspace_root / bucket  # 计算需要搜索的根目录。
        matches = search_workspace_files(root=root, query=query, suffixes=(".md", ".txt", ".json"))  # 调用工作区搜索函数执行检索。
        return "\n".join(matches) if matches else "no matches"  # 返回命中文件列表，如无命中则返回 no matches。

    return [read_artifact, list_bucket_files, parse_pdf_file, search_workspace]  # 返回完整工具集合。


__all__ = ["ArtifactManager", "MessageBus", "MarkdownWriter", "CodeScaffoldGenerator", "parse_pdf_text", "search_workspace_files", "build_tools"]  # 显式声明对外导出接口。
