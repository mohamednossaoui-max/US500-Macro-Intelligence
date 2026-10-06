import hashlib
import json
import pandas as pd
import pytest
import ath_extended_history_research_v10 as m


def frame(start='2000-01-03',end='2002-12-31'):
    dates=m.expected_sessions(start,end).index
    return pd.DataFrame({'observation_date':dates.strftime('%Y-%m-%d'),
                         'availability_date':(dates+pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
                         'SP500':[100+i*.1 for i in range(len(dates))]})


def test_closed_rows_are_distinct_from_missing_sessions():
    f=frame('2001-09-10','2001-09-21')
    closed=pd.DataFrame([dict(observation_date='2001-09-11',availability_date='2001-09-12',SP500=float('nan'))])
    a,clean,_=m.calendar_audit(pd.concat([f,closed]),'2001-09-10','2001-09-21')
    assert a['status']=='CALENDAR_MATCH' and len(clean)==len(f)
    assert a['excluded_rows'][0]['status']=='MARKET_CLOSED_ACCORDING_TO_CALENDAR'
    a,_,_=m.calendar_audit(f.iloc[1:],'2001-09-10','2001-09-21')
    assert a['status']=='CALENDAR_MISMATCH' and a['missing_sessions']==['2001-09-10']


def test_unexpected_prices_block():
    f=frame('2020-01-02','2020-01-10')
    extra=pd.DataFrame([dict(observation_date='2020-01-04',availability_date='2020-01-05',SP500=110)])
    a,_,_=m.calendar_audit(pd.concat([f,extra]),'2020-01-02','2020-01-10')
    assert a['status']=='CALENDAR_MISMATCH' and a['unexpected_price_dates']==['2020-01-04']


def test_source_failure_keeps_failed_gate_no_fallback(tmp_path):
    def fail(start,end):raise RuntimeError('HTTP 429')
    with pytest.raises(RuntimeError,match='429'):m.acquire(tmp_path,'2000-01-03','2002-12-31',fail)
    a=json.loads((tmp_path/'acquisition_audit.json').read_text())
    assert a['status']=='SOURCE_ERROR' and a['fallback_used'] is False
    assert not (tmp_path/'validated_prices.csv').exists()


def test_missing_session_does_not_reach_study(tmp_path):
    with pytest.raises(RuntimeError,match='CALENDAR_MISMATCH'):
        m.acquire(tmp_path,'2000-01-03','2002-12-31',lambda s,e:frame().iloc[1:])
    assert not (tmp_path/'validated_prices.csv').exists()
    assert json.loads((tmp_path/'acquisition_audit.json').read_text())['status']=='SOURCE_ERROR'


def test_fixture_end_to_end_keeps_v9_protocol_and_idempotency(tmp_path):
    cache=tmp_path/'cache';output=tmp_path/'study'
    m.acquire(cache,'2000-01-03','2002-12-31',lambda s,e:frame())
    a=m.study(cache,output)
    assert a['protocol']==m.v9.PROTOCOL and a['live_forecast'] is None
    assert a['calendar_verification']=='NYSE_LIBRARY_CALENDAR_MATCH'
    before={p.name:p.read_bytes() for p in output.iterdir()}
    m.study(cache,output)
    assert before=={p.name:p.read_bytes() for p in output.iterdir()}


@pytest.mark.parametrize('name',['validated_prices.csv','nyse_schedule.csv'])
def test_receipt_tamper_blocks_replay(tmp_path,name):
    cache=tmp_path/'cache';m.acquire(cache,'2000-01-03','2002-12-31',lambda s,e:frame())
    p=cache/name;p.write_bytes(p.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='changed'):m.study(cache,tmp_path/'study')


def test_duplicate_and_bad_availability_fail():
    f=frame('2020-01-02','2020-01-10')
    with pytest.raises(ValueError,match='duplicate'):m.calendar_audit(pd.concat([f,f.iloc[:1]]),'2020-01-02','2020-01-10')
    f.loc[0,'availability_date']=f.loc[0,'observation_date']
    with pytest.raises(ValueError,match='availability'):m.calendar_audit(f,'2020-01-02','2020-01-10')


def test_previous_success_cannot_mask_later_source_failure(tmp_path):
    cache=tmp_path/'cache';m.acquire(cache,'2000-01-03','2002-12-31',lambda s,e:frame())
    def fail(s,e):raise RuntimeError('Source unavailable')
    with pytest.raises(RuntimeError):m.acquire(cache,'2000-01-03','2002-12-31',fail)
    with pytest.raises(ValueError,match='gate'):m.study(cache,tmp_path/'study')


def test_no_public_write_or_prelaunch_history(tmp_path):
    with pytest.raises(ValueError,match='public_data'):m.acquire(tmp_path/'public_data')
    with pytest.raises(ValueError,match='Pre-launch'):m.acquire(tmp_path/'cache','1927-01-01','2000-01-03')
