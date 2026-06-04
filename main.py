from __future__ import annotations  # 启用延后类型注解，便于脚本入口在不同 Python 版本下保持一致。

from app.main import main as app_main  # 导入 app 目录中的正式主入口函数，作为根目录脚本的委托目标。


if __name__ == "__main__":  # 判断当前文件是否以 python main.py 的方式直接运行。
    raise SystemExit(app_main())  # 调用正式主入口并把返回码交给操作系统，支持根目录直接启动。
