from pathlib import Path
import importlib.util
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER = ROOT / "economic_regime_classifier_v1.5.py"
SHOCK = ROOT / "public_data" / "economic_surprise_engine_v1.csv"
REGIME = ROOT / "public_data" / "economic_regime_events_v1.csv"

spec = importlib.util.spec_from_file_location("econ_regime", CLASSIFIER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ENGINE = ROOT / "economic_surprise_engine_v1.1.py"


def _engine():
    spec = importlib.util.spec_from_file_location("econ_surprise_engine", ENGINE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # required by dataclasses inside the engine
    spec.loader.exec_module(module)
    return module


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
    # original-release history for PIT z-scores.
    pce = sub[sub["indicator"].isin({"PCE_PRICE_INDEX", "CORE_PCE"})]
    assert pce["directional_zscore"].notna().any()
    # The remaining expanded series stay fail-closed ONLY while they lack
    # history. The rule is asserted as an invariant, not as a frozen snapshot of
    # today's data: as official releases accumulate a series legitimately
    # matures (e.g. CORE_PPI after its third prior observation) and must not
    # break the publication gate.
    thin = sub[~sub["indicator"].isin({"PCE_PRICE_INDEX", "CORE_PCE"})]
    min_history = _engine().MIN_PRIOR_HISTORY
    prior = pd.to_numeric(thin["prior_valid_observation_count"], errors="coerce").fillna(0)
    scored = thin["directional_zscore"].notna()
    # 1) Never a z-score without enough prior point-in-time observations.
    assert (prior[scored] >= min_history).all()
    # 2) Insufficient history is never scored and is classified fail-closed.
    short = prior < min_history
    assert thin.loc[short, "directional_zscore"].isna().all()
    assert (thin.loc[short, "zscore_class"] == "INSUFFICIENT_HISTORY").all()
    # 3) Class and score agree for every row.
    assert (thin.loc[~scored, "zscore_class"] == "INSUFFICIENT_HISTORY").all()
    assert (thin.loc[scored, "zscore_class"] != "INSUFFICIENT_HISTORY").all()
    r = pd.read_csv(REGIME)
    latest = r.sort_values("release_date").iloc[-1]
    assert pd.notna(latest["inflation_score"])
    assert int(latest["inflation_family_count"]) >= 2
