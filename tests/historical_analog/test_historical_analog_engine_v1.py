import importlib.util
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('ha',ROOT/'historical_analog_engine_v1.py'); ha=importlib.util.module_from_spec(spec); spec.loader.exec_module(ha)

def test_no_future_and_no_outcomes():
    allr,top,ctx=ha.similarity_table(); assert (pd.to_datetime(allr.historical_date)<=ctx-pd.Timedelta(days=ha.RECENT_EXCLUSION_DAYS)).all(); assert (~allr.outcomes_used_in_selection).all()
def test_minimum_coverage_and_missing_fed_not_imputed():
    allr,_,_=ha.similarity_table(); assert (allr.comparable_features>=ha.MIN_COMPARABLE).all(); assert (allr.coverage_pct>=round(100*ha.MIN_COVERAGE,2)).all(); assert (~allr.fed_historical_available).all()
def test_temporal_decluster():
    _,top,_=ha.similarity_table(); d=sorted(pd.to_datetime(top.historical_date)); assert all((b-a).days>=ha.DECLUSTER_DAYS for a,b in zip(d,d[1:]))
def test_deterministic_ranking():
    a,t,_=ha.similarity_table(); b,u,_=ha.similarity_table(); pd.testing.assert_frame_equal(a,b); pd.testing.assert_frame_equal(t,u)
def test_current_outcome_columns_absent():
    allr,_,_=ha.similarity_table(); forbidden=['return_5d','return_20d','return_60d','return_120d','max_drawdown','forward_return']; assert not any(c in allr.columns for c in forbidden)
def test_source_history_is_backward_asof_and_pit():
    h=ha.build_history(); assert h.candidate_date.is_monotonic_increasing; assert (h.stress_date.dropna()<=h.loc[h.stress_date.notna(),'candidate_date']).all(); assert (h.liq_date.dropna()<=h.loc[h.liq_date.notna(),'candidate_date']).all(); assert (h.rc_date.dropna()<=h.loc[h.rc_date.notna(),'candidate_date']).all(); assert (h.tech_available.dropna()<=h.loc[h.tech_available.notna(),'candidate_date']).all()
