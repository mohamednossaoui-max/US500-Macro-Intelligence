import json
from pathlib import Path
import autonomy_dependency_planner_v1 as p
ROOT=Path(__file__).resolve().parents[1]
REG=ROOT/'autonomy_source_registry_v1.json'

def test_registry_contract_and_manual_mode():
    r=p.load_registry(REG)
    assert r['registry_version']=='ASR1.0'
    assert r['policy']['schedules_enabled'] is False
    assert r['policy']['manual_mode_preserved'] is True
    assert r['policy']['atomic_publication_required'] is True
    assert r['policy']['last_known_good_required'] is True

def test_all_declared_workflows_exist():
    r=p.load_registry(REG)
    for n in r['nodes']:
        if n.get('workflow'):
            assert (ROOT/n['workflow']).is_file(), n['workflow']

def test_graph_is_acyclic_and_publication_is_last():
    r=p.load_registry(REG); order=p.topo(r['nodes'])
    assert len(order)==len(r['nodes'])
    assert order[-1]=='publication'

def test_economic_change_propagates_to_final_publication_without_unrelated_sources():
    r=p.load_registry(REG); ids=[x['id'] for x in p.dry_run(r,['economic'])]
    assert ids[0]=='economic' and ids[-1]=='publication'
    for needed in ['research_context','evidence_quality','decision_engine','usv','analogs','market_reaction','decision_intelligence']:
        assert needed in ids
    assert 'cot_historical' not in ids and 'liquidity_historical' not in ids

def test_cot_change_runs_sentiment_chain():
    r=p.load_registry(REG); ids=[x['id'] for x in p.dry_run(r,['cot_historical'])]
    assert ids.index('cot_historical') < ids.index('cot') < ids.index('sentiment') < ids.index('research_context')
    assert ids[-1]=='publication'

def test_contextual_source_never_bypasses_integration_chain():
    r=p.load_registry(REG); ids=[x['id'] for x in p.dry_run(r,['event_news'])]
    assert ids == ['event_news','research_context','evidence_quality','decision_engine','usv','analogs','market_reaction','decision_intelligence','publication']
