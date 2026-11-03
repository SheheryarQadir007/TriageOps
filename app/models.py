"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.enums import LeadStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_status_created", "status", "created_at"),
        Index("ix_leads_urgency_created", "urgency", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Contact / intake fields
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    company: Mapped[str | None] = mapped_column(String(160), nullable=True)
    budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    project_description: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="api", index=True)

    # Triage output
    urgency: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    urgency_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    qualified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    completeness_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qualification_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    triage_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    triage_engine: Mapped[str] = mapped_column(String(32), nullable=False, default="rules")
    triage_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    matched_signals: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    # Operations workflow
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=LeadStatus.NEW.value, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    status_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Lead id={self.id} name={self.name!r} urgency={self.urgency!r}>"
