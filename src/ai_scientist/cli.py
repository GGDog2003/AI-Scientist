from __future__ import annotations  # 启用延后类型注解，便于函数返回类型引用自定义类。

import argparse  # 导入 argparse，用于实现命令行接口。
import json  # 导入 json，用于解析和打印结构化数据。
from pathlib import Path  # 导入 Path，用于解析项目根目录。
from typing import Any  # 导入 Any，用于通用 JSON 负载类型注解。
from uuid import uuid4  # 导入 uuid4，用于在未指定线程时自动生成 thread_id。

from langgraph.types import Command  # 导入 Command，用于恢复被 interrupt 挂起的图执行。

from ai_scientist.config import AppSettings  # 导入配置对象，便于构建工作流应用。
from ai_scientist.config import build_thread_config  # 导入线程配置构造函数，便于 LangGraph 持久化恢复。
from ai_scientist.workflow import ResearchWorkflowApp  # 导入工作流应用入口。


def build_app(project_root: str | Path | None = None) -> ResearchWorkflowApp:  # 根据项目根目录构建应用对象。
    settings = AppSettings.from_env(project_root=project_root)  # 从环境变量与项目路径加载运行配置。
    return ResearchWorkflowApp(settings=settings)  # 返回初始化完成的工作流应用。


def run_graph_until_pause(app: ResearchWorkflowApp, input_value: Any, thread_id: str) -> tuple[Any, list[Any]]:  # 驱动图运行到结束或中断，并返回状态快照和中断列表。
    config = build_thread_config(thread_id)  # 构造 LangGraph 标准线程配置。
    interrupts: list[Any] = []  # 初始化中断列表，用于记录人工输入请求。
    for event in app.graph.stream(input_value, config=config):  # 以流式方式执行工作流，便于捕获中断事件。
        if "__interrupt__" in event:  # 判断当前事件是否是 LangGraph interrupt。
            interrupts.extend(event["__interrupt__"])  # 把中断对象追加到中断列表中。
            continue  # 捕获到中断后跳过普通事件打印。
        print(json.dumps(event, ensure_ascii=False, indent=2, default=str))  # 把普通更新事件打印出来，方便用户观察执行过程。
    snapshot = app.graph.get_state(config)  # 在本轮执行结束后读取线程状态快照。
    return snapshot, interrupts  # 返回最终快照和可能的中断列表。


def parse_resume_value(resume_json: str | None, resume_file: str | None, resume_text: str | None) -> Any:  # 解析恢复工作流时的人类输入。
    if resume_json:  # 判断是否直接传入了 JSON 字符串。
        return json.loads(resume_json)  # 解析 JSON 字符串并返回 Python 对象。
    if resume_file:  # 判断是否传入了 JSON 文件路径。
        return json.loads(Path(resume_file).read_text(encoding="utf-8"))  # 读取文件并反序列化 JSON。
    return resume_text or ""  # 如果前两者都没有，就返回纯文本输入，默认为空串。


def command_start(args: argparse.Namespace) -> int:  # 执行 start 子命令。
    app = build_app(project_root=args.project_root)  # 根据命令行参数构建工作流应用。
    thread_id = args.thread_id or uuid4().hex  # 如果用户未传 thread_id，就自动生成一个。
    initial_state = app.create_initial_state(topic=args.topic, domain=args.domain, paper_paths=args.paper_path, thread_id=thread_id)  # 组装初始状态。
    snapshot, interrupts = run_graph_until_pause(app=app, input_value=initial_state, thread_id=thread_id)  # 驱动图执行到暂停点或结束。
    print(f"thread_id={thread_id}")  # 把 thread_id 打印出来，便于后续 resume 使用。
    print(json.dumps(snapshot.values, ensure_ascii=False, indent=2, default=str))  # 打印当前线程状态快照。
    if interrupts:  # 判断当前执行是否被人工节点中断。
        print("workflow interrupted and waiting for input:")  # 打印中断提示。
        print(json.dumps([item.value for item in interrupts], ensure_ascii=False, indent=2, default=str))  # 打印中断负载，告诉用户需要输入什么。
    return 0  # 返回成功退出码。


def command_resume(args: argparse.Namespace) -> int:  # 执行 resume 子命令。
    app = build_app(project_root=args.project_root)  # 根据命令行参数构建工作流应用。
    resume_value = parse_resume_value(args.resume_json, args.resume_file, args.resume_text)  # 解析恢复输入。
    snapshot, interrupts = run_graph_until_pause(app=app, input_value=Command(resume=resume_value), thread_id=args.thread_id)  # 用 Command 恢复被挂起的工作流。
    print(json.dumps(snapshot.values, ensure_ascii=False, indent=2, default=str))  # 打印恢复执行后的线程状态。
    if interrupts:  # 判断恢复执行后是否又触发了新的中断。
        print("workflow interrupted again and waiting for input:")  # 打印再次中断提示。
        print(json.dumps([item.value for item in interrupts], ensure_ascii=False, indent=2, default=str))  # 打印新的中断负载。
    return 0  # 返回成功退出码。


def command_state(args: argparse.Namespace) -> int:  # 执行 state 子命令。
    app = build_app(project_root=args.project_root)  # 根据命令行参数构建工作流应用。
    snapshot = app.graph.get_state(build_thread_config(args.thread_id))  # 读取指定线程的状态快照。
    print(json.dumps(snapshot.values, ensure_ascii=False, indent=2, default=str))  # 打印线程当前状态。
    return 0  # 返回成功退出码。


def build_parser() -> argparse.ArgumentParser:  # 构建命令行参数解析器。
    parser = argparse.ArgumentParser(description="AI Scientist LangChain + LangGraph workflow runner")  # 创建顶层参数解析器。
    parser.add_argument("--project-root", default=str(Path.cwd()), help="Project root path.")  # 添加项目根目录参数。
    subparsers = parser.add_subparsers(dest="command", required=True)  # 创建子命令解析器集合，并要求必须传入子命令。

    start_parser = subparsers.add_parser("start", help="Start a new research workflow thread.")  # 创建 start 子命令解析器。
    start_parser.add_argument("--topic", required=True, help="Research topic.")  # 添加研究主题参数。
    start_parser.add_argument("--domain", required=True, help="Research domain.")  # 添加研究领域参数。
    start_parser.add_argument("--paper-path", action="append", default=[], help="Relative or absolute paper path. Repeatable.")  # 添加论文路径参数，支持重复多次传值。
    start_parser.add_argument("--thread-id", default=None, help="Optional custom thread id.")  # 添加可选线程 ID 参数。
    start_parser.set_defaults(func=command_start)  # 绑定 start 子命令的处理函数。

    resume_parser = subparsers.add_parser("resume", help="Resume a suspended workflow thread.")  # 创建 resume 子命令解析器。
    resume_parser.add_argument("--thread-id", required=True, help="Thread id to resume.")  # 添加必须的线程 ID 参数。
    resume_parser.add_argument("--resume-json", default=None, help="JSON payload string for resume.")  # 添加 JSON 恢复负载参数。
    resume_parser.add_argument("--resume-file", default=None, help="JSON file path for resume.")  # 添加 JSON 文件恢复参数。
    resume_parser.add_argument("--resume-text", default=None, help="Plain text payload for resume.")  # 添加纯文本恢复参数。
    resume_parser.set_defaults(func=command_resume)  # 绑定 resume 子命令的处理函数。

    state_parser = subparsers.add_parser("state", help="Inspect a workflow thread state.")  # 创建 state 子命令解析器。
    state_parser.add_argument("--thread-id", required=True, help="Thread id to inspect.")  # 添加线程 ID 参数。
    state_parser.set_defaults(func=command_state)  # 绑定 state 子命令的处理函数。

    return parser  # 返回配置完成的命令行解析器。


def main() -> int:  # 定义命令行总入口函数。
    parser = build_parser()  # 构建参数解析器实例。
    args = parser.parse_args()  # 解析命令行输入参数。
    return args.func(args)  # 根据子命令绑定执行对应处理函数，并返回退出码。
