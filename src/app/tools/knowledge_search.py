from app.agents.schemas import AgentTool, ToolResult
from app.rag.references import ReferenceMapper
from app.rag.retriever import HybridRetriever
from app.rag.schemas import SearchResult
from app.tools.base import ToolContext, get_int, get_required_string, integer_schema, object_schema, string_schema

DEFAULT_TOP_K = 5
MAX_SEARCH_DOCS = 20


class KnowledgeSearchTool:
    definition = AgentTool(
        name="search_knowledge",
        description=(
            "Search the enterprise knowledge base for document chunks relevant to the user question. "
            "Call this when the answer may depend on uploaded files, internal enterprise knowledge, "
            "product/project/system facts, definitions, processes, implementation details, or citations. "
            "Do not call for greetings, pure open-ended creation, or when the user explicitly says not to search."
        ),
        parameters=object_schema(
            {
                "query": string_schema(
                    "The query used for knowledge retrieval. Preserve core entities, acronyms, and constraints."
                ),
                "topK": integer_schema("Number of chunks to return.", default=DEFAULT_TOP_K, minimum=1, maximum=MAX_SEARCH_DOCS),
            },
            ["query"],
        ),
    )

    async def execute(self, arguments: dict[str, object], context: ToolContext) -> ToolResult:
        query = get_required_string(arguments, "query")
        top_k = get_int(arguments, "topK", DEFAULT_TOP_K, 1, MAX_SEARCH_DOCS)
        retriever = HybridRetriever(context.session)
        try:
            _, _, _, results = await retriever.retrieve_results(
                query=query,
                top_k=top_k,
                current_user=context.user,
            )
        finally:
            await retriever.close()

        mapper = ReferenceMapper()
        reference_mappings = mapper.build_mapping(results, query)
        content = self._format_results(results)
        return ToolResult(
            tool=self.definition.name,
            success=True,
            content=content,
            data={
                "query": query,
                "topK": top_k,
                "results": [self._to_response(result) for result in results],
            },
            reference_mappings=reference_mappings,
        )

    def _format_results(self, results: list[SearchResult]) -> str:
        if not results:
            return "未检索到相关知识库片段。"

        lines = [
            f"检索到 {len(results)} 个知识库片段。请基于这些片段回答用户问题；如果片段不足，请明确说明依据有限。"
        ]
        for index, result in enumerate(results, start=1):
            file_name = result.file_name or result.file_md5
            page = f", page={result.page_number}" if result.page_number else ""
            lines.append(
                f"[{index}] {file_name} (fileMd5={result.file_md5}, chunkId={result.chunk_id}{page}, "
                f"score={result.score:.4f})\n{self._limit(result.text_content, 1200)}"
            )
        return "\n\n".join(lines)

    def _to_response(self, result: SearchResult) -> dict[str, object]:
        return {
            "fileMd5": result.file_md5,
            "fileName": result.file_name,
            "chunkId": result.chunk_id,
            "textContent": result.text_content,
            "score": result.score,
            "pageNumber": result.page_number,
            "anchorText": result.anchor_text,
            "retrievalMode": result.retrieval_mode,
        }

    @staticmethod
    def _limit(text: str, max_chars: int) -> str:
        return text if len(text) <= max_chars else text[:max_chars] + "..."
