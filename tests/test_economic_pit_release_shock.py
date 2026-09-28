from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "public_data" / "economic_historical_events_v1.csv"
QUALITY = ROOT / "public_data" / "economic_historical_quality_v1.csv"
SHOCK = ROOT / "public_data" / "economic_surprise_engine_v1.csv"

EXPANDED = {
    "PPI_FINAL_DEMAND", "CORE_PPI", "PCE_PRICE_INDEX", "CORE_PCE",
    "AVERAGE_HOURLY_EARNINGS", "ISM_SERVICES_PMI", "RETAIL_SALES",
}


def test_expanded_series_are_published():
    h = pd.read_csv(EVENTS)
    assert EXPANDED <= set(h["indicator"].astype(str))


def test_pit_temporal_order_is_preserved():
    h = pd.read_csv(EVENTS)
    release = pd.to_datetime(h["release_date"], errors="raise")
    vintage = pd.to_datetime(h["vintage_date"], errors="raise")
    assert (vintage <= release).all()
    q = pd.read_csv(QUALITY)
    assert q["point_in_time_safe"].fillna(False).astype(bool).all()


def test_consensus_is_not_fabricated():
    s = pd.read_csv(SHOCK)
    assert not s["consensus_available"].fillna(False).astype(bool).any()
    assert set(s["consensus_method"].dropna().astype(str)) == {"NOT_AVAILABLE"}


def test_expanded_series_reach_release_shock_layer():
    s = pd.read_csv(SHOCK)
    sub = s[s["indicator"].isin(EXPANDED)]
    assert set(sub["indicator"].astype(str)) == EXPANDED
    assert sub["point_in_time_safe"].fillna(False).astype(bool).all()
    # The first observation of a series may have no release shock when neither
    # an official previous nor a prior PIT observation exists. Every subsequent
    # PCE/Core-PCE observation must have a PIT-safe sequential shock.
    for indicator, g in sub.groupby("indicator"):
        g = g.sort_values("release_date")
        if len(g) > 1:
            assert g.iloc[1:]["directional_release_shock"].notna().all()
    pce = sub[sub["indicator"].isin({"PCE_PRICE_INDEX", "CORE_PCE"})]
    assert pce["directional_zscore"].notna().any()


def test_research_only_boundary_remains_closed():
    s = pd.read_csv(SHOCK)
    assert s["research_only"].fillna(False).astype(bool).all()
    assert not s["decision_engine_ready"].fillna(True).astype(bool).any()


def test_regime_artifact_not_expanded_in_pr061b():
    r = pd.read_csv(ROOT / "public_data" / "economic_regime_events_v1.csv")
    # PR-06.1B intentionally stops before dimension/regime scoring integration.
    for indicator in EXPANDED:
        assert not any(indicator.lower() in str(c).lower() for c in r.columns)
