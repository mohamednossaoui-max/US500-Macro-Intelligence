import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from ath_pullback_context_v1 import bars, classify, label, study, available_before, describe, audit, loss


def prices(dates, highs, lows, closes=None):
    closes = lows if closes is None else closes
    return pd.DataFrame({'Date': dates, 'Open': closes, 'High': highs, 'Low': lows, 'Close': closes})


@pytest.mark.parametrize('depth,result', [(0,'NO_MEANINGFUL_PULLBACK'),(2.99,'NO_MEANINGFUL_PULLBACK'),
                                         (3,'LIMITED'),(4.99,'LIMITED'),(5,'MEDIUM'),(19.99,'MEDIUM'),(20,'CRASH'),(30,'CRASH')])
def test_class_boundaries(depth, result):
    assert classify(depth) == result


def test_exact_price_thresholds_do_not_float_across_classes():
    assert classify(loss(100,80)) == 'CRASH'
    assert classify(loss(100,95)) == 'MEDIUM'


def test_recovery_depth_and_unknown_intraday_sequence():
    data = bars(prices(['2020-01-01','2020-01-02','2020-01-03'], [100,98,101],[99,96,79]))
    result = label(data,0)
    assert result['complete'] and result['label_end'] == '2020-01-03'
    assert result['depth_lower_pct'] == 4
    assert result['depth_upper_pct'] == 21
    assert result['intraday_ambiguous']


def test_original_anchor_vs_new_peak_inside_fixed_horizon():
    data = bars(prices(['2020-01-01','2020-01-02','2020-01-03','2020-02-01'],
                       [100,120,110,110],[99,115,100,109]))
    result = label(data,0,1)
    assert result['complete']
    assert result['anchor_depth_upper_pct'] == 0
    assert result['depth_lower_pct'] == pytest.approx(100/6)


def test_calendar_months_and_end_of_month():
    data = bars(prices(['2020-01-31','2020-02-28','2020-02-29','2020-03-01'],
                       [100,99,95,80],[99,98,94,79]))
    result = label(data,0,1)
    assert result['label_end'] == '2020-02-29'
    assert result['depth_upper_pct'] == 6


def test_horizons_can_give_different_depths():
    data = bars(prices(['2020-01-01','2020-01-15','2020-02-01','2020-03-01','2020-04-01'],
                       [100,99,101,80,101],[99,97,100,75,100]))
    assert label(data,0,1)['class_lower'] == 'LIMITED'
    assert label(data,0,3)['class_lower'] == 'CRASH'
    assert label(data,0)['class_lower'] == 'LIMITED'


def test_censored_horizons_are_not_resolved_class_counts():
    data = prices(['2020-01-01','2020-01-02','2020-01-03'],[99,100,95],[98,99,90])
    result = study(data,warmup=1)
    assert (~result.complete).all()
    for item in describe(result):
        assert item['complete_unambiguous_count'] == 0
        assert sum(item['historical_class_counts'].values()) == 0
        assert item['forecast_probabilities'] is None


def test_future_prices_excluded_at_asof():
    data = prices(['2020-01-01','2020-01-02','2020-01-03'],[99,100,95],[98,99,90])
    a = study(data,as_of='2020-01-02',warmup=1)
    data.loc[2,['High','Low','Open','Close']] = [200,1,1,1]
    pd.testing.assert_frame_equal(a,study(data,as_of='2020-01-02',warmup=1))


def test_strict_before_blocks_same_day_and_current_snapshot_backcast():
    context = pd.DataFrame({'available':['2026-10-03'],'state':['SUPPORTIVE']})
    assert available_before(context,'available','2020-01-01') is None
    assert available_before(context,'available','2026-10-03') is None
    assert available_before(context,'available','2026-10-04')['state'] == 'SUPPORTIVE'


@pytest.mark.parametrize('context', [pd.DataFrame({'state':[1]}),
                                   pd.DataFrame({'available':['bad']}),
                                   pd.DataFrame({'available':['2020-01-01']*2})])
def test_bad_availability_fails_closed(context):
    with pytest.raises(ValueError): available_before(context,'available','2021-01-01')


def test_deterministic_and_date_spaced_sample():
    dates = pd.date_range('2020-01-01','2020-10-01')
    data = prices(dates,range(100,100+len(dates)),range(99,99+len(dates)))
    a,b = study(data,warmup=1),study(data,warmup=1)
    pd.testing.assert_frame_equal(a,b)
    selected = a[a.descriptive_sample & a.horizon.eq('1M')]
    d = pd.to_datetime(selected.peak_date)
    assert len(selected) == 3
    assert all(y > x + pd.DateOffset(months=3) for x,y in zip(d.iloc[:-1],d.iloc[1:]))


@pytest.mark.parametrize('problem', ['duplicate','nan','negative','range'])
def test_bad_prices(problem):
    data = prices(['2020-01-01','2020-01-02'],[100,100],[99,99])
    if problem == 'duplicate': data.loc[1,'Date']='2020-01-01'
    if problem == 'nan': data.loc[1,'Close']=float('nan')
    if problem == 'negative': data.loc[1,'Low']=-1
    if problem == 'range': data.loc[1,'High']=1
    with pytest.raises(ValueError): bars(data)


def test_actual_audit_does_not_write_publication_or_claim_forecast():
    root = Path(__file__).resolve().parents[1]/'public_data'
    before = {p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
    result,_ = audit(root)
    assert result['forecast_status'] == 'INSUFFICIENT_PIT_CONTEXT_AND_CALIBRATION'
    assert all(h['forecast_class'] is None for h in result['horizons'])
    assert not any(layer['used_as_historical_predictor'] for layer in result['context_inventory'])
    json.dumps(result,allow_nan=False)
    assert before == {p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}


def test_cli_rejects_output_inside_public_data():
    root=Path(__file__).resolve().parents[1]
    p=subprocess.run([sys.executable,str(root/'ath_pullback_context_v1.py'),'--public-data',str(root/'public_data'),
                      '--output',str(root/'public_data'/'forbidden')],capture_output=True,text=True)
    assert p.returncode == 2
    assert 'outside public_data' in p.stderr


def test_ui_smoke_without_trading_controls(tmp_path):
    from streamlit.testing.v1 import AppTest
    page=tmp_path/'page.py'
    page.write_text('from ath_pullback_context_ui_v1 import render_ath_pullback_context\nrender_ath_pullback_context()\n')
    app=AppTest.from_file(str(page)).run(timeout=30)
    assert not app.exception
    assert len(app.get('file_uploader')) == 2
    assert len(app.get('number_input')) == 0
    assert len(app.get('selectbox')) == 0


def test_app_registers_depth_context_without_entry_strategy():
    app=(Path(__file__).resolve().parents[1]/'app.py').read_text()
    assert '"ATH Pullback Context": ath_pullback_context' in app
    assert '"Daily Pullback Strategy": pullback_strategy' not in app
