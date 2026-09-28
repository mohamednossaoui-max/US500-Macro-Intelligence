from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('edf2', ROOT/'economic_data_foundation_v2.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def test_expanded_universe_and_pit_contract():
    r=m.validate(ROOT/'public_data/economic_historical_events_v1.csv', ROOT/'public_data/economic_historical_quality_v1.csv')
    assert r['indicators'] >= 14
    assert r['families'] >= 11
    assert {'PCE_PRICE_INDEX','CORE_PCE'} <= set(r['counts'].index)

def test_ingestion_registry_knows_expanded_indicators():
    import sys
    sys.path.insert(0, str(ROOT))
    import economic_data_v1 as ed
    assert m.REQUIRED <= set(ed.SUPPORTED_INDICATORS)
