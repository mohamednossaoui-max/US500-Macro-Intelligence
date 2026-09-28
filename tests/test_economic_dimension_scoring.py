from pathlib import Path
import importlib.util
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER = ROOT / "economic_regime_classifier_v1.5.py"
SHOCK = ROOT / "public_data" / "economic_surprise_engine_v1.csv"
REGIME = ROOT / "public_data" / "economic_regime_events_v1.csv"

spec = importlib.util.spec_from_file_location("econ_regime", CLASSIFIER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

EXPANDED = {
    "PPI_FINAL_DEMAND", "CORE_PPI", "PCE_PRICE_INDEX", "CORE_PCE",
    "AVERAGE_HOURLY_EARNINGS", "ISM_SERVICES_PMI", "RETAIL_SALES",
}

def test_expanded_indicators_are_mapped_to_dimensions():
    assert EXPANDED <= set(mod.DIMENSION_MAP)
    assert mod.DIMENSION_MAP["PPI_FINAL_DEMAND"] == "INFLATION"
    assert mod.DIMENSION_MAP["AVERAGE_HOURLY_EARNINGS"] == "LABOR"
    assert mod.DIMENSION_MAP["RETAIL_SALES"] == "GROWTH"


def test_related_variants_share_families_to_avoid_double_counting():
    assert mod.INDICATOR_FAMILY["CPI"] == mod.INDICATOR_FAMILY["CORE_CPI"]
    assert mod.INDICATOR_FAMILY["PPI_FINAL_DEMAND"] == mod.INDICATOR_FAMILY["CORE_PPI"]
    assert mod.INDICATOR_FAMILY["PCE_PRICE_INDEX"] == mod.INDICATOR_FAMILY["CORE_PCE"]
    assert mod.INDICATOR_FAMILY["ISM_MANUFACTURING_PMI"] == mod.INDICATOR_FAMILY["ISM_SERVICES_PMI"]
    assert mod.INDICATOR_FAMILY["RETAIL_SALES"] == mod.INDICATOR_FAMILY["RETAIL_SALES_EX_AUTOS"]


def test_only_series_with_sufficient_pit_history_enter_dimension_score():
    s = pd.read_csv(SHOCK)
    sub = s[s["indicator"].isin(EXPANDED)]
    # Historical coverage expansion intentionally gives PCE/Core PCE enough
    # original-release history for PIT z-scores. Other one-release expansion
    # series remain fail-closed until their own history is backfilled.
    pce = sub[sub["indicator"].isin({"PCE_PRICE_INDEX", "CORE_PCE"})]
    assert pce["directional_zscore"].notna().any()
    thin = sub[~sub["indicator"].isin({"PCE_PRICE_INDEX", "CORE_PCE"})]
    assert (thin["zscore_class"] == "INSUFFICIENT_HISTORY").all()
    assert thin["directional_zscore"].isna().all()
    r = pd.read_csv(REGIME)
    latest = r.sort_values("release_date").iloc[-1]
    assert pd.notna(latest["inflation_score"])
    assert int(latest["inflation_family_count"]) >= 2


def test_family_balancing_math():
    df = pd.DataFrame([
        {"indicator":"CPI","release_date":"2026-09-01","pit_safe":True,"directional_shock_z":1.0,"regime_eligible":True},
        {"indicator":"CORE_CPI","release_date":"2026-09-01","pit_safe":True,"directional_shock_z":3.0,"regime_eligible":True},
        {"indicator":"PPI_FINAL_DEMAND","release_date":"2026-09-01","pit_safe":True,"directional_shock_z":0.0,"regime_eligible":True},
    ])
    df["release_date"] = pd.to_datetime(df["release_date"])
    result = mod.build_dimension(df, pd.Timestamp("2026-09-02"), "INFLATION")
    # CPI family=(1+3)/2=2; PPI family=0; equal-family score=(2+0)/2=1.
    assert result["score"] == 1.0
    assert result["method"] == "FAMILY_BALANCED_FRESH_ZSCORES"


def test_research_only_and_pit_outputs_remain_closed():
    r = pd.read_csv(REGIME)
    assert r["pit_safe"].fillna(False).astype(bool).all()
    assert r["research_only"].fillna(False).astype(bool).all()
    assert not r["decision_engine_ready"].fillna(True).astype(bool).any()


def test_dimension_sufficiency_counts_independent_families_not_variants():
    df = pd.DataFrame([
        {"indicator":"CPI","release_date":"2026-09-01","pit_safe":True,"directional_shock_z":1.0,"regime_eligible":True},
        {"indicator":"CORE_CPI","release_date":"2026-09-01","pit_safe":True,"directional_shock_z":3.0,"regime_eligible":True},
    ])
    df["release_date"] = pd.to_datetime(df["release_date"])
    result = mod.build_dimension(df, pd.Timestamp("2026-09-02"), "INFLATION")
    assert pd.isna(result["score"])
    assert result["indicator_count"] == 2
    assert result["family_count"] == 1
    assert result["method"] == "INSUFFICIENT_FRESH_FAMILIES"


def test_two_independent_families_are_sufficient():
    df = pd.DataFrame([
        {"indicator":"CPI","release_date":"2026-09-01","pit_safe":True,"directional_shock_z":1.0,"regime_eligible":True},
        {"indicator":"CORE_CPI","release_date":"2026-09-01","pit_safe":True,"directional_shock_z":3.0,"regime_eligible":True},
        {"indicator":"PPI_FINAL_DEMAND","release_date":"2026-09-01","pit_safe":True,"directional_shock_z":0.0,"regime_eligible":True},
    ])
    df["release_date"] = pd.to_datetime(df["release_date"])
    result = mod.build_dimension(df, pd.Timestamp("2026-09-02"), "INFLATION")
    assert result["score"] == 1.0
    assert result["family_count"] == 2
