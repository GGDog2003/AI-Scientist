from __future__ import annotations

import json
import time
from typing import Any
from typing import Callable
from typing import TypeVar

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from pydantic import BaseModel

from ai_scientist.config import AppSettings
from ai_scientist.prompts import build_task_prompt
from ai_scientist.prompts import get_system_prompt
from ai_scientist.schemas import BlindReview
from ai_scientist.schemas import ExperimentGateReview
from ai_scientist.schemas import ExperimentPlan
from ai_scientist.schemas import InnovationProposal
from ai_scientist.schemas import InnovationReview
from ai_scientist.schemas import LiteratureSynthesis
from ai_scientist.schemas import ManuscriptDraft
from ai_scientist.schemas import PaperReview
from ai_scientist.schemas import ResultAnalysis


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class BaseRoleAgent:
    def __init__(self, settings: AppSettings, role_name: str, tools: list) -> None:
        self.settings = settings
        self.role_name = role_name
        self.system_prompt = get_system_prompt(role_name)
        self.tools = tools
        self.model = self._build_model()

    def _build_model(self):
        if self.settings.model_provider:
            return init_chat_model(
                self.settings.model_name,
                model_provider=self.settings.model_provider,
                temperature=self.settings.temperature,
            )
        return init_chat_model(self.settings.model_name, temperature=self.settings.temperature)

    def _task_prompt(self, task_name: str, payload: dict[str, Any]) -> str:
        return build_task_prompt(self.role_name, task_name, payload)

    def _reconnect_model(self) -> None:
        # 重建底层模型实例，用于在超时、限流或上游中断后主动重连大模型。
        self.model = self._build_model()

    def _is_retryable_llm_error(self, error: Exception) -> bool:
        # 统一转成小写文本，便于基于错误内容识别可恢复的大模型异常。
        message = str(error).lower()
        # 这批关键字覆盖了 524、超时、限流、临时不可用等常见可重试场景。
        retryable_markers = (
            "524",
            "proxy read timeout",
            "timed out",
            "timeout",
            "read timeout",
            "connection reset",
            "connection aborted",
            "temporarily unavailable",
            "temporary failure",
            "internalservererror",
            "internal server error",
            "server error",
            "rate limit",
            "429",
            "too many requests",
            "the origin web server did not return a complete response",
        )
        # 只要错误文本命中可恢复标记，就允许后续重连并重试。
        return any(marker in message for marker in retryable_markers)

    def _invoke_with_retry(
        self,
        operation_name: str,
        invoke_fn: Callable[[], Any],
    ) -> Any:
        # 先显式保留操作名，便于后续接日志或指标埋点时直接复用。
        _ = operation_name
        # 总尝试次数等于首次调用加上配置的重试次数，最少保证执行一次。
        total_attempts = max(1, self.settings.llm_max_retries + 1)
        # 逐轮执行真实 LLM 调用，并在可恢复异常时重建模型后重试。
        for attempt_index in range(total_attempts):
            try:
                # 执行传入的真实调用闭包，闭包内部可以自由重建 agent 或复用消息体。
                return invoke_fn()
            except Exception as error:
                # 不可恢复错误直接抛出，避免把结构化校验等逻辑误判成网络异常。
                if not self._is_retryable_llm_error(error):
                    raise
                # 已经耗尽重试次数时保留原始异常，让上层按真实失败处理。
                if attempt_index >= total_attempts - 1:
                    raise
                # 每次重试前主动重建模型实例，达到 reconnect 大模型的效果。
                self._reconnect_model()
                # 线性退避时间按尝试轮次递增，避免连续瞬时重试继续撞到上游超时。
                backoff_seconds = self.settings.llm_retry_backoff_seconds * (attempt_index + 1)
                # 仅在配置了正数退避时间时等待，允许用户把等待时间设为 0。
                if backoff_seconds > 0:
                    time.sleep(backoff_seconds)

    def _build_task_json_prompt(
        self,
        task_prompt: str,
        task_name: str,
        payload: dict[str, Any],
        response_model: type[StructuredModel],
    ) -> str:
        schema_json = json.dumps(response_model.model_json_schema(), ensure_ascii=False, indent=2)
        payload_json = json.dumps({"task_name": task_name, "payload": payload}, ensure_ascii=False, indent=2)
        prompt_parts = [
            task_prompt.strip(),
            "你必须严格返回一个合法 JSON 对象，且只能返回 JSON，不能输出解释、前后缀、Markdown 代码块。",
            "返回的 JSON 必须满足下面这个 JSON Schema：",
            schema_json,
            "当前任务输入如下：",
            payload_json,
        ]
        return "\n\n".join(part for part in prompt_parts if part)

    def _extract_text_content(self, result: Any) -> str:
        if hasattr(result, "content"):
            content = result.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                text_parts: list[str] = []
                for item in content:
                    if isinstance(item, str):
                        text_parts.append(item)
                        continue
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        text_parts.append(item["text"])
                return "".join(text_parts)
        return str(result)

    def _parse_structured_text(
        self,
        text: str,
        response_model: type[StructuredModel],
    ) -> StructuredModel:
        stripped_text = text.strip()
        if stripped_text.startswith("```"):
            stripped_text = stripped_text.strip("`")
            if stripped_text.lower().startswith("json"):
                stripped_text = stripped_text[4:].strip()
        parsed = json.loads(stripped_text)
        return response_model.model_validate(parsed)

    def _invoke_structured_json_text(
        self,
        task_prompt: str,
        task_name: str,
        payload: dict[str, Any],
        response_model: type[StructuredModel],
    ) -> StructuredModel:
        prompt_text = self._build_task_json_prompt(
            task_prompt=task_prompt,
            task_name=task_name,
            payload=payload,
            response_model=response_model,
        )
        messages = [
            SystemMessage(content=f"{self.system_prompt}\n\n{task_prompt}".strip()),
            HumanMessage(content=prompt_text),
        ]
        # 纯消息调用直接包裹重试逻辑，确保超时后先重连模型再继续请求。
        result = self._invoke_with_retry(
            operation_name=f"{self.role_name}.{task_name}.json_text",
            invoke_fn=lambda: self.model.invoke(messages),
        )
        text = self._extract_text_content(result)
        return self._parse_structured_text(text=text, response_model=response_model)

    def _should_fallback_to_json_text(self, error: Exception) -> bool:
        message = str(error)
        fallback_markers = (
            "tool_choice",
            "Thinking mode does not support this tool_choice",
            "response_format",
            "This response_format type is unavailable now",
            "Failed to parse structured output",
            "Native structured output expected valid JSON",
            "StructuredOutputValidationError",
            "invalid_request_error",
        )
        return any(marker in message for marker in fallback_markers)

    def _invoke_structured(
        self,
        task_name: str,
        payload: dict[str, Any],
        response_model: type[StructuredModel],
    ) -> StructuredModel:
        task_prompt = self._task_prompt(task_name, payload)
        if not self.tools:
            return self._invoke_structured_json_text(
                task_prompt=task_prompt,
                task_name=task_name,
                payload=payload,
                response_model=response_model,
            )
        try:
            user_message = {
                "role": "user",
                "content": json.dumps({"task_name": task_name, "payload": payload}, ensure_ascii=False, indent=2),
            }
            # 每轮重试都重建一次 agent，使 agent 内部绑定到最新的大模型连接。
            result = self._invoke_with_retry(
                operation_name=f"{self.role_name}.{task_name}.structured_agent",
                invoke_fn=lambda: create_agent(
                    model=self.model,
                    tools=self.tools,
                    system_prompt=f"{self.system_prompt}\n\n{task_prompt}".strip(),
                    response_format=response_model,
                ).invoke({"messages": [user_message]}),
            )
            structured = result["structured_response"]
            if isinstance(structured, response_model):
                return structured
            return response_model.model_validate(structured)
        except Exception as error:
            if self._should_fallback_to_json_text(error):
                return self._invoke_structured_json_text(
                    task_prompt=task_prompt,
                    task_name=task_name,
                    payload=payload,
                    response_model=response_model,
                )
            raise


class StudentAgent(BaseRoleAgent):
    def __init__(self, settings: AppSettings, tools: list) -> None:
        super().__init__(settings=settings, role_name="student", tools=tools)

    def summarize_literature(self, payload: dict[str, Any]) -> LiteratureSynthesis:
        return self._invoke_structured("summarize_literature", payload, LiteratureSynthesis)

    def propose_innovations(self, payload: dict[str, Any]) -> InnovationProposal:
        return self._invoke_structured("propose_innovations", payload, InnovationProposal)

    def design_experiment(self, payload: dict[str, Any]) -> ExperimentPlan:
        return self._invoke_structured("design_experiment", payload, ExperimentPlan)

    def analyze_results(self, payload: dict[str, Any]) -> ResultAnalysis:
        return self._invoke_structured("analyze_results", payload, ResultAnalysis)

    def draft_manuscript(self, payload: dict[str, Any]) -> ManuscriptDraft:
        return self._invoke_structured("draft_manuscript", payload, ManuscriptDraft)


class AdvisorAgent(BaseRoleAgent):
    def __init__(self, settings: AppSettings, tools: list) -> None:
        super().__init__(settings=settings, role_name="advisor", tools=tools)

    def review_innovations(self, payload: dict[str, Any]) -> InnovationReview:
        return self._invoke_structured("review_innovations", payload, InnovationReview)

    def review_manuscript(self, payload: dict[str, Any]) -> PaperReview:
        return self._invoke_structured("review_manuscript", payload, PaperReview)

    def review_experiment_results(self, payload: dict[str, Any]) -> ExperimentGateReview:
        return self._invoke_structured("review_experiment_results", payload, ExperimentGateReview)


class ReviewerAgent(BaseRoleAgent):
    def __init__(self, settings: AppSettings, tools: list) -> None:
        super().__init__(settings=settings, role_name="reviewer", tools=tools)

    def blind_review(self, payload: dict[str, Any]) -> BlindReview:
        return self._invoke_structured("blind_review", payload, BlindReview)


__all__ = ["AdvisorAgent", "BaseRoleAgent", "ReviewerAgent", "StudentAgent"]
