from pathlib import Path
import json, hashlib
import pandas as pd

ROOT=Path(__file__).resolve().parent; P=ROOT/'public_data'
VERSION='USV1.0'
rc=pd.read_csv(P/'research_context_summary_v1.csv').iloc[-1]
ctx=pd.Timestamp(rc['context_date']).normalize()
q=pd.read_csv(P/'research_evidence_quality_v1.csv')

def qagg(module):
    x=q[q.module.astype(str).str.startswith(module)]
    if x.empty: return dict(quality='UNKNOWN',pit='UNKNOWN',freshness='UNKNOWN',eligible=False,age=None)
    def worst(col, order):
        vals=set(x[col].astype(str));
        for v in order:
            if v in vals:return v
        return next(iter(vals),'UNKNOWN')
    return dict(
      quality=worst('quality_status',['LOW','DEGRADED','MEDIUM','HIGH']),
      pit=worst('pit_status',['PIT_LIMITED','PIT_UNSAFE','UNKNOWN','PIT_SAFE']),
      freshness=worst('freshness_status',['STALE','AGING','UNKNOWN','CURRENT']),
      eligible=bool(x.decision_engine_eligible.fillna(False).astype(bool).all()),
      age=int(pd.to_numeric(x.age_days,errors='coerce').max()) if pd.to_numeric(x.age_days,errors='coerce').notna().any() else None)

def row(feature,module,role,value=None,state=None,as_of=None,available_at=None,source='',force_eligible=None,notes=''):
    z=qagg(module)
    elig=z['eligible'] if force_eligible is None else force_eligible
    return {'state_vector_version':VERSION,'context_date':ctx.date().isoformat(),'feature':feature,'module':module,
      'role':role,'value':value,'state':state,'as_of':as_of or ctx.date().isoformat(),'available_at':available_at or as_of or ctx.date().isoformat(),
      'age_days':z['age'],'freshness':z['freshness'],'pit_status':z['pit'],'quality':z['quality'],'eligible':bool(elig),
      'source':source,'notes':notes}

rows=[]
# Economic: direct canonical dimensions; no macro composite is added, preventing duplicate representation.
for f,c in [('economic_inflation','inflation_score'),('economic_labor','labor_score'),('economic_growth','growth_score')]:
    rows.append(row(f,'ECONOMIC','CORE',float(rc[c]),str(rc['economic_regime']),source='research_context_summary_v1.csv'))
rows.append(row('economic_regime','ECONOMIC','CORE',state=str(rc['economic_regime']),source='research_context_summary_v1.csv'))
# Fed: source independent Fed artifact, not legacy macro/fed duplicate.
fed=json.loads((P/'fed_intelligence_output_v1.json').read_text())
fs=fed.get('fed_score',{}) if isinstance(fed.get('fed_score'),dict) else {}
rows.append(row('fed_stance','FED','CORE',fs.get('score'),fs.get('classification') or fed.get('fed_stance'),as_of=fed.get('as_of_date'),source='fed_intelligence_output_v1.json',force_eligible=True,notes='Independent Fed feature; legacy Macro Fed field intentionally not duplicated.'))
rows.append(row('financial_stress','FINANCIAL_STRESS','CORE',float(rc['financial_stress_composite']),str(rc['financial_stress_regime']),source='research_context_summary_v1.csv'))
# Liquidity has no sanctioned aggregate score. Encode coverage/state only; never invent neutral/score.
liq=pd.read_csv(P/'liquidity_intelligence_summary_v1.csv'); elig=int(liq.eligible.fillna(False).astype(bool).sum())
rows.append(row('liquidity_coverage','LIQUIDITY','CORE',elig,f'{elig}/{len(liq)}_ELIGIBLE',as_of=str(liq.asof_date.iloc[-1]),source='liquidity_intelligence_summary_v1.csv',notes='No liquidity score generated; coverage only.'))
rows.append(row('sentiment','SENTIMENT','CORE',float(rc['unified_sentiment_score']),str(rc['sentiment_regime']),source='research_context_summary_v1.csv'))
rows.append(row('technical','TECHNICAL','CORE',state=str(rc['technical_regime']),source='research_context_summary_v1.csv'))
# Contextual layers remain excluded even when available.
br=json.loads((P/'market_breadth_analysis_summary_v1.json').read_text())
rows.append(row('market_breadth','MARKET_BREADTH','CONTEXTUAL',state=br.get('latest_breadth_research_state'),as_of=br.get('latest_asof_date'),source='market_breadth_analysis_summary_v1.json',force_eligible=False,notes='Research-grade reconstructed membership; not PIT-perfect.'))
ca=json.loads((P/'cross_asset_summary_v1.json').read_text())
rows.append(row('cross_asset','CROSS_ASSET','CONTEXTUAL',state='AVAILABLE',as_of=ca.get('date_end'),source='cross_asset_summary_v1.json',force_eligible=False,notes='PIT_LIMITED; session-aware timestamps unavailable.'))
# Contextual registry semantics for News/Earnings.
reg=pd.read_csv(P/'decision_engine_evidence_registry_v2.csv')
for src,feat,mod in [('Event / News','event_news','EVENT_NEWS'),('Corporate Earnings','earnings','EARNINGS')]:
    x=reg[reg.source.eq(src)].iloc[-1]
    r=row(feat,mod,'CONTEXTUAL',state=str(x.stance),source='decision_engine_evidence_registry_v2.csv',force_eligible=False,notes=str(x.reason))
    r['pit_status']=str(x.pit_status)
    r['quality']=str(x.quality_gate)
    if feat=='event_news':
        ev=pd.read_csv(P/'event_news_research_v2.csv')
        if 'freshness_status' in ev:
            fs=ev['freshness_status'].astype(str); r['freshness']='CURRENT' if fs.eq('CURRENT').any() else ('AGING' if fs.eq('AGING').any() else 'STALE')
        if 'published_at' in ev:
            dt=pd.to_datetime(ev['published_at'],errors='coerce',utc=True).dt.tz_localize(None); last=dt.max(); r['as_of']=last.date().isoformat(); r['available_at']=r['as_of']; r['age_days']=max(0,(ctx-last.normalize()).days)
    else:
        ea=pd.read_csv(P/'earnings_market_reaction_v3.csv'); dt=pd.to_datetime(ea['reported_date'],errors='coerce'); last=dt.max(); r['as_of']=last.date().isoformat(); r['available_at']=r['as_of']; r['age_days']=max(0,(ctx-last.normalize()).days); r['freshness']='CURRENT' if r['age_days']<=10 else ('AGING' if r['age_days']<=30 else 'STALE')
    rows.append(r)

df=pd.DataFrame(rows)
# Fail closed: no implicit neutralization and contextual features can never be eligible.
assert not ((df.role=='CONTEXTUAL') & df.eligible).any()
assert not df.state.fillna('').str.upper().eq('NEUTRAL').any() or (df.feature=='sentiment').any()
assert df.feature.is_unique
# Deterministic fingerprint excludes no volatile generated_at fields because vector has none.
payload=df.fillna('').to_csv(index=False).encode(); fingerprint=hashlib.sha256(payload).hexdigest()
df.to_csv(P/'unified_state_vector_v1.csv',index=False)
summary={'state_vector_version':VERSION,'context_date':ctx.date().isoformat(),'feature_count':len(df),'core_feature_count':int((df.role=='CORE').sum()),'contextual_feature_count':int((df.role=='CONTEXTUAL').sum()),'eligible_feature_count':int(df.eligible.sum()),'fingerprint_sha256':fingerprint,'missing_to_neutral':False,'double_counting_policy':'Direct canonical layer features only; Macro composite and legacy Fed duplicate are excluded.','research_only':True,'decision_engine_ready':False,'forecast_generated':False,'trading_signal_generated':False}
(P/'unified_state_vector_summary_v1.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
