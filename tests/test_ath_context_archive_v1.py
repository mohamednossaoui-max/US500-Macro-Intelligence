import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from ath_context_archive_v1 import capture, load, before, REQUIRED


def manifest(root):
    files={}
    for name in REQUIRED:
        p=root/name
        files[name]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    (root/'manifest.json').write_text(json.dumps({'files':files}))


def inputs(root):
    root.mkdir()
    vector=pd.DataFrame([{'feature':'economic_inflation','value':1,'context_date':'2020-01-01',
                          'as_of':'2020-01-01','available_at':'2020-01-01','eligible':True,
                          'freshness':'CURRENT','pit_status':'PIT_SAFE'}])
    vector.to_csv(root/REQUIRED[0],index=False)
    pd.DataFrame([{'context_date':'2020-01-01','inflation_score':1}]).to_csv(root/REQUIRED[1],index=False)
    pd.DataFrame([{'as_of_date':'2020-01-01','state':'SUPPORTIVE'}]).to_csv(root/REQUIRED[2],index=False)
    (root/REQUIRED[3]).write_text(json.dumps({'as_of_date':'2020-01-01','fed_score':{'score':50}}))
    manifest(root)
    return root


def test_capture_duplicate_preserves_first_observed_time(tmp_path):
    public=inputs(tmp_path/'public');archive=tmp_path/'archive'
    first=capture(public,archive,'2020-01-02T12:00:00Z')
    frozen={p.name:p.read_bytes() for p in (archive/'snapshots').iterdir()}
    second=capture(public,archive,'2020-01-03T12:00:00Z')
    assert first['status']=='CAPTURED' and second['status']=='UNCHANGED'
    assert first['snapshot_id']==second['snapshot_id']
    assert frozen=={p.name:p.read_bytes() for p in (archive/'snapshots').iterdir()}
    assert load(archive)[0]['available_at']=='2020-01-02T12:00:00+00:00'


def test_revision_keeps_prior_payload_and_asof_access(tmp_path):
    public=inputs(tmp_path/'public');archive=tmp_path/'archive'
    capture(public,archive,'2020-01-02T12:00:00Z')
    vector=pd.read_csv(public/REQUIRED[0]);vector['value']=2;vector.to_csv(public/REQUIRED[0],index=False);manifest(public)
    capture(public,archive,'2020-01-03T12:00:00Z')
    assert len(load(archive))==2
    assert before(archive,'2020-01-03T11:00:00Z')['payload'][REQUIRED[0]][0]['value']==1
    assert before(archive,'2020-01-03T13:00:00Z')['payload'][REQUIRED[0]][0]['value']==2


def test_cannot_backcast_source_reference_date_or_same_capture_instant(tmp_path):
    public=inputs(tmp_path/'public');archive=tmp_path/'archive'
    capture(public,archive,'2020-02-01T12:00:00Z')
    assert before(archive,'2020-01-02') is None
    assert before(archive,'2020-02-01T12:00:00Z') is None
    assert before(archive,'2020-02-10') is None  # stale archive context


def test_source_failure_does_not_change_archive(tmp_path):
    public=inputs(tmp_path/'public');archive=tmp_path/'archive'
    capture(public,archive,'2020-01-02')
    original={p.name:p.read_bytes() for p in (archive/'snapshots').iterdir()}
    (public/REQUIRED[3]).unlink()
    with pytest.raises(ValueError):capture(public,archive,'2020-01-03')
    assert original=={p.name:p.read_bytes() for p in (archive/'snapshots').iterdir()}


def test_manifest_mismatch_blocks_capture(tmp_path):
    public=inputs(tmp_path/'public')
    (public/REQUIRED[3]).write_text('{}')
    with pytest.raises(ValueError,match='Publication Integrity'):capture(public,tmp_path/'archive','2020-01-02')


def test_future_context_is_rejected(tmp_path):
    public=inputs(tmp_path/'public')
    with pytest.raises(ValueError,match='future'):capture(public,tmp_path/'archive','2019-01-01')


def test_archive_header_tamper_is_detected(tmp_path):
    public=inputs(tmp_path/'public');archive=tmp_path/'archive'
    capture(public,archive,'2020-01-02')
    path=next((archive/'snapshots').glob('*.json'));d=json.loads(path.read_text())
    d['available_at']='1990-01-01';path.write_text(json.dumps(d))
    with pytest.raises(ValueError,match='checksum'):load(archive)


def test_exact_source_text_and_float_precision_are_preserved(tmp_path):
    public=inputs(tmp_path/'public');archive=tmp_path/'archive'
    data=pd.read_csv(public/REQUIRED[0]);data['value']=0.1234567890123456
    data.to_csv(public/REQUIRED[0],index=False);manifest(public)
    original=(public/REQUIRED[0]).read_text()
    expected=pd.read_csv(public/REQUIRED[0]).value.iloc[0]
    capture(public,archive,'2020-01-02')
    record=load(archive)[0]
    assert record['payload'][REQUIRED[0]][0]['value']==expected
    assert record['payload']['source_text'][REQUIRED[0]]==original


def test_archive_outside_public_and_no_write_to_sources(tmp_path):
    public=inputs(tmp_path/'public');frozen={p.name:p.read_bytes() for p in public.iterdir()}
    with pytest.raises(ValueError):capture(public,public/'archive','2020-01-02')
    capture(public,tmp_path/'archive','2020-01-02')
    assert frozen=={p.name:p.read_bytes() for p in public.iterdir()}


def test_master_captures_after_verification_and_stages_only_archive():
    root=Path(__file__).resolve().parents[1]
    s=(root/'.github/workflows/us500-full-research-pipeline.yml').read_text()
    capture_at=s.index('python ath_context_archive_v1.py')
    assert s.index('python scripts/verify_publication_integrity.py',s.index('Rebuild Integrated Intelligence Layers'))<capture_at
    assert 'git add research_history/ath_context_v1 research_history/ath_depth_model_audit_v1.json' in s
