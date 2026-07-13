from elasticsearch import AsyncElasticsearch, BadRequestError

from app.core.config import settings
from app.models.memory import UserMemory


class MemoryIndex:
    def __init__(self) -> None:
        self.client = AsyncElasticsearch(settings.elasticsearch_url)
        self.index_name = settings.long_term_memory_index_name

    async def index_memory(self, memory: UserMemory, vector: list[float]) -> None:
        await self.ensure_index()
        await self.client.index(
            index=self.index_name,
            id=str(memory.id),
            document={
                "memoryId": memory.id,
                "userId": str(memory.user_id),
                "content": memory.content,
                "memoryType": memory.memory_type,
                "sourceConversationId": memory.source_conversation_id,
                "confidence": memory.confidence,
                "status": memory.status,
                "vector": vector,
            },
            refresh=True,
        )

    async def search(self, *, user_id: int, query_vector: list[float], top_k: int) -> list[dict[str, object]]:
        await self.ensure_index()
        response = await self.client.search(
            index=self.index_name,
            knn={
                "field": "vector",
                "query_vector": query_vector,
                "k": max(top_k, 1),
                "num_candidates": max(top_k * 10, 10),
                "filter": {
                    "bool": {
                        "filter": [
                            {"term": {"userId": str(user_id)}},
                            {"term": {"status": "ACTIVE"}},
                        ]
                    }
                },
            },
            size=top_k,
        )
        hits = response.get("hits", {})
        raw_hits = hits.get("hits", []) if isinstance(hits, dict) else []
        results: list[dict[str, object]] = []
        for hit in raw_hits if isinstance(raw_hits, list) else []:
            if not isinstance(hit, dict):
                continue
            source = hit.get("_source") or {}
            if not isinstance(source, dict):
                continue
            source["score"] = float(hit.get("_score") or 0)
            results.append(source)
        return results

    async def ensure_index(self) -> None:
        try:
            await self.client.indices.create(
                index=self.index_name,
                mappings={
                    "properties": {
                        "memoryId": {"type": "long"},
                        "userId": {"type": "keyword"},
                        "content": {"type": "text"},
                        "memoryType": {"type": "keyword"},
                        "sourceConversationId": {"type": "keyword"},
                        "confidence": {"type": "float"},
                        "status": {"type": "keyword"},
                        "vector": {
                            "type": "dense_vector",
                            "dims": settings.embedding_dimension,
                            "index": True,
                            "similarity": "cosine",
                        },
                    }
                },
            )
        except BadRequestError as exception:
            if "resource_already_exists_exception" not in str(exception):
                raise

    async def close(self) -> None:
        await self.client.close()
