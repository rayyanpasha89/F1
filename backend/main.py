import logging
import hmac
import os
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any, Literal

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.database import SCHEMA, make_engine
from backend.ai.chat import ChatService, ChatRequest
from backend.ai.provider import ProviderError
from backend.config import ConfigurationError
from backend.http import install_http_policy
from threading import BoundedSemaphore
from backend.ai.limits import ChatLimiter
from backend.ml.evidence import ModelBundleError, verify_model_bundle
from backend.ml.model_card import ModelCard, ModelCardError, ModelCardService
from backend.ml.outcomes import PodiumOutcomes, PodiumOutcomeService
from backend.ml.predictor import Predictor, PredictionUnavailable, load_artifacts
from backend.ml.review import RaceReview, RaceReviewService
from backend.ml.scenario import GridScenario, GridScenarioRequest, GridScenarioService
from backend.services.analytics import Analytics, NotFound

logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)


class Rows(BaseModel):
    data: list[dict[str, Any]]


def create_app(engine=None):
    db = engine or make_engine()
    analytics = Analytics(db)
    predictor = Predictor(db)
    podium_outcome_service = PodiumOutcomeService(predictor)
    review_service = RaceReviewService(predictor, analytics)
    scenario_service = GridScenarioService(predictor)
    model_card_service = ModelCardService()
    chat_service = ChatService(db)
    chat_slots = BoundedSemaphore(2)
    chat_limiter = ChatLimiter()

    @asynccontextmanager
    async def lifespan(app):
        if os.environ.get("F1_REQUIRE_READONLY") == "1":
            with db.connect() as conn:
                readonly = conn.scalar(text("SHOW default_transaction_read_only")) == "on"
                writable = conn.scalar(
                    text("""SELECT EXISTS(
                    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='public' AND c.relkind IN ('r','p') AND (
                        has_table_privilege(current_user, c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE')
                    )) OR has_schema_privilege(current_user, 'public', 'CREATE')""")
                )
            if not readonly or writable:
                raise RuntimeError("Production database credentials must be SELECT-only")
            logger.warning("Production PostgreSQL reader privileges verified")
            try:
                load_artifacts()
                model_card_service.get()
            except PredictionUnavailable as error:
                raise RuntimeError("Production model bundle must verify") from error
            except ModelCardError as error:
                raise RuntimeError(
                    "Production model accountability evidence must verify"
                ) from error
            logger.warning("Production model bundle verified")
        yield
        db.dispose()

    app = FastAPI(title="F1 Race Strategist", version="0.1.0", lifespan=lifespan)
    app.state.engine = db
    install_http_policy(app)

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

    @app.exception_handler(ModelCardError)
    async def model_card_error(request: Request, exc: ModelCardError):
        return JSONResponse(
            status_code=503,
            content={"detail": "Model accountability evidence unavailable."},
        )

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
            result = chat_service.answer(body)
            trace = result.get("trace", {})
            tables = trace.get("tables") or []
            logger.info(
                "chat_complete request_id=%s route=%s status=%s provider_calls=%s "
                "repairs=%s tables=%s elapsed_ms=%s",
                request.state.request_id,
                trace.get("route", result.get("intent", "unknown")),
                result.get("status", result.get("intent", "unknown")),
                trace.get("provider_call_count", 0),
                trace.get("repair_count", 0),
                ",".join(table for table in tables if table in SCHEMA) or "-",
                trace.get("total_elapsed_ms", 0),
            )
            return result
        finally:
            chat_slots.release()

    @app.get("/api/predictions/{race_id}")
    def prediction(race_id: int, request: Request):
        started_at = perf_counter()
        analytics.race(race_id)
        result = predictor.predict(race_id)
        logger.info(
            "prediction_complete request_id=%s race_id=%s model_version=%s "
            "postprocessor=%s elapsed_ms=%.1f probability_sum=%.12f",
            request.state.request_id,
            race_id,
            result["model_version"],
            result["postprocessing"]["method"],
            (perf_counter() - started_at) * 1000,
            sum(row["probability"] for row in result["predictions"]),
        )
        return result

    @app.get("/api/predictions/{race_id}/review", response_model=RaceReview)
    def prediction_review(race_id: int, request: Request):
        started_at = perf_counter()
        analytics.race(race_id)
        result = review_service.review(race_id)
        logger.info(
            "review_complete request_id=%s race_id=%s model_version=%s "
            "postprocessor=%s elapsed_ms=%.1f hit_count=%s",
            request.state.request_id,
            race_id,
            result.model_version,
            result.postprocessor.method,
            (perf_counter() - started_at) * 1000,
            result.top_three_hits,
        )
        return result

    @app.get("/api/predictions/{race_id}/podium-outcomes", response_model=PodiumOutcomes)
    def podium_outcomes(
        race_id: int,
        request: Request,
        limit: int = Query(default=12, ge=3, le=25),
    ):
        started_at = perf_counter()
        analytics.race(race_id)
        result = podium_outcome_service.derive(race_id, limit=limit)
        diagnostics = result.diagnostics
        logger.info(
            "podium_outcomes_complete request_id=%s race_id=%s model_version=%s "
            "method=%s elapsed_ms=%.1f driver_count=%s combination_count=%s "
            "returned_count=%s probability_sum=%.12f maximum_marginal_error=%.3e",
            request.state.request_id,
            race_id,
            result.model_version,
            diagnostics.method,
            (perf_counter() - started_at) * 1000,
            diagnostics.driver_count,
            diagnostics.combination_count,
            diagnostics.returned_outcome_count,
            diagnostics.probability_sum,
            diagnostics.maximum_marginal_error,
        )
        return result

    @app.post("/api/predictions/{race_id}/scenario", response_model=GridScenario)
    def prediction_scenario(race_id: int, body: GridScenarioRequest, request: Request):
        started_at = perf_counter()
        analytics.race(race_id)
        result = scenario_service.swap(race_id, body)
        logger.info(
            "scenario_complete request_id=%s race_id=%s model_version=%s "
            "scenario=grid_swap elapsed_ms=%.1f driver_count=%s probability_sum=%.12f",
            request.state.request_id,
            race_id,
            result.model_version,
            (perf_counter() - started_at) * 1000,
            len(result.predictions),
            result.postprocessing.scenario_sum,
        )
        return result

    @app.get("/api/health")
    def health():
        with db.connect() as conn:
            conn.execute(text("SELECT race_id FROM races LIMIT 1")).first()
        return {"status": "ok", "source": "historical CSV snapshot, through 2024"}

    @app.get("/api/health/ready")
    def readiness():
        with db.connect() as conn:
            archive_through = conn.scalar(
                text("SELECT MAX(year) FROM races JOIN results USING (race_id)")
            )
        try:
            manifest = verify_model_bundle()
            load_artifacts()
            model_card_service.get()
        except (ModelBundleError, PredictionUnavailable, ModelCardError):
            return JSONResponse(
                status_code=503,
                content={"status": "unavailable", "detail": "Model bundle unavailable."},
            )
        return {
            "status": "ready",
            "archive_through": int(archive_through),
            "model_version": manifest.model_version,
            "checks": {
                "database": "ok",
                "model_bundle": "verified",
                "model_card": "verified",
            },
        }

    @app.get("/api/model-card", response_model=ModelCard)
    def model_card():
        return model_card_service.get()

    @app.get("/api/seasons", response_model=Rows)
    def seasons():
        return {"data": analytics.seasons()}

    @app.get("/api/races", response_model=Rows)
    def races(year: int = Query(ge=1950, le=2100)):
        return {"data": analytics.races(year)}

    @app.get("/api/races/{race_id}")
    def race(race_id: int):
        return analytics.race(race_id)

    @app.get("/api/races/{race_id}/comparison")
    def comparison(race_id: int, driver_a: int = Query(gt=0), driver_b: int = Query(gt=0)):
        if driver_a == driver_b:
            return JSONResponse(
                status_code=422, content={"detail": "Choose two different drivers."}
            )
        return analytics.comparison(race_id, driver_a, driver_b)

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

    if os.environ.get("WEB_DIST"):
        from backend.web import mount_web

        mount_web(app, os.environ["WEB_DIST"])
    return app


app = create_app()
