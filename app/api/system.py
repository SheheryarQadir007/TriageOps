"""Operational metadata, stats, and demo helpers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import get_db
from app.schemas import StatsOut, TriageMetaOut
from app.seed import seed_demo_leads
from app.services import lead_stats
from app.triage.rules import RuleBasedTriage

router = APIRouter(prefix="/api", tags=["operations"])


@router.get("/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db)) -> StatsOut:
    return lead_stats(db)


@router.get("/meta", response_model=TriageMetaOut)
def meta(request: Request) -> TriageMetaOut:
    settings: Settings = request.app.state.settings
    return TriageMetaOut(
        app_name=settings.app_name,
        triage_provider=settings.effective_provider,
        budget_threshold=settings.budget_threshold,
        demo_tools_enabled=settings.enable_demo_tools,
    )


@router.post("/demo/seed", tags=["demo"])
def seed(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Populate an empty database with sample leads (disabled in production)."""
    settings: Settings = request.app.state.settings
    if not settings.enable_demo_tools:
        raise HTTPException(status_code=404, detail="Not found")

    triage = RuleBasedTriage(
        budget_threshold=settings.budget_threshold,
        min_description_chars=settings.min_description_chars,
    )
    created = seed_demo_leads(db, triage)
    if created == 0:
        return {"created": 0, "message": "Leads already exist; demo seed skipped."}
    return {"created": created, "message": f"Seeded {created} demo leads."}
