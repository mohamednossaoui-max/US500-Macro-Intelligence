"""Workspace validation must never overwrite a newly merged release."""
import pandas as pd
import pytest
import economic_canonical_input_v2 as bridge


def setup(monkeypatch,tmp_path):
 monkeypatch.setattr(bridge,'ROOT',tmp_path);pub=tmp_path/'public_data';pub.mkdir();monkeypatch.setattr(bridge,'PUBLIC',pub)
 for directory,date,value in [(pub,'2024-01-01',100),(tmp_path,'2024-02-01',200)]:
  pd.DataFrame([dict(indicator=i,release_date=date,actual=value) for i in ['NFP','PCE_PRICE_INDEX','CORE_PCE']]).to_csv(directory/bridge.EVENTS,index=False)
  pd.DataFrame([dict(point_in_time_safe=True)]).to_csv(directory/bridge.QUALITY,index=False)
 return tmp_path,pub


def test_workspace_keeps_exact_merged_bytes(monkeypatch,tmp_path):
 root,pub=setup(monkeypatch,tmp_path)
 before={n:(root/n).read_bytes() for n in [bridge.EVENTS,bridge.QUALITY]}
 result=bridge.stage_canonical_input(workspace=True)
 assert result['latest_release']=='2024-02-01'
 assert all((root/n).read_bytes()==b for n,b in before.items())
 assert pd.read_csv(root/bridge.EVENTS).actual.eq(200).all()


def test_default_stages_public_baseline(monkeypatch,tmp_path):
 root,pub=setup(monkeypatch,tmp_path);bridge.stage_canonical_input()
 assert (root/bridge.EVENTS).read_bytes()==(pub/bridge.EVENTS).read_bytes()


def test_workspace_missing_does_not_fallback_to_old_public(monkeypatch,tmp_path):
 root,pub=setup(monkeypatch,tmp_path);(root/bridge.EVENTS).unlink()
 with pytest.raises(FileNotFoundError):bridge.stage_canonical_input(workspace=True)
 assert not (root/bridge.EVENTS).exists()
