import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx


class LLMConfigurationError(RuntimeError):
    pass


class LLMProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str | None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None

    def to_api_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            payload["name"] = self.name
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            payload["tool_calls"] = self.tool_calls
        return payload


@dataclass(frozen=True)
class ChatToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatCompletionResult:
    content: str
    tool_calls: list[ChatToolCall] = field(default_factory=list)


class OpenAICompatibleChatClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        if not api_key:
            raise LLMConfigurationError("LLM API key is required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": [message.to_api_dict() for message in messages],
            "stream": True,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        timeout = httpx.Timeout(self.timeout_seconds, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    detail = await response.aread()
                    raise LLMProviderError(
                        f"LLM request failed with status {response.status_code}: "
                        f"{detail.decode('utf-8', errors='replace')}"
                    )

                async for line in response.aiter_lines():
                    chunk = self._parse_sse_line(line)
                    if chunk:
                        yield chunk

    async def complete_chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
    ) -> ChatCompletionResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [message.to_api_dict() for message in messages],
            "stream": False,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(self.timeout_seconds, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
        if response.status_code >= 400:
            raise LLMProviderError(
                f"LLM request failed with status {response.status_code}: {response.text}"
            )

        payload = response.json()
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return ChatCompletionResult(content="")
        message = choices[0].get("message") or {}
        if not isinstance(message, dict):
            return ChatCompletionResult(content="")
        content = message.get("content")
        raw_tool_calls = message.get("tool_calls")
        return ChatCompletionResult(
            content=content if isinstance(content, str) else "",
            tool_calls=self._parse_tool_calls(raw_tool_calls),
        )

    @staticmethod
    def _parse_sse_line(line: str) -> str | None:
        if not line.startswith("data:"):
            return None

        data = line.removeprefix("data:").strip()
        if not data or data == "[DONE]":
            return None

        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return None

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return None

        delta = choices[0].get("delta")
        if not isinstance(delta, dict):
            return None

        content = delta.get("content")
        return content if isinstance(content, str) else None

    @staticmethod
    def _parse_tool_calls(raw_tool_calls: object) -> list[ChatToolCall]:
        if not isinstance(raw_tool_calls, list):
            return []
        tool_calls: list[ChatToolCall] = []
        for raw_tool_call in raw_tool_calls:
            if not isinstance(raw_tool_call, dict):
                continue
            function = raw_tool_call.get("function")
            if not isinstance(function, dict):
                continue
            name = function.get("name")
            if not isinstance(name, str) or not name:
                continue
            raw_arguments = function.get("arguments") or "{}"
            arguments: dict[str, Any]
            if isinstance(raw_arguments, str):
                try:
                    parsed = json.loads(raw_arguments)
                except json.JSONDecodeError:
                    parsed = {}
                arguments = parsed if isinstance(parsed, dict) else {}
            elif isinstance(raw_arguments, dict):
                arguments = raw_arguments
            else:
                arguments = {}
            tool_calls.append(
                ChatToolCall(
                    id=str(raw_tool_call.get("id") or name),
                    name=name,
                    arguments=arguments,
                )
            )
        return tool_calls
