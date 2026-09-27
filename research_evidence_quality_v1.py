from __future__ import annotations
from datetime import timedelta
import pandas as pd
from research_evidence_schema_v1 import FREQUENCY_MAX_AGE_DAYS

def _date(v):
    if v is None or str(v).strip() in {"", "nan", "NaT", "None"}: return None
    x = pd.to_datetime(v, errors="coerce", utc=True)
    return None if pd.isna(x) else x

def classify_pit(row):
    explicit = row.get("pit_status")
    if explicit in {"PIT_LIMITED", "NOT_PIT_SAFE"}: return explicit
    available, asof = _date(row.get("available_at") or row.get("release_date")), _date(row.get("as_of_date"))
    if available is not None and asof is not None and available > asof: return "NOT_PIT_SAFE"
    if explicit == "PIT_SAFE": return "PIT_SAFE"
    return "UNKNOWN"

def classify_freshness(row):
    available, asof = _date(row.get("available_at") or row.get("release_date") or row.get("observation_date")), _date(row.get("as_of_date"))
    if available is None or asof is None: return "UNKNOWN", None, None
    age = max(0, int((asof.normalize() - available.normalize()).days))
    freq = str(row.get("expected_frequency") or "").upper()
    current, stale = FREQUENCY_MAX_AGE_DAYS.get(freq, (None, None))
    if current is None: status = "UNKNOWN"
    elif age <= current: status = "CURRENT"
    elif age <= stale: status = "AGING"
    else: status = "STALE"
    nxt = available + timedelta(days=current) if current else None
    return status, age, nxt.date().isoformat() if nxt else ""

def apply_quality(rows):
    out=[]
    for raw in rows:
        r=dict(raw)
        pit=classify_pit(r); fresh, age, nxt=classify_freshness(r)
        avail=r.get("availability_status") or "AVAILABLE"
        limitations=str(r.get("limitations") or "")
        if avail == "UNAVAILABLE": quality="INSUFFICIENT"
        elif pit == "PIT_SAFE" and fresh == "CURRENT" and not limitations: quality="HIGH"
        elif pit in {"PIT_SAFE","PIT_LIMITED"} and fresh in {"CURRENT","AGING"}: quality="MEDIUM"
        else: quality="LOW"
        eligible = bool(avail == "AVAILABLE" and pit == "PIT_SAFE" and fresh != "STALE")
        reason=""
        if avail != "AVAILABLE": reason="EVIDENCE_UNAVAILABLE_OR_PARTIAL"
        elif pit != "PIT_SAFE": reason=f"{pit}_EVIDENCE"
        elif fresh == "STALE": reason="STALE_EVIDENCE"
        r.update(pit_status=pit, freshness_status=fresh, quality_status=quality,
                 age_days=age if age is not None else "", expected_next_release=nxt,
                 included_in_synthesis=eligible, decision_engine_eligible=eligible,
                 exclusion_reason=reason)
        out.append(r)
    return out
