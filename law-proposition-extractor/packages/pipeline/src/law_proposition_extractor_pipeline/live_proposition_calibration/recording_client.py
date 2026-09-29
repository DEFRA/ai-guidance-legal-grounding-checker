"""Recording LLM client wrapper for live calibration provenance (evaluation-only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from law_proposition_extractor_llm.client import JuditLLMClient, TextCompletionResult
from openai.types.chat import ChatCompletionMessageParam


FORBIDDEN_CALL_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "headers",
        "credentials",
        "chain_of_thought",
        "reasoning",
        "thinking",
        "private_reasoning",
        "hidden_reasoning",
    }
)


def _redact_secrets(text: str) -> str:
    # Best-effort: strip common secret-looking substrings from accidental dumps.
    out = text
    for marker in ("sk-ant-", "sk-proj-", "Bearer ", "LITELLM_MASTER_KEY", "ANTHROPIC_API_KEY"):
        if marker in out:
            out = out.replace(marker, "[REDACTED]")
    return out


@dataclass
class RecordedProviderCall:
    call_index: int
    started_at: str
    ended_at: str
    latency_seconds: float
    model_alias: str
    resolved_model: str | None
    temperature: float
    system_prompt: str
    prompt_excerpt: str
    prompt_chars: int
    fragment_locator_hint: str | None
    raw_response: str
    finish_reason: str | None
    response_format: dict[str, Any] | None
    token_usage: dict[str, Any] | None
    provider_request_id: str | None
    is_retry: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_index": self.call_index,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "latency_seconds": self.latency_seconds,
            "model_alias": self.model_alias,
            "resolved_model": self.resolved_model,
            "temperature": self.temperature,
            "system_prompt": self.system_prompt,
            "prompt_excerpt": self.prompt_excerpt[:2000],
            "prompt_chars": self.prompt_chars,
            "fragment_locator_hint": self.fragment_locator_hint,
            "raw_response": self.raw_response,
            "finish_reason": self.finish_reason,
            "response_format": self.response_format,
            "token_usage": self.token_usage,
            "provider_request_id": self.provider_request_id,
            "is_retry": self.is_retry,
            "error": self.error,
        }


@dataclass
class RecordingJuditLLMClient:
    """Wraps JuditLLMClient; captures provenance without secrets or CoT."""

    inner: JuditLLMClient
    calls: list[RecordedProviderCall] = field(default_factory=list)
    _retry_window: bool = False

    @property
    def settings(self) -> Any:
        return self.inner.settings

    def mark_retry_window(self, active: bool = True) -> None:
        self._retry_window = active

    def list_models(self) -> list[str]:
        return self.inner.list_models()

    def complete_text(
        self,
        prompt: str,
        model: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        enforce_json_object: bool = False,
    ) -> str:
        return self.complete_text_result(
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            enforce_json_object=enforce_json_object,
        ).content

    def complete_text_result(
        self,
        prompt: str,
        model: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        enforce_json_object: bool = False,
        json_schema: dict[str, Any] | None = None,
    ) -> TextCompletionResult:
        started = datetime.now(UTC)
        t0 = perf_counter()
        locator_hint = None
        needle = "Fragment locator (traceability): "
        if needle in prompt:
            after = prompt.split(needle, 1)[1]
            locator_hint = after.split("\n", 1)[0].strip() or None

        messages: list[ChatCompletionMessageParam] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        request: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        response_format: dict[str, Any] | None = None
        if json_schema is not None:
            response_format = {"type": "json_schema", "json_schema": json_schema}
            request["response_format"] = response_format
        elif enforce_json_object:
            response_format = {"type": "json_object"}
            request["response_format"] = response_format

        error: str | None = None
        content = ""
        finish_reason: str | None = None
        resolved_model: str | None = None
        token_usage: dict[str, Any] | None = None
        provider_request_id: str | None = None
        try:
            response = self.inner.client.chat.completions.create(**request)
            choice = response.choices[0]
            content = _redact_secrets(choice.message.content or "")
            finish_reason = getattr(choice, "finish_reason", None)
            resolved_model = getattr(response, "model", None)
            usage = getattr(response, "usage", None)
            if usage is not None:
                token_usage = {
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                }
            provider_request_id = getattr(response, "id", None)
            result = TextCompletionResult(
                content=content,
                finish_reason=finish_reason,
                model=resolved_model,
                response_format=response_format,
            )
        except Exception as exc:
            error = str(exc)
            ended = datetime.now(UTC)
            self.calls.append(
                RecordedProviderCall(
                    call_index=len(self.calls) + 1,
                    started_at=started.isoformat(),
                    ended_at=ended.isoformat(),
                    latency_seconds=round(perf_counter() - t0, 3),
                    model_alias=model,
                    resolved_model=None,
                    temperature=temperature,
                    system_prompt=system_prompt or "",
                    prompt_excerpt=_redact_secrets(prompt[:500]),
                    prompt_chars=len(prompt),
                    fragment_locator_hint=locator_hint,
                    raw_response="",
                    finish_reason=None,
                    response_format=response_format,
                    token_usage=None,
                    provider_request_id=None,
                    is_retry=self._retry_window,
                    error=error,
                )
            )
            raise

        ended = datetime.now(UTC)
        self.calls.append(
            RecordedProviderCall(
                call_index=len(self.calls) + 1,
                started_at=started.isoformat(),
                ended_at=ended.isoformat(),
                latency_seconds=round(perf_counter() - t0, 3),
                model_alias=model,
                resolved_model=resolved_model,
                temperature=temperature,
                system_prompt=system_prompt or "",
                prompt_excerpt=_redact_secrets(prompt[:500]),
                prompt_chars=len(prompt),
                fragment_locator_hint=locator_hint,
                raw_response=content,
                finish_reason=finish_reason,
                response_format=response_format,
                token_usage=token_usage,
                provider_request_id=provider_request_id,
                is_retry=self._retry_window,
                error=None,
            )
        )
        return result


def assert_no_forbidden_fields(payload: Any, *, path: str = "$") -> list[str]:
    """Return paths that look like secrets / CoT / request headers."""
    errors: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_l = str(key).lower()
            child = f"{path}.{key}"
            if key_l in FORBIDDEN_CALL_KEYS or key_l.endswith("_api_key"):
                errors.append(f"forbidden field present: {child}")
            if key_l in {"authorization", "headers", "request_headers"}:
                errors.append(f"forbidden field present: {child}")
            errors.extend(assert_no_forbidden_fields(value, path=child))
    elif isinstance(payload, list):
        for idx, item in enumerate(payload):
            errors.extend(assert_no_forbidden_fields(item, path=f"{path}[{idx}]"))
    return errors
