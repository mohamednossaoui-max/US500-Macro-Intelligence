import json
from pathlib import Path
import pandas as pd
import pytest
import ath_cause_context_v1 as m


def vector(value=.7,**changes):
    r={'feature':'economic_inflation','value':value,'state':'MIXED','as_of':'2024-01-01',
       'available_at':'2024-01-02','age_days':1,'freshness':'CURRENT','pit_status':'PIT_SAFE',
       'quality':'MEDIUM','eligible':True,'source':'official_input.csv'}
    r.update(changes);return pd.DataFrame([r])


def news(title='Inflation surges as rate hike fears rise',**changes):
    r={'title':title,'url':'https://example.org/report','source':'fixture','published_at':'2024-01-02T10:00:00Z',
       'availability_date':'2024-01-02T10:00:00Z','point_in_time_safe':True,'pit_status':'PIT_SAFE',
       'event_class':'MACRO','is_duplicate':False}
    r.update(changes);return pd.DataFrame([r])


def test_directional_feature_not_inflation_level():
    values,evidence,excluded=m.select_features(vector(),m.utc('2024-01-03'))
    assert values['economic_inflation']==.7 and evidence[0]['verification'].startswith('PROGRAMME')


@pytest.mark.parametrize('changes,reason',[({'available_at':'2024-01-04'},'FUTURE'),({'eligible':False},'PIT_INELIGIBLE'),
 ({'pit_status':'PIT_LIMITED'},'PIT_INELIGIBLE'),({'age_days':99},'STALE'),({'value':float('nan')},'METADATA_UNVERIFIED')])
def test_bad_feature_never_imputed(changes,reason):
    values,_,excluded=m.select_features(vector(**changes),m.utc('2024-01-03'))
    assert 'economic_inflation' not in values and excluded[0]['reason']==reason


def test_news_candidate_not_a_probability():
    items,_=m.news_candidates(news(),m.utc('2024-01-03'))
    assert len(items['INFLATION_RATE_PRESSURE'])==1
    assert items['INFLATION_RATE_PRESSURE'][0]['verification']=='TITLE_CANDIDATE_REQUIRES_CONTEXT_REVIEW'


@pytest.mark.parametrize('title',['No recession expected','Recession fears easing','Bank failure unlikely'])
def test_negation_never_asserts_adverse_case(title):
    items,excluded=m.news_candidates(news(title),m.utc('2024-01-03'))
    assert not any(items.values()) and excluded[0]['reason'].startswith('NEGATION')


def test_duplicates_and_administrative_news_excluded():
    n=pd.concat([news(),news(),news(event_class='ADMINISTRATIVE',url='https://example.org/admin')])
    items,excluded=m.news_candidates(n,m.utc('2024-01-03'))
    assert len(items['INFLATION_RATE_PRESSURE'])==1
    assert {x['reason'] for x in excluded}=={'DUPLICATE','ADMINISTRATIVE'}


@pytest.mark.parametrize('changes,reason',[({'published_at':'2024-01-04','availability_date':'2024-01-04'},'FUTURE'),
 ({'availability_date':'2024-01-01'},'AVAILABILITY_BEFORE_PUBLICATION'),({'pit_status':'UNKNOWN'},'PIT_INELIGIBLE')])
def test_news_timestamps_and_pit_checked(changes,reason):
    items,excluded=m.news_candidates(news(**changes),m.utc('2024-01-03'))
    assert not any(items.values()) and excluded[0]['reason']==reason


def receipt():
    return {'as_of':'2024-01-03T00:00:00Z','source_sha256':{'fixture':'abc'},'context_features':{'economic_inflation':.7},
            'feature_evidence':[{'feature':'economic_inflation','value':.7,'available_at':'2024-01-02T00:00:00Z','as_of':'2024-01-01'}],
            'causes':[],'observed_market_response':{'available_at':'2024-01-02T00:00:00Z'}}


def test_genuine_capture_idempotent_without_backdating(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'now_utc',lambda:m.utc('2024-01-04'))
    a=m.capture(receipt(),tmp_path/'archive');b=m.capture(receipt(),tmp_path/'archive')
    assert a['status']=='CAPTURED' and b['status']=='UNCHANGED' and b['snapshot_count']==1
    r=m.load(tmp_path/'archive')[0]
    assert r['available_at']==m.utc('2024-01-04').isoformat()


def test_archive_change_preserves_previous_vintage(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'now_utc',lambda:m.utc('2024-01-04'))
    m.capture(receipt(),tmp_path);r=receipt();r['context_features']['economic_inflation']=.9
    m.capture(r,tmp_path)
    assert len(m.load(tmp_path))==2


def test_archive_tampering_rejected(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'now_utc',lambda:m.utc('2024-01-04'));m.capture(receipt(),tmp_path)
    p=next(tmp_path.glob('snapshots/*.json'));r=json.loads(p.read_text());r['available_at']='2023-01-01';p.write_text(json.dumps(r))
    with pytest.raises(ValueError,match='checksum'):m.load(tmp_path)


def test_publication_failure_blocks_assessment(tmp_path):
    with pytest.raises(ValueError,match='Publication'):m.assess(tmp_path)


def test_future_assessment_rejected():
    with pytest.raises(ValueError,match='Future'):m.assess(Path('.'),m.now_utc()+pd.Timedelta(days=1))


def test_current_ui_has_no_live_probability_or_trading_controls():
    p=Path(__file__).resolve().parents[1]/'ath_cause_context_ui_v1.py'
    s=p.read_text()
    assert 'غير موثوق' in s and 'render_cause_context' in s
    assert 'buy_button' not in s and 'sell_button' not in s


def test_news_quality_gate_is_not_silently_ignored():
    items,excluded=m.news_candidates(news(quality_gate='INELIGIBLE'),m.utc('2024-01-03'))
    assert not any(items.values()) and excluded[0]['reason']=='QUALITY_INELIGIBLE'


def test_archive_asof_includes_news_availability(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'now_utc',lambda:m.utc('2024-01-04'))
    r=receipt();r['causes']=[{'news_evidence':[{'available_at':'2024-01-03T00:00:00Z'}]}]
    m.capture(r,tmp_path)
    assert m.load(tmp_path)[0]['payload']['as_of']==m.utc('2024-01-03').isoformat()


def test_future_record_rejected_even_with_valid_checksum(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'now_utc',lambda:m.utc('2024-01-04'));m.capture(receipt(),tmp_path)
    monkeypatch.setattr(m,'now_utc',lambda:m.utc('2024-01-03'))
    with pytest.raises(ValueError,match='future'):m.load(tmp_path)


def test_real_cause_ui_smoke():
    from streamlit.testing.v1 import AppTest
    root=Path(__file__).resolve().parents[1]/'public_data'
    app=AppTest.from_string('from ath_cause_context_ui_v1 import render_cause_context\nrender_cause_context('+repr(str(root))+')').run(timeout=30)
    assert not app.exception and not app.error
    assert any('غير موثوق' in x.value for x in app.markdown)
