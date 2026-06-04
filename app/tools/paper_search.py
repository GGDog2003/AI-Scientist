from __future__ import annotations  # 启用延后类型注解，便于后续扩展类型标注。

from pathlib import Path  # 导入 Path，用于遍历工作区文件。


def search_workspace_files(root: str | Path, query: str, suffixes: tuple[str, ...] = (".md", ".txt", ".json", ".pdf")) -> list[str]:  # 在指定目录中按文件名粗略搜索论文或文档。
    resolved_root = Path(root).resolve()  # 把根目录解析成绝对路径，避免不同 cwd 影响结果。
    matches: list[str] = []  # 初始化匹配路径列表。
    for candidate in sorted(resolved_root.rglob("*")):  # 递归遍历根目录下的全部文件。
        if not candidate.is_file():  # 只处理文件，跳过子目录。
            continue  # 跳到下一个路径继续处理。
        if candidate.suffix.lower() not in suffixes:  # 过滤掉不在目标后缀集合中的文件。
            continue  # 跳过无关文件。
        if query.lower() in candidate.name.lower():  # 使用文件名做大小写无关匹配。
            matches.append(str(candidate.relative_to(resolved_root)))  # 记录相对路径，便于返回给上层展示。
    return matches  # 返回全部匹配结果。
