"""Lead intake and operations API."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.enums import LeadCategory, LeadStatus, Urgency
from app.models import Lead
from app.schemas import LeadCreate, LeadListOut, LeadRead, LeadStatusUpdate
from app.services import (
    create_lead as create_lead_record,
    export_leads,
    list_leads,
    update_lead_status,
)
from app.triage.base import TriageStrategy

router = APIRouter(prefix="/api/leads", tags=["leads"])


def get_triage(request: Request) -> TriageStrategy:
    return request.app.state.triage


def _get_lead_or_404(db: Session, lead_id: int) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.post("", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: LeadCreate,
    db: Session = Depends(get_db),
    triage: TriageStrategy = Depends(get_triage),
) -> Lead:
    """Intake endpoint for webhooks, forms, and the dashboard simulator."""
    return create_lead_record(db, payload, triage)


@router.get("", response_model=LeadListOut)
def list_leads_endpoint(
    status_filter: LeadStatus | None = Query(default=None, alias="status"),
    urgency: Urgency | None = Query(default=None),
    category: LeadCategory | None = Query(default=None),
    qualified: bool | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    sort: Literal["urgency", "newest", "oldest", "score"] = Query(default="urgency"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> LeadListOut:
    items, total = list_leads(
        db,
        status=status_filter,
        urgency=urgency.value if urgency else None,
        category=category.value if category else None,
        qualified=qualified,
        q=q,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return LeadListOut(
        items=[LeadRead.model_validate(lead) for lead in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/export.csv", response_class=Response, include_in_schema=False)
def export_leads_csv(
    status_filter: LeadStatus | None = Query(default=None, alias="status"),
    urgency: Urgency | None = Query(default=None),
    category: LeadCategory | None = Query(default=None),
    qualified: bool | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    db: Session = Depends(get_db),
) -> Response:
    leads = export_leads(
        db,
        status=status_filter,
        urgency=urgency.value if urgency else None,
        category=category.value if category else None,
        qualified=qualified,
        q=q,
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "created_at",
            "name",
            "email",
            "phone",
            "company",
            "budget",
            "urgency",
            "urgency_score",
            "category",
            "qualified",
            "triage_score",
            "status",
            "triage_engine",
            "project_description",
        ]
    )
    for lead in leads:
        writer.writerow(
            [
                lead.id,
                lead.created_at.isoformat() if lead.created_at else "",
                lead.name,
                lead.email,
                lead.phone or "",
                lead.company or "",
                lead.budget if lead.budget is not None else "",
                lead.urgency,
                lead.urgency_score,
                lead.category,
                "yes" if lead.qualified else "no",
                lead.triage_score,
                lead.status,
                lead.triage_engine,
                lead.project_description,
            ]
        )

    filename = f"triageops-leads-{datetime.now(timezone.utc):%Y%m%d}.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{lead_id}", response_model=LeadRead)
def get_lead(lead_id: int, db: Session = Depends(get_db)) -> Lead:
    return _get_lead_or_404(db, lead_id)


@router.patch("/{lead_id}/status", response_model=LeadRead)
def set_lead_status(
    lead_id: int,
    payload: LeadStatusUpdate,
    db: Session = Depends(get_db),
) -> Lead:
    lead = _get_lead_or_404(db, lead_id)
    return update_lead_status(db, lead, payload.status)
