import importlib.util
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('liq', ROOT / 'liquidity_intelligence_analyzer_v1.py')
liq = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(liq)


def test_mixed_frequency_freshness_limits():
    panel = pd.DataFrame({
        'asof_date': pd.to_datetime(['2026-09-21'] * 1),
        'SOFR': [3.8], 'SOFR_available_at': pd.to_datetime(['2026-09-13']), 'SOFR_frequency': ['Daily'],
        'FED_TOTAL_ASSETS': [1.0], 'FED_TOTAL_ASSETS_available_at': pd.to_datetime(['2026-09-08']), 'FED_TOTAL_ASSETS_frequency': ['Weekly'],
    })
    out = liq.add_freshness_fields(panel)
    assert not bool(out.loc[0, 'SOFR_fresh'])  # 8 days > daily allowance
    assert bool(out.loc[0, 'FED_TOTAL_ASSETS_fresh'])  # 13 days <= weekly allowance


def test_stale_component_is_excluded_from_derived_spread():
    panel = pd.DataFrame({
        'SOFR': [3.8], 'SOFR_eligible_value': [float('nan')],
        'EFFR': [3.9], 'EFFR_eligible_value': [3.9],
    })
    out = liq.add_rates_and_spreads(panel)
    assert pd.isna(out.loc[0, 'SOFR_EFFR_SPREAD_BPS'])


def test_stale_component_is_excluded_from_net_liquidity_proxy():
    panel = pd.DataFrame({
        'FED_TOTAL_ASSETS': [10.0], 'FED_TOTAL_ASSETS_eligible_value': [10.0],
        'TREASURY_GENERAL_ACCOUNT': [2.0], 'TREASURY_GENERAL_ACCOUNT_eligible_value': [float('nan')],
        'ON_RRP': [0.001], 'ON_RRP_eligible_value': [0.001],
    })
    out = liq.add_net_liquidity_proxy(panel)
    assert pd.isna(out.loc[0, 'NET_LIQUIDITY_PROXY_MILLIONS'])


def test_current_published_liquidity_has_real_availability_and_freshness():
    df = pd.read_csv(ROOT / 'public_data' / 'liquidity_intelligence_research_v1.csv')
    x = df.iloc[-1]
    for ind in liq.EXPECTED_INDICATORS:
        assert ind + '_available_at' in df.columns
        assert ind + '_age_days' in df.columns
        assert ind + '_fresh' in df.columns
        assert pd.notna(x[ind + '_available_at'])
        assert bool(x[ind + '_fresh'])


def test_evidence_adapter_uses_component_availability_not_asof(tmp_path):
    from evidence_adapters.liquidity import build
    row = {'asof_date': '2026-09-21', 'point_in_time_safe': True}
    for ind in ['FED_TOTAL_ASSETS','TREASURY_GENERAL_ACCOUNT','ON_RRP','RESERVE_BALANCES','EFFR','SOFR']:
        row[ind] = 1.0
        row[ind + '_observation_date'] = '2026-09-16'
        row[ind + '_available_at'] = '2026-09-17'
        row[ind + '_age_days'] = 4
        row[ind + '_fresh'] = True
    pd.DataFrame([row]).to_csv(tmp_path / 'liquidity_intelligence_research_v1.csv', index=False)
    evidence = build(tmp_path)
    assert evidence
    assert all(str(item['available_at']).startswith('2026-09-17') for item in evidence)


def test_evidence_adapter_does_not_publish_stale_value_as_pit_safe(tmp_path):
    from evidence_adapters.liquidity import build
    row = {'asof_date': '2026-09-21', 'point_in_time_safe': True}
    for ind in ['FED_TOTAL_ASSETS','TREASURY_GENERAL_ACCOUNT','ON_RRP','RESERVE_BALANCES','EFFR','SOFR']:
        row[ind] = 1.0
        row[ind + '_observation_date'] = '2026-09-01'
        row[ind + '_available_at'] = '2026-09-02'
        row[ind + '_age_days'] = 19
        row[ind + '_fresh'] = False
    pd.DataFrame([row]).to_csv(tmp_path / 'liquidity_intelligence_research_v1.csv', index=False)
    evidence = build(tmp_path)
    assert all(item['pit_status'] == 'PIT_LIMITED' for item in evidence)
    assert all(item['value'] == '' for item in evidence)
