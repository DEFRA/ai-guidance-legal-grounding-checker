import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from .settings import LLMSettings, settings


@dataclass(frozen=True)
class TextCompletionResult:
    content: str
    finish_reason: str | None = None
    model: str | None = None
    response_format: dict[str, Any] | None = None


class JuditLLMClient:
    def __init__(self, llm_settings: LLMSettings | None = None) -> None:
        self.settings = llm_settings or settings
        self.client = OpenAI(
            base_url=self.settings.base_url,
            api_key=self.settings.api_key,
        )

    def list_models(self) -> list[str]:
        models = self.client.models.list()
        return sorted(model.id for model in models.data)

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
            response_format = {
                "type": "json_schema",
                "json_schema": json_schema,
            }
            request["response_format"] = response_format
        elif enforce_json_object:
            response_format = {"type": "json_object"}
            request["response_format"] = response_format

        response = self.client.chat.completions.create(**request)
        choice = response.choices[0]
        content = choice.message.content
        return TextCompletionResult(
            content=content or "",
            finish_reason=getattr(choice, "finish_reason", None),
            model=getattr(response, "model", None),
            response_format=response_format,
        )

    def complete_json(
        self,
        prompt: str,
        model: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> Any:
        raw = self.complete_text(
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
        )
        return self._parse_json(raw)

    def extract_text(self, prompt: str) -> str:
        return self.complete_text(
            prompt=prompt,
            model=self.settings.local_extract_model,
            system_prompt="You extract structured legal propositions.",
            temperature=0.0,
        )

    def classify_text(self, prompt: str) -> str:
        return self.complete_text(
            prompt=prompt,
            model=self.settings.local_classify_model,
            system_prompt="You classify legal divergence carefully and tersely.",
            temperature=0.0,
        )

    def reason_text(self, prompt: str) -> str:
        return self.complete_text(
            prompt=prompt,
            model=self.settings.frontier_reason_model,
            system_prompt="You explain legal divergence in precise, audit-friendly language.",
            temperature=0.1,
        )

    def writeup_text(self, prompt: str) -> str:
        return self.complete_text(
            prompt=prompt,
            model=self.settings.frontier_writeup_model,
            system_prompt="You draft concise narrative summaries for legal comparison outputs.",
            temperature=0.2,
        )

    @staticmethod
    def _parse_json(raw: str) -> Any:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()
        return json.loads(text)


def main() -> None:
    client = JuditLLMClient()
    print(
        f"Law Proposition Extractor LLM client ready. Base URL={client.settings.base_url} "
        f"local_extract_model={client.settings.local_extract_model}"
    )


if __name__ == "__main__":
    main()
