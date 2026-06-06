from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver


@dataclass(slots=True)
class AppSettings:
    project_root: Path
    workspace_root: Path
    checkpoint_db: Path
    model_name: str
    model_provider: str | None
    model_source: str
    temperature: float
    llm_max_retries: int  # 控制单次 LLM 调用失败后的最大重试次数。
    llm_retry_backoff_seconds: float  # 控制每次重试前的基础退避秒数。
    has_any_key: bool

    @classmethod
    def from_env(cls, project_root: str | Path | None = None) -> "AppSettings":
        resolved_project_root = Path(project_root or Path.cwd()).resolve()
        workspace_root = resolved_project_root / "workspace"
        checkpoint_db = Path(
            os.getenv("AI_SCIENTIST_CHECKPOINT_DB", workspace_root / "checkpoints.sqlite")
        ).resolve()
        if os.getenv("AI_SCIENTIST_MODEL"):
            raw_model_name = os.getenv("AI_SCIENTIST_MODEL", "openai:gpt-4.1-mini")
            model_source = "AI_SCIENTIST_MODEL"
        elif os.getenv("OPENAI_MODEL_NAME"):
            raw_model_name = f"openai:{os.getenv('OPENAI_MODEL_NAME')}"
            model_source = "OPENAI_MODEL_NAME"
        else:
            raw_model_name = "openai:gpt-4.1-mini"
            model_source = "default"
        if ":" in raw_model_name:
            model_provider, model_name = raw_model_name.split(":", 1)
        else:
            model_provider, model_name = None, raw_model_name
        has_any_key = any(
            os.getenv(name) for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY")
        )
        return cls(
            project_root=resolved_project_root,
            workspace_root=workspace_root,
            checkpoint_db=checkpoint_db,
            model_name=model_name,
            model_provider=model_provider,
            model_source=model_source,
            temperature=float(os.getenv("AI_SCIENTIST_TEMPERATURE", "0")),
            llm_max_retries=max(0, int(os.getenv("AI_SCIENTIST_LLM_MAX_RETRIES", "3"))),
            llm_retry_backoff_seconds=max(
                0.0,
                float(os.getenv("AI_SCIENTIST_LLM_RETRY_BACKOFF_SECONDS", "3")),
            ),
            has_any_key=has_any_key,
        )

    def ensure_workspace(self) -> None:
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        for bucket in (
            "papers",
            "parsed_papers",
            "literature_reports",
            "innovation_meetings",
            "experiment_plans",
            "experiment_results",
            "manuscripts",
            "reviews",
            "logs",
        ):
            (self.workspace_root / bucket).mkdir(parents=True, exist_ok=True)
        self.checkpoint_db.parent.mkdir(parents=True, exist_ok=True)

    def build_checkpointer(self) -> Any:
        if str(self.checkpoint_db).lower() == ":memory:":
            return InMemorySaver()
        connection = sqlite3.connect(self.checkpoint_db, check_same_thread=False)
        return SqliteSaver(connection)

    def _validate_api_keys(self) -> None:
        for env_name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
            value = os.getenv(env_name)
            if not value:
                continue
            try:
                value.encode("ascii")
            except UnicodeEncodeError as exc:
                raise RuntimeError(
                    f"{env_name} 包含非 ASCII 字符，请替换成平台签发的真实 API Key。"
                ) from exc
            normalized = value.strip()
            if not normalized:
                raise RuntimeError(f"{env_name} 为空字符串，请设置真实 API Key。")
            placeholder_tokens = (
                "your",
                "token",
                "key",
                "apikey",
                "api_key",
                "example",
                "test",
                "demo",
                "placeholder",
            )
            lowered = normalized.lower()
            if any(token in lowered for token in placeholder_tokens) and not normalized.startswith("sk-"):
                raise RuntimeError(
                    f"{env_name} 看起来像占位文本，而不是真实 API Key。"
                )

    def validate_runtime(self) -> None:
        if not self.has_any_key:
            raise RuntimeError(
                "当前未检测到大模型 API Key。此项目已移除 stub 模式，请先设置 "
                "OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY。"
            )
        self._validate_api_keys()

    def runtime_mode_label(self) -> str:
        prefix = f"{self.model_provider}:" if self.model_provider else ""
        return f"llm({prefix}{self.model_name})"


def build_thread_config(thread_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": thread_id}}
