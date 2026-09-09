import logging
import hmac
import os
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.database import make_engine
from backend.ai.chat import ChatService, ChatRequest
from backend.ai.provider import ProviderError
from backend.config import ConfigurationError
from threading import BoundedSemaphore
from backend.ai.limits import ChatLimiter
from backend.ml.predictor import Predictor, PredictionUnavailable
from backend.services.analytics import Analytics, NotFound

logger = logging.getLogger(__name__)


class Rows(BaseModel):
    data: list[dict[str, Any]]


def create_app(engine=None):
    db = engine or make_engine()
    analytics = Analytics(db)
    predictor = Predictor(db)
    chat_service = ChatService(db)
    chat_slots = BoundedSemaphore(2)
    chat_limiter = ChatLimiter()

    @asynccontextmanager
    async def lifespan(app):
        yield
        db.dispose()

    app = FastAPI(title="F1 Race Strategist", version="0.1.0", lifespan=lifespan)
    app.state.engine = db

    @app.exception_handler(NotFound)
    async def missing(request: Request, exc: NotFound):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(SQLAlchemyError)
    async def db_error(request: Request, exc: SQLAlchemyError):
        logger.error("Database operation failed: %s", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Database unavailable; verify ingestion and connection configuration."
            },
        )

    @app.exception_handler(PredictionUnavailable)
    async def prediction_error(request: Request, exc: PredictionUnavailable):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(ProviderError)
    @app.exception_handler(ConfigurationError)
    async def provider_error(request: Request, exc):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.get("/api/chat/config")
    def chat_config():
        return {"requires_access_code": bool(os.environ.get("CHAT_ACCESS_CODE"))}

    @app.post("/api/chat")
    def chat(body: ChatRequest, request: Request):
        access_code = os.environ.get("CHAT_ACCESS_CODE")
        if access_code and not hmac.compare_digest(
            request.headers.get("x-chat-access-code", "").encode(), access_code.encode()
        ):
            return JSONResponse(
                status_code=401, content={"detail": "Enter the demo chat access code."}
            )
        client = request.client.host if request.client else "unknown"
        if not chat_limiter.allow(client):
            return JSONResponse(
                status_code=429, content={"detail": "Chat request limit reached. Try again later."}
            )
        if not chat_slots.acquire(blocking=False):
            return JSONResponse(
                status_code=429,
                content={"detail": "Two chat requests are running. Try again shortly."},
            )
        try:
            return chat_service.answer(body)
        finally:
            chat_slots.release()

    @app.get("/api/predictions/{race_id}")
    def prediction(race_id: int):
        analytics.race(race_id)
        return predictor.predict(race_id)

    @app.get("/api/health")
    def health():
        with db.connect() as conn:
            conn.execute(text("SELECT race_id FROM races LIMIT 1")).first()
        return {"status": "ok", "source": "historical CSV snapshot, through 2024"}

    @app.get("/api/seasons", response_model=Rows)
    def seasons():
        return {"data": analytics.seasons()}

    @app.get("/api/races", response_model=Rows)
    def races(year: int = Query(ge=1950, le=2100)):
        return {"data": analytics.races(year)}

    @app.get("/api/races/{race_id}")
    def race(race_id: int):
        return analytics.race(race_id)

    @app.get("/api/races/{race_id}/{kind}", response_model=Rows)
    def race_table(race_id: int, kind: Literal["results", "qualifying", "pit-stops", "grid"]):
        return {"data": analytics.race_table(race_id, kind)}

    @app.get("/api/standings/{kind}/{year}", response_model=Rows)
    def standings(kind: Literal["drivers", "constructors"], year: int):
        return {"data": analytics.standings(year, kind)}

    @app.get("/api/profiles/{kind}", response_model=Rows)
    def entities(kind: Literal["drivers", "constructors"], year: int | None = None):
        return {"data": analytics.entities(kind, year)}

    @app.get("/api/profiles/{kind}/{identifier}")
    def profile(kind: Literal["drivers", "constructors"], identifier: int, year: int | None = None):
        return analytics.profile(kind, identifier, year)

    return app


app = create_app()
