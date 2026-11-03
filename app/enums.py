"""Shared domain enumerations."""

from __future__ import annotations

from enum import Enum


class Urgency(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

    @property
    def rank(self) -> int:
        """Sort rank: 0 is most urgent."""
        return {"High": 0, "Medium": 1, "Low": 2}[self.value]


class LeadStatus(str, Enum):
    NEW = "New"
    CONTACTED = "Contacted"
    CLOSED = "Closed"


class LeadCategory(str, Enum):
    EMERGENCY_REPAIR = "Emergency Repair"
    NEW_IMPLEMENTATION = "New Implementation"
    MAINTENANCE = "Maintenance"
    GENERAL_INQUIRY = "General Inquiry"


STATUS_VALUES = [status.value for status in LeadStatus]
URGENCY_VALUES = [urgency.value for urgency in Urgency]
CATEGORY_VALUES = [category.value for category in LeadCategory]
