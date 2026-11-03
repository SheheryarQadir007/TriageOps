"""Triage engine factory.

Usage:
    engine = build_triage_engine(settings)
    result = engine.classify(LeadContext(...))
"""

from __future__ import annotations

import logging

from app.config import Settings
from app.triage.base import LeadContext, TriageResult, TriageStrategy, combine_scores
from app.triage.llm import LLMTriage
from app.triage.rules import RuleBasedTriage, description_completeness, find_deadline

logger = logging.getLogger(__name__)

__all__ = [
    "LeadContext",
    "TriageResult",
    "TriageStrategy",
    "RuleBasedTriage",
    "LLMTriage",
    "build_triage_engine",
    "combine_scores",
    "description_completeness",
    "find_deadline",
]


def build_triage_engine(settings: Settings) -> TriageStrategy:
    provider = settings.effective_provider
    fallback = RuleBasedTriage(
        budget_threshold=settings.budget_threshold,
        min_description_chars=settings.min_description_chars,
    )

    if provider == "rules":
        logger.info("Triage engine: rules (budget threshold $%.0f)", settings.budget_threshold)
        return fallback

    if provider == "openai":
        if not settings.openai_api_key:
            logger.warning("OpenAI selected but OPENAI_API_KEY is missing; using rules")
            return fallback
        logger.info("Triage engine: OpenAI (%s)", settings.openai_model)
        return LLMTriage(
            "openai",
            settings.openai_api_key,
            settings.openai_model,
            budget_threshold=settings.budget_threshold,
            min_description_chars=settings.min_description_chars,
            timeout_seconds=settings.llm_timeout_seconds,
            fallback=fallback,
        )

    if provider == "gemini":
        if not settings.gemini_api_key:
            logger.warning("Gemini selected but GEMINI_API_KEY is missing; using rules")
            return fallback
        logger.info("Triage engine: Gemini (%s)", settings.gemini_model)
        return LLMTriage(
            "gemini",
            settings.gemini_api_key,
            settings.gemini_model,
            budget_threshold=settings.budget_threshold,
            min_description_chars=settings.min_description_chars,
            timeout_seconds=settings.llm_timeout_seconds,
            fallback=fallback,
        )

    # Defensive: an unknown value should never break intake.
    logger.warning("Unknown triage provider %r; using rules", provider)
    return fallback
