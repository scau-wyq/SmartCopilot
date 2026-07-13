from dataclasses import dataclass, field
from typing import Any, Literal


ToolStatus = Literal["executing", "success", "failed"]


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    parameters: dict[str, Any]

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    tool: str
    success: bool
    content: str
    data: dict[str, Any] = field(default_factory=dict)
    reference_mappings: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class ToolEvent:
    tool: str
    status: ToolStatus
    id: str | None = None
    timestamp: int | None = None

    def to_api_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tool": self.tool,
            "status": self.status,
        }
        if self.id:
            payload["id"] = self.id
        if self.timestamp is not None:
            payload["timestamp"] = self.timestamp
        return payload


@dataclass
class AgentStreamEvent:
    type: Literal["chunk", "tool"]
    chunk: str = ""
    tool_event: ToolEvent | None = None
