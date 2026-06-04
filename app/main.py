from __future__ import annotations  # 启用延后类型注解，便于在函数签名里直接引用后续类型。
import argparse  # 导入 argparse，用于构建命令行参数解析器。
import json  # 导入 json，用于打印状态快照和解析恢复负载。
from pathlib import Path  # 导入 Path，用于解析项目根目录、论文目录和恢复文件路径。
from typing import Any  # 导入 Any，用于标注工作流输入输出中的通用类型。
from uuid import uuid4  # 导入 uuid4，用于在未传入 thread_id 时自动生成线程标识。

from langgraph.types import Command  # 导入 Command，用于把人工恢复输入送回 LangGraph 工作流。

from app.workflows.state_machine import ResearchStateMachine  # 导入正式状态机类，作为仓库内唯一的工作流主入口。


def build_app(project_root: str | Path | None = None) -> ResearchStateMachine:  # 根据项目根目录创建状态机实例。
    return ResearchStateMachine(project_root=str(project_root) if project_root is not None else None)  # 把可选项目根目录统一转成字符串后传给状态机构造函数。


def collect_paper_paths(project_root: str | Path, paper_dir: str | None, paper_paths: list[str] | None) -> list[str]:  # 收集 start 阶段需要处理的全部 PDF 路径。
    root_path = Path(project_root).resolve()  # 解析项目根目录，便于把相对路径统一展开为绝对路径。
    collected_paths: list[str] = []  # 初始化论文路径列表，用于汇总目录扫描结果和手动补充文件。
    if paper_dir:  # 判断用户是否提供了论文目录参数。
        directory_path = Path(paper_dir)  # 把论文目录字符串转换为 Path 对象，便于后续判断和遍历。
        resolved_directory = directory_path if directory_path.is_absolute() else root_path / directory_path  # 如果论文目录是相对路径，就相对项目根目录解析。
        resolved_directory = resolved_directory.resolve()  # 把论文目录规范化成绝对路径，避免同一路径出现多种表示形式。
        if not resolved_directory.exists():  # 判断论文目录是否真实存在。
            raise FileNotFoundError(f"论文目录不存在：{resolved_directory}")  # 目录不存在时直接报错，避免启动空流程。
        if not resolved_directory.is_dir():  # 判断传入路径是否确实是目录。
            raise NotADirectoryError(f"论文目录不是文件夹：{resolved_directory}")  # 如果传入的是文件而不是目录，就明确提示用户修正参数。
        for pdf_path in sorted(resolved_directory.glob("*.pdf")):  # 按文件名顺序遍历目录下全部 PDF 文件，保证处理顺序稳定。
            collected_paths.append(str(pdf_path.resolve()))  # 把每个 PDF 的绝对路径加入列表，供研究生 Agent 逐篇阅读。
    for paper_path in paper_paths or []:  # 遍历用户额外补充的单篇论文路径，兼容目录之外临时追加文件。
        resolved_path = Path(paper_path)  # 把单篇论文路径转换为 Path 对象，便于统一解析。
        resolved_path = resolved_path if resolved_path.is_absolute() else root_path / resolved_path  # 如果是相对路径，就相对项目根目录解析绝对位置。
        collected_paths.append(str(resolved_path.resolve()))  # 把解析后的绝对文件路径加入结果列表，保持下游处理逻辑统一。
    deduplicated_paths = list(dict.fromkeys(collected_paths))  # 按原有顺序去重，避免同一篇论文被目录扫描和手动参数重复加入。
    if not deduplicated_paths:  # 判断最终是否至少收集到一篇论文 PDF。
        raise ValueError("未找到任何论文 PDF，请通过 --paper-dir 指定论文目录，或通过 --paper-path 补充论文文件。")  # 如果没有 PDF，则提示正确用法并阻止启动。
    return deduplicated_paths  # 返回整理好的论文路径列表，供状态机初始化使用。


def run_graph_until_pause(app: ResearchStateMachine, input_value: Any, thread_id: str) -> tuple[Any, list[Any]]:  # 驱动工作流运行到结束或中断点。
    config = {"configurable": {"thread_id": thread_id}}  # 构造 LangGraph 标准线程配置，确保同一线程状态可持续恢复。
    interrupts: list[Any] = []  # 初始化中断列表，用于接收人工实验或人工确认节点的挂起请求。
    for event in app.graph.stream(input_value, config=config):  # 以流式方式执行工作流，便于捕获中断和阶段更新。
        if "__interrupt__" in event:  # 判断当前事件是否为 LangGraph 的 interrupt 事件。
            interrupts.extend(event["__interrupt__"])  # 把中断对象追加到列表里，供命令行层统一输出给用户。
            continue  # 捕获到中断后跳过普通事件打印，避免干扰用户阅读关键输入提示。
        print(json.dumps(event, ensure_ascii=False, indent=2, default=str))  # 把普通状态更新事件按中文 JSON 打印出来，方便观察执行过程。
    snapshot = app.graph.get_state(config)  # 在本轮执行结束后读取当前线程的最新状态快照。
    return snapshot, interrupts  # 返回状态快照和中断列表，供 start/resume 命令统一处理。


def parse_resume_value(resume_json: str | None, resume_file: str | None, resume_text: str | None) -> Any:  # 解析 resume 命令接收的人类反馈内容。
    if resume_json:  # 判断用户是否直接传入了 JSON 字符串。
        return json.loads(resume_json)  # 解析 JSON 字符串并返回对应 Python 对象。
    if resume_file:  # 判断用户是否提供了 JSON 文件路径。
        return json.loads(Path(resume_file).read_text(encoding="utf-8"))  # 读取 JSON 文件文本并反序列化为 Python 对象。
    return resume_text or ""  # 如果既没有 JSON 字符串也没有 JSON 文件，就回退为纯文本输入。


def command_start(args: argparse.Namespace) -> int:  # 执行 start 子命令，启动一个新的科研工作流线程。
    app = build_app(project_root=args.project_root)  # 根据命令行参数创建状态机应用实例。
    app.settings.validate_runtime()  # 在真正启动前先校验运行环境，避免无密钥时静默回退到假流程。
    thread_id = args.thread_id or uuid4().hex  # 如果用户没有显式指定 thread_id，就自动生成一个新的线程编号。
    paper_paths = collect_paper_paths(project_root=args.project_root, paper_dir=args.paper_dir, paper_paths=args.paper_path)  # 收集论文目录和补充文件里的全部 PDF。
    print(f"[AI-Scientist] 运行模式: {app.settings.runtime_mode_label()}")  # 打印当前运行模式，明确说明是否会真实调用大模型。
    print(f"[AI-Scientist] 模型配置来源: {app.settings.model_source}")  # 打印模型配置来源，便于确认本次是否真的读到了用户设置的模型变量。
    print(f"[AI-Scientist] 已识别论文 PDF 数量: {len(paper_paths)}")  # 打印本次纳入工作流的论文数量，避免用户误以为没有真正读取目录。
    print(f"[AI-Scientist] 论文目录/文件准备完成，开始执行多 Agent 工作流。")  # 打印启动提示，说明接下来会进入实际工作流执行。
    initial_state = app.create_initial_state(topic=args.topic, domain=args.domain, paper_paths=paper_paths, thread_id=thread_id)  # 组装工作流启动时需要的初始状态。
    try:  # 开始保护真实模型调用流程，把底层接口异常翻译成更可读的命令行错误。
        snapshot, interrupts = run_graph_until_pause(app=app, input_value=initial_state, thread_id=thread_id)  # 驱动工作流运行到挂起点或最终结束。
    except Exception as exc:  # 捕获启动阶段的全部异常，避免直接把超长堆栈完全裸露给用户。
        message = str(exc)  # 提取异常文本，便于做关键字判断和输出更明确的提示。
        if "ascii" in message and "encode characters" in message:  # 判断是否命中了请求头 ASCII 编码失败错误。
            raise RuntimeError("模型调用前的请求头构造失败，通常是 API Key 里包含中文或其他非法字符。请检查 OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY 是否被填成了“你的新key”这类占位文本。") from exc  # 把底层 httpx 编码异常翻译成直接可执行的排查建议。
        if "unsupported_country_region_territory" in message:  # 判断是否命中了 OpenAI 区域限制错误。
            raise RuntimeError("模型调用被目标平台拒绝，错误为 unsupported_country_region_territory。当前程序实际命中了 OpenAI 兼容接口，但你的模型配置很可能没有被正确传入。请优先检查两点：1）在 PowerShell 中要用 $env:OPENAI_API_KEY / $env:OPENAI_BASE_URL / $env:OPENAI_MODEL_NAME，而不是 set；2）启动日志里的“模型配置来源”必须显示为 OPENAI_MODEL_NAME 或 AI_SCIENTIST_MODEL，而不是 default。") from exc  # 把区域限制错误翻译成贴合当前场景的可执行排查建议。
        raise  # 如果不是这个特定问题，就保留原异常继续抛出，避免吞掉真实错误。
    print(f"thread_id={thread_id}")  # 输出线程编号，方便用户后续执行 resume 和 state 命令。
    print(json.dumps(snapshot.values, ensure_ascii=False, indent=2, default=str))  # 输出当前线程的完整状态快照，便于排查和确认阶段结果。
    if interrupts:  # 判断当前执行是否触发了需要人类输入的挂起点。
        print("workflow interrupted and waiting for input:")  # 输出挂起提示，明确说明工作流正在等待外部反馈。
        print(json.dumps([item.value for item in interrupts], ensure_ascii=False, indent=2, default=str))  # 输出中断负载，提示用户下一步应补充什么内容。
    return 0  # 返回成功退出码，表示 start 命令已正常完成本轮执行。


def command_resume(args: argparse.Namespace) -> int:  # 执行 resume 子命令，恢复一个已挂起的科研工作流线程。
    app = build_app(project_root=args.project_root)  # 根据命令行参数重新创建状态机应用实例。
    app.settings.validate_runtime()  # 在恢复执行前先校验运行环境，避免无密钥时静默回退到假流程。
    resume_value = parse_resume_value(args.resume_json, args.resume_file, args.resume_text)  # 解析恢复执行时的人类反馈内容。
    print(f"[AI-Scientist] 运行模式: {app.settings.runtime_mode_label()}")  # 打印当前恢复执行使用的运行模式，明确说明是否会真实调用大模型。
    print(f"[AI-Scientist] 模型配置来源: {app.settings.model_source}")  # 打印模型配置来源，便于确认恢复执行时实际读取了哪个模型变量。
    print(f"[AI-Scientist] 开始恢复线程: {args.thread_id}")  # 打印当前恢复的线程编号，便于用户确认操作目标。
    snapshot, interrupts = run_graph_until_pause(app=app, input_value=Command(resume=resume_value), thread_id=args.thread_id)  # 把恢复负载封装成 Command 并继续运行工作流。
    print(json.dumps(snapshot.values, ensure_ascii=False, indent=2, default=str))  # 输出恢复执行后的线程状态，便于确认是否进入下一阶段。
    if interrupts:  # 判断恢复执行后是否又进入了新的人工挂起点。
        print("workflow interrupted again and waiting for input:")  # 输出再次挂起的提示信息。
        print(json.dumps([item.value for item in interrupts], ensure_ascii=False, indent=2, default=str))  # 输出新的中断负载，引导用户继续补充输入。
    return 0  # 返回成功退出码，表示 resume 命令本轮已正常执行完毕。


def command_state(args: argparse.Namespace) -> int:  # 执行 state 子命令，查看指定线程的当前状态快照。
    app = build_app(project_root=args.project_root)  # 根据命令行参数创建状态机应用实例。
    snapshot = app.get_state(args.thread_id)  # 读取目标线程的当前状态快照。
    print(json.dumps(snapshot.values, ensure_ascii=False, indent=2, default=str))  # 把线程状态格式化输出给用户查看。
    return 0  # 返回成功退出码，表示 state 命令执行完成。


def build_parser() -> argparse.ArgumentParser:  # 构建命令行参数解析器，统一定义 start、resume、state 三类子命令。
    parser = argparse.ArgumentParser(description="AI Scientist LangChain + LangGraph workflow runner")  # 创建顶层命令行解析器。
    parser.add_argument("--project-root", default=str(Path.cwd()), help="Project root path.")  # 添加项目根目录参数，默认使用当前工作目录。
    subparsers = parser.add_subparsers(dest="command", required=True)  # 创建子命令集合，并要求用户必须显式选择一个子命令。

    start_parser = subparsers.add_parser("start", help="Start a new research workflow thread.")  # 创建 start 子命令解析器。
    start_parser.add_argument("--topic", required=True, help="Research topic.")  # 添加研究主题参数，描述当前科研任务的问题方向。
    start_parser.add_argument("--domain", required=True, help="Research domain.")  # 添加研究领域参数，描述当前科研任务所属学科范围。
    start_parser.add_argument("--paper-dir", default=None, help="Directory that contains all paper PDF files.")  # 添加论文目录参数，让程序自动扫描该目录下全部 PDF。
    start_parser.add_argument("--paper-path", action="append", default=[], help="Optional extra paper path. Repeatable.")  # 保留单篇论文补充参数，用于在目录之外临时追加 PDF 文件。
    start_parser.add_argument("--thread-id", default=None, help="Optional custom thread id.")  # 添加可选线程编号参数，支持外部系统自定义线程 ID。
    start_parser.set_defaults(func=command_start)  # 绑定 start 子命令的处理函数。

    resume_parser = subparsers.add_parser("resume", help="Resume a suspended workflow thread.")  # 创建 resume 子命令解析器。
    resume_parser.add_argument("--thread-id", required=True, help="Thread id to resume.")  # 添加必填线程编号参数，用于指定要恢复的工作流线程。
    resume_parser.add_argument("--resume-json", default=None, help="JSON payload string for resume.")  # 添加 JSON 字符串恢复负载参数，适合直接粘贴结构化实验结果。
    resume_parser.add_argument("--resume-file", default=None, help="JSON file path for resume.")  # 添加 JSON 文件恢复参数，适合从文件导入较长结果。
    resume_parser.add_argument("--resume-text", default=None, help="Plain text payload for resume.")  # 添加纯文本恢复参数，适合简单人工说明。
    resume_parser.set_defaults(func=command_resume)  # 绑定 resume 子命令的处理函数。

    state_parser = subparsers.add_parser("state", help="Inspect a workflow thread state.")  # 创建 state 子命令解析器。
    state_parser.add_argument("--thread-id", required=True, help="Thread id to inspect.")  # 添加必填线程编号参数，用于查看指定线程的状态。
    state_parser.set_defaults(func=command_state)  # 绑定 state 子命令的处理函数。

    return parser  # 返回配置完成的命令行解析器。


def main() -> int:  # 定义 app 目录内的主入口函数，供根目录脚本和打包脚本复用。
    parser = build_parser()  # 创建命令行参数解析器实例。
    args = parser.parse_args()  # 解析当前进程收到的命令行参数。
    return args.func(args)  # 根据子命令绑定关系执行对应处理函数，并把退出码返回给调用方。


__all__ = ["main", "build_app", "build_parser", "collect_paper_paths"]  # 显式导出主入口和工具函数，便于外部脚本或测试复用。
