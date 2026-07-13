from app.agents.schemas import AgentTool, ToolResult
from app.core.redis import redis_client
from app.core.security import now_millis
from app.tools.base import ToolContext, get_optional_string, get_required_string, object_schema, string_schema


class FeedbackTool:
    definition = AgentTool(
        name="submit_feedback",
        description=(
            "Record explicit user feedback about the current answer. Call only when the user clearly expresses "
            "satisfaction, dissatisfaction, correction, like, dislike, or asks to record feedback."
        ),
        parameters=object_schema(
            {
                "rating": string_schema("Feedback rating. Must be good or bad.", enum=["good", "bad"]),
                "reason": string_schema("Optional feedback reason."),
            },
            ["rating"],
        ),
    )

    async def execute(self, arguments: dict[str, object], context: ToolContext) -> ToolResult:
        rating = get_required_string(arguments, "rating").lower()
        if rating not in {"good", "bad"}:
            raise ValueError("rating must be good or bad")
        reason = get_optional_string(arguments, "reason")
        key = f"feedback:{context.user.id}"
        field = str(now_millis())
        value = f"rating={rating}" if not reason else f"rating={rating}; reason={reason}"
        await redis_client.hset(key, field, value)
        data = {
            "key": key,
            "field": field,
            "rating": rating,
            "reason": reason,
        }
        return ToolResult(
            tool=self.definition.name,
            success=True,
            content=f"已记录用户反馈: {value}",
            data=data,
        )
