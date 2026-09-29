from pathlib import Path
import shutil
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "sentiment-engine-v1.py"


def _base(dates, extra):
    df = pd.DataFrame({
        "observation_date": dates,
        "availability_date": [(pd.Timestamp(x) + pd.Timedelta(days=1)).strftime("%Y-%m-%d") for x in dates],
        "point_in_time_safe": True,
        "research_only": True,
        "decision_engine_ready": False,
    })
    for k, v in extra.items():
        df[k] = v
    return df


def _run(tmp_path, cot_dates, aaii_dates, vix_dates):
    shutil.copy2(ENGINE, tmp_path / "sentiment-engine-v1.py")
    _base(cot_dates, {"asset_manager_net_percentile": 60.0, "leveraged_money_net_percentile": 40.0}).to_csv(tmp_path / "cot_positioning_research_v1.csv", index=False)
    _base(aaii_dates, {"bull_bear_spread_percentile": 55.0}).to_csv(tmp_path / "aaii_sentiment_research_v1.csv", index=False)
    _base(vix_dates, {"VIX_percentile": 30.0}).to_csv(tmp_path / "vix_sentiment_research_v1.csv", index=False)
    subprocess.run([sys.executable, "sentiment-engine-v1.py"], cwd=tmp_path, check=True, capture_output=True, text=True)
    return pd.read_csv(tmp_path / "sentiment_engine_research_v1.csv")


def test_stale_weekly_component_is_available_but_not_eligible(tmp_path):
    out = _run(tmp_path, ["2026-01-01"], ["2026-01-20"], ["2026-01-20"])
    latest = out.iloc[-1]
    assert bool(latest.cot_available)
    assert not bool(latest.cot_fresh)
    assert not bool(latest.cot_eligible)
    assert latest.eligible_component_count == 2


def test_insufficient_fresh_components_does_not_become_neutral(tmp_path):
    out = _run(tmp_path, ["2026-01-01"], ["2026-01-01"], ["2026-01-20"])
    latest = out.iloc[-1]
    assert latest.eligible_component_count == 1
    assert pd.isna(latest.unified_sentiment_score)
    assert latest.research_regime == "INSUFFICIENT_DATA"


def test_mixed_frequency_current_inputs_remain_eligible(tmp_path):
    out = _run(tmp_path, ["2026-01-14"], ["2026-01-14"], ["2026-01-20"])
    latest = out.iloc[-1]
    assert latest.cot_fresh and latest.aaii_fresh and latest.vix_fresh
    assert latest.eligible_component_count == 3
    assert 0 <= latest.unified_sentiment_score <= 100


def test_sentiment_adapter_preserves_true_availability_and_freshness(tmp_path):
    from evidence_adapters.sentiment import build
    common = {"point_in_time_safe": True, "research_only": True, "decision_engine_ready": False}
    pd.DataFrame([{**common, "observation_date":"2026-01-01", "availability_date":"2026-01-02", "research_regime":"NEUTRAL", "source":"AAII", "availability_semantics":"release"}]).to_csv(tmp_path/"aaii_sentiment_research_v1.csv", index=False)
    pd.DataFrame([{**common, "observation_date":"2026-01-20", "availability_date":"2026-01-21", "research_regime":"NEUTRAL", "source":"CBOE"}]).to_csv(tmp_path/"vix_sentiment_research_v1.csv", index=False)
    pd.DataFrame([{**common, "observation_date":"2026-01-14", "availability_date":"2026-01-15", "asset_manager_research_regime":"NEUTRAL", "leveraged_money_research_regime":"NEUTRAL"}]).to_csv(tmp_path/"cot_positioning_research_v1.csv", index=False)
    rows = build(tmp_path)
    aaii = next(x for x in rows if x["indicator"] == "AAII")
    assert aaii["available_at"] == "2026-01-02"
    assert aaii["age_days"] == 19
    assert aaii["freshness_status"] == "STALE"
    assert aaii["availability_status"] == "STALE"
