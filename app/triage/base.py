"""Triage strategy interface and shared value objects."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.enums import LeadCategory, Urgency


@dataclass(frozen=True, slots=True)
class LeadContext:
    """The normalised subset of a lead the classifier needs."""

    name: str
    email: str
    company: str | None
    budget: float | None
    project_description: str

    def to_prompt(self) -> str:
        company = self.company or "not provided"
        budget = f"${self.budget:,.0f}" if self.budget is not None else "not provided"
        return (
            f"Contact name: {self.name}\n"
            f"Email: {self.email}\n"
            f"Company: {company}\n"
            f"Budget: {budget}\n"
            f"Project description:\n{self.project_description}"
        )


@dataclass(slots=True)
class TriageResult:
    urgency: Urgency
    urgency_score: int
    category: LeadCategory
    qualified: bool
    completeness_score: int
    qualification_score: int
    triage_score: int
    reasons: list[str] = field(default_factory=list)
    matched_signals: list[str] = field(default_factory=list)
    engine: str = "rules"


class TriageStrategy(ABC):
    """Extensible classifier interface.

    Implementations receive a :class:`LeadContext` and must return a fully
    populated :class:`TriageResult`. They own their dependencies (HTTP clients,
    models, etc.) and may expose ``close()`` for graceful shutdown.
    """

    name: str = "base"

    @abstractmethod
    def classify(self, lead: LeadContext) -> TriageResult:
        raise NotImplementedError

    def close(self) -> None:
        """Release any long-lived resources. No-op for pure rule engines."""


def combine_scores(urgency_score: int, qualification_score: int) -> int:
    """Blend urgency and qualification into a single 0-100 priority score."""
    return max(0, min(100, round(0.65 * urgency_score + 0.35 * qualification_score)))
