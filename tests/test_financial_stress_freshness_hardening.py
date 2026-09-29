import numpy as np
import pandas as pd

from financial_stress_analyzer_v1 import (
    FRESHNESS_LIMIT_DAYS,
    apply_composite_eligibility,
    asof_series,
)


def _source(indicator, availability="2026-01-01", observation="2026-01-01", actual=10.0):
    return pd.DataFrame({
        "indicator": [indicator],
        "availability_date": pd.to_datetime([availability]),
        "observation_date": pd.to_datetime([observation]),
        "actual": [actual],
    })


def test_daily_component_is_excluded_after_freshness_limit():
    limit = FRESHNESS_LIMIT_DAYS["VIX"]
    dates = pd.DatetimeIndex([pd.Timestamp("2026-01-01") + pd.Timedelta(days=limit + 1)])
    out = asof_series(_source("VIX"), dates, "VIX")
    assert int(out.iloc[0]["age_days"]) == limit + 1
    assert not bool(out.iloc[0]["fresh"])
    assert pd.isna(out.iloc[0]["eligible_actual"])


def test_weekly_component_remains_eligible_inside_weekly_buffer():
    limit = FRESHNESS_LIMIT_DAYS["NFCI"]
    dates = pd.DatetimeIndex([pd.Timestamp("2026-01-01") + pd.Timedelta(days=limit)])
    out = asof_series(_source("NFCI"), dates, "NFCI")
    assert bool(out.iloc[0]["fresh"])
    assert out.iloc[0]["eligible_actual"] == 10.0


def test_anti_lookahead_cannot_be_promoted_by_freshness():
    dates = pd.DatetimeIndex([pd.Timestamp("2026-01-01")])
    out = asof_series(
        _source("VIX", availability="2026-01-01", observation="2026-01-02"),
        dates,
        "VIX",
    )
    assert not bool(out.iloc[0]["fresh"])
    assert pd.isna(out.iloc[0]["eligible_actual"])


def test_composite_requires_two_eligible_components():
    panel = pd.DataFrame({"a": [1.0, 1.0], "b": [np.nan, 3.0], "c": [np.nan, np.nan]})
    out = apply_composite_eligibility(panel, ["a", "b", "c"])
    assert out.loc[0, "stress_component_count"] == 1
    assert pd.isna(out.loc[0, "composite_stress_score"])
    assert out.loc[1, "stress_component_count"] == 2
    assert out.loc[1, "composite_stress_score"] == 2.0
