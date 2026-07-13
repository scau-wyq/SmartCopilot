from fastapi import APIRouter, Query

from app.api.dependencies import CurrentUserDep, SessionDep
from app.api.responses import ok
from app.rag.retriever import HybridRetriever

router = APIRouter()


@router.get("/hybrid")
async def hybrid_search(
    current_user: CurrentUserDep,
    session: SessionDep,
    query: str = Query(..., min_length=1),
    top_k: int = Query(default=5, ge=1, le=50),
    topK: int | None = Query(default=None, ge=1, le=50),
    userId: str | None = Query(default=None),
) -> dict[str, object]:
    _ = userId
    retriever = HybridRetriever(session)
    try:
        data = await retriever.search(query=query, top_k=topK or top_k, current_user=current_user)
    finally:
        await retriever.close()
    return ok("Hybrid search successful", data["results"])
