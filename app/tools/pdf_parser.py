from __future__ import annotations  # 启用延后类型注解，便于以后扩展返回类型。

from pathlib import Path  # 导入 Path，用于处理 PDF 路径。

from pypdf import PdfReader  # 导入 PdfReader，用于解析 PDF 文件内容。


def parse_pdf_text(path: str | Path) -> str:  # 解析指定 PDF 文件的全部文本内容。
    resolved = Path(path).resolve()  # 把输入路径标准化为绝对路径，避免相对路径歧义。
    reader = PdfReader(str(resolved))  # 打开 PDF 文件并创建读取器。
    chunks: list[str] = []  # 初始化文本片段列表，用于收集每页文本。
    for page_index, page in enumerate(reader.pages, start=1):  # 遍历 PDF 每一页，并保留页码。
        text = page.extract_text() or ""  # 抽取当前页文本，如为空则回退为空串。
        chunks.append(f"[page {page_index}]\n{text}")  # 追加页码和对应文本内容。
    return "\n\n".join(chunks).strip()  # 返回按页拼接后的整篇文本。
