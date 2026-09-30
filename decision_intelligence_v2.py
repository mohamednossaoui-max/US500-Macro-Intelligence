from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parent
PD=ROOT/'public_data'
VERSION='DIV2.0'

def _load_json(name):
    return json.loads((PD/name).read_text(encoding='utf-8'))

def _fmt(x): return f'{float(x):+.2f}'

def build():
    dec=pd.read_csv(PD/'decision_engine_research_summary_v1.csv').iloc[-1]
    usv=pd.read_csv(PD/'unified_state_vector_v1.csv')
    analog=pd.read_csv(PD/'historical_analog_top_v1.csv')
    reaction=_load_json('historical_market_reaction_summary_v1.json')
    asum=_load_json('historical_analog_summary_v1.json')
    ctx=str(usv.iloc[0]['context_date'])
    def row(feature): return usv.loc[usv.feature.eq(feature)].iloc[-1]
    inf,lab,growth=row('economic_inflation'),row('economic_labor'),row('economic_growth')
    econ=row('economic_regime'); fed=row('fed_stance'); stress=row('financial_stress'); sent=row('sentiment'); tech=row('technical')
    top=analog.iloc[0]
    horizons={k:{kk:v for kk,v in val.items()} for k,val in reaction['horizons'].items()}
    current=(f"Economic regime is {econ.state}: inflation {_fmt(inf.value)}, labor {_fmt(lab.value)}, and growth {_fmt(growth.value)}. "
             f"Fed stance is {fed.state}; financial stress is {stress.state}; sentiment is {sent.state}; technical regime is {tech.state}. "
             f"Published Decision Engine state remains {dec.state}.")
    what_changed={"status":"UNAVAILABLE","reason":"No prior canonical USV1.0 snapshot is published; change is not inferred from non-canonical history."}
    hist=(f"Stage 10 selected {len(analog)} independent analog regimes without using outcomes. Closest is {top.historical_date} "
          f"with {top.similarity_pct:.2f}% similarity and {top.coverage_pct:.2f}% comparable CORE coverage.")
    h60=horizons['60d']; h120=horizons['120d']
    reaction_text=(f"Across the locked analog set, historical median US500 return was {h60['median_return_pct']:+.2f}% at 60 trading days "
                   f"({h60['positive_hit_rate_pct']:.1f}% positive) and {h120['median_return_pct']:+.2f}% at 120 trading days "
                   f"({h120['positive_hit_rate_pct']:.1f}% positive). Outcomes were dispersed: 60D range {h60['min_return_pct']:+.2f}% to {h60['max_return_pct']:+.2f}%. "
                   "These are conditional historical outcomes, not expected returns or forecasts.")
    limitations=[
      f"Closest analog similarity is {top.similarity_pct:.2f}%, not a close match.",
      "Historical Fed feature is unavailable under the same PIT-safe USV1.0 definition; analog CORE coverage is reduced accordingly.",
      f"Overall evidence PIT status is {dec.overall_evidence_pit_status}; CORE PIT remains {bool(dec.core_point_in_time_safe)}.",
      "CONTEXTUAL evidence does not alter the Decision Engine state.",
      "Historical market reactions are descriptive conditional evidence and are not forecasts or trading signals."
    ]
    synthesis=(f"The current research state is {dec.state}, with a mixed economic backdrop, low research stress, neutral sentiment and bullish technicals. "
               f"The closest historical analog is only moderately similar ({top.similarity_pct:.2f}%). The locked analog set had positive median outcomes over 60D and 120D, "
               "but dispersion included negative cases and material drawdowns. This supports historical context, not a directional forecast. "
               f"Evidence quality is {dec.overall_evidence_quality} and overall PIT status is {dec.overall_evidence_pit_status}.")
    obj={
      'decision_intelligence_version':VERSION,'context_date':ctx,'decision_state':str(dec.state),
      'current_environment':current,'what_changed':what_changed,
      'evidence_quality':{'overall_quality':str(dec.overall_evidence_quality),'coverage_pct':float(dec.overall_evidence_coverage_pct),'freshness':str(dec.overall_evidence_freshness),'core_pit_safe':bool(dec.core_point_in_time_safe),'overall_pit_status':str(dec.overall_evidence_pit_status),'overall_pit_safe_pct':float(dec.overall_evidence_pit_safe_pct)},
      'historical_analogs':{'count':int(len(analog)),'closest_date':str(top.historical_date),'closest_similarity_pct':float(top.similarity_pct),'closest_coverage_pct':float(top.coverage_pct),'summary':hist,'key_differences':str(top.key_differences)},
      'historical_market_reaction':{'summary':reaction_text,'horizons':horizons,'selection_locked':bool(reaction['analog_selection_locked']),'outcomes_used_in_selection':bool(reaction['outcomes_used_in_selection'])},
      'important_differences':str(top.key_differences),'risks_and_limitations':limitations,'final_research_synthesis':synthesis,
      'research_only':True,'forecast_generated':False,'trading_signal_generated':False,'expected_return_generated':False,'execution':False,
      'source_versions':{'state_vector':str(usv.iloc[0].state_vector_version),'analog_engine':str(asum['analog_engine_version']),'reaction_engine':str(reaction['reaction_engine_version'])}
    }
    (PD/'decision_intelligence_v2.json').write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    flat={'context_date':ctx,'decision_state':dec.state,'overall_quality':dec.overall_evidence_quality,'coverage_pct':dec.overall_evidence_coverage_pct,'overall_pit_status':dec.overall_evidence_pit_status,'closest_analog_date':top.historical_date,'closest_similarity_pct':top.similarity_pct,'closest_coverage_pct':top.coverage_pct}
    for h,v in horizons.items():
      flat[f'{h}_median_return_pct']=v['median_return_pct']; flat[f'{h}_positive_hit_rate_pct']=v['positive_hit_rate_pct']; flat[f'{h}_median_max_drawdown_pct']=v['median_max_drawdown_pct']
    flat.update({'research_only':True,'forecast_generated':False,'trading_signal_generated':False})
    pd.DataFrame([flat]).to_csv(PD/'decision_intelligence_summary_v2.csv',index=False)
    return obj
if __name__=='__main__': build()
