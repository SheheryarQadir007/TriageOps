"""Business logic shared by the API, dashboard, and seed helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Sequence

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.enums import LeadStatus
from app.models import Lead, utcnow
from app.schemas import LeadCreate, StatsOut
from app.triage.base import LeadContext, TriageStrategy

SortOption = Literal["urgency", "newest", "oldest", "score"]


def create_lead(
    db: Session,
    payload: LeadCreate,
    triage: TriageStrategy,
    *,
    source_override: str | None = None,
) -> Lead:
    context = LeadContext(
        name=payload.name,
        email=str(payload.email),
        company=payload.company,
        budget=payload.budget,
        project_description=payload.project_description,
    )
    result = triage.classify(context)

    lead = Lead(
        name=payload.name,
        email=str(payload.email),
        phone=payload.phone,
        company=payload.company,
        budget=payload.budget,
        project_description=payload.project_description,
        source=(source_override or payload.source or "api")[:40],
        urgency=result.urgency.value,
        urgency_score=result.urgency_score,
        category=result.category.value,
        qualified=result.qualified,
        completeness_score=result.completeness_score,
        qualification_score=result.qualification_score,
        triage_score=result.triage_score,
        triage_engine=result.engine,
        triage_reasons=result.reasons,
        matched_signals=result.matched_signals,
        status=LeadStatus.NEW.value,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def update_lead_status(db: Session, lead: Lead, status: LeadStatus) -> Lead:
    lead.status = status.value
    lead.status_updated_at = datetime.now(timezone.utc)
    lead.updated_at = utcnow()
    db.commit()
    db.refresh(lead)
    return lead


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _filter_conditions(
    *,
    status: LeadStatus | None = None,
    urgency: str | None = None,
    category: str | None = None,
    qualified: bool | None = None,
    q: str | None = None,
) -> list:
    conditions = []
    if status is not None:
        conditions.append(Lead.status == status.value)
    if urgency:
        conditions.append(Lead.urgency == urgency)
    if category:
        conditions.append(Lead.category == category)
    if qualified is not None:
        conditions.append(Lead.qualified.is_(qualified))
    if q and q.strip():
        term = f"%{_escape_like(q.strip())}%"
        conditions.append(
            or_(
                Lead.name.ilike(term, escape="\\"),
                Lead.company.ilike(term, escape="\\"),
                Lead.email.ilike(term, escape="\\"),
                Lead.project_description.ilike(term, escape="\\"),
            )
        )
    return conditions


def list_leads(
    db: Session,
    *,
    status: LeadStatus | None = None,
    urgency: str | None = None,
    category: str | None = None,
    qualified: bool | None = None,
    q: str | None = None,
    sort: SortOption = "urgency",
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Lead], int]:
    conditions = _filter_conditions(
        status=status, urgency=urgency, category=category, qualified=qualified, q=q
    )

    total = db.scalar(select(func.count()).select_from(Lead).where(*conditions)) or 0

    urgency_rank = case(
        (Lead.urgency == "High", 0),
        (Lead.urgency == "Medium", 1),
        (Lead.urgency == "Low", 2),
        else_=3,
    )
    if sort == "newest":
        ordering = [Lead.created_at.desc(), Lead.id.desc()]
    elif sort == "oldest":
        ordering = [Lead.created_at.asc(), Lead.id.asc()]
    elif sort == "score":
        ordering = [Lead.triage_score.desc(), Lead.created_at.desc()]
    else:
        ordering = [urgency_rank.asc(), Lead.triage_score.desc(), Lead.created_at.desc()]

    statement = (
        select(Lead)
        .where(*conditions)
        .order_by(*ordering)
        .limit(limit)
        .offset(offset)
    )
    items = list(db.scalars(statement).all())
    return items, total


def export_leads(db: Session, **filters) -> list[Lead]:
    """Return all matching leads (capped) for CSV export."""
    conditions = _filter_conditions(**filters)
    urgency_rank = case(
        (Lead.urgency == "High", 0),
        (Lead.urgency == "Medium", 1),
        (Lead.urgency == "Low", 2),
        else_=3,
    )
    statement = (
        select(Lead)
        .where(*conditions)
        .order_by(urgency_rank.asc(), Lead.created_at.desc())
        .limit(10_000)
    )
    return list(db.scalars(statement).all())


def lead_stats(db: Session) -> StatsOut:
    row = db.execute(
        select(
            func.count(Lead.id),
            func.coalesce(func.sum(case((Lead.urgency == "High", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Lead.qualified.is_(True), 1), else_=0)), 0),
            func.coalesce(
                func.sum(case((Lead.status == LeadStatus.NEW.value, 1), else_=0)), 0
            ),
            func.coalesce(
                func.sum(case((Lead.status == LeadStatus.CONTACTED.value, 1), else_=0)), 0
            ),
            func.coalesce(
                func.sum(case((Lead.status == LeadStatus.CLOSED.value, 1), else_=0)), 0
            ),
            func.coalesce(func.avg(Lead.triage_score), 0),
            func.coalesce(
                func.sum(
                    case(
                        (Lead.qualified.is_(True), func.coalesce(Lead.budget, 0)),
                        else_=0,
                    )
                ),
                0,
            ),
            func.max(Lead.created_at),
        )
    ).one()

    return StatsOut(
        total=int(row[0] or 0),
        high_urgency=int(row[1] or 0),
        qualified=int(row[2] or 0),
        new_leads=int(row[3] or 0),
        contacted=int(row[4] or 0),
        closed=int(row[5] or 0),
        avg_triage_score=round(float(row[6] or 0), 1),
        qualified_pipeline=round(float(row[7] or 0), 2),
        last_created_at=row[8],
    )
