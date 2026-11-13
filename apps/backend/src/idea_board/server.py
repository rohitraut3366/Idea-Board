import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.responses import JSONResponse

from idea_board.api import router
from idea_board.config import Settings
from idea_board.database import create_database_engine
from idea_board.middleware import RequestBodyLimitMiddleware
from idea_board.models import Idea

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_database_engine(app_settings)
        app.state.engine = engine
        try:
            try:
                with engine.connect() as connection:
                    connection.execute(select(Idea).limit(0))
            except DBAPIError:
                raise RuntimeError(
                    "Database or schema unavailable; "
                    "check the database and run migrations before startup"
                ) from None
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="Idea Board API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestBodyLimitMiddleware)
    app.include_router(router)

    async def database_error_handler(request: Request, error: Exception) -> JSONResponse:
        logger.warning("Database request failed: %s", type(error).__name__)
        return JSONResponse(status_code=503, content={"detail": "Database unavailable"})

    app.add_exception_handler(DBAPIError, database_error_handler)
    app.add_exception_handler(PoolTimeoutError, database_error_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {"type": item["type"], "loc": item["loc"], "msg": item["msg"]}
            for item in error.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": errors})

    return app
