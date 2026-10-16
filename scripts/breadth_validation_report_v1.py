"""Build a failure-aware Breadth report, retaining diagnostics on failed stages."""
import argparse,json,os
from pathlib import Path

PATHS={
 'historical_collector':'market_breadth_historical_v1/market_breadth_validation_v1.json',
 'analyzer':'market_breadth_analysis_v1/market_breadth_analysis_validation_v1.json',
 'validation_robustness':'market_breadth_validation_robustness_v1/market_breadth_robustness_validation_v1.json'}

def load(path):
    if not path.is_file():return {'file_found':False}
    try:
        obj=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(obj,dict):raise ValueError('Expected report object')
        return dict(obj,file_found=True)
    except (OSError,ValueError) as exc:return {'file_found':True,'parse_error':str(exc)}

def build_report(root,step_outcomes=None):
    root=Path(root);steps=step_outcomes or {}
    reports={key:load(root/name) for key,name in PATHS.items()}
    stages={key:obj.get('validation_pass') is True and steps.get(key,'success')=='success' for key,obj in reports.items()}
    passed=all(stages.values()) and all(s=='success' for s in steps.values())
    logs=root/'market_breadth_full_validation_v1/logs'
    failures=[key for key,value in steps.items() if value in {'failure','cancelled'}]
    metadata=load(root/'market_breadth_historical_v1/market_breadth_metadata_v1.json')
    stale=metadata.get('collection_status')=='STALE' or metadata.get('requested_range_complete') is False
    data_status='STALE' if stale else 'CURRENT' if metadata.get('requested_range_complete') is True else 'UNKNOWN'
    return {'data_status':data_status,'validation_scope':'STRUCTURE_AND_ACCOUNTING_ONLY',
            'freshness_pass':data_status=='CURRENT',
            'warnings':['Membership coverage ends before the requested date; validation PASS does not mean current data.'] if stale else [],
            'validator':'Market Breadth Full Validation v1','research_only':True,'pit_perfect':False,
            'decision_engine_ready':False,'trading_signal':False,'forecast':False,
            'stages':stages,'final_status':'PASS' if passed else 'FAIL',
            'collector':reports['historical_collector'],'analyzer':reports['analyzer'],'robustness':reports['validation_robustness'],
            'workflow_steps':steps,'failure_stage':failures[0] if failures else (None if passed else 'MISSING_OR_INVALID_STAGE_REPORT'),
            'log_files':[p.relative_to(root).as_posix() for p in sorted(logs.glob('*.log'))],
            'requested_range':{k:metadata.get(k) for k in ['requested_end_date','end_date','membership_last_date','source_lag_days','collection_status','requested_range_complete']}}

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');a=p.parse_args()
    root=Path(a.root);steps={k:os.getenv(v,'unknown') for k,v in {
        'preflight':'STEP_PREFLIGHT','historical_collector':'STEP_COLLECTOR','analyzer':'STEP_ANALYZER','validation_robustness':'STEP_ROBUSTNESS'}.items()}
    report=build_report(root,steps);output=root/'market_breadth_full_validation_v1';output.mkdir(parents=True,exist_ok=True)
    (output/'market_breadth_full_validation_summary_v1.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    if report['data_status']=='STALE':
        print('::warning title=Breadth membership coverage is stale::Historical validation passed only for the available period. See requested_range; do not extrapolate membership.')
    print(json.dumps(report,indent=2,ensure_ascii=False));return 0 if report['final_status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
