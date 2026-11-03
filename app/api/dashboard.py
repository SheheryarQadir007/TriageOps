"""Server-rendered dashboard shell. All live data is loaded from the JSON API."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.config import Settings
from app.enums import CATEGORY_VALUES, STATUS_VALUES, URGENCY_VALUES
from app.schemas import TriageMetaOut

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request) -> HTMLResponse:
    settings: Settings = request.app.state.settings
    meta = TriageMetaOut(
        app_name=settings.app_name,
        triage_provider=settings.effective_provider,
        budget_threshold=settings.budget_threshold,
        demo_tools_enabled=settings.enable_demo_tools,
    )
    bootstrap = {
        "appName": meta.app_name,
        "provider": meta.triage_provider,
        "budgetThreshold": meta.budget_threshold,
        "urgencies": URGENCY_VALUES,
        "categories": CATEGORY_VALUES,
        "statuses": STATUS_VALUES,
        "demoToolsEnabled": meta.demo_tools_enabled,
        "seedDemoData": settings.seed_demo_data,
    }
    response = request.app.state.templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "app_name": settings.app_name,
            "meta": meta,
            "bootstrap": bootstrap,
        },
    )
    response.headers["Cache-Control"] = "no-store"
    return response
