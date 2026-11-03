"""End-to-end API and dashboard tests against an isolated SQLite database."""

from __future__ import annotations

import csv
import io

from fastapi.testclient import TestClient

HIGH_LEAD = {
    "name": "Maya Chen",
    "email": "maya.chen@acmesystems.example",
    "phone": "+1 (415) 555-0102",
    "company": "Acme Systems",
    "budget": 18_000,
    "project_description": (
        "URGENT: our customer portal is down after last night's deploy and the support "
        "team cannot access accounts. We are losing orders every hour. The app returns a "
        "502 error; it runs on React and FastAPI behind AWS. Need someone to jump in "
        "immediately, diagnose the outage, and restore service today."
    ),
    "source": "pytest",
}

MEDIUM_LEAD = {
    "name": "Ethan Cole",
    "email": "ethan@colefitness.example",
    "company": "Cole Fitness",
    "budget": "8,000",
    "project_description": (
        "We need a bug fix soon for our booking page this week. Confirmation emails do not "
        "send and the calendar shows the wrong timezone for customers in Europe. Please "
        "help us fix the Stripe integration before the next class season starts."
    ),
    "source": "pytest",
}

LOW_LEAD = {
    "name": "Sofia Mendes",
    "email": "sofia@brightlinestudio.example",
    "company": "Brightline Studio",
    "budget": None,
    "project_description": (
        "Hi, just curious about pricing and availability for web design services. We may "
        "have a project later this year but are still exploring options."
    ),
    "source": "pytest",
}


def create_lead(client: TestClient, payload: dict) -> dict:
    response = client.post("/api/leads", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_health_and_meta(client: TestClient) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["database"] == "ok"
    assert health.json()["triage_engine"] == "rules"

    meta = client.get("/api/meta")
    assert meta.status_code == 200
    body = meta.json()
    assert body["triage_provider"] == "rules"
    assert body["budget_threshold"] == 5_000
    assert body["urgencies"] == ["High", "Medium", "Low"]
    assert "Emergency Repair" in body["categories"]
    assert body["demo_tools_enabled"] is True


def test_create_lead_runs_triage_and_persists(client: TestClient) -> None:
    lead = create_lead(client, HIGH_LEAD)

    assert lead["id"] > 0
    assert lead["name"] == "Maya Chen"
    assert lead["email"] == "maya.chen@acmesystems.example"
    assert lead["budget"] == 18_000
    assert lead["urgency"] == "High"
    assert lead["category"] == "Emergency Repair"
    assert lead["qualified"] is True
    assert lead["status"] == "New"
    assert lead["triage_engine"] == "rules"
    assert lead["triage_score"] >= 80
    assert lead["created_at"].endswith("Z")
    assert lead["status_updated_at"] is None
    assert isinstance(lead["triage_reasons"], list) and lead["triage_reasons"]

    detail = client.get(f"/api/leads/{lead['id']}")
    assert detail.status_code == 200
    assert detail.json()["project_description"] == HIGH_LEAD["project_description"]


def test_validation_errors(client: TestClient) -> None:
    invalid_email = client.post("/api/leads", json={**HIGH_LEAD, "email": "not-an-email"})
    assert invalid_email.status_code == 422

    no_description = client.post(
        "/api/leads", json={"name": "No Brief", "email": "no@example.com"}
    )
    assert no_description.status_code == 422

    assert client.get("/api/leads/9999").status_code == 404
    assert client.patch("/api/leads/9999/status", json={"status": "Closed"}).status_code == 404


def test_budget_string_and_invalid_status(client: TestClient) -> None:
    lead = create_lead(client, {**MEDIUM_LEAD, "budget": "$12k"})
    assert lead["budget"] == 12_000

    bad_status = client.patch(f"/api/leads/{lead['id']}/status", json={"status": "Archived"})
    assert bad_status.status_code == 422


def test_list_filters_search_sort_and_pagination(client: TestClient) -> None:
    high = create_lead(client, HIGH_LEAD)
    medium = create_lead(client, MEDIUM_LEAD)
    low = create_lead(client, LOW_LEAD)

    listing = client.get("/api/leads")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 3
    assert [item["name"] for item in body["items"]] == [
        "Maya Chen",
        "Ethan Cole",
        "Sofia Mendes",
    ]

    by_urgency = client.get("/api/leads", params={"urgency": "High"}).json()
    assert by_urgency["total"] == 1
    assert by_urgency["items"][0]["id"] == high["id"]

    by_status = client.get("/api/leads", params={"status": "New"}).json()
    assert by_status["total"] == 3

    by_search = client.get("/api/leads", params={"q": "booking"}).json()
    assert by_search["total"] == 1
    assert by_search["items"][0]["id"] == medium["id"]

    qualified = client.get("/api/leads", params={"qualified": "true"}).json()
    assert qualified["total"] == 2
    assert {item["id"] for item in qualified["items"]} == {high["id"], medium["id"]}

    oldest = client.get("/api/leads", params={"sort": "oldest"}).json()
    assert oldest["items"][0]["id"] == high["id"]

    newest = client.get("/api/leads", params={"sort": "newest"}).json()
    assert newest["items"][0]["id"] == low["id"]

    page = client.get("/api/leads", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 3
    assert len(page["items"]) == 1
    assert page["limit"] == 1
    assert page["offset"] == 1

    assert client.get("/api/leads", params={"limit": 0}).status_code == 422


def test_status_workflow_and_stats(client: TestClient) -> None:
    high = create_lead(client, HIGH_LEAD)
    medium = create_lead(client, MEDIUM_LEAD)
    create_lead(client, LOW_LEAD)

    before = client.get("/api/stats").json()
    assert before["total"] == 3
    assert before["high_urgency"] == 1
    assert before["qualified"] == 2
    assert before["new_leads"] == 3
    assert before["qualified_pipeline"] == 26_000

    updated = client.patch(f"/api/leads/{high['id']}/status", json={"status": "Contacted"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "Contacted"
    assert updated.json()["status_updated_at"] is not None

    closed = client.patch(f"/api/leads/{medium['id']}/status", json={"status": "Closed"})
    assert closed.status_code == 200

    after = client.get("/api/stats").json()
    assert after["total"] == 3
    assert after["new_leads"] == 1
    assert after["contacted"] == 1
    assert after["closed"] == 1

    filtered = client.get("/api/leads", params={"status": "Contacted"}).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == high["id"]


def test_csv_export(client: TestClient) -> None:
    create_lead(client, HIGH_LEAD)
    create_lead(client, LOW_LEAD)

    response = client.get("/api/leads/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=" in response.headers["content-disposition"]

    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0][0:4] == ["id", "created_at", "name", "email"]
    assert len(rows) == 3
    assert any(row[2] == "Maya Chen" for row in rows[1:])

    filtered = client.get("/api/leads/export.csv", params={"urgency": "High"})
    assert len(list(csv.reader(io.StringIO(filtered.text)))) == 2


def test_demo_seed_is_idempotent(client: TestClient) -> None:
    first = client.post("/api/demo/seed")
    assert first.status_code == 200
    assert first.json()["created"] == 10

    second = client.post("/api/demo/seed")
    assert second.status_code == 200
    assert second.json()["created"] == 0

    listing = client.get("/api/leads", params={"limit": 200}).json()
    assert listing["total"] == 10
    assert all(item["triage_engine"] == "rules" for item in listing["items"])

    stats = client.get("/api/stats").json()
    assert stats["high_urgency"] == 3
    assert stats["qualified"] == 6
    assert stats["qualified_pipeline"] == 77_500


def test_dashboard_and_static_assets(client: TestClient) -> None:
    create_lead(client, HIGH_LEAD)

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "TriageOps" in dashboard.text
    assert "Submit test lead" in dashboard.text
    assert "window.__TRIAGEOPS__" in dashboard.text
    assert dashboard.headers["cache-control"] == "no-store"

    script = client.get("/static/js/main.js")
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]

    styles = client.get("/static/dashboard.css")
    assert styles.status_code == 200
    assert "text/css" in styles.headers["content-type"]

    root = client.get("/", follow_redirects=False)
    assert root.status_code == 307
    assert root.headers["location"] == "/dashboard"

    headers = dashboard.headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"


def test_docs_and_openapi(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "/api/leads" in schema["paths"]
    assert "/api/stats" in schema["paths"]
    assert "/health" in schema["paths"]
