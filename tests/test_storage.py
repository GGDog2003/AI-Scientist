from pathlib import Path  # 导入 Path，用于拼接临时目录中的文件路径。

from app.tools.file_store import ArtifactManager  # 从新的 app 目录结构导入工件管理器，验证正式目录结构可用。


def test_artifact_manager_writes_versioned_markdown(tmp_path: Path) -> None:  # 验证 Markdown 工件会按日期和版本号递增写入。
    manager = ArtifactManager(tmp_path)  # 创建一个指向临时目录的工件管理器。
    manager.ensure_workspace()  # 创建工件管理器需要的全部目录。
    first = manager.write_markdown("literature_reports", "文献调研汇总报告", "标题A", [("章节A", "内容A")], {"stage": "test"})  # 写入第一份文档。
    second = manager.write_markdown("literature_reports", "文献调研汇总报告", "标题B", [("章节B", "内容B")], {"stage": "test"})  # 写入第二份文档。
    assert first.path != second.path  # 断言两次写入得到的路径不相同，说明版本号已递增。
    assert (tmp_path / first.path).exists()  # 断言第一份文档实际已写入磁盘。
    assert (tmp_path / second.path).exists()  # 断言第二份文档实际已写入磁盘。
