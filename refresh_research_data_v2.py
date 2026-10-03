"""Isolated official refresh and validated publication for local research use.

All selected sources must validate before rebuilding and installing public_data.
The default audit mode leaves the repository's public_data untouched. No git,
trade, account, deployment or external write operation is performed.
"""
from __future__ import annotations
import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
ECONOMIC_FILES = ['economic_historical_events_v1.csv','economic_historical_quality_v1.csv',
    'economic_surprise_engine_v1.csv','economic_surprise_summary_v1.csv',
    'economic_regime_events_v1.csv','economic_regime_summary_v1.csv','economic_ingestion_status_v1.json']
NEWS_FILES = ['event_news_research_v2.csv','event_news_validation_v2.json','event_news_research_summary_v2.json']


def command(work, *args, env=None):
    environment = dict(os.environ)
    if env:
        environment.update(env)
    print('RUN', ' '.join(map(str,args)), flush=True)
    subprocess.run([sys.executable, *map(str,args)], cwd=work, env=environment, check=True)


def install_validated(public, candidate, history):
    """Swap a fully validated directory with rollback; archive changed old bytes."""
    from scripts.verify_publication_integrity import run
    report = run(candidate)
    if report['errors'] or any(any(m['summary'][k] for k in ['mismatch','missing','error']) for m in report['manifests']):
        raise RuntimeError('Publication integrity failed; no installation')
    public, candidate, history = Path(public), Path(candidate), Path(history)
    for old in public.iterdir():
        new = candidate/old.name
        if old.is_file() and new.is_file() and old.read_bytes() != new.read_bytes():
            digest=hashlib.sha256(old.read_bytes()).hexdigest()
            target=history/old.name/digest
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(old,target)
    temporary = public.with_name('public_data.validated.tmp')
    backup = public.with_name('public_data.rollback.tmp')
    if temporary.exists() or backup.exists():
        raise RuntimeError('Unresolved previous publication transaction; inspect temporary directories')
    shutil.copytree(candidate, temporary)
    public.replace(backup)
    try:
        temporary.replace(public)
    except BaseException:
        backup.replace(public)
        raise
    shutil.rmtree(backup)


def validate_fed(stage):
    data = json.loads((stage/'fed_intelligence_output_v1.json').read_text())
    if not data.get('available') or data.get('source_verification') != 'VERIFIED' or data.get('source_errors'):
        raise RuntimeError('Fed official verification failed')
    if data.get('as_of_date') != date.today().isoformat():
        raise RuntimeError('Staged Fed snapshot is not from today')
    if not (data.get('document_status') or {}).get('statement',{}).get('publication_date'):
        raise RuntimeError('Fed statement release metadata unavailable')


def validate_news(stage):
    import pandas as pd
    validation = json.loads((stage/'event_news_validation_v2.json').read_text())
    if not validation.get('validation_pass') or validation.get('source_verification') == 'SOURCE_ERROR':
        raise RuntimeError('News official verification failed')
    data=pd.read_csv(stage/'event_news_research_v2.csv')
    published=pd.to_datetime(data.published_at, format='mixed', utc=True, errors='coerce')
    now=pd.Timestamp.now(tz='UTC')
    if published.isna().any() or (published>now).any() or (now-published.max()).total_seconds()>7*86400:
        raise RuntimeError('News publication freshness failed')
    if len(data) != validation.get('rows') or published.max() != pd.Timestamp(validation['latest_publication']):
        raise RuntimeError('Staged News CSV differs from its validated release state')


def rebuild(work):
    pub=work/'public_data'
    for path in pub.iterdir():
        if path.is_file() and path.suffix in {'.json','.csv'}:
            shutil.copy2(path,work/path.name)
    context_env = {}
    status_file = pub/'economic_ingestion_status_v1.json'
    if status_file.exists():
        status = json.loads(status_file.read_text())
        from macro_context_v1 import resolve_context_date, verified_economic_context_date
        economic_as_of = verified_economic_context_date(status)
        if economic_as_of:
            # Source dates and per-layer PIT gates remain independently recorded.
            fed = json.loads((pub/'fed_intelligence_output_v1.json').read_text())
            context_env['MACRO_CONTEXT_AS_OF_DATE'] = resolve_context_date(
                fed.get('as_of_date'), economic_as_of).isoformat()
    command(work,'macro_context_v1.py',env=context_env)
    for name in ['macro_context_v1.csv','macro_context_v1.json']:
        shutil.copy2(work/name,pub/name)
    command(work,'research-context-v1.py',env={
        'MACRO_CONTEXT_FILE':str(work/'macro_context_v1.csv'),
        'SENTIMENT_ENGINE_FILE':str(work/'sentiment_engine_research_v1.csv'),
        'TECHNICAL_INTELLIGENCE_FILE':str(work/'technical_intelligence_research_v1.csv')})
    for name in ['research_context_v1.csv','research_context_summary_v1.csv','research_context_extremes_v1.csv']:
        shutil.copy2(work/name,pub/name)
    for name in ['research_evidence_contract_v1.py','research_context_quality_integration_v1.py']:
        command(work,name)
    output=work/'decision_engine_output'
    if output.exists():shutil.rmtree(output)
    command(work,'tests/decision_engine/decision_engine_v1.py','--input',pub/'research_context_summary_v1.csv','--output-dir',output)
    for path in output.iterdir():shutil.copy2(path,pub/path.name)
    for name in ['remaining_layers_quality_v1.py','final_remaining_layers_hardening_v1.py',
                 'unified_state_vector_v1.py','historical_analog_engine_v1.py',
                 'historical_market_reaction_v1.py','decision_intelligence_v2.py','system_health_monitor_v1.py']:
        command(work,name)
    command(work,'scripts/rebuild_publication_manifest.py','--public-data',pub,'--source','official-research-refresh-v2')
    command(work,'scripts/verify_publication_integrity.py','--public-data',pub)


def refresh(root=ROOT, modules=('economic','fed','news'), mode='audit', staging=None, fed_stage=None, news_stage=None, economic_audit=None):
    root=Path(root).resolve()
    staging=Path(staging or root/'official_refresh_staging').resolve()
    if staging==root or root/'public_data' in staging.parents or staging==root/'public_data':
        raise ValueError('Staging must be separate from the repository and public_data')
    staging.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='us500-refresh-'))
    try:
        shutil.copytree(root,work,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache','official_refresh_staging','ingestion_history','.git'))
        pub=work/'public_data'
        if 'economic' in modules:
            command(work,'economic_official_ingestion_v1.py','--mode','merge' if mode=='publish' else 'audit','--staging',staging/'economic')
            if mode=='publish':
                command(work,'economic_canonical_input_v2.py','--workspace')
                command(work,'economic_surprise_engine_v1.1.py')
                command(work,'economic_regime_classifier_v1.5.py')
                command(work,'economic_official_ingestion_v1.py','--mode','gate','--staging',staging/'economic')
                for name in ECONOMIC_FILES:shutil.copy2(work/name,pub/name)
        if 'fed' in modules:
            reuse_fed = fed_stage is not None
            fed_stage=Path(fed_stage) if reuse_fed else staging/'fed'
            if not reuse_fed:
                command(work,'fed_intelligence_export_v1.py','--output',fed_stage/'fed_intelligence_output_v1.json')
            validate_fed(fed_stage)
            shutil.copy2(fed_stage/'fed_intelligence_output_v1.json',pub/'fed_intelligence_output_v1.json')
        if 'news' in modules:
            reuse_news = news_stage is not None
            news_stage=Path(news_stage) if reuse_news else staging/'news'
            if not reuse_news:
                command(work,'tests/event_news/event_news_intelligence_v1.py','--output',news_stage)
            validate_news(news_stage)
            for name in NEWS_FILES:shutil.copy2(news_stage/name,pub/name)
        if economic_audit and 'economic' not in modules:
            # A failed Economic audit updates diagnostics and eligibility only,
            # without merging any unvalidated economic observation.
            audit=json.loads(Path(economic_audit).read_text())
            status={'as_of_date':audit['retrieved_at'][:10],'retrieved_at':audit['retrieved_at'],
                    'source_verification':'VERIFIED' if audit['passed'] else 'SOURCE_ERROR',
                    'indicators':audit['reports']}
            (pub/'economic_ingestion_status_v1.json').write_text(json.dumps(status,indent=2)+'\n')
        if mode=='audit':
            return {'status':'VALIDATED_STAGING','published':False}
        rebuild(work)
        shutil.copytree(pub,staging/'validated_public_data',dirs_exist_ok=True)
        install_validated(root/'public_data',pub,root/'ingestion_history')
        result={'status':'PASS','published':True,'modules':list(modules),'research_only':True,'trading_signal':False}
        (staging/'refresh_result.json').write_text(json.dumps(result,indent=2)+'\n')
        return result
    finally:
        shutil.rmtree(work)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['audit','publish'],default='audit')
    parser.add_argument('--modules',default='economic,fed,news')
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--staging',type=Path)
    parser.add_argument('--fed-stage',type=Path)
    parser.add_argument('--news-stage',type=Path)
    parser.add_argument('--economic-audit',type=Path)
    args=parser.parse_args()
    modules=args.modules.split(',')
    if set(modules)-{'economic','fed','news'} or not modules:
        parser.error('Modules: economic,fed,news')
    print(json.dumps(refresh(args.root,modules,args.mode,args.staging,args.fed_stage,args.news_stage,args.economic_audit),indent=2))


if __name__=='__main__':main()
