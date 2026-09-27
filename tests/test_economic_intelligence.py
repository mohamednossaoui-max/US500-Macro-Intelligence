from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "public_data"


def test_economic_artifacts_exist_and_are_nonempty():
    for name in [
        "economic_regime_events_v1.csv",
        "economic_surprise_engine_v1.csv",
        "economic_historical_events_v1.csv",
        "economic_historical_quality_v1.csv",
    ]:
        df = pd.read_csv(DATA / name)
        assert not df.empty


def test_latest_regime_contract_is_pit_safe_and_research_only():
    df = pd.read_csv(DATA / "economic_regime_events_v1.csv")
    latest = df.sort_values("release_date").iloc[-1]
    assert latest["economic_regime"]
    assert bool(latest["pit_safe"]) is True
    assert bool(latest["research_only"]) is True
    for field in ["inflation_score", "labor_score", "growth_score"]:
        assert pd.notna(latest[field])


def test_dimension_freshness_and_evidence_are_published():
    df = pd.read_csv(DATA / "economic_regime_events_v1.csv")
    latest = df.sort_values("release_date").iloc[-1]
    for dim in ["inflation", "labor", "growth"]:
        assert pd.notna(latest[f"{dim}_age_days"])
        assert str(latest[f"{dim}_indicators"]).strip()


def test_release_engine_preserves_pit_and_does_not_fabricate_consensus():
    df = pd.read_csv(DATA / "economic_surprise_engine_v1.csv")
    assert df["point_in_time_safe"].fillna(False).astype(bool).all()
    unavailable = df["consensus_method"].astype(str).eq("NOT_AVAILABLE")
    assert unavailable.any()
    assert df.loc[unavailable, "consensus_available"].fillna(False).astype(bool).eq(False).all()
    assert df.loc[unavailable, "classic_surprise"].isna().all()


def test_release_shock_contract_is_available_without_consensus():
    df = pd.read_csv(DATA / "economic_surprise_engine_v1.csv")
    required = ["release_delta", "directional_release_shock", "directional_zscore", "zscore_class"]
    for field in required:
        assert field in df.columns
    assert df["directional_zscore"].notna().any()


def test_economic_ui_exposes_required_intelligence_sections():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    for marker in [
        'st.subheader("Economic Pulse")',
        'st.subheader("What Changed?")',
        'st.subheader("Economic Bottom Line")',
        'st.subheader("Dimension Pulse")',
        'st.subheader("Latest Economic Releases")',
        'st.subheader("Research Detail")',
        'with st.expander("Regime history")',
        'with st.expander("Data quality")',
    ]:
        assert marker in source


def test_economic_ui_explicitly_rejects_fake_consensus_and_forecast_language():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "NOT_AVAILABLE is never converted into a beat/miss claim" in source
    assert "not consensus surprises" in source
    assert "not a market forecast" in source
    econ = source[source.index("def economic() -> None:"):source.index("def fed() -> None:")]
    for forbidden in ["BUY", "SELL", "STOP LOSS", "TAKE PROFIT", "TARGET PRICE"]:
        assert forbidden not in econ
