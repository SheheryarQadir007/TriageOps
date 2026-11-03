# TriageOps

A production-ready lead intake and operational triage backend built with **FastAPI**, **SQLAlchemy**, and **SQLite** — plus a single-page operations dashboard for reviewing, filtering, and working the pipeline.

Inbound leads are scored synchronously on intake: urgency, category, qualification, a blended 0–100 priority score, and human-readable reasoning are persisted with each lead. The default classifier is deterministic and rule-based; OpenAI or Gemini can be enabled as a drop-in replacement with automatic fallback to the rules engine.

---

## What it does

- **Lead intake** — `POST /api/leads` accepts contact details, budget, and a project brief. Budget inputs tolerate common formats such as `12000`, `$12,000`, and `12k`.
- **Triage** — detects urgency language (`urgent`, `ASAP`, `down`, `broken`, `outage`, security incidents), parses deadlines (including relative dates and `<48h` cutoffs), classifies the work, and computes description completeness.
- **Qualification policy** — a lead is qualified only when **budget ≥ threshold** *and* **description completeness ≥ 60/100**. The threshold defaults to **$5,000**.
- **Priority score** — `65% urgency + 35% qualification`, clamped to 0–100.
- **Operations workflow** — status moves through `New → Contacted → Closed`, with timestamps and audit-friendly triage reasons stored in SQLite.
- **Dashboard** — summary cards, status tabs, urgency/category/qualified filters, search, sorting, detail drawer, status updates, CSV export, and a live test-lead simulator.
- **Optional LLMs** — OpenAI or Gemini can classify leads. API/parse failures transparently fall back to the rule engine, and the LLM cannot override the budget/description qualification policy.

---

## Project layout

```
TriageOps/
├── main.py                     # App factory, lifespan, middleware, health, static mount
├── app/
│   ├── config.py               # Pydantic settings / .env loading
│   ├── database.py             # SQLAlchemy engine, SQLite WAL, session dependency
│   ├── enums.py                # Urgency, status, and category values
│   ├── models.py               # Lead ORM model
│   ├── schemas.py              # Request/response schemas and budget parsing
│   ├── services.py             # Intake, filtering, stats, CSV, status workflow
│   ├── seed.py                 # Deterministic demo dataset
│   ├── api/
│   │   ├── leads.py            # POST/GET/PATCH + CSV export
│   │   ├── system.py           # /api/stats, /api/meta, demo seed
│   │   └── dashboard.py        # Server-rendered dashboard shell
│   ├── triage/
│   │   ├── base.py             # TriageStrategy interface and LeadContext
│   │   ├── rules.py            # Default rule engine, deadlines, completeness
│   │   ├── llm.py              # OpenAI/Gemini adapters with fallback
│   │   └── __init__.py         # Engine factory
│   ├── templates/dashboard.html
│   └── static/                 # CSS + ES-module dashboard JavaScript
├── tests/                      # Triage unit tests + API/dashboard tests
├── requirements.txt
├── requirements-dev.txt
├── render.yaml                 # Render blueprint (free tier)
├── Dockerfile
└── .env.example
```

---

## Quick start

Requires Python 3.12+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

Open:

| URL | Purpose |
| --- | --- |
| <http://127.0.0.1:8000/dashboard> | Operations dashboard |
| <http://127.0.0.1:8000/docs> | Swagger UI |
| <http://127.0.0.1:8000/redoc> | ReDoc |
| <http://127.0.0.1:8000/health> | Health / DB check |

On first start, 10 realistic demo leads are seeded into an empty database (`SEED_DEMO_DATA=true`). If you prefer a blank pipeline, set `SEED_DEMO_DATA=false` and delete `triageops.db`.

### Submit a lead

```bash
curl -X POST http://127.0.0.1:8000/api/leads \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Maya Chen",
    "email": "maya@acmesystems.example",
    "company": "Acme Systems",
    "phone": "+1 (415) 555-0102",
    "budget": "18000",
    "project_description": "URGENT: our customer portal is down after last night'\''s deploy. We are losing orders every hour. The app returns a 502 error. Need someone to diagnose the outage and restore service today."
  }'
```

Example triage output:

```json
{
  "id": 11,
  "urgency": "High",
  "urgency_score": 100,
  "category": "Emergency Repair",
  "qualified": true,
  "completeness_score": 68,
  "qualification_score": 82,
  "triage_score": 94,
  "status": "New",
  "triage_reasons": [
    "Urgency signals detected: urgent, down, outage, revenue impact.",
    "Category matched emergency/repair language.",
    "Budget $18,000 meets the $5,000 threshold.",
    "Description completeness 68/100 — enough detail to qualify.",
    "Auto-qualified: budget and description both meet policy."
  ]
}
```

---

## API

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/leads` | Create and triage a lead |
| `GET` | `/api/leads` | List/filter/search/sort leads |
| `GET` | `/api/leads/{id}` | Fetch one lead |
| `PATCH` | `/api/leads/{id}/status` | Set `New`, `Contacted`, or `Closed` |
| `GET` | `/api/leads/export.csv` | Export the current filter as CSV |
| `GET` | `/api/stats` | Pipeline summary metrics |
| `GET` | `/api/meta` | Triage policy and enum metadata |
| `POST` | `/api/demo/seed` | Idempotent demo seed (when enabled) |
| `GET` | `/health` | Liveness and database check |
| `GET` | `/dashboard` | Dashboard UI |

### List query parameters

| Parameter | Values | Default |
| --- | --- | --- |
| `status` | `New`, `Contacted`, `Closed` | all |
| `urgency` | `High`, `Medium`, `Low` | all |
| `category` | `Emergency Repair`, `New Implementation`, `Maintenance`, `General Inquiry` | all |
| `qualified` | `true` / `false` | all |
| `q` | free-text search over name, company, email, description | — |
| `sort` | `urgency`, `score`, `newest`, `oldest` | `urgency` |
| `limit` | 1–200 | 100 |
| `offset` | ≥ 0 | 0 |

---

## How triage works

The engine receives a normalized `LeadContext` and returns a `TriageResult`. Scores are deterministic and every reason is stored for auditing.

### Urgency

1. Keyword signals are weighted (`urgent` 35, `outage` 40, production `down` 50, security incident 55, and so on).
2. Deadlines are parsed from phrases like `within 12 hours`, `by tomorrow`, `by Friday`, `2026-06-01`, and `June 1`.
3. Deadline points depend on proximity: `<24h` 50, `<48h` 42, `<72h` 28, `<7d` 16, `<30d` 8.
4. Any **strong** signal or a `<48h` deadline forces `High`. Otherwise scores ≥ 60 are `High`, ≥ 20 `Medium`, and the rest `Low`.

### Category

Weighted phrase matching selects `Emergency Repair`, `New Implementation`, `Maintenance`, or `General Inquiry`. Ties are resolved by operational priority (emergency first). High urgency nudges emergency classification; a budget at/above threshold nudges implementation.

### Qualification

```text
budget_ok      = budget is present and budget >= BUDGET_THRESHOLD
description_ok = completeness >= 60
qualified      = budget_ok and description_ok
```

Completeness rewards length, word count, a concrete ask, business context, and specificity (platforms, numbers, URLs). `qualification_score` blends completeness (55%) with budget fit (45%).

```text
triage_score = round(0.65 * urgency_score + 0.35 * qualification_score)
```

### Adding a classifier

Implement `TriageStrategy` and return a `TriageResult`:

```python
from app.triage.base import LeadContext, TriageResult, TriageStrategy

class MyTriage(TriageStrategy):
    name = "my-engine"

    def classify(self, lead: LeadContext) -> TriageResult:
        # call a model, vendor API, or internal service here
        ...

# in main.py
app = create_app(settings, triage_engine=MyTriage())
```

The service owns the strategy and calls `close()` during shutdown, so long-lived HTTP clients can be released cleanly.

---

## Optional OpenAI / Gemini triage

Set a provider and key in `.env`:

```dotenv
TRIAGE_PROVIDER=openai      # auto | rules | openai | gemini
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# or
TRIAGE_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
```

`TRIAGE_PROVIDER=auto` (the default) uses OpenAI when `OPENAI_API_KEY` is set, then Gemini, and otherwise rules. When an LLM call fails, times out, or returns invalid JSON, the rules engine classifies the lead instead and the stored engine name becomes `rules-fallback`.

LLM output is normalized before persistence: qualification is still subject to the budget/description policy, scores are clamped, and invalid categories/urgencies fall back to the rule result.

---

## Configuration

All settings are environment variables (case-insensitive), loaded from `.env` when present. See `.env.example`.

| Variable | Default | Description |
| --- | --- | --- |
| `APP_NAME` | `TriageOps` | Display name |
| `ENVIRONMENT` | `development` | Deployment environment |
| `DATABASE_URL` | `sqlite:///./triageops.db` | SQLAlchemy database URL |
| `LOG_LEVEL` | `INFO` | Python log level |
| `BUDGET_THRESHOLD` | `5000` | Minimum budget for qualification |
| `MIN_DESCRIPTION_CHARS` | `60` | Minimum descriptive length used by completeness scoring |
| `TRIAGE_PROVIDER` | `auto` | `auto`, `rules`, `openai`, or `gemini` |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | — / `gpt-4o-mini` | OpenAI adapter |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | — / `gemini-2.5-flash` | Gemini adapter |
| `LLM_TIMEOUT_SECONDS` | `12` | LLM request timeout |
| `SEED_DEMO_DATA` | `true` | Seed demo leads into an empty DB on startup |
| `ENABLE_DEMO_TOOLS` | `true` | Enable `POST /api/demo/seed` |
| `CORS_ORIGINS` | empty | Comma-separated allowed origins |

For production, set `ENVIRONMENT=production`, turn off demo tools, and provide a persistent database path or volume. The app always seeds only when the leads table is empty.

---

## Deployment

### Render (free tier)

`render.yaml` defines a Python web service with a `/health` check:

1. Push the repository to GitHub/GitLab.
2. In Render, create a **Blueprint** from the repo. Render reads `render.yaml`.
3. Add `OPENAI_API_KEY` or `GEMINI_API_KEY` as secret env vars if you want LLM triage (optional).
4. Deploy. The dashboard is served at the service URL.

The free plan has an **ephemeral filesystem**, so SQLite resets on redeploy/restart. `SEED_DEMO_DATA=true` repopulates the demo pipeline on each fresh instance. For durable data, attach a paid persistent disk and point `DATABASE_URL` at it (see the comment at the bottom of `render.yaml`).

### Docker

```bash
docker build -t triageops .
docker run --rm -p 8000:8000 \
  -v "$(pwd)/data:/app/data" \
  -e SEED_DEMO_DATA=true \
  triageops
```

The image runs as a non-root user, stores SQLite data in `/app/data`, and includes a health check. Set `OPENAI_API_KEY` / `GEMINI_API_KEY`, `TRIAGE_PROVIDER`, or a different `DATABASE_URL` with `-e` or an env file.

---

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite covers:

- urgent/security/low-urgency classification and category detection
- budget and description qualification policy
- deadline parsing and completeness ordering
- LLM fallback and qualification-policy override
- intake validation, filtering, search, sorting, pagination, stats, CSV, and status updates
- dashboard rendering, static assets, redirect, security headers, and OpenAPI

Tests use temporary SQLite databases; they never touch `triageops.db` or call external APIs.

---

## Operational notes

- SQLite runs in WAL mode with a 5-second busy timeout and `synchronous=NORMAL`, which is appropriate for a small operations desk.
- The dashboard uses the Tailwind Play CDN and Google Fonts. It needs internet access in the browser; for a fully offline/production build, compile Tailwind and self-host fonts.
- `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy` headers are set on every response.
- API responses are gzip-compressed above 1 KB.
- Lead descriptions are treated as untrusted data, including in LLM prompts (`SYSTEM_PROMPT` explicitly instructs the model not to follow instructions inside lead text).
