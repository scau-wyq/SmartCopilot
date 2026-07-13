from collections.abc import AsyncIterator
from typing import Any

from app.core.config import settings
from app.integrations.llm_client import ChatCompletionResult, ChatMessage, LLMConfigurationError, OpenAICompatibleChatClient
from app.services.model_preference_service import ChatModelConfig, ModelPreferenceService


class LLMService:
    def _get_client(self, model_config: ChatModelConfig | None = None) -> OpenAICompatibleChatClient:
        resolved = model_config or ModelPreferenceService.default_free_model()
        return OpenAICompatibleChatClient(
            base_url=resolved.base_url,
            api_key=resolved.api_key,
            model=resolved.model,
            timeout_seconds=settings.llm_request_timeout_seconds,
        )

    def create_langchain_chat_model(
        self,
        temperature: float = 0.7,
        model_config: ChatModelConfig | None = None,
    ):
        from langchain_openai import ChatOpenAI

        resolved = model_config or ModelPreferenceService.default_free_model()
        base_url = resolved.base_url
        api_key = resolved.api_key
        model = resolved.model
        if not api_key:
            raise LLMConfigurationError("LLM API key is not configured")

        return ChatOpenAI(
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            model=model,
            temperature=temperature,
            timeout=settings.llm_request_timeout_seconds,
        )

    async def complete_messages(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        model_config: ChatModelConfig | None = None,
    ) -> str:
        result = await self._get_client(model_config).complete_chat(messages, temperature=temperature)
        return result.content

    async def plan_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        temperature: float = 0.2,
        model_config: ChatModelConfig | None = None,
    ) -> ChatCompletionResult:
        return await self._get_client(model_config).complete_chat(messages, tools=tools, temperature=temperature)

    async def stream_messages(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        model_config: ChatModelConfig | None = None,
    ) -> AsyncIterator[str]:
        async for chunk in self._get_client(model_config).stream_chat(messages, temperature=temperature):
            yield chunk

    async def stream_answer(self, question: str, rag_context: str | None = None) -> AsyncIterator[str]:
        system_prompt = (
            "You are SmartCopilot's enterprise knowledge assistant. "
            "Answer clearly and stay faithful to the user's question."
        )
        if rag_context:
            system_prompt = (
                "You are SmartCopilot's enterprise knowledge assistant. "
                "Use the provided knowledge-base context as the primary evidence. "
                "If the context is relevant, cite sources in Chinese exactly like "
                "'来源#1: 文件名 | 第2页'. If the context is insufficient, say so clearly."
            )
            user_content = f"{rag_context}\n\n请回答用户问题：{question}"
        else:
            user_content = question

        messages = [
            ChatMessage(
                role="system",
                content=system_prompt,
            ),
            ChatMessage(role="user", content=user_content),
        ]
        async for chunk in self._get_client().stream_chat(messages):
            yield chunk


llm_service = LLMService()
