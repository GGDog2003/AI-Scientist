from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from langgraph.types import Command

from ai_scientist.config import AppSettings
from ai_scientist.config import build_thread_config
from ai_scientist.workflow import ResearchWorkflowApp


def build_app(project_root: str | Path | None = None) -> ResearchWorkflowApp:
    settings = AppSettings.from_env(project_root=project_root)
    return ResearchWorkflowApp(settings=settings)


def collect_paper_paths(project_root: str | Path, paper_dir: str | None, paper_paths: list[str] | None) -> list[str]:
    root_path = Path(project_root).resolve()
    collected_paths: list[str] = []
    if paper_dir:
        directory_path = Path(paper_dir)
        resolved_directory = directory_path if directory_path.is_absolute() else root_path / directory_path
        resolved_directory = resolved_directory.resolve()
        if not resolved_directory.exists():
            raise FileNotFoundError(f"论文目录不存在：{resolved_directory}")
        if not resolved_directory.is_dir():
            raise NotADirectoryError(f"论文目录不是文件夹：{resolved_directory}")
        for pdf_path in sorted(resolved_directory.glob("*.pdf")):
            collected_paths.append(str(pdf_path.resolve()))
    for paper_path in paper_paths or []:
        resolved_path = Path(paper_path)
        resolved_path = resolved_path if resolved_path.is_absolute() else root_path / resolved_path
        collected_paths.append(str(resolved_path.resolve()))
    deduplicated_paths = list(dict.fromkeys(collected_paths))
    if not deduplicated_paths:
        raise ValueError("未找到任何论文 PDF，请通过 --paper-dir 或 --paper-path 提供输入。")
    return deduplicated_paths


def run_graph_until_pause(app: ResearchWorkflowApp, input_value: Any, thread_id: str) -> tuple[Any, list[Any]]:
    config = build_thread_config(thread_id)
    interrupts: list[Any] = []
    for event in app.graph.stream(input_value, config=config):
        if "__interrupt__" in event:
            interrupts.extend(event["__interrupt__"])
            continue
        print(json.dumps(event, ensure_ascii=False, indent=2, default=str))
    snapshot = app.graph.get_state(config)
    return snapshot, interrupts


def parse_resume_value(resume_json: str | None, resume_file: str | None, resume_text: str | None) -> Any:
    if resume_json:
        return json.loads(resume_json)
    if resume_file:
        return json.loads(Path(resume_file).read_text(encoding="utf-8"))
    return resume_text or ""


def command_start(args: argparse.Namespace) -> int:
    app = build_app(project_root=args.project_root)
    app.settings.validate_runtime()
    thread_id = args.thread_id or uuid4().hex
    paper_paths = collect_paper_paths(
        project_root=args.project_root,
        paper_dir=args.paper_dir,
        paper_paths=args.paper_path,
    )
    print(f"[AI-Scientist] 运行模式: {app.settings.runtime_mode_label()}")
    print(f"[AI-Scientist] 模型配置来源: {app.settings.model_source}")
    print(f"[AI-Scientist] 已识别论文 PDF 数量: {len(paper_paths)}")
    initial_state = app.create_initial_state(
        topic=args.topic,
        domain=args.domain,
        paper_paths=paper_paths,
        thread_id=thread_id,
    )
    snapshot, interrupts = run_graph_until_pause(app=app, input_value=initial_state, thread_id=thread_id)
    print(f"thread_id={thread_id}")
    print(json.dumps(snapshot.values, ensure_ascii=False, indent=2, default=str))
    if interrupts:
        print("workflow interrupted and waiting for input:")
        print(json.dumps([item.value for item in interrupts], ensure_ascii=False, indent=2, default=str))
    return 0


def command_resume(args: argparse.Namespace) -> int:
    app = build_app(project_root=args.project_root)
    app.settings.validate_runtime()
    resume_value = parse_resume_value(args.resume_json, args.resume_file, args.resume_text)
    print(f"[AI-Scientist] 运行模式: {app.settings.runtime_mode_label()}")
    print(f"[AI-Scientist] 模型配置来源: {app.settings.model_source}")
    snapshot, interrupts = run_graph_until_pause(
        app=app,
        input_value=Command(resume=resume_value),
        thread_id=args.thread_id,
    )
    print(json.dumps(snapshot.values, ensure_ascii=False, indent=2, default=str))
    if interrupts:
        print("workflow interrupted again and waiting for input:")
        print(json.dumps([item.value for item in interrupts], ensure_ascii=False, indent=2, default=str))
    return 0


def command_state(args: argparse.Namespace) -> int:
    app = build_app(project_root=args.project_root)
    snapshot = app.graph.get_state(build_thread_config(args.thread_id))
    print(json.dumps(snapshot.values, ensure_ascii=False, indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI Scientist LangChain + LangGraph workflow runner")
    parser.add_argument("--project-root", default=str(Path.cwd()), help="Project root path.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="Start a new research workflow thread.")
    start_parser.add_argument("--topic", required=True, help="Research topic.")
    start_parser.add_argument("--domain", required=True, help="Research domain.")
    start_parser.add_argument("--paper-dir", default=None, help="Directory that contains paper PDFs.")
    start_parser.add_argument("--paper-path", action="append", default=[], help="Optional extra paper path.")
    start_parser.add_argument("--thread-id", default=None, help="Optional custom thread id.")
    start_parser.set_defaults(func=command_start)

    resume_parser = subparsers.add_parser("resume", help="Resume a suspended workflow thread.")
    resume_parser.add_argument("--thread-id", required=True, help="Thread id to resume.")
    resume_parser.add_argument("--resume-json", default=None, help="JSON payload string for resume.")
    resume_parser.add_argument("--resume-file", default=None, help="JSON file path for resume.")
    resume_parser.add_argument("--resume-text", default=None, help="Plain text payload for resume.")
    resume_parser.set_defaults(func=command_resume)

    state_parser = subparsers.add_parser("state", help="Inspect a workflow thread state.")
    state_parser.add_argument("--thread-id", required=True, help="Thread id to inspect.")
    state_parser.set_defaults(func=command_state)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


__all__ = ["build_app", "build_parser", "collect_paper_paths", "main"]
