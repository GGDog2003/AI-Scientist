from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from langgraph.types import Command

from app.main import build_app
from app.main import collect_paper_paths
from app.main import parse_resume_value


def _latest_interrupt_payload(interrupts: list[Any]) -> dict[str, Any] | None:
    # 从 LangGraph 中断列表里提取最后一个可序列化负载，供 GUI 判断是否需要导入实验结果。
    if not interrupts:
        return None
    latest = interrupts[-1]
    return latest.value if hasattr(latest, "value") else latest


def _load_progress_events(project_root: Path, thread_id: str | None) -> list[dict[str, Any]]:
    # 读取工作区进度日志，并按线程过滤，供 GUI 以无序列表方式展示当前链路状态。
    progress_path = project_root / "workspace" / "logs" / "progress.jsonl"
    if not progress_path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in progress_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        event = json.loads(stripped)
        if thread_id and event.get("thread_id") != thread_id:
            continue
        events.append(event)
    return events


def _build_gui_payload(
    project_root: Path,
    snapshot: Any,
    interrupts: list[Any],
) -> dict[str, Any]:
    # 统一组装 GUI 需要的结构化返回值，避免前端直接理解 LangGraph 内部对象。
    state = snapshot.values
    return {
        "thread_id": state.get("thread_id"),
        "workflow_status": state.get("workflow_status"),
        "current_stage": state.get("current_stage"),
        "active_agent": state.get("active_agent"),
        "waiting_for_agent": state.get("waiting_for_agent"),
        "final_summary": state.get("final_summary"),
        "manuscript_path": state.get("manuscript_path"),
        "experiment_plan_path": state.get("experiment_plan_path"),
        "experiment_result_path": state.get("experiment_result_path"),
        "advisor_review_path": state.get("advisor_review_path"),
        "reviewer_review_path": state.get("reviewer_review_path"),
        "artifacts": state.get("artifacts", []),
        "messages_log": state.get("messages_log", []),
        "interrupt": _latest_interrupt_payload(interrupts),
        "progress_events": _load_progress_events(project_root, state.get("thread_id")),
    }


def start_workflow(
    project_root: str,
    topic: str,
    domain: str,
    paper_dir: str,
    paper_paths: list[str] | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    # 供 GUI 启动新线程：内部复用正式状态机，但返回结构化 JSON 结果。
    resolved_project_root = Path(project_root).resolve()
    app = build_app(project_root=resolved_project_root)
    app.settings.validate_runtime()
    resolved_thread_id = thread_id or uuid4().hex
    collected_papers = collect_paper_paths(
        project_root=resolved_project_root,
        paper_dir=paper_dir,
        paper_paths=paper_paths or [],
    )
    initial_state = app.create_initial_state(
        topic=topic,
        domain=domain,
        paper_paths=collected_papers,
        thread_id=resolved_thread_id,
    )
    snapshot, interrupts = app.run_until_pause(initial_state, resolved_thread_id)
    return _build_gui_payload(
        project_root=resolved_project_root,
        snapshot=snapshot,
        interrupts=interrupts,
    )


def resume_workflow(
    project_root: str,
    thread_id: str,
    resume_json: str | None = None,
    resume_file: str | None = None,
    resume_text: str | None = None,
) -> dict[str, Any]:
    # 供 GUI 在实验结果导入后恢复线程执行。
    resolved_project_root = Path(project_root).resolve()
    app = build_app(project_root=resolved_project_root)
    app.settings.validate_runtime()
    resume_value = parse_resume_value(resume_json, resume_file, resume_text)
    snapshot, interrupts = app.run_until_pause(Command(resume=resume_value), thread_id)
    return _build_gui_payload(
        project_root=resolved_project_root,
        snapshot=snapshot,
        interrupts=interrupts,
    )


def inspect_workflow(project_root: str, thread_id: str) -> dict[str, Any]:
    # 供 GUI 轮询状态与进度，不会推进工作流，只读取快照和进度日志。
    resolved_project_root = Path(project_root).resolve()
    app = build_app(project_root=resolved_project_root)
    try:
        snapshot = app.get_state(thread_id)
    except Exception:
        return {
            "thread_id": thread_id,
            "workflow_status": "running",
            "current_stage": "bootstrap",
            "active_agent": "system",
            "waiting_for_agent": None,
            "final_summary": None,
            "manuscript_path": None,
            "experiment_plan_path": None,
            "experiment_result_path": None,
            "advisor_review_path": None,
            "reviewer_review_path": None,
            "artifacts": [],
            "messages_log": [],
            "interrupt": None,
            "progress_events": _load_progress_events(resolved_project_root, thread_id),
        }
    return _build_gui_payload(
        project_root=resolved_project_root,
        snapshot=snapshot,
        interrupts=[],
    )


__all__ = ["inspect_workflow", "resume_workflow", "start_workflow"]
