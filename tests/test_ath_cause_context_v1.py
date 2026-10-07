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
    assert 'not validated' in s and 'render_cause_context' in s
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


def test_real_cause_ui_smoke(ath_ui_publication):
    from streamlit.testing.v1 import AppTest
    root=ath_ui_publication
    app=AppTest.from_string('from ath_cause_context_ui_v1 import render_cause_context\nrender_cause_context('+repr(str(root))+')').run(timeout=30)
    assert not app.exception and not app.error
    assert any('not validated' in x.value for x in app.markdown)



def test_ath_interface_labels_are_english():
    import ast
    from ath_cause_context_ui_v1 import CAUSE_LABELS
    root=Path(__file__).resolve().parents[1]
    for name in ('ath_pullback_context_ui_v1.py','ath_cause_context_ui_v1.py'):
        literals=[x.value for x in ast.walk(ast.parse((root/name).read_text()))
                  if isinstance(x,ast.Constant) and isinstance(x.value,str)]
        assert not any(any('\u0600'<=c<='\u06ff' for c in text) for text in literals)
    assert set(CAUSE_LABELS)==set(m.RULES)
    assert all(not any('\u0600'<=c<='\u06ff' for c in text) for text in CAUSE_LABELS.values())


def test_page_renders_without_calendar_or_research_imports(ath_ui_publication):
    import subprocess,sys
    root=Path(__file__).resolve().parents[1]
    script='''
import importlib.abc,sys
class NoResearch(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in {'pandas_market_calendars','ath_ema19_touch_research_v12','ath_extended_history_research_v10'}:
            raise ModuleNotFoundError('Forbidden UI dependency: '+fullname)
sys.meta_path.insert(0,NoResearch())
from streamlit.testing.v1 import AppTest
app=AppTest.from_string('from ath_pullback_context_ui_v1 import render_ath_pullback_context\\nrender_ath_pullback_context('+repr(sys.argv[1])+')').run(timeout=30)
assert not app.exception and not app.error
assert any('Drawdown-depth probability' in x.value for x in app.markdown)
'''
    r=subprocess.run([sys.executable,'-c',script,str(ath_ui_publication)],cwd=root,capture_output=True,text=True,timeout=45)
    assert r.returncode==0,r.stdout+r.stderr


def price_frame():
    return pd.DataFrame({'observation_date':['2024-01-01','2024-01-02'],
        'availability_date':['2024-01-02','2024-01-03'],
        'Open':[99,99],'High':[100,100],'Low':[98,97],'Close':[99,98],
        'symbol':['^GSPC','ES']})


@pytest.mark.parametrize('problem',['date','duplicate','availability','nan','nonpositive','range'])
def test_published_price_validation_remains_strict(problem):
    f=price_frame()
    if problem=='date':f.loc[1,'observation_date']='bad'
    elif problem=='duplicate':f.loc[1,'observation_date']='2024-01-01'
    elif problem=='availability':f.loc[1,'availability_date']='2024-01-02'
    elif problem=='nan':f.loc[1,'Close']=float('nan')
    elif problem=='nonpositive':f.loc[1,'Low']=0
    elif problem=='range':f.loc[1,'High']=90
    with pytest.raises(ValueError):m.price_context(f,m.utc('2024-01-04'))


def test_future_price_and_instrument_are_excluded():
    r=m.price_context(price_frame(),m.utc('2024-01-02'))
    assert r['last_session']=='2024-01-01' and r['instrument']=='^GSPC'
    assert r['drawdown_at_close_pct']==pytest.approx(1.)


def test_ui_fixture_keeps_integrity_gate_strict(ath_ui_publication, tmp_path):
    import shutil
    from streamlit.testing.v1 import AppTest
    root = tmp_path / 'public_data'
    shutil.copytree(ath_ui_publication, root)
    target = root / 'unified_state_vector_v1.csv'
    target.write_bytes(target.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='Publication'):
        m.assess(root)
    app = AppTest.from_string(
        'from ath_cause_context_ui_v1 import render_cause_context\n'
        'render_cause_context(' + repr(str(root)) + ')'
    ).run(timeout=30)
    assert not app.exception
    assert any('Risk evidence unavailable' in x.value for x in app.markdown)
    assert not any('not validated' in x.value for x in app.markdown)
