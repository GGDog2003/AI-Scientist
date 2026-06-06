from __future__ import annotations

import argparse
import json
from pathlib import Path


def command_start(args: argparse.Namespace) -> int:
    from app.gui_api import start_workflow

    payload = start_workflow(
        project_root=args.project_root,
        topic=args.topic,
        domain=args.domain,
        paper_dir=args.paper_dir,
        paper_paths=args.paper_path,
        thread_id=args.thread_id,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def command_resume(args: argparse.Namespace) -> int:
    from app.gui_api import resume_workflow

    payload = resume_workflow(
        project_root=args.project_root,
        thread_id=args.thread_id,
        resume_json=args.resume_json,
        resume_file=args.resume_file,
        resume_text=args.resume_text,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def command_state(args: argparse.Namespace) -> int:
    from app.gui_api import inspect_workflow

    payload = inspect_workflow(project_root=args.project_root, thread_id=args.thread_id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI Scientist GUI bridge CLI")
    parser.add_argument("--project-root", default=str(Path.cwd()), help="Project root path.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="Start workflow for GUI.")
    start_parser.add_argument("--topic", default="自动生成论文")
    start_parser.add_argument("--domain", default="人工智能")
    start_parser.add_argument("--paper-dir", required=True)
    start_parser.add_argument("--paper-path", action="append", default=[])
    start_parser.add_argument("--thread-id", default=None)
    start_parser.set_defaults(func=command_start)

    resume_parser = subparsers.add_parser("resume", help="Resume workflow for GUI.")
    resume_parser.add_argument("--thread-id", required=True)
    resume_parser.add_argument("--resume-json", default=None)
    resume_parser.add_argument("--resume-file", default=None)
    resume_parser.add_argument("--resume-text", default=None)
    resume_parser.set_defaults(func=command_resume)

    state_parser = subparsers.add_parser("state", help="Inspect workflow state for GUI.")
    state_parser.add_argument("--thread-id", required=True)
    state_parser.set_defaults(func=command_state)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


__all__ = ["build_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
