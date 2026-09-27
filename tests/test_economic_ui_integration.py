from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "public_data"

NEW_UI_INDICATORS = {
    "PPI_FINAL_DEMAND", "CORE_PPI", "PCE_PRICE_INDEX", "CORE_PCE",
    "AVERAGE_HOURLY_EARNINGS", "ISM_SERVICES_PMI", "RETAIL_SALES",
}


def test_new_economic_series_are_published_in_release_engine():
    df = pd.read_csv(DATA / "economic_surprise_engine_v1.csv")
    assert NEW_UI_INDICATORS.issubset(set(df["indicator"].astype(str)))


def test_price_series_publish_mom_and_yoy_for_ui():
    df = pd.read_csv(DATA / "economic_surprise_engine_v1.csv")
    for indicator in ["CPI", "CORE_CPI", "PPI_FINAL_DEMAND", "CORE_PPI", "PCE_PRICE_INDEX", "CORE_PCE"]:
        latest = df[df["indicator"].eq(indicator)].sort_values("release_date").iloc[-1]
        assert pd.notna(latest["mom"])
        assert pd.notna(latest["yoy"])


def test_ui_separates_yoy_trend_from_mom_momentum_and_ism_level():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    econ = source[source.index("def economic() -> None:"):source.index("def fed() -> None:")]
    assert 'st.subheader("Economic Indicator Pulse")' in econ
    assert "% YoY" in econ
    assert "% MoM" in econ
    assert "Expansion" in econ and "Contraction" in econ
    assert "nominal / not price-adjusted" in econ


def test_ui_exposes_new_indicator_families_without_fake_consensus():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    econ = source[source.index("def economic() -> None:"):source.index("def fed() -> None:")]
    for marker in ["PPI_FINAL_DEMAND", "CORE_PCE", "AVERAGE_HOURLY_EARNINGS", "ISM_SERVICES_PMI", "RETAIL_SALES"]:
        assert marker in econ
    assert "No beat/miss claim is inferred" in econ
    assert "Consensus:" not in econ


def test_retail_sales_ex_autos_is_not_fabricated_when_unpublished():
    df = pd.read_csv(DATA / "economic_surprise_engine_v1.csv")
    assert "RETAIL_SALES_EX_AUTOS" not in set(df["indicator"].astype(str))
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'if release is None:' in source
