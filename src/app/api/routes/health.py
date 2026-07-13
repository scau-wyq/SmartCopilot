from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, object]:
    return {"code": 200, "message": "ok", "data": {"status": "UP"}}
