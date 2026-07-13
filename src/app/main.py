from fastapi import FastAPI

from app.api.responses import ApiError, error
from app.api.router import api_router
from app.chat.websocket_handler import router as websocket_router
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    @app.exception_handler(ApiError)
    async def api_error_handler(_, exception: ApiError):
        return error(exception.status_code, exception.message, exception.data)

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    app.include_router(websocket_router)
    return app


app = create_app()
