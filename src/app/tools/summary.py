from app.agents.schemas import AgentTool, ToolResult
from app.integrations.llm_client import ChatMessage
from app.rag.references import ReferenceMapper
from app.rag.retriever import HybridRetriever
from app.services.llm_service import LLMService
from app.tools.base import ToolContext, get_int, get_required_string, integer_schema, object_schema, string_schema

DEFAULT_MAX_DOCS = 5
MAX_SUMMARY_DOCS = 20


class SummaryTool:
    definition = AgentTool(
        name="generate_summary",
        description=(
            "Generate a structured summary for a topic using knowledge-base documents. Call this when the user asks "
            "to summarize, organize, extract, or synthesize knowledge-base content. This tool internally retrieves "
            "sources and calls the LLM for summarization."
        ),
        parameters=object_schema(
            {
                "topic": string_schema("The topic to summarize from the knowledge base."),
                "maxDocs": integer_schema("Maximum related chunks used for summary.", default=DEFAULT_MAX_DOCS, minimum=1, maximum=MAX_SUMMARY_DOCS),
            },
            ["topic"],
        ),
    )

    async def execute(self, arguments: dict[str, object], context: ToolContext) -> ToolResult:
        topic = get_required_string(arguments, "topic")
        max_docs = get_int(arguments, "maxDocs", DEFAULT_MAX_DOCS, 1, MAX_SUMMARY_DOCS)
        retriever = HybridRetriever(context.session)
        try:
            _, _, _, results = await retriever.retrieve_results(
                query=topic,
                top_k=max_docs,
                current_user=context.user,
            )
        finally:
            await retriever.close()

        mapper = ReferenceMapper()
        reference_mappings = mapper.build_mapping(results, topic)
        context_text = mapper.build_context(results, topic)
        summary = await LLMService().complete_messages(
            [
                ChatMessage(
                    role="system",
                    content="你是企业知识库摘要助手。请只基于提供的知识库片段，输出结构化、准确、可核对的中文摘要。",
                ),
                ChatMessage(
                    role="user",
                    content=f"{context_text}\n\n请围绕主题「{topic}」生成摘要，并在关键结论后标注来源编号。",
                ),
            ],
            temperature=0.3,
        )
        content = f"主题：{topic}\n检索片段数：{len(results)}\n\n{summary}"
        return ToolResult(
            tool=self.definition.name,
            success=True,
            content=content,
            data={
                "topic": topic,
                "maxDocs": max_docs,
                "sourceCount": len(results),
            },
            reference_mappings=reference_mappings,
        )
