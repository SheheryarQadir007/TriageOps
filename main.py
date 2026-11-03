"""TriageOps — lead intake and operational triage service.

Run locally:
    uvicorn main:app --reload

Read the API docs at http://localhost:8000/docs and the dashboard at
http://localhost:8000/dashboard.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.api import dashboard as dashboard_api
from app.api import leads as leads_api
from app.api import system as system_api
from app.config import Settings, get_settings
from app.database import Database
from app.schemas import HealthOut
from app.seed import seed_demo_leads
from app.triage import TriageStrategy, build_triage_engine
from app.triage.rules import RuleBasedTriage

BASE_DIR = Path(__file__).resolve().parent
VERSION = "1.0.0"

logger = logging.getLogger("triageops")


def _configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def create_app(
    settings: Settings | None = None,
    triage_engine: TriageStrategy | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    _configure_logging(settings)

    triage = triage_engine or build_triage_engine(settings)
    templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = Database(settings.database_url)
        database.create_all()

        app.state.db = database
        app.state.settings = settings
        app.state.triage = triage
        app.state.templates = templates

        if settings.seed_demo_data:
            try:
                rule_engine = RuleBasedTriage(
                    budget_threshold=settings.budget_threshold,
                    min_description_chars=settings.min_description_chars,
                )
                with database.session() as session:
                    created = seed_demo_leads(session, rule_engine)
                if created:
                    logger.info("Demo dataset loaded (%d leads)", created)
            except Exception:  # noqa: BLE001 - seeding must never block startup
                logger.exception("Demo seed failed; continuing without sample data")

        logger.info(
            "%s started | env=%s | db=%s | triage=%s",
            settings.app_name,
            settings.environment,
            settings.database_url.split("://", 1)[0],
            triage.name,
        )
        try:
            yield
        finally:
            triage.close()
            database.dispose()
            logger.info("TriageOps shut down cleanly")

    app = FastAPI(
        title=settings.app_name,
        version=VERSION,
        description=(
            "Lead intake and operational triage backend. Submit leads to "
            "`POST /api/leads`, inspect them in `/dashboard`, and review the API "
            "contract in `/docs`."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=[
            {"name": "leads", "description": "Intake, filtering, and status workflow."},
            {"name": "operations", "description": "Stats, metadata, and demo tools."},
            {"name": "demo", "description": "Optional demo data helpers."},
        ],
    )

    app.state.settings = settings
    app.state.triage = triage
    app.state.templates = templates

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
            allow_headers=["*"],
            max_age=600,
        )

    app.add_middleware(GZipMiddleware, minimum_size=1_000)

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/dashboard", status_code=307)

    @app.get("/health", response_model=HealthOut, tags=["operations"])
    def health(request: Request) -> HealthOut:
        try:
            with request.app.state.db.session() as session:
                session.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Health check failed")
            raise HTTPException(status_code=503, detail="Database unavailable") from exc
        return HealthOut(
            status="ok",
            database="ok",
            triage_engine=request.app.state.triage.name,
            version=VERSION,
        )

    app.include_router(leads_api.router)
    app.include_router(system_api.router)
    app.include_router(dashboard_api.router)
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

    return app


app = create_app()
