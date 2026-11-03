"""Pydantic request / response schemas."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_serializer,
    field_validator,
)

from app.enums import (
    CATEGORY_VALUES,
    STATUS_VALUES,
    URGENCY_VALUES,
    LeadCategory,
    LeadStatus,
    Urgency,
)

_BUDGET_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([km]?)")


class LeadCreate(BaseModel):
    """Inbound lead payload. Tolerant of extra webhook fields."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    company: str | None = Field(default=None, max_length=160)
    budget: float | None = Field(default=None, ge=0, le=1_000_000_000)
    project_description: str = Field(min_length=5, max_length=20_000)
    source: str | None = Field(default=None, max_length=40)

    @field_validator("phone", "company", "source", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("budget", mode="before")
    @classmethod
    def _parse_budget(cls, value: object) -> object:
        """Accept numbers as well as common currency strings ("$12,500", "12k")."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            cleaned = value.strip().lower().replace(",", "").replace("$", "")
            cleaned = cleaned.replace("usd", "").replace("_", "").strip()
            cleaned = re.sub(r"^(?:around|about|approx\.?|~)\s*", "", cleaned)
            if not cleaned:
                return None
            match = _BUDGET_RE.fullmatch(cleaned)
            if not match:
                raise ValueError('Budget must be a number, e.g. 5000 or "$5,000"')
            amount = float(match.group(1))
            multiplier = {"": 1, "k": 1_000, "m": 1_000_000}[match.group(2)]
            return amount * multiplier
        raise ValueError("Budget must be numeric")


class LeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    phone: str | None
    company: str | None
    budget: float | None
    project_description: str
    source: str

    urgency: Urgency
    urgency_score: int
    category: LeadCategory
    qualified: bool
    completeness_score: int
    qualification_score: int
    triage_score: int
    triage_engine: str
    triage_reasons: list[str]
    matched_signals: list[str]

    status: LeadStatus
    created_at: datetime
    updated_at: datetime
    status_updated_at: datetime | None

    @field_serializer("created_at", "updated_at", "status_updated_at")
    def _serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class LeadStatusUpdate(BaseModel):
    status: LeadStatus


class LeadListOut(BaseModel):
    items: list[LeadRead]
    total: int
    limit: int
    offset: int


class StatsOut(BaseModel):
    total: int
    high_urgency: int
    qualified: int
    new_leads: int
    contacted: int
    closed: int
    avg_triage_score: float
    qualified_pipeline: float
    last_created_at: datetime | None

    @field_serializer("last_created_at")
    def _serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class TriageMetaOut(BaseModel):
    app_name: str
    triage_provider: str
    budget_threshold: float
    urgencies: list[str] = URGENCY_VALUES
    categories: list[str] = CATEGORY_VALUES
    statuses: list[str] = STATUS_VALUES
    demo_tools_enabled: bool


class HealthOut(BaseModel):
    status: str = "ok"
    database: str = "ok"
    triage_engine: str
    version: str = "1.0.0"
