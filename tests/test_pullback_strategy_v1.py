import pandas as pd
import pytest
pytest.importorskip('pullback_strategy_v1', reason='Optional retired entry-strategy module is not part of the depth patch.')
from pullback_strategy_v1 import validate_bars, wilder_atr, snapshot, position_levels, next_attempt


def bars(n=16, price=100):
    return pd.DataFrame({'Date': pd.date_range('2026-01-01', periods=n),
                         'Open': [price]*n, 'High': [price+2]*n,
                         'Low': [float(price-2)]*n, 'Close': [float(price)]*n})


def test_wilder_seed_and_recurrence_and_gap_true_range():
    data = bars()
    data.loc[15, ['Open', 'High', 'Low', 'Close']] = [110, 112, 108, 110]
    atr = wilder_atr(validate_bars(data))
    assert atr.iloc[:14].isna().all()
    assert atr.iloc[14] == 4
    assert atr.iloc[15] == pytest.approx((13*4+12)/14)


def test_insufficient_history_blocks_plan():
    result = snapshot(bars(14), 'ES')
    assert result['status'] == 'INSUFFICIENT_ATR_HISTORY'
    assert all(x['stop_if_filled_at_level'] is None for x in result['levels'])


def test_independent_markets_and_exact_levels():
    es, us = snapshot(bars(price=100), 'ES'), snapshot(bars(price=200), 'US500')
    assert es['reference_peak'] == 102 and us['reference_peak'] == 202
    assert es['levels'][0]['entry'] == pytest.approx(102*.97)
    row = es['levels'][0]
    assert row['entry'] - row['stop_if_filled_at_level'] == 4
    assert row['target_if_filled_at_level'] - row['entry'] == 16
    assert es['forecast'] is None and es['execution'] is False


@pytest.mark.parametrize('stopped,expected', [(None,3),(3,5),(5,10),(10,20),(20,30),(30,None)])
def test_sequential_attempts(stopped, expected):
    assert next_attempt(stopped) == expected


def test_exhaustion_does_not_restart():
    assert snapshot(bars(), 'ES', stopped_level=30, cycle_peak=102)['status'] == 'SEQUENCE_EXHAUSTED'
    with pytest.raises(ValueError):
        snapshot(bars(), 'ES', stopped_level=3)


def test_entry_atr_frozen_and_gap_actual_price():
    assert position_levels(96, 2) == {'entry':96,'entry_atr':2,'stop':94,'target':104,'reward_to_risk':4}
    # A later snapshot has ATR=4, but a recorded trade keeps ATR=2.
    assert snapshot(bars(), 'ES')['atr14'] == 4
    assert position_levels(96, 2)['stop'] == 94


def test_past_snapshot_does_not_see_future_high_or_atr():
    data = bars(20)
    original = snapshot(data, 'ES', as_of='2026-01-16')
    data.loc[19, ['Open','High','Low','Close']] = [500,600,400,500]
    assert snapshot(data, 'ES', as_of='2026-01-16') == original
    assert snapshot(data, 'ES')['reference_peak'] == 600


def test_target_requires_later_strictly_higher_peak():
    data = bars(17)
    result = snapshot(data,'ES',cycle_peak=102,target_achieved=True,target_date='2026-01-16')
    assert result['status'] == 'WAIT_NEW_HIGH' and result['active_level_pct'] is None
    data.loc[16, ['Open','High','Low','Close']] = [103,104,102,103]
    result = snapshot(data,'ES',cycle_peak=102,target_achieved=True,target_date='2026-01-16')
    assert result['reference_peak'] == 104 and result['active_level_pct'] == 3
    with pytest.raises(ValueError):
        snapshot(data,'ES',target_achieved=True)
    with pytest.raises(ValueError):
        snapshot(data,'ES',cycle_peak=102,target_achieved=True,target_date='2027-01-01')


def test_crossed_level_is_not_claimed_as_a_fill():
    result = snapshot(bars(),'US500',cycle_peak=120)
    assert result['status'] == 'LEVEL_ALREADY_CROSSED'
    assert result['peak_verification'] == 'USER_RECORDED_CYCLE_PEAK'


@pytest.mark.parametrize('fault', ['duplicate','nan','infinity','range','negative'])
def test_bad_data_fails_closed(fault):
    data = bars()
    if fault == 'duplicate': data.loc[1,'Date'] = data.loc[0,'Date']
    if fault == 'nan': data.loc[1,'Close'] = float('nan')
    if fault == 'infinity': data.loc[1,'Close'] = float('inf')
    if fault == 'range': data.loc[1,'High'] = 90
    if fault == 'negative': data.loc[1,'Low'] = -1
    with pytest.raises(ValueError): snapshot(data,'ES')


def test_app_registers_separate_page_without_changing_decision_rules():
    from pathlib import Path
    app = (Path(__file__).resolve().parents[1]/'app.py').read_text()
    assert '"Daily Pullback Strategy": pullback_strategy' not in app
    assert '"ATH Pullback Context": ath_pullback_context' in app


def test_ui_smoke(tmp_path):
    pytest.importorskip('pullback_strategy_ui_v1', reason='Optional retired strategy UI.')
    from streamlit.testing.v1 import AppTest
    page = tmp_path / "page.py"
    page.write_text("from pullback_strategy_ui_v1 import render_pullback_strategy\nrender_pullback_strategy()\n")
    app = AppTest.from_file(str(page)).run()
    assert not app.exception
    assert len(app.get("file_uploader")) == 2
