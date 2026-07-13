from app.agents.schemas import AgentTool, ToolResult
from app.rag.indexer import VectorIndex
from app.repositories.file_upload_repository import FileUploadRepository
from app.tools.base import ToolContext, object_schema


class KnowledgeStatsTool:
    definition = AgentTool(
        name="knowledge_stats",
        description=(
            "Return knowledge-base statistics, including accessible document count, Elasticsearch chunk count, "
            "deleted chunk count, index store size, and latest document update time. Only call when the user asks "
            "about knowledge-base scale, document count, chunk count, index state, or latest update time."
        ),
        parameters=object_schema({}, []),
    )

    async def execute(self, arguments: dict[str, object], context: ToolContext) -> ToolResult:
        repository = FileUploadRepository(context.session)
        uploads = await repository.list_accessible(
            user_id=str(context.user.id),
            org_tags=context.user.org_tag_list,
            is_admin=context.user.role == "ADMIN",
        )

        latest_updated_at = None
        if uploads:
            latest = max(uploads, key=lambda upload: upload.merged_at or upload.created_at)
            value = latest.merged_at or latest.created_at
            latest_updated_at = value.isoformat() if value else None

        index = VectorIndex()
        try:
            stats = await index.stats()
        finally:
            await index.close()

        data = {
            "index": stats.get("index"),
            "documentCount": len(uploads),
            "fragmentCount": stats.get("fragmentCount", 0),
            "deletedFragmentCount": stats.get("deletedFragmentCount"),
            "storeSizeInBytes": stats.get("storeSizeInBytes"),
            "latestUpdatedAt": latest_updated_at,
        }
        content = (
            "知识库统计："
            f"\n- 当前用户可访问文档数：{data['documentCount']}"
            f"\n- Elasticsearch 片段总数：{data['fragmentCount']}"
            f"\n- ES 已删除片段数：{self._dash(data['deletedFragmentCount'])}"
            f"\n- ES 存储大小(bytes)：{self._dash(data['storeSizeInBytes'])}"
            f"\n- 最近更新时间：{self._dash(data['latestUpdatedAt'])}"
        )
        return ToolResult(tool=self.definition.name, success=True, content=content, data=data)

    @staticmethod
    def _dash(value: object) -> object:
        return "-" if value is None else value
