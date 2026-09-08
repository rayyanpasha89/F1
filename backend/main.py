import logging
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.database import make_engine
from backend.services.analytics import Analytics, NotFound

logger = logging.getLogger(__name__)


class Rows(BaseModel):
    data: list[dict[str, Any]]


def create_app(engine=None):
    db = engine or make_engine()
    analytics = Analytics(db)

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
