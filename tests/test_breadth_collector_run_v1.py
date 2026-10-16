"""Exercise the collector and its actual downstream stages without network I/O."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[1]
FILE=ROOT/'tests/market_breadth/market_breadth_historical_collector_v1.py'
spec=importlib.util.spec_from_file_location('breadth_collector_run',FILE)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_calculation_needs_no_run_metadata_globals():
    days=pd.bdate_range('2026-08-10',periods=3)
    prices=pd.DataFrame({'AAA':[100.,101.,100.],'BBB':[100.,99.,99.]},index=days)
    d=m.calculate_breadth(days,{t:{'AAA','BBB'} for t in days},prices)
    assert list(d.advances)==[1,0] and list(d.declines)==[1,1]
    assert list(d.unchanged)==[0,1] and list(d.net_advances)==[0,-1]
    assert list(d.cumulative_ad_line)==[0,-1]
    assert not {'requested_end_date','membership_last_date','collection_status'} & set(d.columns)
    assert m.validate_output(d)['validation_pass']


def fixture_run(tmp_path,monkeypatch,start,end):
    last=pd.Timestamp('2026-08-18');members={'AAA','BBB','CCC'}
    snapshots={pd.Timestamp('2018-12-31'):members,last:members}
    monkeypatch.setattr(m,'load_membership_history',lambda _:snapshots)
    monkeypatch.setattr(m,'load_sp500_sessions',lambda s,e:pd.bdate_range(s,e))
    def prices(tickers,s,e):
        days=pd.bdate_range(s,e);x=np.arange(len(days))
        return pd.DataFrame({t:100+j*5+np.cumsum(np.sin(x/(j+2))+0.01) for j,t in enumerate(tickers)},index=days)
    monkeypatch.setattr(m,'download_prices',prices)
    output=tmp_path/'collector'
    monkeypatch.setattr(sys,'argv',['collector','--start',start,'--end',end,'--output',str(output)])
    assert m.main()==0
    meta=json.loads((output/'market_breadth_metadata_v1.json').read_text())
    assert meta['validation']['validation_pass'] and meta['pit_perfect'] is False
    assert meta['research_only'] and not meta['decision_engine_ready']
    return output,meta


@pytest.mark.parametrize('end,status,complete,lag',[
    ('2026-08-17','CURRENT',True,0),
    ('2026-08-18','CURRENT',True,0),
    ('2026-10-16','STALE',False,59)])
def test_main_writes_metadata_without_inventing_membership(tmp_path,monkeypatch,end,status,complete,lag):
    output,meta=fixture_run(tmp_path,monkeypatch,'2026-08-10',end)
    assert meta['requested_end_date']==end
    assert meta['membership_last_date']=='2026-08-18'
    assert meta['collection_status']==status and meta['requested_range_complete'] is complete
    assert meta['source_lag_days']==lag
    d=pd.read_csv(output/'market_breadth_records_v1.csv')
    assert d.asof_date.max()<=min(end,'2026-08-18')


def test_actual_three_stage_pipeline_with_frozen_inputs(tmp_path,monkeypatch):
    output,meta=fixture_run(tmp_path,monkeypatch,'2019-01-01','2026-10-16')
    analysis=tmp_path/'analysis';robust=tmp_path/'robustness'
    commands=[
        [ROOT/'tests/market_breadth/market_breadth_analyzer_v1.py','--input',output/'market_breadth_records_v1.csv','--output',analysis],
        [ROOT/'tests/market_breadth/market_breadth_validation_robustness_v1.py','--input',analysis/'market_breadth_analysis_v1.csv','--output',robust]]
    for args in commands:
        r=subprocess.run([sys.executable]+list(map(str,args)),capture_output=True,text=True)
        assert r.returncode==0,r.stdout+r.stderr
    assert json.loads((analysis/'market_breadth_analysis_validation_v1.json').read_text())['validation_pass']
    assert json.loads((robust/'market_breadth_robustness_validation_v1.json').read_text())['validation_pass']
    assert meta['collection_status']=='STALE' and not meta['requested_range_complete']


def write_stage_reports(root,value=True):
    from scripts.breadth_validation_report_v1 import PATHS
    for name in PATHS.values():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps({'validation_pass':value}))


def test_missing_output_summary_is_failure_without_guessing_cause(tmp_path):
    from scripts.breadth_validation_report_v1 import build_report
    report=build_report(tmp_path)
    assert report['final_status']=='FAIL'
    assert not any(report['stages'].values())
    assert report['failure_stage']=='MISSING_OR_INVALID_STAGE_REPORT'


def test_failure_outcome_beats_old_pass_reports_and_retains_log(tmp_path):
    from scripts.breadth_validation_report_v1 import build_report
    write_stage_reports(tmp_path)
    log=tmp_path/'market_breadth_full_validation_v1/logs/collector.log';log.parent.mkdir(parents=True);log.write_text('Synthetic collector exception')
    report=build_report(tmp_path,{'preflight':'success','historical_collector':'failure','analyzer':'skipped','validation_robustness':'skipped'})
    assert report['final_status']=='FAIL' and report['failure_stage']=='historical_collector'
    assert report['log_files']==['market_breadth_full_validation_v1/logs/collector.log']
    assert report['stages']['historical_collector'] is False


def test_valid_reports_with_success_outcomes_pass(tmp_path):
    from scripts.breadth_validation_report_v1 import build_report
    write_stage_reports(tmp_path)
    report=build_report(tmp_path,{name:'success' for name in ['preflight','historical_collector','analyzer','validation_robustness']})
    assert report['final_status']=='PASS' and report['failure_stage'] is None


def test_text_false_never_becomes_validation_pass(tmp_path):
    from scripts.breadth_validation_report_v1 import build_report
    write_stage_reports(tmp_path,'False')
    assert build_report(tmp_path)['final_status']=='FAIL'


def test_tee_keeps_failure_exit_status(tmp_path):
    log=tmp_path/'failed.log'
    command=f'set -o pipefail\n"{sys.executable}" -c "import sys; print(\'synthetic failure\'); sys.exit(23)" 2>&1 | tee "{log}"'
    result=subprocess.run(['bash','-c',command],capture_output=True,text=True)
    assert result.returncode==23 and 'synthetic failure' in log.read_text()


def test_report_cli_fails_closed_and_still_writes_diagnostic(tmp_path):
    script=ROOT/'scripts/breadth_validation_report_v1.py'
    result=subprocess.run([sys.executable,str(script),'--root',str(tmp_path)],capture_output=True,text=True)
    assert result.returncode==1
    report=json.loads((tmp_path/'market_breadth_full_validation_v1/market_breadth_full_validation_summary_v1.json').read_text())
    assert report['final_status']=='FAIL' and not any(report['stages'].values())


def test_workflow_captures_logs_without_masking_failures():
    import yaml,re
    source=(ROOT/'.github/workflows/market-breadth-full-validation-v1.yml').read_text()
    workflow=yaml.safe_load(source)
    steps=workflow['jobs']['full-validation']['steps']
    stage_steps={s.get('id'):s for s in steps if s.get('id') in {'preflight','collector','analyzer','robustness'}}
    assert set(stage_steps)=={'preflight','collector','analyzer','robustness'}
    for id,step in stage_steps.items():
        assert 'set -euo pipefail' in step['run'] and ' | tee ' in step['run']
        result=subprocess.run(['bash','-n'],input=step['run'],capture_output=True,text=True)
        assert result.returncode==0,result.stderr
    report=next(s for s in steps if s.get('name')=='Build unified final report')
    assert report['if']=='always()' and 'breadth_validation_report_v1.py' in report['run']
    assert len(report['env'])==4
    upload=next(s for s in steps if s.get('uses')=='actions/upload-artifact@v4')
    assert upload['if']=='always()'
