import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('hmr', ROOT/'historical_market_reaction_v1.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def test_stage10_selection_is_locked_and_unmodified():
    a=m.load_locked_analogs(); r=m.build_reactions()
    assert r.historical_date.astype(str).tolist()==a.historical_date.astype(str).tolist()
    assert np.allclose(r.similarity_pct,a.similarity_pct)
    assert r.selection_locked.all() and not r.outcomes_used_in_selection.any()

def test_horizons_are_trading_session_counts():
    p=m.load_price_history(); r=m.build_reactions()
    x=r.iloc[0]; i0=p.index[p.observation_date==pd.Timestamp(x.anchor_session)][0]
    for h in m.HORIZONS:
        if x[f'horizon_{h}d_available']:
            assert p.iloc[i0+h].observation_date.date().isoformat()==x[f'horizon_{h}d_end_session']

def test_returns_use_anchor_and_exact_forward_close():
    p=m.load_price_history(); r=m.build_reactions(); x=r.iloc[0]
    i0=p.index[p.observation_date==pd.Timestamp(x.anchor_session)][0]
    h=20; expected=100*(float(p.iloc[i0+h].Close)/float(p.iloc[i0].Close)-1)
    assert abs(x[f'return_{h}d_pct']-expected)<1e-5

def test_incomplete_horizons_are_missing_not_imputed():
    p=m.load_price_history(); fake={'historical_date':p.iloc[-3].observation_date.date().isoformat(),'similarity_pct':1.0}
    x=m._reaction_for_one(fake,p)
    assert not x['horizon_5d_available'] and pd.isna(x['return_5d_pct'])
    assert not x['horizon_120d_available'] and pd.isna(x['return_120d_pct'])

def test_drawdown_and_volatility_are_path_based():
    r=m.build_reactions(); x=r.iloc[0]
    for h in m.HORIZONS:
        if x[f'horizon_{h}d_available']:
            assert x[f'max_drawdown_{h}d_pct'] <= max(0.0, x[f'return_{h}d_pct'])
            assert x[f'realized_volatility_{h}d_pct'] >= 0

def test_summary_uses_only_available_horizons_and_is_research_only():
    r=m.build_reactions(); s=m.build_summary(r)
    assert s['analog_selection_locked'] and not s['analog_reranking_by_outcome']
    assert s['research_only'] and not s['decision_engine_ready'] and not s['forecast_generated']
    for h in m.HORIZONS:
        expected=int(r[f'horizon_{h}d_available'].sum())
        assert s['horizons'][f'{h}d']['available_analogs']==expected
