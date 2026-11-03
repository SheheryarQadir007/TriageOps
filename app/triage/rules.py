"""Deterministic, rule-based lead triage.

The rules are intentionally transparent: every score has a human-readable
reason attached so operators can audit (and tune) the classifier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from app.enums import LeadCategory, Urgency
from app.triage.base import LeadContext, TriageResult, TriageStrategy, combine_scores

# ── Keyword signals ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class KeywordSignal:
    label: str
    pattern: re.Pattern[str]
    weight: int
    reason: str
    strong: bool = False


def _kw(
    label: str,
    pattern: str,
    weight: int,
    reason: str,
    *,
    strong: bool = False,
) -> KeywordSignal:
    return KeywordSignal(label, re.compile(pattern, re.IGNORECASE), weight, reason, strong)


HIGH_SIGNALS: tuple[KeywordSignal, ...] = (
    _kw("urgent", r"\b(urgent|urgently|urgency)\b", 35, "Explicitly marked urgent.", strong=True),
    _kw(
        "asap",
        r"\b(asap|as soon as possible)\b",
        35,
        "Requested as soon as possible.",
        strong=True,
    ),
    _kw(
        "immediately",
        r"\b(immediately|right away|without delay)\b",
        30,
        "Requested immediately.",
        strong=True,
    ),
    _kw("emergency", r"\bemergency\b", 45, "Described as an emergency.", strong=True),
    _kw("critical", r"\bcritical\b", 35, "Flagged as critical.", strong=True),
    _kw(
        "site down",
        r"\b(?:production|site|website|web app|server|system|app|application)\s+"
        r"(?:is\s+|seems\s+|appears\s+)?(?:down|offline|unreachable)\b",
        50,
        "A production system is reported down.",
        strong=True,
    ),
    _kw("down", r"\bdown\b", 30, "Mentions a system being down.", strong=False),
    _kw(
        "broken",
        r"\b(broken|not working|doesn'?t work|does not work|won'?t (?:load|start|open))\b",
        35,
        "Something is broken or not working.",
        strong=True,
    ),
    _kw(
        "outage",
        r"\b(outage|crash(?:ed|ing)?|fatal|locked out)\b",
        40,
        "Mentions a crash, outage, or lockout.",
        strong=True,
    ),
    _kw(
        "security incident",
        r"\b(hacked|hacking|breach|data loss|ransomware|security incident)\b",
        55,
        "Potential security or data-loss incident.",
        strong=True,
    ),
    _kw(
        "login failure",
        r"\b(can'?t|cannot|unable to)\s+(?:log|sign)\s*in\b",
        30,
        "Users cannot sign in.",
        strong=True,
    ),
    _kw(
        "revenue impact",
        r"\b(losing|lose)\s+(?:revenue|customers|sales|money|orders)\b",
        40,
        "Reports active revenue or customer loss.",
        strong=True,
    ),
    _kw(
        "time-sensitive",
        r"\b(time[- ]sensitive|no later than)\b",
        30,
        "Explicitly time-sensitive.",
        strong=False,
    ),
    _kw(
        "end of day",
        r"\b(end of (?:day|week)|eod)\b",
        25,
        "References an end-of-day or end-of-week cutoff.",
        strong=False,
    ),
    _kw("today", r"\b(today|tonight)\b", 20, "References today.", strong=False),
    _kw("tomorrow", r"\bby tomorrow\b", 30, "Due by tomorrow.", strong=False),
    _kw("deadline", r"\bdeadline\b", 20, "Explicit deadline mentioned.", strong=False),
    _kw("blocking", r"\bblocking\b", 25, "Work is currently blocked.", strong=False),
)

MEDIUM_SIGNALS: tuple[KeywordSignal, ...] = (
    _kw("soon", r"\bsoon\b", 8, "Wants work started soon."),
    _kw("this week", r"\bthis week\b", 15, "Targeting this week."),
    _kw("next week", r"\bnext week\b", 10, "Targeting next week."),
    _kw("priority", r"\bpriority\b", 12, "Marked as a priority."),
    _kw("important", r"\bimportant\b", 10, "Marked as important."),
    _kw("migration", r"\b(migrate|migration)\b", 10, "Involves a migration."),
    _kw("upgrade", r"\bupgrade\b", 10, "Involves an upgrade."),
    _kw("launch", r"\blaunch(?:ing)?\b", 10, "Has an upcoming launch."),
    _kw("slow", r"\b(slow|slowdown|performance issue)\b", 12, "Reports slow performance."),
    _kw("bug", r"\bbug\b", 15, "Reports a bug."),
    _kw("issue", r"\bissue\b", 8, "Reports an issue."),
    _kw("fix", r"\b(fix|repair)\b", 12, "Requests a fix or repair."),
    _kw("integration", r"\b(integration|integrate)\b", 8, "Involves an integration."),
    _kw("review", r"\b(review|audit)\b", 6, "Requests a review or audit."),
    _kw("quote", r"\b(quote|proposal|pricing)\b", 5, "Requests pricing or a proposal."),
)


# ── Category signals ─────────────────────────────────────────────────────────

CATEGORY_TERMS: dict[LeadCategory, tuple[tuple[re.Pattern[str], int], ...]] = {
    LeadCategory.EMERGENCY_REPAIR: tuple(
        (re.compile(pattern, re.IGNORECASE), weight)
        for pattern, weight in (
            (
                r"\b(emergency|outage|down|offline|unreachable|broken|crash(?:ed|ing)?|fatal|locked out)\b",
                4,
            ),
            (r"\b(hacked|hacking|breach|data loss|ransomware|security incident)\b", 5),
            (
                r"\b(not working|doesn'?t work|does not work|won'?t (?:load|open|start)|"
                r"can'?t log ?in|cannot log ?in|error|failing|failure)\b",
                3,
            ),
            (r"\b(bug|fix|repair|restore|recover|troubleshoot)\b", 2),
            (
                r"\b(?:production|server|website|site|app|application)\s+"
                r"(?:is\s+|seems\s+)?(?:down|offline|broken)\b",
                5,
            ),
        )
    ),
    LeadCategory.NEW_IMPLEMENTATION: tuple(
        (re.compile(pattern, re.IGNORECASE), weight)
        for pattern, weight in (
            (r"\b(new project|from scratch|greenfield)\b", 4),
            (r"\b(build|develop|implement|create)\b", 3),
            (r"\b(design|redesign|moderni[sz]e|revamp)\b", 2),
            (r"\b(launch|rollout|set up|setup)\b", 2),
            (r"\b(migrat(?:e|ion)|integration|integrate|automation|automate)\b", 2),
            (r"\b(platform|website|web app|mobile app|portal|dashboard|api|saas)\b", 1),
            (r"\bnew\b", 2),
        )
    ),
    LeadCategory.MAINTENANCE: tuple(
        (re.compile(pattern, re.IGNORECASE), weight)
        for pattern, weight in (
            (r"\b(maintain|maintenance|retainer|ongoing support)\b", 4),
            (r"\b(support|updates?|upgrades?|patches?|security patch)\b", 2),
            (r"\b(audit|monitor|monitoring|backup|backups|optimi[sz]e|optimi[sz]ation|tune|cleanup)\b", 2),
            (r"\b(monthly|quarterly|annual|recurring)\b", 3),
            (r"\b(minor|small change|bug fix|tweak)\b", 2),
        )
    ),
    LeadCategory.GENERAL_INQUIRY: tuple(
        (re.compile(pattern, re.IGNORECASE), weight)
        for pattern, weight in (
            (r"\b(pricing|price|cost|quote|estimate|proposal)\b", 3),
            (r"\b(consultation|consult|information|info|question|questions)\b", 2),
            (r"\b(curious|exploring|looking around|learn more|not sure|just checking)\b", 3),
            (r"\b(services|availability|available)\b", 1),
        )
    ),
}

CATEGORY_REASONS: dict[LeadCategory, str] = {
    LeadCategory.EMERGENCY_REPAIR: "Category matched emergency/repair language.",
    LeadCategory.NEW_IMPLEMENTATION: "Category matched build, design, or launch language.",
    LeadCategory.MAINTENANCE: "Category matched ongoing support or maintenance language.",
    LeadCategory.GENERAL_INQUIRY: "No strong project signal; treated as a general inquiry.",
}

CATEGORY_PRIORITY: tuple[LeadCategory, ...] = (
    LeadCategory.EMERGENCY_REPAIR,
    LeadCategory.NEW_IMPLEMENTATION,
    LeadCategory.MAINTENANCE,
    LeadCategory.GENERAL_INQUIRY,
)


# ── Deadline parsing ─────────────────────────────────────────────────────────

UNIT_HOURS = {
    "h": 1,
    "hr": 1,
    "hrs": 1,
    "hour": 1,
    "hours": 1,
    "d": 24,
    "day": 24,
    "days": 24,
    "w": 168,
    "wk": 168,
    "wks": 168,
    "week": 168,
    "weeks": 168,
    "mo": 720,
    "mos": 720,
    "month": 720,
    "months": 720,
}

_UNIT_PATTERN = r"(hours?|hrs?|hr|h|days?|d|weeks?|wks?|wk|w|months?|mos?|mo)\b"

WITHIN_RE = re.compile(
    rf"\b(?:within|inside|under|in)\s+(?:the\s+next\s+)?(\d{{1,3}})\s*(?:-\s*)?{_UNIT_PATTERN}",
    re.IGNORECASE,
)
FROM_NOW_RE = re.compile(
    rf"\b(\d{{1,3}})\s*{_UNIT_PATTERN}\s+(?:from\s+now|out)\b",
    re.IGNORECASE,
)
DEADLINE_UNIT_RE = re.compile(
    rf"\b(\d{{1,3}})\s*(?:-\s*)?{_UNIT_PATTERN}\s+(?:deadline|window|turnaround|sla)\b",
    re.IGNORECASE,
)

RELATIVE_RE = re.compile(
    r"\b(?:by|before|due|deadline(?:\s+is)?)\s+"
    r"(today|tonight|tomorrow|end of day|end of week|eod|this week)\b",
    re.IGNORECASE,
)
WEEKDAY_RE = re.compile(
    r"\b(?:by|before|due|deadline(?:\s+is)?)\s+(next\s+)?"
    r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)
ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
MONTH_DATE_RE = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b",
    re.IGNORECASE,
)

MONTH_NUMBERS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


@dataclass(frozen=True, slots=True)
class Deadline:
    hours: float
    label: str
    reason: str


def _hours_until(moment: datetime, now: datetime) -> float:
    return (moment - now).total_seconds() / 3600


def _at_eod(day: datetime, hour: int = 18) -> datetime:
    return datetime.combine(day.date(), time(hour, 0), tzinfo=timezone.utc)


def _deadline_points(hours: float) -> int:
    if hours < 0:
        return 55
    if hours <= 24:
        return 50
    if hours <= 48:
        return 42
    if hours <= 72:
        return 28
    if hours <= 7 * 24:
        return 16
    if hours <= 30 * 24:
        return 8
    return 3


def _deadline_label(hours: float) -> str:
    if hours < 0:
        return "deadline overdue"
    if hours <= 48:
        return "deadline <48h"
    if hours <= 7 * 24:
        return "deadline <7d"
    if hours <= 30 * 24:
        return "deadline <30d"
    return "deadline >30d"


def _deadline_reason(hours: float) -> str:
    if hours < 0:
        return "The stated deadline has already passed."
    if hours <= 48:
        return f"Deadline is in about {max(1, round(hours))} hours (< 48h)."
    days = max(1, round(hours / 24))
    return f"Deadline is about {days} days away."


def find_deadline(text: str, now: datetime | None = None) -> Deadline | None:
    """Extract the earliest explicit deadline from free text, if any."""
    now = now or datetime.now(timezone.utc)
    candidates: list[float] = []

    for regex in (WITHIN_RE, FROM_NOW_RE, DEADLINE_UNIT_RE):
        for match in regex.finditer(text):
            amount = int(match.group(1))
            unit = match.group(2).lower()
            candidates.append(amount * UNIT_HOURS.get(unit, 24))

    for match in RELATIVE_RE.finditer(text):
        phrase = match.group(1).lower()
        if phrase in {"today", "tonight"}:
            hour = 22 if phrase == "tonight" else 18
            hours = _hours_until(_at_eod(now, hour), now)
            candidates.append(max(0.5, hours))
        elif phrase == "tomorrow":
            hours = _hours_until(_at_eod(now + timedelta(days=1)), now)
            candidates.append(max(0.5, hours))
        else:  # end of day / eod / this week / end of week
            if "week" in phrase:
                days = (4 - now.weekday()) % 7
                target = now + timedelta(days=days)
                hours = _hours_until(_at_eod(target), now)
                if hours <= 0:
                    hours += 7 * 24
                candidates.append(hours)
            else:
                hours = _hours_until(_at_eod(now), now)
                candidates.append(max(0.5, hours))

    for match in WEEKDAY_RE.finditer(text):
        is_next = bool(match.group(1))
        weekday = WEEKDAYS[match.group(2).lower()]
        days = (weekday - now.weekday()) % 7
        if is_next and days == 0:
            days = 7
        target = now + timedelta(days=days)
        hours = _hours_until(_at_eod(target), now)
        if hours < 0:
            hours += 7 * 24
        candidates.append(hours)

    for match in ISO_DATE_RE.finditer(text):
        try:
            target = datetime(
                int(match.group(1)), int(match.group(2)), int(match.group(3)),
                18, 0, tzinfo=timezone.utc,
            )
        except ValueError:
            continue
        hours = _hours_until(target, now)
        if hours >= -7 * 24:
            candidates.append(hours)

    for match in NUMERIC_DATE_RE.finditer(text):
        month, day = int(match.group(1)), int(match.group(2))
        if not (1 <= month <= 12 and 1 <= day <= 31):
            continue
        year_part = match.group(3)
        if year_part:
            year = int(year_part)
            if year < 100:
                year += 2000
        else:
            year = now.year
        try:
            target = datetime(year, month, day, 18, 0, tzinfo=timezone.utc)
        except ValueError:
            continue
        if not year_part and target < now - timedelta(days=7):
            target = target.replace(year=year + 1)
        hours = _hours_until(target, now)
        if hours >= -7 * 24:
            candidates.append(hours)

    for match in MONTH_DATE_RE.finditer(text):
        month = MONTH_NUMBERS[match.group(1).lower()[:3]]
        day = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else now.year
        try:
            target = datetime(year, month, day, 18, 0, tzinfo=timezone.utc)
        except ValueError:
            continue
        if not match.group(3) and target < now - timedelta(days=7):
            target = target.replace(year=year + 1)
        hours = _hours_until(target, now)
        if hours >= -7 * 24:
            candidates.append(hours)

    if not candidates:
        return None

    earliest = min(candidates)
    return Deadline(
        hours=earliest,
        label=_deadline_label(earliest),
        reason=_deadline_reason(earliest),
    )


# ── Description completeness ─────────────────────────────────────────────────

_CONCRETE_ASK_RE = re.compile(
    r"\b(need|needs|looking to|looking for|want|would like|help|build|fix|migrate|"
    r"integrate|design|develop|implement|audit|automate|improve|replace|set up|launch|"
    r"support|maintain|quote|proposal|scope)\b",
    re.IGNORECASE,
)
_CONTEXT_RE = re.compile(
    r"\b(we|our|my|i am|i'm|company|business|team|customers|users|currently|existing|"
    r"goal|because|so that|problem|challenge)\b",
    re.IGNORECASE,
)
_SPECIFICITY_RE = re.compile(
    r"(\$\s?\d|\b\d{1,3}(?:,\d{3})+\b|\b\d+\s*(?:users|employees|locations|hours|days|weeks|"
    r"products|sites|stores)\b|\b(?:wordpress|shopify|salesforce|hubspot|aws|azure|react|"
    r"python|node|stripe|quickbooks|zapier)\b|https?://)",
    re.IGNORECASE,
)


def description_completeness(text: str, min_chars: int = 60) -> int:
    stripped = text.strip()
    chars = len(stripped)
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", stripped)
    word_count = len(words)

    score = min(35.0, chars / 350 * 35)
    score += min(20.0, word_count / 50 * 20)
    if _CONCRETE_ASK_RE.search(stripped):
        score += 12
    if _CONTEXT_RE.search(stripped):
        score += 10
    if _SPECIFICITY_RE.search(stripped):
        score += 8
    if word_count >= 12 and chars >= min_chars:
        score += 15

    return int(max(0, min(100, round(score))))


# ── Rule engine ──────────────────────────────────────────────────────────────


class RuleBasedTriage(TriageStrategy):
    """Fast, deterministic classifier used by default and as LLM fallback."""

    name = "rules"

    def __init__(self, budget_threshold: float = 5_000.0, min_description_chars: int = 60) -> None:
        self.budget_threshold = budget_threshold
        self.min_description_chars = min_description_chars

    def classify(self, lead: LeadContext) -> TriageResult:
        text = " ".join(lead.project_description.split())
        now = datetime.now(timezone.utc)

        high_matches = [signal for signal in HIGH_SIGNALS if signal.pattern.search(text)]
        medium_matches = [signal for signal in MEDIUM_SIGNALS if signal.pattern.search(text)]
        deadline = find_deadline(text, now)

        keyword_score = sum(signal.weight for signal in high_matches)
        keyword_score += sum(signal.weight for signal in medium_matches)
        deadline_points = _deadline_points(deadline.hours) if deadline else 0
        urgency_score = min(100, keyword_score + deadline_points)

        has_strong_signal = any(signal.strong for signal in high_matches)
        has_short_deadline = deadline is not None and deadline.hours <= 48
        if has_strong_signal or has_short_deadline or urgency_score >= 60:
            urgency = Urgency.HIGH
            urgency_score = max(urgency_score, 60)
        elif urgency_score >= 20:
            urgency = Urgency.MEDIUM
            urgency_score = max(urgency_score, 25)
        else:
            urgency = Urgency.LOW
            urgency_score = min(urgency_score, 24)

        category, category_reason, category_hits = self._classify_category(
            text, urgency, lead.budget
        )

        completeness = description_completeness(text, self.min_description_chars)
        budget_fit = (
            0
            if lead.budget is None
            else round(min(100.0, max(0.0, lead.budget / self.budget_threshold * 100)))
        )
        qualification_score = round(0.55 * completeness + 0.45 * budget_fit)

        budget_ok = lead.budget is not None and lead.budget >= self.budget_threshold
        description_ok = completeness >= 60
        qualified = budget_ok and description_ok

        reasons: list[str] = []
        signals: list[str] = []

        if high_matches:
            labels = _unique_labels(high_matches)
            reasons.append(f"Urgency signals detected: {', '.join(labels[:4])}.")
            signals.extend(labels)
        if medium_matches:
            labels = _unique_labels(medium_matches)
            reasons.append(f"Priority language detected: {', '.join(labels[:3])}.")
            signals.extend(labels)
        if deadline:
            reasons.append(deadline.reason)
            signals.append(deadline.label)
        if not high_matches and not medium_matches and not deadline:
            reasons.append("No urgency or deadline language detected; triaged as low urgency.")

        reasons.append(category_reason)
        if category_hits:
            signals.append(f"topic: {category_hits[0]}")

        if lead.budget is None:
            reasons.append("No budget provided, so the lead cannot be auto-qualified.")
            signals.append("budget:missing")
        elif budget_ok:
            reasons.append(
                f"Budget ${lead.budget:,.0f} meets the ${self.budget_threshold:,.0f} threshold."
            )
            signals.append("budget:met")
        else:
            reasons.append(
                f"Budget ${lead.budget:,.0f} is below the ${self.budget_threshold:,.0f} threshold."
            )
            signals.append("budget:below")

        if description_ok:
            reasons.append(f"Description completeness {completeness}/100 — enough detail to qualify.")
            signals.append("description:complete")
        else:
            reasons.append(
                f"Description completeness {completeness}/100 — more detail is needed to qualify."
            )
            signals.append("description:incomplete")

        if qualified:
            reasons.append("Auto-qualified: budget and description both meet policy.")
        else:
            failed = []
            if not budget_ok:
                failed.append("budget")
            if not description_ok:
                failed.append("description detail")
            reasons.append(f"Not auto-qualified ({' and '.join(failed)} did not meet policy).")

        return TriageResult(
            urgency=urgency,
            urgency_score=urgency_score,
            category=category,
            qualified=qualified,
            completeness_score=completeness,
            qualification_score=qualification_score,
            triage_score=combine_scores(urgency_score, qualification_score),
            reasons=reasons,
            matched_signals=_dedupe(signals),
            engine=self.name,
        )

    def _classify_category(
        self, text: str, urgency: Urgency, budget: float | None
    ) -> tuple[LeadCategory, str, list[str]]:
        scores: dict[LeadCategory, int] = {}
        hits: dict[LeadCategory, list[str]] = {}

        for category, terms in CATEGORY_TERMS.items():
            score = 0
            category_hits: list[str] = []
            for pattern, weight in terms:
                match = pattern.search(text)
                if match:
                    score += weight
                    category_hits.append(match.group(0).strip().lower())
            scores[category] = score
            hits[category] = category_hits

        if urgency is Urgency.HIGH:
            scores[LeadCategory.EMERGENCY_REPAIR] += 4
        if budget is not None and budget >= self.budget_threshold:
            scores[LeadCategory.NEW_IMPLEMENTATION] += 1
        if "?" in text:
            scores[LeadCategory.GENERAL_INQUIRY] += 1

        best_score = max(scores.values())
        if best_score <= 0:
            return (
                LeadCategory.GENERAL_INQUIRY,
                CATEGORY_REASONS[LeadCategory.GENERAL_INQUIRY],
                [],
            )

        # Deterministic tie-breaking based on operational priority.
        for category in CATEGORY_PRIORITY:
            if scores[category] == best_score:
                return category, CATEGORY_REASONS[category], hits[category]

        return LeadCategory.GENERAL_INQUIRY, CATEGORY_REASONS[LeadCategory.GENERAL_INQUIRY], []


def _unique_labels(signals: list[KeywordSignal]) -> list[str]:
    seen: set[str] = set()
    labels: list[str] = []
    for signal in signals:
        if signal.label not in seen:
            seen.add(signal.label)
            labels.append(signal.label)
    return labels


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
