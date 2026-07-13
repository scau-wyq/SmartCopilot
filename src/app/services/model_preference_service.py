from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import ApiError
from app.core.config import settings
from app.integrations.llm_client import ChatMessage, OpenAICompatibleChatClient
from app.models.billing import UserModelPreference
from app.models.user import User
from app.repositories.billing_repository import BillingRepository
from app.services.secret_service import SecretService, mask_secret


class ModelPreferencePayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    model_mode: str = Field(alias="modelMode")


class CustomLLMPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    base_url: str = Field(alias="baseUrl")
    model: str
    api_key: str | None = Field(default=None, alias="apiKey")


@dataclass(frozen=True)
class ChatModelConfig:
    mode: str
    base_url: str
    api_key: str
    model: str
    billable: bool


class ModelPreferenceService:
    valid_modes = {"FREE", "PAID", "CUSTOM"}

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = BillingRepository(session)
        self.secrets = SecretService()

    async def get_or_create_preference(self, user_id: int) -> UserModelPreference:
        preference = await self.repository.get_model_preference(user_id)
        if preference is not None:
            return preference
        preference = UserModelPreference(user_id=user_id, model_mode="FREE")
        await self.repository.save_model_preference(preference)
        await self.session.flush()
        return preference

    async def set_model_preference(self, user: User, payload: ModelPreferencePayload) -> dict[str, object]:
        mode = self._normalize_mode(payload.model_mode)
        preference = await self.get_or_create_preference(int(user.id))
        if mode == "CUSTOM" and not self._has_custom_config(preference):
            raise ApiError(400, "Custom model is not configured")
        preference.model_mode = mode
        await self.session.commit()
        return await self.to_profile_model_settings(user)

    async def save_custom_llm(self, user: User, payload: CustomLLMPayload) -> dict[str, object]:
        base_url = payload.base_url.strip().rstrip("/")
        model = payload.model.strip()
        if not base_url or not model:
            raise ApiError(400, "Base URL and model are required")
        preference = await self.get_or_create_preference(int(user.id))
        preference.custom_base_url = base_url
        preference.custom_model = model
        if payload.api_key is not None and payload.api_key.strip():
            preference.custom_api_key_encrypted = self.secrets.encrypt(payload.api_key.strip())
        await self.session.commit()
        return await self.to_profile_model_settings(user)

    async def test_custom_llm(self, user: User, payload: CustomLLMPayload) -> dict[str, object]:
        api_key = payload.api_key
        if not api_key:
            preference = await self.get_or_create_preference(int(user.id))
            api_key = self._decrypt_api_key(preference)
        client = OpenAICompatibleChatClient(
            base_url=payload.base_url,
            api_key=api_key or "",
            model=payload.model,
            timeout_seconds=min(settings.llm_request_timeout_seconds, 20.0),
        )
        await client.complete_chat([ChatMessage(role="user", content="ping")], temperature=0)
        return {"success": True, "message": "Model connection succeeded"}

    async def to_profile_model_settings(self, user: User) -> dict[str, object]:
        preference = await self.get_or_create_preference(int(user.id))
        api_key = self._decrypt_api_key(preference)
        return {
            "modelMode": preference.model_mode,
            "customModel": {
                "baseUrl": preference.custom_base_url or "",
                "model": preference.custom_model or "",
                "hasApiKey": bool(api_key),
                "maskedApiKey": mask_secret(api_key),
            },
        }

    async def model_options(self, user: User, balances: dict[str, int]) -> dict[str, object]:
        settings_payload = await self.to_profile_model_settings(user)
        return {
            "defaultMode": settings_payload["modelMode"],
            "options": [
                {
                    "mode": "FREE",
                    "label": "免费模型",
                    "model": self._free_model_name(),
                    "enabled": bool(self._free_api_key()),
                    "billable": False,
                },
                {
                    "mode": "PAID",
                    "label": "计费模型",
                    "model": self._paid_model_name(),
                    "enabled": bool(self._paid_api_key()) and balances.get("llmToken", 0) > 0,
                    "billable": True,
                    "remainingTokens": balances.get("llmToken", 0),
                },
                {
                    "mode": "CUSTOM",
                    "label": "我的模型",
                    "model": settings_payload["customModel"]["model"],
                    "enabled": bool(settings_payload["customModel"]["hasApiKey"]),
                    "billable": False,
                },
            ],
            "customModel": settings_payload["customModel"],
            "balances": balances,
        }

    async def resolve_chat_model(self, user: User, requested_mode: str | None) -> ChatModelConfig:
        preference = await self.get_or_create_preference(int(user.id))
        mode = self._normalize_mode(requested_mode or preference.model_mode)
        if mode == "CUSTOM":
            api_key = self._decrypt_api_key(preference)
            if not preference.custom_base_url or not preference.custom_model or not api_key:
                raise ApiError(400, "Custom model is not configured")
            return ChatModelConfig(
                mode="CUSTOM",
                base_url=preference.custom_base_url,
                api_key=api_key,
                model=preference.custom_model,
                billable=False,
            )
        if mode == "PAID":
            self._ensure_configured(settings.paid_llm_base_url, settings.paid_llm_api_key, settings.paid_llm_model, "Paid")
            return ChatModelConfig(
                mode="PAID",
                base_url=settings.paid_llm_base_url,
                api_key=settings.paid_llm_api_key,
                model=settings.paid_llm_model,
                billable=True,
            )
        self._ensure_configured(settings.free_llm_base_url, settings.free_llm_api_key, settings.free_llm_model, "Free")
        return ChatModelConfig(
            mode="FREE",
            base_url=settings.free_llm_base_url,
            api_key=settings.free_llm_api_key,
            model=settings.free_llm_model,
            billable=False,
        )

    @staticmethod
    def default_free_model() -> ChatModelConfig:
        ModelPreferenceService._ensure_configured(
            settings.free_llm_base_url,
            settings.free_llm_api_key,
            settings.free_llm_model,
            "Free",
        )
        return ChatModelConfig(
            mode="FREE",
            base_url=settings.free_llm_base_url,
            api_key=settings.free_llm_api_key,
            model=settings.free_llm_model,
            billable=False,
        )

    def _decrypt_api_key(self, preference: UserModelPreference) -> str:
        if not preference.custom_api_key_encrypted:
            return ""
        return self.secrets.decrypt(preference.custom_api_key_encrypted)

    def _has_custom_config(self, preference: UserModelPreference) -> bool:
        return bool(preference.custom_base_url and preference.custom_model and preference.custom_api_key_encrypted)

    def _normalize_mode(self, value: str | None) -> str:
        mode = (value or "FREE").upper()
        if mode not in self.valid_modes:
            raise ApiError(400, "Unsupported model mode")
        return mode

    @staticmethod
    def _free_api_key() -> str:
        return settings.free_llm_api_key

    @staticmethod
    def _paid_api_key() -> str:
        return settings.paid_llm_api_key

    @staticmethod
    def _free_model_name() -> str:
        return settings.free_llm_model

    @staticmethod
    def _paid_model_name() -> str:
        return settings.paid_llm_model

    @staticmethod
    def _ensure_configured(base_url: str, api_key: str, model: str, label: str) -> None:
        if not base_url or not api_key or not model:
            raise ApiError(500, f"{label} LLM configuration is incomplete")
