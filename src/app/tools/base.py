from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.schemas import AgentTool, ToolResult
from app.models.user import User


@dataclass(frozen=True)
class ToolContext:
    session: AsyncSession
    user: User


class Tool(Protocol):
    definition: AgentTool

    async def execute(self, arguments: dict[str, object], context: ToolContext) -> ToolResult:
        ...


def object_schema(properties: dict[str, object], required: list[str]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def string_schema(description: str, enum: list[str] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": "string",
        "description": description,
    }
    if enum:
        payload["enum"] = enum
    return payload


def integer_schema(description: str, default: int | None = None, minimum: int | None = None, maximum: int | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": "integer",
        "description": description,
    }
    if default is not None:
        payload["default"] = default
    if minimum is not None:
        payload["minimum"] = minimum
    if maximum is not None:
        payload["maximum"] = maximum
    return payload


def get_required_string(arguments: dict[str, object], name: str) -> str:
    value = arguments.get(name)
    if value is None or not str(value).strip():
        raise ValueError(f"{name} cannot be empty")
    return str(value).strip()


def get_optional_string(arguments: dict[str, object], name: str) -> str | None:
    value = arguments.get(name)
    if value is None or not str(value).strip():
        return None
    return str(value).strip()


def get_int(arguments: dict[str, object], name: str, default: int, minimum: int, maximum: int) -> int:
    raw = arguments.get(name)
    if raw is None or not str(raw).strip():
        return default
    value = int(raw) if not isinstance(raw, int) else raw
    return max(minimum, min(maximum, value))
