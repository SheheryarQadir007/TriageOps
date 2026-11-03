"""Shared pytest fixtures: isolated SQLite app instances."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.triage.rules import RuleBasedTriage
from main import create_app


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        seed_demo_data=False,
        enable_demo_tools=True,
        triage_provider="rules",
        budget_threshold=5_000,
        min_description_chars=60,
    )


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    triage = RuleBasedTriage(
        budget_threshold=settings.budget_threshold,
        min_description_chars=settings.min_description_chars,
    )
    app = create_app(settings, triage)
    with TestClient(app) as test_client:
        yield test_client
