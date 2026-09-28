"""Economic Data Foundation v2 — coverage/PIT contract validator.

Research-only. This module does not fetch revised time series and does not score regimes.
It validates that the published historical release artifact can safely support the expanded
Economic Intelligence universe without silently falling back to the legacy seven-series set.
"""
from pathlib import Path
import pandas as pd

CORE = {"CPI","CORE_CPI","NFP","UNEMPLOYMENT_RATE","INITIAL_JOBLESS_CLAIMS","ISM_MANUFACTURING_PMI","GDP"}
EXPANDED = {"PPI_FINAL_DEMAND","CORE_PPI","PCE_PRICE_INDEX","CORE_PCE","AVERAGE_HOURLY_EARNINGS","ISM_SERVICES_PMI","RETAIL_SALES"}
REQUIRED = CORE | EXPANDED
FAMILIES = {
    "CPI":"CPI","CORE_CPI":"CPI","PPI_FINAL_DEMAND":"PPI","CORE_PPI":"PPI","PCE_PRICE_INDEX":"PCE","CORE_PCE":"PCE",
    "NFP":"PAYROLLS","UNEMPLOYMENT_RATE":"UNEMPLOYMENT","INITIAL_JOBLESS_CLAIMS":"CLAIMS","AVERAGE_HOURLY_EARNINGS":"WAGES",
    "ISM_MANUFACTURING_PMI":"ISM_MFG","ISM_SERVICES_PMI":"ISM_SERVICES","GDP":"GDP","RETAIL_SALES":"RETAIL",
}

def validate(events_path="public_data/economic_historical_events_v1.csv", quality_path="public_data/economic_historical_quality_v1.csv"):
    events, quality = pd.read_csv(events_path), pd.read_csv(quality_path)
    needed = {"indicator","release_date","reference_period","actual","vintage_date","source","source_url"}
    missing_cols = needed - set(events.columns)
    if missing_cols: raise AssertionError(f"missing event columns: {sorted(missing_cols)}")
    present = set(events.indicator.astype(str))
    missing = REQUIRED - present
    if missing: raise AssertionError(f"expanded economic universe incomplete: {sorted(missing)}")
    rd, vd = pd.to_datetime(events.release_date, errors="raise"), pd.to_datetime(events.vintage_date, errors="raise")
    if not (vd <= rd).all(): raise AssertionError("PIT temporal order failed: vintage_date > release_date")
    if events.source.isna().any() or events.source_url.isna().any(): raise AssertionError("official-source provenance incomplete")
    if not quality.point_in_time_safe.fillna(False).astype(bool).all(): raise AssertionError("quality PIT gate failed")
    if quality.historical_consensus_available.fillna(False).astype(bool).any(): raise AssertionError("fabricated/unsupported historical consensus detected")
    latest = events.assign(_rd=rd).groupby("indicator")._rd.max()
    counts = events.groupby("indicator").size()
    return {"records":len(events),"indicators":len(present),"families":len({FAMILIES[x] for x in REQUIRED}),"latest":latest,"counts":counts}

if __name__ == "__main__":
    r=validate(); print(f"ECONOMIC DATA FOUNDATION v2: PASS | records={r['records']} indicators={r['indicators']} families={r['families']}")
