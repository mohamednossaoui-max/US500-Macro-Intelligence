import json
import pandas as pd
import pytest
import ath_official_vintage_backfill_v1 as m
from ath_vintage_receipt_replay_v1 import replay


def acquired(tmp_path):
    cache=tmp_path/'cache';audit={'results':[],'first_provider_vintages':{},'archive_metadata_errors':{}}
    for sid,(freq,sa,units,_) in m.SERIES.items():
        date='2020-03-01' if freq=='Monthly' else '2020-01-01' if freq=='Quarterly' else '2020-03-31'
        payload={'realtime_start':'2020-04-01','realtime_end':'2020-04-01',
                 'observations':[{'date':date,'value':'110'}]}
        if freq=='Monthly':payload['observations'].append({'date':'2020-02-01','value':'100'})
        sha=m.immutable_receipt(cache,sid,'2020-04-01',{'id':sid,'frequency':freq,'seasonal_adjustment':sa,'units':units},payload)
        audit['results'].append({'series':sid,'as_of_date':'2020-04-01','receipt_sha256':sha})
        audit['first_provider_vintages'][sid]='1990-01-01'
    path=tmp_path/'audit.json';path.write_text(json.dumps(audit))
    return cache,path,pd.DataFrame({'decision_at':['2020-04-02T00:00:00+00:00']})


def test_offline_replay_is_idempotent_and_missing_derived_fields_explicit(tmp_path):
    cache,audit,events=acquired(tmp_path)
    a=replay(events,audit,cache,tmp_path/'out');b=replay(events,audit,cache,tmp_path/'out')
    assert a==b and a['verified']==10 and a['unavailable_derived_fields']==3
    assert len(list((tmp_path/'out'/'receipts').glob('*')))==10
    assert a['live_forecast'] is None


def test_replay_audit_hash_mismatch_blocks(tmp_path):
    cache,audit,events=acquired(tmp_path)
    data=json.loads(audit.read_text());data['results'][0]['receipt_sha256']='wrong';audit.write_text(json.dumps(data))
    with pytest.raises(m.SourceError):replay(events,audit,cache,tmp_path/'out')
