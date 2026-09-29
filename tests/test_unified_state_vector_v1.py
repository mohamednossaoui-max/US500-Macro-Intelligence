from pathlib import Path
import json, subprocess, sys, hashlib
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; P=ROOT/'public_data'

def run(): subprocess.run([sys.executable,str(ROOT/'unified_state_vector_v1.py')],cwd=ROOT,check=True,capture_output=True,text=True)
def test_schema_and_unique_features():
 run(); d=pd.read_csv(P/'unified_state_vector_v1.csv'); req={'state_vector_version','context_date','feature','module','role','value','state','as_of','available_at','age_days','freshness','pit_status','quality','eligible','source'}; assert req<=set(d); assert d.feature.is_unique

def test_contextual_never_eligible_and_limits_preserved():
 run(); d=pd.read_csv(P/'unified_state_vector_v1.csv'); assert not d.loc[d.role.eq('CONTEXTUAL'),'eligible'].any(); assert d.loc[d.feature.eq('market_breadth'),'pit_status'].iloc[0]=='PIT_LIMITED'; assert d.loc[d.feature.eq('cross_asset'),'pit_status'].iloc[0]=='PIT_LIMITED'

def test_no_missing_to_neutral_and_no_macro_duplicate():
 run(); d=pd.read_csv(P/'unified_state_vector_v1.csv'); s=json.loads((P/'unified_state_vector_summary_v1.json').read_text()); assert s['missing_to_neutral'] is False; assert not d.feature.str.contains('macro_composite',case=False).any(); assert d.feature.eq('fed_stance').sum()==1

def test_liquidity_does_not_invent_score():
 run(); d=pd.read_csv(P/'unified_state_vector_v1.csv'); x=d[d.feature.eq('liquidity_coverage')].iloc[0]; assert 'ELIGIBLE' in x['state']; assert 'score' not in x['feature'].lower()

def test_deterministic_fingerprint():
 run(); a=json.loads((P/'unified_state_vector_summary_v1.json').read_text())['fingerprint_sha256']; run(); b=json.loads((P/'unified_state_vector_summary_v1.json').read_text())['fingerprint_sha256']; assert a==b
