from pathlib import Path
import json, math
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent; P=ROOT/'public_data'
VERSION='HAE1.0'; VECTOR_VERSION='USV1.0'
CORE_FEATURES=['economic_inflation','economic_labor','economic_growth','economic_regime','fed_stance','financial_stress','liquidity_coverage','sentiment','technical']
HISTORICAL_FEATURES=[x for x in CORE_FEATURES if x!='fed_stance']
MIN_COMPARABLE=7; MIN_COVERAGE=MIN_COMPARABLE/len(CORE_FEATURES); DECLUSTER_DAYS=30; RECENT_EXCLUSION_DAYS=90

def _asof(left, right, ldate, rdate, cols):
    l=left.sort_values(ldate).copy(); r=right[[rdate]+cols].copy().sort_values(rdate)
    return pd.merge_asof(l,r,left_on=ldate,right_on=rdate,direction='backward')

def build_history():
    econ=pd.read_csv(P/'economic_regime_events_v1.csv')
    econ['candidate_date']=pd.to_datetime(econ.release_date)
    econ=econ[(econ.dimensions_available>=3)&econ.pit_safe.astype(bool)].copy()
    h=econ[['candidate_date','inflation_score','labor_score','growth_score','economic_regime']].rename(columns={'inflation_score':'economic_inflation','labor_score':'economic_labor','growth_score':'economic_growth'})
    stress=pd.read_csv(P/'financial_stress_research_v1.csv'); stress['stress_date']=pd.to_datetime(stress.asof_date)
    h=_asof(h,stress,'candidate_date','stress_date',['composite_stress_score','point_in_time_safe']).rename(columns={'composite_stress_score':'financial_stress','point_in_time_safe':'stress_pit'})
    liq=pd.read_csv(P/'liquidity_intelligence_research_v1.csv'); liq['liq_date']=pd.to_datetime(liq.asof_date)
    fresh=[c for c in liq.columns if c.upper().endswith('_FRESH')]; liq['liquidity_coverage']=liq[fresh].fillna(False).astype(bool).sum(axis=1)
    h=_asof(h,liq,'candidate_date','liq_date',['liquidity_coverage','point_in_time_safe']).rename(columns={'point_in_time_safe':'liq_pit'})
    rc=pd.read_csv(P/'research_context_v1.csv',low_memory=False); rc['rc_date']=pd.to_datetime(rc.context_date)
    rc=rc[['rc_date','sentiment_unified_sentiment_score','sentiment_point_in_time_safe']]
    h=_asof(h,rc,'candidate_date','rc_date',['sentiment_unified_sentiment_score','sentiment_point_in_time_safe']).rename(columns={'sentiment_unified_sentiment_score':'sentiment','sentiment_point_in_time_safe':'sentiment_pit'})
    tech=pd.read_csv(P/'technical_intelligence_research_v1.csv'); tech['tech_available']=pd.to_datetime(tech.availability_date)
    h=_asof(h,tech,'candidate_date','tech_available',['technical_regime','point_in_time_safe']).rename(columns={'technical_regime':'technical','point_in_time_safe':'technical_pit'})
    # Fail closed on source PIT. No forward lookup is used anywhere above.
    for c in ['stress_pit','liq_pit','sentiment_pit','technical_pit']:
        h.loc[~h[c].fillna(False).astype(bool), [x for x in HISTORICAL_FEATURES if x.split('_')[0] in c]] = np.nan
    return h

def target():
    d=pd.read_csv(P/'unified_state_vector_v1.csv'); assert d.state_vector_version.eq(VECTOR_VERSION).all()
    out={}
    for f in CORE_FEATURES:
        x=d[d.feature.eq(f)].iloc[-1]; out[f]=x['value'] if pd.notna(x['value']) else x['state']
    return out,pd.Timestamp(d.context_date.iloc[-1])

def similarity_table():
    h=build_history(); t,ctx=target()
    h=h[h.candidate_date <= ctx-pd.Timedelta(days=RECENT_EXCLUSION_DAYS)].copy()
    numeric=['economic_inflation','economic_labor','economic_growth','financial_stress','liquidity_coverage','sentiment']
    categorical=['economic_regime','technical']
    scales={}
    for f in numeric:
        s=pd.to_numeric(h[f],errors='coerce'); mad=(s-s.median()).abs().median()*1.4826; std=s.std()
        scales[f]=float(mad if pd.notna(mad) and mad>1e-9 else (std if pd.notna(std) and std>1e-9 else 1.0))
    rows=[]
    for _,r in h.iterrows():
        scores={}; diffs=[]
        for f in numeric:
            a=pd.to_numeric(pd.Series([r.get(f)]),errors='coerce').iloc[0]; b=pd.to_numeric(pd.Series([t.get(f)]),errors='coerce').iloc[0]
            if pd.notna(a) and pd.notna(b):
                z=abs(float(a)-float(b))/scales[f]; scores[f]=math.exp(-z); diffs.append((1-scores[f],f,float(a),float(b)))
        for f in categorical:
            a=r.get(f); b=t.get(f)
            if pd.notna(a) and pd.notna(b): scores[f]=1.0 if str(a)==str(b) else 0.0; diffs.append((1-scores[f],f,str(a),str(b)))
        comparable=len(scores); coverage=comparable/len(CORE_FEATURES)
        if comparable<MIN_COMPARABLE: continue
        sim=100*sum(scores.values())/comparable
        diffs=sorted(diffs,reverse=True)[:3]
        rows.append({'historical_date':r.candidate_date.date().isoformat(),'similarity_pct':round(sim,4),'comparable_features':comparable,'core_feature_count':len(CORE_FEATURES),'coverage_pct':round(100*coverage,2),'fed_historical_available':False,'key_differences':' | '.join(f'{f}: hist={a}, current={b}' for _,f,a,b in diffs),'state_vector_version':VECTOR_VERSION,'analog_engine_version':VERSION,'pit_safe_selection':True,'outcomes_used_in_selection':False})
    allr=pd.DataFrame(rows).sort_values(['similarity_pct','coverage_pct','historical_date'],ascending=[False,False,False]).reset_index(drop=True)
    # Temporal de-clustering after ranking: nearby dates are one regime episode, not independent analogs.
    chosen=[]
    for _,r in allr.iterrows():
        d=pd.Timestamp(r.historical_date)
        if all(abs((d-pd.Timestamp(x.historical_date)).days)>=DECLUSTER_DAYS for x in chosen): chosen.append(r)
        if len(chosen)>=10: break
    top=pd.DataFrame(chosen)
    return allr,top,ctx

def main():
    allr,top,ctx=similarity_table()
    allr.to_csv(P/'historical_analog_candidates_v1.csv',index=False); top.to_csv(P/'historical_analog_top_v1.csv',index=False)
    summary={'analog_engine_version':VERSION,'state_vector_version':VECTOR_VERSION,'context_date':ctx.date().isoformat(),'candidate_count':len(allr),'selected_analog_count':len(top),'minimum_comparable_features':MIN_COMPARABLE,'core_feature_count':len(CORE_FEATURES),'minimum_coverage_pct':round(100*MIN_COVERAGE,2),'temporal_decluster_days':DECLUSTER_DAYS,'recent_exclusion_days':RECENT_EXCLUSION_DAYS,'historical_fed_available':False,'historical_fed_policy':'Missing historical Fed feature is never imputed; similarity coverage is reduced accordingly.','missing_to_neutral':False,'outcomes_used_in_selection':False,'research_only':True,'decision_engine_ready':False,'forecast_generated':False,'trading_signal_generated':False}
    (P/'historical_analog_summary_v1.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2)); print(top[['historical_date','similarity_pct','coverage_pct','comparable_features','key_differences']].to_string(index=False))
if __name__=='__main__': main()
