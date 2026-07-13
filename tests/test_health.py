import pytest

from app.api.routes.health import health_check


@pytest.mark.asyncio
async def test_health_check() -> None:
    assert await health_check() == {"code": 200, "message": "ok", "data": {"status": "UP"}}
