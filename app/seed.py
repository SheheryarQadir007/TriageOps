"""Seed the empty dashboard with realistic demo leads.

Seeding deliberately uses the deterministic rule engine (never the LLM) so it
is free, fast, and reproducible.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import LeadStatus
from app.models import Lead, utcnow
from app.triage.base import LeadContext, TriageStrategy

logger = logging.getLogger(__name__)

DEMO_LEADS: list[dict] = [
    {
        "name": "Priya Raman",
        "email": "priya@northwindlogistics.example",
        "phone": "+1 (415) 555-0142",
        "company": "Northwind Logistics",
        "budget": 18_000,
        "project_description": (
            "URGENT: our production warehouse dashboard went down this morning and the "
            "team cannot process shipments. We are losing orders every hour. The app is "
            "showing a 502 error after last night's deploy. Need someone to jump in "
            "immediately, diagnose the outage, and restore service today. We have a "
            "React frontend, FastAPI backend, and Postgres database on AWS."
        ),
        "age_hours": 0.5,
        "status": LeadStatus.NEW,
    },
    {
        "name": "Jae Park",
        "email": "jae.park@corexmfg.example",
        "phone": "+1 (206) 555-0188",
        "company": "Corex Manufacturing",
        "budget": 25_000,
        "project_description": (
            "We suspect a security incident. Multiple employees received phishing emails "
            "and we found an unfamiliar admin login on our Azure tenant last night. We "
            "need an urgent security audit, containment, and a remediation plan. Our IT "
            "team of 6 can provide logs. This is time-sensitive because we handle "
            "regulated customer data."
        ),
        "age_hours": 1.4,
        "status": LeadStatus.NEW,
    },
    {
        "name": "Sofia Mendes",
        "email": "sofia@brightlinestudio.example",
        "phone": None,
        "company": "Brightline Studio",
        "budget": None,
        "project_description": (
            "Hi — just curious about pricing and availability for web design services. "
            "We may have a project later this year but are still exploring options."
        ),
        "age_hours": 2.2,
        "status": LeadStatus.NEW,
    },
    {
        "name": "Leo Martins",
        "email": "leo@martinsbikes.example",
        "phone": "+1 (312) 555-0110",
        "company": "Martins Bikes",
        "budget": 10_000,
        "project_description": "Site down. Need help ASAP.",
        "age_hours": 3.1,
        "status": LeadStatus.NEW,
    },
    {
        "name": "Dana Kim",
        "email": "dana.kim@heliohealth.example",
        "phone": "+1 (617) 555-0163",
        "company": "Helio Health",
        "budget": 12_000,
        "project_description": (
            "We are looking for a monthly maintenance retainer for our WordPress site. "
            "The site has 40 pages, a patient intake form, and HubSpot integration. We "
            "need security patches, weekly backups, uptime monitoring, and about 10 hours "
            "of small updates each month. Our current agency is unresponsive and we want "
            "to transition within two weeks."
        ),
        "age_hours": 5.5,
        "status": LeadStatus.NEW,
    },
    {
        "name": "Ethan Cole",
        "email": "ethan@colefitness.example",
        "phone": "+1 (503) 555-0199",
        "company": "Cole Fitness",
        "budget": 1_500,
        "project_description": (
            "Need help fixing a bug on our booking page before next week. The confirmation "
            "email does not send after a customer books a class, and the calendar sometimes "
            "shows the wrong timezone. We use Squarespace and Stripe."
        ),
        "age_hours": 9.0,
        "status": LeadStatus.NEW,
    },
    {
        "name": "Marcus Webb",
        "email": "marcus@lumencoffee.example",
        "phone": "+1 (512) 555-0177",
        "company": "Lumen Coffee",
        "budget": 3_200,
        "project_description": (
            "I need a simple new website built for my coffee shop. Five pages, online menu, "
            "and a contact form. I already have photos and a logo. Hoping to launch before "
            "the holiday season."
        ),
        "age_hours": 26.0,
        "status": LeadStatus.CONTACTED,
    },
    {
        "name": "Tom Alvarez",
        "email": "tom@alvarezlegal.example",
        "phone": "+1 (213) 555-0121",
        "company": "Alvarez Legal",
        "budget": 7_500,
        "project_description": (
            "We need a secure client portal built for our 12-person law firm. Requirements: "
            "document upload with encryption, role-based access, e-signature via DocuSign, "
            "and Stripe billing. We currently use Dropbox and need to migrate 8,000 files. "
            "Target launch is in about six weeks, and our budget is approved."
        ),
        "age_hours": 31.0,
        "status": LeadStatus.CONTACTED,
    },
    {
        "name": "Ruth Okafor",
        "email": "ruth@atlasnonprofit.example",
        "phone": "+1 (404) 555-0155",
        "company": "Atlas Nonprofit",
        "budget": 9_000,
        "project_description": (
            "We want to redesign our donation page and add recurring giving. Our current "
            "site is on WordPress with GiveWP and Mailchimp. We need the new flow to be "
            "mobile-friendly, accessible, and connected to Salesforce. The board has "
            "approved a $9,000 budget and we would like to launch this quarter."
        ),
        "age_hours": 48.0,
        "status": LeadStatus.NEW,
    },
    {
        "name": "Nina Patel",
        "email": "nina@greenleafretail.example",
        "phone": "+1 (646) 555-0138",
        "company": "GreenLeaf Retail",
        "budget": 6_000,
        "project_description": (
            "Our Shopify store has been slow for weeks and we keep finding small bugs in "
            "the checkout flow. We need ongoing monthly support, performance optimization, "
            "and a cleanup of 30+ abandoned apps. Looking for a reliable maintenance "
            "partner for the next 12 months."
        ),
        "age_hours": 24 * 8,
        "status": LeadStatus.CLOSED,
    },
]


def seed_demo_leads(db: Session, triage: TriageStrategy) -> int:
    existing = db.scalar(select(func.count(Lead.id))) or 0
    if existing:
        return 0

    now = utcnow()
    for item in DEMO_LEADS:
        result = triage.classify(
            LeadContext(
                name=item["name"],
                email=item["email"],
                company=item["company"],
                budget=item["budget"],
                project_description=item["project_description"],
            )
        )
        created_at = now - timedelta(hours=item["age_hours"])
        status: LeadStatus = item["status"]
        lead = Lead(
            name=item["name"],
            email=item["email"],
            phone=item["phone"],
            company=item["company"],
            budget=item["budget"],
            project_description=item["project_description"],
            source="demo",
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
            status=status.value,
            created_at=created_at,
            updated_at=created_at,
            status_updated_at=(
                None
                if status is LeadStatus.NEW
                else created_at + timedelta(hours=2)
            ),
        )
        db.add(lead)

    db.commit()
    logger.info("Seeded %d demo leads", len(DEMO_LEADS))
    return len(DEMO_LEADS)
