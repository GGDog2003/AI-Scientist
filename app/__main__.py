from app.main import main  # 导入 app 目录下的正式命令行入口，支持 python -m app 运行。

if __name__ == "__main__":  # 判断当前是否以模块方式直接执行。
    raise SystemExit(main())  # 执行主入口并把返回码传回系统。
