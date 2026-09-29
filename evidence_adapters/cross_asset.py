import pandas as pd
from .common import row

ASSETS = ["SP500", "NASDAQ", "GOLD", "DXY", "VIX", "US10Y", "WTI", "BITCOIN"]


def _context_date(p, d):
    rc = p / "research_context_summary_v1.csv"
    if rc.exists():
        c = pd.read_csv(rc)
        if not c.empty and "context_date" in c.columns:
            value = pd.to_datetime(c.iloc[-1]["context_date"], errors="coerce")
            if pd.notna(value):
                return value.normalize()
    return pd.to_datetime(d["availability_date"], errors="coerce").max().normalize()


def build(p):
    """Build per-asset evidence without borrowing the final row's session date.

    Cross-asset remains PIT_LIMITED because the source artifact only models a
    calendar-day availability proxy, not exchange/session-aware timestamps.
    """
    d = pd.read_csv(p / "cross_asset_research_v1.csv")
    as_of = _context_date(p, d)
    out = []

    for asset in ASSETS:
        valid = d.loc[d[asset].notna()] if asset in d.columns else d.iloc[0:0]
        if valid.empty:
            out.append(row(
                "CROSS_ASSET", "CROSS_ASSET", asset,
                availability_status="UNAVAILABLE",
                as_of_date=as_of.strftime("%Y-%m-%d"),
                source_name="Yahoo Finance via yfinance",
                source_artifact="cross_asset_research_v1.csv",
                pit_status="PIT_LIMITED",
                expected_frequency="DAILY",
                limitations="No observation available; session-aware availability is not represented",
            ))
            continue

        x = valid.iloc[-1]
        available_at = pd.to_datetime(x["availability_date"], errors="coerce")
        age = int((as_of - available_at.normalize()).days) if pd.notna(available_at) else None
        out.append(row(
            "CROSS_ASSET", "CROSS_ASSET", asset,
            value=x[asset],
            observation_date=x["observation_date"],
            available_at=x["availability_date"],
            as_of_date=as_of.strftime("%Y-%m-%d"),
            source_name="Yahoo Finance via yfinance",
            source_artifact="cross_asset_research_v1.csv",
            pit_status="PIT_LIMITED",
            availability_status="AVAILABLE",
            expected_frequency="DAILY",
            limitations=(
                "Calendar-day availability proxy only; exchange/session-aware "
                "availability is not represented. No cross-session forward-fill."
            ),
        ) | {"age_days": age if age is not None else ""})

    return out
