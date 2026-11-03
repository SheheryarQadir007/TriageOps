"""Unit tests for the deterministic triage engine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.enums import LeadCategory, Urgency
from app.schemas import LeadCreate
from app.triage.base import LeadContext, combine_scores
from app.triage.llm import LLMTriage
from app.triage.rules import (
    RuleBasedTriage,
    description_completeness,
    find_deadline,
)

URGENT_BRIEF = (
    "URGENT: our production warehouse dashboard went down this morning and the team "
    "cannot process shipments. We are losing orders every hour. The app is showing a "
    "502 error after last night's deploy. Need someone to jump in immediately, diagnose "
    "the outage, and restore service today. We have a React frontend, FastAPI backend, "
    "and Postgres database on AWS."
)


def context(**overrides) -> LeadContext:
    values = {
        "name": "Maya Chen",
        "email": "maya@example.com",
        "company": "Acme Systems",
        "budget": 18_000,
        "project_description": URGENT_BRIEF,
    }
    values.update(overrides)
    return LeadContext(**values)


@pytest.fixture()
def engine() -> RuleBasedTriage:
    return RuleBasedTriage(budget_threshold=5_000, min_description_chars=60)


def test_urgent_outage_is_high_priority_and_qualified(engine: RuleBasedTriage) -> None:
    result = engine.classify(context())

    assert result.urgency is Urgency.HIGH
    assert result.urgency_score >= 60
    assert result.category is LeadCategory.EMERGENCY_REPAIR
    assert result.qualified is True
    assert result.completeness_score >= 60
    assert result.triage_score >= 80
    assert result.engine == "rules"
    assert any("urgent" in signal for signal in result.matched_signals)
    assert any("Budget" in reason for reason in result.reasons)


def test_critical_security_incident_is_high_urgency(engine: RuleBasedTriage) -> None:
    result = engine.classify(
        context(
            budget=25_000,
            project_description=(
                "We suspect a security breach. Multiple employees received phishing emails "
                "and there is an unfamiliar admin login on our Azure tenant. We need an "
                "urgent security audit and containment plan for our team of 6."
            ),
        )
    )

    assert result.urgency is Urgency.HIGH
    assert result.category is LeadCategory.EMERGENCY_REPAIR
    assert result.qualified is True


def test_low_budget_blocks_qualification(engine: RuleBasedTriage) -> None:
    result = engine.classify(
        context(
            budget=1_500,
            project_description=(
                "Need help fixing a bug on our booking page before next week. The "
                "confirmation email does not send after a customer books a class."
            ),
        )
    )

    assert result.qualified is False
    assert "budget:below" in result.matched_signals
    assert any("below" in reason for reason in result.reasons)


def test_missing_budget_is_not_qualified(engine: RuleBasedTriage) -> None:
    result = engine.classify(context(budget=None))

    assert result.qualified is False
    assert "budget:missing" in result.matched_signals


def test_browsing_inquiry_is_low_urgency(engine: RuleBasedTriage) -> None:
    result = engine.classify(
        context(
            budget=None,
            project_description=(
                "Hi, just curious about pricing and availability for web design services. "
                "We may have a project later this year but are still exploring options."
            ),
        )
    )

    assert result.urgency is Urgency.LOW
    assert result.urgency_score <= 24
    assert result.category is LeadCategory.GENERAL_INQUIRY
    assert result.qualified is False


def test_new_build_is_classified_as_implementation(engine: RuleBasedTriage) -> None:
    result = engine.classify(
        context(
            budget=20_000,
            project_description=(
                "We want to build a new client portal from scratch for our 40-person team. "
                "It needs document upload, role-based access, Stripe billing, and a React "
                "frontend backed by FastAPI. We would like to launch this quarter and have "
                "a detailed scope ready to share."
            ),
        )
    )

    assert result.category is LeadCategory.NEW_IMPLEMENTATION
    assert result.qualified is True


def test_maintenance_retainer_is_classified(engine: RuleBasedTriage) -> None:
    result = engine.classify(
        context(
            budget=12_000,
            project_description=(
                "We are looking for a monthly maintenance retainer for our WordPress site. "
                "We need security patches, weekly backups, uptime monitoring, and about 10 "
                "hours of small updates each month for our 40-page site."
            ),
        )
    )

    assert result.category is LeadCategory.MAINTENANCE
    assert result.qualified is True


def test_short_brief_does_not_qualify(engine: RuleBasedTriage) -> None:
    result = engine.classify(context(project_description="Site down. Need help ASAP."))

    assert result.urgency is Urgency.HIGH
    assert result.completeness_score < 60
    assert result.qualified is False
    assert "description:incomplete" in result.matched_signals


def test_deadline_within_48_hours_is_parsed() -> None:
    now = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    deadline = find_deadline("Need this restored within 12 hours.", now)

    assert deadline is not None
    assert deadline.hours == pytest.approx(12)
    assert deadline.label == "deadline <48h"


def test_relative_deadline_and_absence() -> None:
    now = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)

    tomorrow = find_deadline("Can you deliver this by tomorrow?", now)
    assert tomorrow is not None
    assert 20 <= tomorrow.hours <= 48

    assert find_deadline("No schedule mentioned here.", now) is None


def test_description_completeness_rewards_detail() -> None:
    short = description_completeness("Need help.")
    detailed = description_completeness(URGENT_BRIEF)

    assert short < 40
    assert detailed >= 60
    assert detailed > short


def test_combine_scores_weights_urgency() -> None:
    assert combine_scores(100, 100) == 100
    assert combine_scores(100, 0) == 65
    assert combine_scores(0, 100) == 35
    assert combine_scores(150, -20) == 90


def test_budget_string_parsing() -> None:
    assert LeadCreate(
        name="A", email="a@example.com", budget="$12,500", project_description="Need a rebuild."
    ).budget == 12_500
    assert LeadCreate(
        name="A", email="a@example.com", budget="12k", project_description="Need a rebuild."
    ).budget == 12_000
    assert LeadCreate(
        name="A", email="a@example.com", budget=None, project_description="Need a rebuild."
    ).budget is None


def test_llm_failure_falls_back_to_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = LLMTriage(
        "openai",
        "test-key",
        "test-model",
        budget_threshold=5_000,
        fallback=RuleBasedTriage(5_000, 60),
    )
    monkeypatch.setattr(llm, "_request", lambda _lead: (_ for _ in ()).throw(RuntimeError("boom")))

    result = llm.classify(context())
    llm.close()

    assert result.engine == "rules-fallback"
    assert result.urgency is Urgency.HIGH
    assert result.qualified is True
    assert any("fallback" in reason for reason in result.reasons)


def test_llm_cannot_override_qualification_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = LLMTriage(
        "openai",
        "test-key",
        "test-model",
        budget_threshold=5_000,
        fallback=RuleBasedTriage(5_000, 60),
    )
    monkeypatch.setattr(
        llm,
        "_request",
        lambda _lead: {
            "urgency": "High",
            "urgency_score": 90,
            "category": "Emergency Repair",
            "qualified": True,
            "reasons": ["LLM thinks this is a great lead."],
            "matched_signals": ["llm-tag"],
        },
    )

    result = llm.classify(context(budget=1_000))
    llm.close()

    assert result.qualified is False
    assert result.engine == "openai"
    assert any("Policy override" in reason for reason in result.reasons)
