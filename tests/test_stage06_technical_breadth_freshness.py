from pathlib import Path
import pandas as pd
from research_evidence_quality_v1 import apply_quality
import importlib
technical_adapter = importlib.import_module('evidence_adapters.technical')
breadth_adapter = importlib.import_module('evidence_adapters.breadth')

PUBLIC = Path(__file__).resolve().parents[1] / 'public_data'


def _one(module, rows):
    return [r for r in apply_quality(rows) if r['module'] == module]


def test_technical_uses_research_context_for_freshness_clock():
    rows = _one('TECHNICAL', technical_adapter.build(PUBLIC))
    assert len(rows) == 3
    assert {r['as_of_date'] for r in rows} == {'2026-09-27'}
    assert {r['age_days'] for r in rows} == {2}
    assert {r['freshness_status'] for r in rows} == {'CURRENT'}


def test_technical_stale_data_is_not_decision_eligible(tmp_path):
    pd.DataFrame([{'context_date':'2026-10-20'}]).to_csv(tmp_path/'research_context_summary_v1.csv', index=False)
    src = pd.read_csv(PUBLIC/'technical_intelligence_research_v1.csv')
    src.to_csv(tmp_path/'technical_intelligence_research_v1.csv', index=False)
    rows = _one('TECHNICAL', technical_adapter.build(tmp_path))
    assert all(r['freshness_status'] == 'STALE' for r in rows)
    assert not any(r['decision_engine_eligible'] for r in rows)
    assert {r['exclusion_reason'] for r in rows} == {'STALE_EVIDENCE'}


def test_technical_warmup_preserves_insufficient_data():
    d = pd.read_csv(PUBLIC/'technical_intelligence_research_v1.csv')
    warm = d[d['SMA200'].isna()]
    assert not warm.empty
    assert set(warm['technical_regime']) == {'INSUFFICIENT_DATA'}


def test_breadth_freshness_is_measured_against_context_date():
    rows = _one('MARKET_BREADTH', breadth_adapter.build(PUBLIC))
    assert len(rows) == 1
    r = rows[0]
    assert r['as_of_date'] == '2026-09-27'
    assert r['available_at'] == '2026-08-18'
    assert r['age_days'] == 40
    assert r['freshness_status'] == 'STALE'


def test_breadth_remains_pit_limited_and_excluded():
    r = _one('MARKET_BREADTH', breadth_adapter.build(PUBLIC))[0]
    assert r['pit_status'] == 'PIT_LIMITED'
    assert r['freshness_status'] == 'STALE'
    assert r['decision_engine_eligible'] is False
    assert r['included_in_synthesis'] is False
    assert r['exclusion_reason'] == 'PIT_LIMITED_EVIDENCE'


def test_breadth_reconstruction_is_not_promoted_to_pit_perfect():
    d = pd.read_csv(PUBLIC/'market_breadth_analysis_v1.csv')
    x = d.iloc[-1]
    assert bool(x['point_in_time_reconstructed']) is True
    assert bool(x['cross_validated']) is True
    assert bool(x['pit_perfect']) is False
    assert bool(x['price_pit_perfect']) is False
    assert x['membership_quality'] == 'RESEARCH_GRADE'
