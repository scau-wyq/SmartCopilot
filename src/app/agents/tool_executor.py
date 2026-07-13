import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.schemas import ToolCall, ToolEvent, ToolResult
from app.agents.tool_registry import ToolRegistry
from app.core.security import now_millis
from app.models.user import User
from app.tools.base import ToolContext

TOOL_TIMEOUT_SECONDS = 30

ToolEventCallback = Callable[[ToolEvent], Awaitable[None]]


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, session: AsyncSession, user: User) -> None:
        self.registry = registry
        self.context = ToolContext(session=session, user=user)

    async def execute(self, tool_call: ToolCall, on_event: ToolEventCallback | None = None) -> ToolResult:
        await self._emit(tool_call, "executing", on_event)
        try:
            tool = self.registry.get(tool_call.name)
            result = await asyncio.wait_for(
                tool.execute(tool_call.arguments, self.context),
                timeout=TOOL_TIMEOUT_SECONDS,
            )
        except Exception as exception:
            await self._emit(tool_call, "failed", on_event)
            return ToolResult(
                tool=tool_call.name,
                success=False,
                content=f"工具 {tool_call.name} 执行失败: {exception}",
                data={"error": str(exception)},
            )

        await self._emit(tool_call, "success", on_event)
        return result

    async def _emit(self, tool_call: ToolCall, status: str, on_event: ToolEventCallback | None) -> None:
        if on_event is None:
            return
        await on_event(
            ToolEvent(
                id=tool_call.id,
                tool=tool_call.name,
                status=status,  # type: ignore[arg-type]
                timestamp=now_millis(),
            )
        )
