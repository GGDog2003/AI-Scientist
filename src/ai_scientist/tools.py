from __future__ import annotations  # 启用延后类型注解，便于闭包函数引用外部类型。

from pathlib import Path  # 导入 Path，用于路径解析和遍历。

from langchain.tools import tool  # 导入 LangChain tool 装饰器，用于把函数包装成 Agent 工具。
from pypdf import PdfReader  # 导入 PdfReader，用于解析论文 PDF 文本。

from ai_scientist.storage import ArtifactManager  # 导入工件管理器，便于工具读写工作区文件。


def build_tools(artifact_manager: ArtifactManager) -> list:  # 根据当前工作区构建一组可供 Agent 调用的工具。
    @tool  # 把读取工件函数注册成 LangChain 工具。
    def read_artifact(path: str) -> str:  # 定义读取文本工件的工具函数。
        """读取工作区中的文本工件内容。"""  # 描述工具用途，帮助模型理解调用场景。
        return artifact_manager.read_text(path)  # 使用工件管理器返回目标文件内容。

    @tool  # 把列目录函数注册成 LangChain 工具。
    def list_bucket_files(bucket: str) -> str:  # 定义列出目录内容的工具函数。
        """列出工作区某个目录桶下的全部文件。"""  # 描述工具用途，便于模型检索上下文。
        bucket_path = artifact_manager.workspace_root / bucket  # 计算目标目录绝对路径。
        if not bucket_path.exists():  # 判断目标目录是否存在。
            return f"bucket not found: {bucket}"  # 返回目录不存在提示。
        return "\n".join(str(path.relative_to(artifact_manager.workspace_root)) for path in sorted(bucket_path.rglob("*")) if path.is_file())  # 返回目录下所有文件的相对路径列表。

    @tool  # 把 PDF 解析函数注册成 LangChain 工具。
    def parse_pdf_file(path: str) -> str:  # 定义解析 PDF 文本的工具函数。
        """读取并抽取 PDF 论文文本。"""  # 描述工具用途，帮助模型在读论文时主动调用。
        candidate = Path(path)  # 把输入路径转换成 Path 对象。
        resolved = candidate if candidate.is_absolute() else artifact_manager.workspace_root / candidate  # 根据路径是否绝对来决定最终文件位置。
        reader = PdfReader(str(resolved))  # 打开 PDF 文件并创建读取器。
        chunks: list[str] = []  # 初始化文本片段列表，用于收集所有页的内容。
        for page_index, page in enumerate(reader.pages, start=1):  # 遍历 PDF 的每一页，并保留页码。
            text = page.extract_text() or ""  # 抽取当前页文本，如为空则回退为空串。
            chunks.append(f"[page {page_index}]\n{text}")  # 把页码和正文一起加入结果列表。
        return "\n\n".join(chunks).strip()  # 返回合并后的整篇论文文本。

    @tool  # 把文本搜索函数注册成 LangChain 工具。
    def search_workspace(query: str, bucket: str = "workspace1") -> str:  # 定义在工作区里全文搜索的工具函数。
        """在工作区文本文件中搜索关键词。"""  # 描述工具用途，帮助模型回查已有文档。
        root = artifact_manager.workspace_root if bucket == "workspace1" else artifact_manager.workspace_root / bucket  # 计算需要搜索的根目录。
        matches: list[str] = []  # 初始化命中结果列表。
        for path in sorted(root.rglob("*")):  # 遍历根目录下的全部文件和子目录。
            if not path.is_file():  # 跳过目录，只处理文件。
                continue  # 继续处理下一个路径。
            if path.suffix.lower() not in {".md", ".txt", ".json"}:  # 仅搜索常见文本类型文件。
                continue  # 跳过非目标后缀文件。
            text = path.read_text(encoding="utf-8", errors="ignore")  # 读取文件内容，并在编码异常时忽略坏字符。
            if query.lower() in text.lower():  # 判断文件内容是否包含目标关键词。
                matches.append(str(path.relative_to(artifact_manager.workspace_root)))  # 记录命中文件的相对路径。
        return "\n".join(matches) if matches else "no matches"  # 返回命中列表，如果没有就返回 no matches。

    return [read_artifact, list_bucket_files, parse_pdf_file, search_workspace]  # 返回当前工作区对应的全部工具集合。
