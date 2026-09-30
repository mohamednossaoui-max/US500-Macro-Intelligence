import json, sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from decision_intelligence_v2 import build

def test_build_is_grounded_and_research_only():
    o=build(); assert o['research_only'] and not o['forecast_generated'] and not o['trading_signal_generated'] and not o['expected_return_generated']

def test_analog_selection_is_immutable():
    o=build(); a=pd.read_csv(ROOT/'public_data/historical_analog_top_v1.csv'); assert o['historical_analogs']['closest_date']==str(a.iloc[0].historical_date); assert o['historical_market_reaction']['selection_locked']; assert not o['historical_market_reaction']['outcomes_used_in_selection']

def test_reaction_numbers_equal_stage11():
    o=build(); r=json.load(open(ROOT/'public_data/historical_market_reaction_summary_v1.json')); assert o['historical_market_reaction']['horizons']==r['horizons']

def test_missing_prior_vector_is_not_invented():
    o=build(); assert o['what_changed']['status']=='UNAVAILABLE'

def test_limitations_surface_fed_and_pit():
    o=build(); t=' '.join(o['risks_and_limitations']); assert 'Historical Fed' in t and 'PIT' in t

def test_synthesis_does_not_label_historical_median_expected_return():
    o=build(); s=(o['final_research_synthesis']+' '+o['historical_market_reaction']['summary']).lower(); assert 'not a directional forecast' in s; assert 'not expected returns or forecasts' in s
