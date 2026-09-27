from __future__ import annotations

PIT_STATUS = {"PIT_SAFE", "PIT_LIMITED", "NOT_PIT_SAFE", "UNKNOWN"}
FRESHNESS_STATUS = {"CURRENT", "AGING", "STALE", "UNKNOWN"}
QUALITY_STATUS = {"HIGH", "MEDIUM", "LOW", "INSUFFICIENT"}
AVAILABILITY_STATUS = {"AVAILABLE", "PARTIAL", "UNAVAILABLE"}

CONTRACT_COLUMNS = [
    "evidence_id", "module", "dimension", "indicator", "state", "direction",
    "value", "unit", "observation_date", "release_date", "available_at", "as_of_date",
    "source_name", "source_type", "source_artifact", "pit_status", "freshness_status",
    "quality_status", "availability_status", "age_days", "expected_frequency",
    "expected_next_release", "included_in_synthesis", "decision_engine_eligible",
    "exclusion_reason", "research_only", "limitations",
]

FREQUENCY_MAX_AGE_DAYS = {
    "DAILY": (3, 7),
    "WEEKLY": (10, 21),
    "MONTHLY": (45, 75),
    "QUARTERLY": (120, 180),
    "EVENT_DRIVEN": (90, 180),
}
