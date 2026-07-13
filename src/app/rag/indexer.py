from app.core.config import settings
from app.rag.schemas import SearchResult, TextChunk
from elasticsearch import AsyncElasticsearch, BadRequestError


class VectorIndex:
    def __init__(self) -> None:
        self.client = AsyncElasticsearch(settings.elasticsearch_url)
        self.index_name = settings.elasticsearch_index_name

    async def bulk_index(self, chunks: list[TextChunk], vectors: list[list[float]]) -> None:
        if not chunks:
            return
        await self.ensure_index()
        operations: list[dict[str, object]] = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            document_id = f"{chunk.file_md5}:{chunk.chunk_id}"
            operations.append({"index": {"_index": self.index_name, "_id": document_id}})
            operations.append(
                {
                    "fileMd5": chunk.file_md5,
                    "chunkId": chunk.chunk_id,
                    "textContent": chunk.text_content,
                    "pageNumber": chunk.page_number,
                    "anchorText": chunk.anchor_text,
                    "vector": vector,
                    "userId": chunk.user_id,
                    "orgTag": chunk.org_tag,
                    "isPublic": chunk.is_public,
                }
            )
        response = await self.client.bulk(operations=operations, refresh=True)
        if response.get("errors"):
            raise RuntimeError(f"Elasticsearch bulk index failed: {response}")

    async def delete_by_file_md5(self, file_md5: str) -> int:
        await self.ensure_index()
        response = await self.client.delete_by_query(
            index=self.index_name,
            query={"term": {"fileMd5": file_md5}},
            refresh=True,
            conflicts="proceed",
        )
        return int(response.get("deleted", 0))

    async def hybrid_search(
        self,
        *,
        query: str,
        query_vector: list[float],
        top_k: int,
        user_id: str,
        org_tags: list[str],
        is_admin: bool,
    ) -> list[SearchResult]:
        await self.ensure_index()
        recall_k = max(top_k * 30, top_k)
        response = await self.client.search(
            index=self.index_name,
            knn={
                "field": "vector",
                "query_vector": query_vector,
                "k": recall_k,
                "num_candidates": recall_k,
                "filter": self._permission_filter(user_id, org_tags, is_admin),
            },
            query={"match": {"textContent": query}},
            rescore={
                "window_size": recall_k,
                "query": {
                    "query_weight": 0.2,
                    "rescore_query_weight": 1.0,
                    "rescore_query": {
                        "match": {
                            "textContent": {
                                "query": query,
                                "operator": "and",
                            }
                        }
                    },
                },
            },
            size=top_k,
        )
        return self._to_search_results(response, "HYBRID")

    async def text_search(
        self,
        *,
        query: str,
        top_k: int,
        user_id: str,
        org_tags: list[str],
        is_admin: bool,
    ) -> list[SearchResult]:
        await self.ensure_index()
        response = await self.client.search(
            index=self.index_name,
            query={
                "bool": {
                    "must": [{"match": {"textContent": query}}],
                    "filter": [self._permission_filter(user_id, org_tags, is_admin)],
                }
            },
            size=top_k,
        )
        return self._to_search_results(response, "TEXT_ONLY")

    async def stats(self) -> dict[str, object]:
        await self.ensure_index()
        response = await self.client.indices.stats(index=self.index_name)
        indices = response.get("indices", {}) if isinstance(response, dict) else {}
        index_stats = indices.get(self.index_name, {}) if isinstance(indices, dict) else {}
        total = index_stats.get("total", {}) if isinstance(index_stats, dict) else {}
        docs = total.get("docs", {}) if isinstance(total, dict) else {}
        store = total.get("store", {}) if isinstance(total, dict) else {}
        return {
            "index": self.index_name,
            "fragmentCount": docs.get("count", 0) if isinstance(docs, dict) else 0,
            "deletedFragmentCount": docs.get("deleted") if isinstance(docs, dict) else None,
            "storeSizeInBytes": store.get("size_in_bytes") if isinstance(store, dict) else None,
        }

    async def ensure_index(self) -> None:
        try:
            await self.client.indices.create(
                index=self.index_name,
                mappings={
                    "properties": {
                        "fileMd5": {"type": "keyword"},
                        "chunkId": {"type": "integer"},
                        "textContent": {"type": "text"},
                        "pageNumber": {"type": "integer"},
                        "anchorText": {"type": "text"},
                        "vector": {
                            "type": "dense_vector",
                            "dims": settings.embedding_dimension,
                            "index": True,
                            "similarity": "cosine",
                        },
                        "userId": {"type": "keyword"},
                        "orgTag": {"type": "keyword"},
                        "isPublic": {"type": "boolean"},
                    }
                },
            )
        except BadRequestError as exception:
            if "resource_already_exists_exception" not in str(exception):
                raise

    async def close(self) -> None:
        await self.client.close()

    def _permission_filter(self, user_id: str, org_tags: list[str], is_admin: bool) -> dict[str, object]:
        if is_admin:
            return {"match_all": {}}
        should: list[dict[str, object]] = [
            {"term": {"userId": user_id}},
            {"term": {"isPublic": True}},
            {"bool": {"must_not": [{"exists": {"field": "orgTag"}}]}},
            {"term": {"orgTag": ""}},
            {"term": {"orgTag": "DEFAULT"}},
        ]
        for org_tag in org_tags:
            should.append({"term": {"orgTag": org_tag}})
        return {"bool": {"should": should, "minimum_should_match": 1}}

    def _to_search_results(self, response: dict[str, object], retrieval_mode: str) -> list[SearchResult]:
        hits = response.get("hits", {})
        if not isinstance(hits, dict):
            return []
        raw_hits = hits.get("hits", [])
        if not isinstance(raw_hits, list):
            return []

        results: list[SearchResult] = []
        for hit in raw_hits:
            if not isinstance(hit, dict):
                continue
            source = hit.get("_source") or {}
            if not isinstance(source, dict):
                continue
            results.append(
                SearchResult(
                    file_md5=str(source.get("fileMd5") or ""),
                    chunk_id=int(source.get("chunkId") or 0),
                    text_content=str(source.get("textContent") or ""),
                    score=float(hit.get("_score") or 0),
                    page_number=source.get("pageNumber"),
                    anchor_text=source.get("anchorText"),
                    user_id=str(source.get("userId") or ""),
                    org_tag=source.get("orgTag"),
                    is_public=bool(source.get("isPublic") or False),
                    retrieval_mode=retrieval_mode,
                )
            )
        return results
