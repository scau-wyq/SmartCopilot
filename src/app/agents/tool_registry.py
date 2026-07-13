from app.agents.schemas import AgentTool
from app.tools.base import Tool
from app.tools.feedback import FeedbackTool
from app.tools.knowledge_search import KnowledgeSearchTool
from app.tools.knowledge_stats import KnowledgeStatsTool
from app.tools.summary import SummaryTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {
            KnowledgeSearchTool.definition.name: KnowledgeSearchTool(),
            SummaryTool.definition.name: SummaryTool(),
            FeedbackTool.definition.name: FeedbackTool(),
            KnowledgeStatsTool.definition.name: KnowledgeStatsTool(),
        }

    def list_tools(self) -> list[AgentTool]:
        return [tool.definition for tool in self._tools.values()]

    def openai_tools(self) -> list[dict[str, object]]:
        return [tool.to_openai_tool() for tool in self.list_tools()]

    def get(self, name: str) -> Tool:
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f"Unknown tool: {name}")
        return tool
