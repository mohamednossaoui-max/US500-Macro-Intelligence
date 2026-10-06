import json
import numpy as np
import pandas as pd
import pytest
import ath_sequential_pullback_research_v9 as m


def data(prices):
    dates = pd.date_range('2000-01-01', periods=len(prices), tz='UTC')
    return m.history(pd.DataFrame({'observation_date': dates,
                                  'availability_date': dates+pd.Timedelta(days=1), 'SP500': prices}))


def test_landmarks_do_not_use_future():
    d = data(list(np.linspace(80,100,260))+[99,96,94,89,88,100,101])
    full = m.landmarks(d)
    prefix = m.landmarks(d.iloc[:264])
    pd.testing.assert_frame_equal(prefix.reset_index(drop=True),
                                  full[full['index']<264].reset_index(drop=True))
    crossed = full[full.stage_pct>0]
    assert crossed.stage_pct.tolist()==[3,5,10]
    assert crossed.cycle_id.nunique()==1


def test_gap_does_not_predict_already_reached_target():
    d = data(list(np.linspace(80,100,260))+[89,100])
    e = m.outcomes(d,m.landmarks(d))
    crossed = e[e.stage_pct.eq(3)]
    assert not crossed[crossed.target_pct.isin([5,10])].eligible.any()
    assert crossed[crossed.target_pct.eq(20)].eligible.all()


def test_label_stops_at_recovery_and_no_future_cycle():
    d = data(list(np.linspace(80,100,260))+[96,100,70,100])
    e = m.outcomes(d,m.landmarks(d))
    first = e[e.event_id.eq('2000-09-17:3')]
    assert len(first)==3
    assert first.complete.all() and first.hit.eq(0).all()
    assert first.label_available_at.eq(d.available.iloc[261].isoformat()).all()


def test_ath_horizon_does_not_stop_at_immediate_new_record():
    d=data(list(np.linspace(80,100,260))+[101,102,80]+[90]*70)
    e=m.outcomes(d,m.landmarks(d))
    ath=e[e.stage_pct.eq(0)].iloc[:3]
    assert ath.complete.all() and ath.hit.eq(1).all()


def test_unmatured_outcome_is_not_false_negative():
    d = data(list(np.linspace(80,100,260))+[96,94])
    e = m.outcomes(d,m.landmarks(d))
    last = e[e.stage_pct.eq(3)]
    assert not last.complete.any() and last.hit.isna().all()


def test_walk_forward_excludes_unavailable_labels_and_same_cycle(monkeypatch):
    monkeypatch.setitem(m.PROTOCOL,'minimum_training_cases',2)
    rows=[]
    for i in range(5):
        rows.append(dict(event_id=str(i),cycle_id=str(i),decision_at=f'2020-01-0{i+1}T00:00:00+00:00',
                         label_available_at=f'2020-01-0{i+2}T00:00:00+00:00',stage_pct=3,target_pct=5,
                         eligible=True,complete=True,hit=i%2,**{f:float(i) for f in m.FEATURES}))
    frame=pd.DataFrame(rows)
    a=m.evaluate(frame)
    assert a and all(r['latest_training_label_at']<r['decision_at'] for r in a)
    frame.loc[0,'cycle_id']='4'
    b=m.evaluate(frame)
    assert b[-1]['training_count']==a[-1]['training_count']-1


def test_availability_and_missing_prices_fail_closed():
    d=data([100]*260)
    raw=d[['observation_date','availability_date','SP500']].copy()
    raw.loc[3,'SP500']=np.nan
    with pytest.raises(ValueError):m.history(raw)
    raw.loc[3,'SP500']=100;raw.loc[3,'availability_date']=raw.loc[3,'observation_date']
    with pytest.raises(ValueError):m.history(raw)


def test_outputs_idempotent_and_no_live_probability(tmp_path):
    d=data(list(np.linspace(80,100,260))+[96,94,89,100,101])
    src=tmp_path/'prices.csv';d.to_csv(src,index=False)
    output=tmp_path/'study';m.run(src,output)
    first={p.name:p.read_bytes() for p in output.iterdir()}
    m.run(src,output)
    assert first=={p.name:p.read_bytes() for p in output.iterdir()}
    assert src.read_bytes()==d.to_csv(index=False).encode()
    audit=json.loads((output/'sequential_v9_audit.json').read_text())
    assert audit['live_forecast'] is None
    assert all(c['high_confidence_probability'] is None for c in audit['comparisons'])
    with pytest.raises(ValueError):m.run(src,tmp_path/'public_data')


def test_empty_and_insufficient_history_are_explicit(tmp_path):
    src=tmp_path/'prices.csv';data([100]*20).to_csv(src,index=False)
    a=m.run(src,tmp_path/'study')
    assert a['landmarks']==0 and all(r['evaluations']==0 for r in a['comparisons'])


def test_partial_cross_asset_history_needs_explicit_opt_in(tmp_path):
    d=data(list(np.linspace(80,100,260)))
    d.loc[10,'SP500']=np.nan
    src=tmp_path/'prices.csv';d.to_csv(src,index=False)
    with pytest.raises(ValueError,match='explicit'):m.run(src,tmp_path/'study')
    a=m.run(src,tmp_path/'study',True)
    assert len(a['excluded_rows'])==1 and a['cash_observations']==259
    assert a['calendar_verification']=='UNVERIFIED_OBSERVED_SESSIONS_ONLY'
    assert a['live_forecast'] is None
