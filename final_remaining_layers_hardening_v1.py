from pathlib import Path
import json
import pandas as pd
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parent
P=ROOT/'public_data'
now=datetime.now(timezone.utc).isoformat()

# 1. Event/News: deterministic research classification; remains contextual only.
ev=pd.read_csv(P/'event_news_research_v2.csv')
titles=ev['title'].fillna('').str.lower()
def event_class(t):
    if any(k in t for k in ['consumer price','producer price','employment situation','retail sales','gross domestic product','personal income','pce','ism','job openings']): return 'MACRO_RELEASE'
    if any(k in t for k in ['fomc','federal open market','monetary policy','beige book','minutes of the']): return 'POLICY_EVENT'
    if any(k in t for k in ['approval of application','enforcement action','termination of enforcement','consent order']): return 'ADMINISTRATIVE'
    return 'OTHER_OFFICIAL'
ev['event_class']=[event_class(t) for t in titles]
# Event identity must not collapse recurring official releases that reuse a title.
# Prefer canonical URL; fall back to source + exact publication timestamp + normalized title.
urls=ev.get('url',pd.Series('',index=ev.index)).fillna('').astype(str).str.strip().str.lower()
pubts=ev.get('published_at',pd.Series('',index=ev.index)).fillna('').astype(str).str.strip()
normalized_titles=titles.str.replace(r'\s+',' ',regex=True).str.strip()
fallback=ev['source'].fillna('').astype(str).str.lower().str.strip()+'|'+pubts+'|'+normalized_titles
ev['dedup_key']=urls.where(urls.ne(''),fallback)
ev['is_duplicate']=ev.duplicated('dedup_key',keep='first')
rel=pd.to_numeric(ev.get('topic_relevance_title'),errors='coerce').fillna(0)
ev['research_relevance']='LOW'
ev.loc[(ev['event_class'].isin(['MACRO_RELEASE','POLICY_EVENT'])) | (rel>=0.5),'research_relevance']='HIGH'
ev.loc[(ev['research_relevance']=='LOW') & ((rel>=0.25) | (ev['topic'].isin(['inflation','labor','growth','fed']))),'research_relevance']='MEDIUM'
ev['importance_rule']='title/topic heuristic; contextual only'
ev.to_csv(P/'event_news_research_v2.csv',index=False)
summary=json.loads((P/'event_news_research_summary_v2.json').read_text())
summary.update({
 'hardening_version':'final-remaining-layers-hardening-v1',
 'structured_evidence':True,
 'event_class_counts':ev['event_class'].value_counts().to_dict(),
 'research_relevance_counts':ev['research_relevance'].value_counts().to_dict(),
 'duplicate_rows':int(ev['is_duplicate'].sum()),
 'decision_role':'CONTEXTUAL',
 'included_in_decision_state':False,
 'interpretation':'Rule-based relevance and event class are research metadata only; no sentiment, forecast, or trading score is inferred.'
})
(P/'event_news_research_summary_v2.json').write_text(json.dumps(summary,indent=2))

# 2. Earnings coverage/quality summary. Post-event reactions remain contextual and excluded from contemporaneous state.
ea=pd.read_csv(P/'earnings_market_reaction_v3.csv')
rd=pd.to_datetime(ea.get('reported_date'),errors='coerce')
quality={
 'module':'Corporate Earnings Intelligence','version':'3.1-hardening','generated_at':now,
 'rows':int(len(ea)),'ticker_count':int(ea['ticker'].nunique()) if 'ticker' in ea else 0,
 'date_start':rd.min().date().isoformat() if rd.notna().any() else None,
 'date_end':rd.max().date().isoformat() if rd.notna().any() else None,
 'pit_safe_event_rows':int(ea.get('point_in_time_safe',pd.Series(dtype=bool)).astype(str).str.lower().eq('true').sum()),
 'reaction_rows':int(ea.get('market_reaction_available',pd.Series(dtype=bool)).astype(str).str.lower().eq('true').sum()),
 'quality_gate_counts':ea.get('quality_gate',pd.Series(dtype=str)).fillna('MISSING').value_counts().to_dict(),
 'decision_role_counts':ea.get('decision_role',pd.Series(dtype=str)).fillna('MISSING').value_counts().to_dict(),
 'decision_role':'CONTEXTUAL','included_in_decision_state':False,'research_only':True,
 'pit_limitation':'Event facts can be PIT-safe; post-event reaction fields are only knowable after their stated horizon has elapsed and are not contemporaneous decision inputs.'
}
(P/'earnings_quality_summary_v3.json').write_text(json.dumps(quality,indent=2))

# 3. Event-study reliability is explicit per definition.
ad=pd.read_csv(P/'historical_event_study_sample_adequacy_v2.csv')
n=pd.to_numeric(ad['event_observations'],errors='coerce').fillna(0)
def tier(x):
    if x < 5: return 'INSUFFICIENT'
    if x < 10: return 'LIMITED'
    if x < 25: return 'MODERATE'
    return 'ADEQUATE'
ad['reliability_tier']=[tier(x) for x in n]
ad['eligible_for_descriptive_summary']=n>=10
ad['eligible_for_inference']=False
ad['interpretation']='descriptive association only; not causal or predictive'
ad.to_csv(P/'historical_event_study_sample_adequacy_v2.csv',index=False)

# 4. Unified evidence registry. Contextual layers are visible but cannot alter Decision Engine V1 state.
core=pd.read_csv(P/'decision_engine_research_evidence_v1.csv')
core['quality_gate']='ELIGIBLE'; core['decision_role']='CORE'; core['included_in_state']=True; core['pit_status']='FROM_RESEARCH_CONTEXT'
rows=[]
rows.append({'source':'Event / News','category':'event_news','stance':'CONTEXTUAL','reason':f"{len(ev)} official items; {int((ev['research_relevance']=='HIGH').sum())} high-relevance; {int(ev['is_duplicate'].sum())} duplicates flagged.",'value':summary.get('coverage_level','—'),'quality_gate':'ELIGIBLE','decision_role':'CONTEXTUAL','included_in_state':False,'pit_status':'PIT_SAFE_BY_PUBLICATION_TIME'})
rows.append({'source':'Corporate Earnings','category':'earnings','stance':'CONTEXTUAL','reason':f"{len(ea)} historical earnings events; post-event reactions are horizon-dependent and excluded from contemporaneous state.",'value':quality['date_end'],'quality_gate':'DEGRADED','decision_role':'CONTEXTUAL','included_in_state':False,'pit_status':'PIT_LIMITED'})
# Fed Intelligence is surfaced as the independently published current research layer.
# It is deliberately CONTEXTUAL here: Research Context already carries legacy Fed fields,
# so promoting this artifact into V1 state would risk double counting and change semantics.
fed_path=P/'fed_intelligence_output_v1.json'
if fed_path.exists():
    fed=json.loads(fed_path.read_text())
    fq=fed.get('quality') if isinstance(fed.get('quality'),dict) else {}
    fs=fed.get('fed_score') if isinstance(fed.get('fed_score'),dict) else {}
    rows.append({
        'source':'Fed Intelligence (current)',
        'category':'fed',
        'stance':'CONTEXTUAL',
        'reason':f"Independent Fed artifact as of {fed.get('as_of_date','—')}; {fq.get('quality_reason','quality reason unavailable')}. Excluded from V1 state to prevent double counting legacy Research Context Fed fields.",
        'value':fs.get('score'),
        'quality_gate':fq.get('quality_gate','DEGRADED'),
        'decision_role':'CONTEXTUAL',
        'included_in_state':False,
        'pit_status':fq.get('pit_status','UNKNOWN'),
    })
reg=pd.concat([core,pd.DataFrame(rows)],ignore_index=True)
reg.to_csv(P/'decision_engine_evidence_registry_v2.csv',index=False)

# 5. Hardening validation artifact.
checks=[
 ('event_news_structured', all(c in ev for c in ['event_class','research_relevance','is_duplicate'])),
 ('event_news_contextual', (ev['decision_role'].astype(str).str.upper()=='CONTEXTUAL').all()),
 ('earnings_contextual', (ea['decision_role'].astype(str).str.upper()=='CONTEXTUAL').all()),
 ('event_study_reliability', 'reliability_tier' in ad),
 ('decision_registry_has_context', {'Event / News','Corporate Earnings','Fed Intelligence (current)'}.issubset(set(reg['source']))),
 ('context_excluded_from_state', (~reg.loc[reg['decision_role']=='CONTEXTUAL','included_in_state'].astype(bool)).all()),
]
out={'validator':'Final Remaining-Layers Hardening v1','generated_at':now,'status':'PASS' if all(v for _,v in checks) else 'FAIL','checks':[{'check':k,'pass':bool(v)} for k,v in checks],'research_only':True,'decision_semantics_changed':False}
(P/'final_remaining_layers_hardening_v1.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
