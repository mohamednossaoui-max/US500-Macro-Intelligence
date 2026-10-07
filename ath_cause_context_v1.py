"""Evidence-based risk candidates; rule labels are never causal proof or probabilities."""
from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse
import numpy as np
import pandas as pd
from scripts.verify_publication_integrity import run as verify

VERSION='ATH_CAUSE_CONTEXT_V1'
REQUIRED=('technical_intelligence_research_v1.csv','event_news_research_v2.csv','unified_state_vector_v1.csv')
FEATURES=('economic_inflation','economic_labor','economic_growth','fed_stance','financial_stress')
AGE={'economic_inflation':45,'economic_labor':45,'economic_growth':45,'fed_stance':45,'financial_stress':14}
RULES={
 'VALUATION_PROFIT_TAKING':('جني أرباح / ضغط تقييمات',r'profit[- ]taking|overvalued|stretched valuations|valuation concerns'),
 'INFLATION_RATE_PRESSURE':('تضخم / تشديد نقدي',r'inflation (?:rises|surges|accelerates)|hotter.than.expected inflation|rate hike|raises? (?:interest )?rates|hawkish'),
 'GROWTH_SLOWDOWN':('تباطؤ اقتصادي',r'recession|growth slowdown|slowing (?:economy|growth)|unemployment rises|weak jobs|job losses'),
 'EARNINGS_PRESSURE':('ضغط الأرباح',r'profit warning|cuts? (?:its )?(?:earnings|profit|revenue) (?:forecast|outlook)|earnings miss|profits? (?:fall|drop|decline)'),
 'TRADE_POLICY_SHOCK':('رسوم / قيود تجارية',r'tariff|trade war|export restrictions|export ban'),
 'CREDIT_FINANCIAL_STRESS':('ضغط ائتمان / بنوك',r'bank failure|bank run|credit crunch|credit spreads widen|default risk|funding stress'),
 'FORCED_DELEVERAGING':('بيع اضطراري / تصفية رافعة',r'margin calls?|forced selling|deleveraging|carry.trade unwinding|unwinding.*carry.trade'),
 'SUPPLY_GEOPOLITICAL_SHOCK':('صدمة إمدادات / حرب / تعطّل',r'invasion|war outbreak|supply disruption|oil (?:surges|spikes)|pandemic|economic shutdown')}
NEGATION=re.compile(r'\b(no|not|unlikely|easing|receding|averted|avoided|denies|denied)\b',re.I)


def utc(x):
    t=pd.to_datetime(x,utc=True,errors='coerce')
    if pd.isna(t):raise ValueError('Invalid timestamp.')
    return t


def now_utc():return pd.Timestamp.now(tz='UTC')
def truth(x):return str(x).lower() in {'true','1','1.0'}
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(x):return hashlib.sha256(x).hexdigest()


def publication(root):
    r=verify(Path(root))
    if r['errors'] or len(r['manifests'])!=1:raise ValueError('Publication Integrity failed.')
    m=r['manifests'][0]
    if any(m['summary'][k] for k in ('mismatch','missing','error')):raise ValueError('Publication Integrity failed.')
    matched={x['file'] for x in m['results'] if x['status']=='MATCH'}
    if not set(REQUIRED)<=matched:raise ValueError('Cause inputs must be manifest verified.')
    return m['summary']


def select_features(vector,cutoff):
    if 'feature' not in vector or vector.feature.duplicated().any():raise ValueError('Unique vector features required.')
    values={};evidence=[];excluded=[]
    for name in FEATURES:
        rows=vector[vector.feature==name]
        if rows.empty:excluded.append({'feature':name,'reason':'MISSING'});continue
        r=rows.iloc[0].to_dict()
        try:
            available=utc(r.get('available_at'));asof=utc(r.get('as_of'))
            age=max(float(r.get('age_days')),float((cutoff-asof).total_seconds()/86400))
            value=float(r.get('value'))
            if not np.isfinite(value) or not np.isfinite(age):raise ValueError('Nonfinite')
            if available>cutoff or asof>cutoff:reason='FUTURE'
            elif not truth(r.get('eligible')) or r.get('pit_status')!='PIT_SAFE':reason='PIT_INELIGIBLE'
            elif r.get('freshness')!='CURRENT' or age>AGE[name]:reason='STALE'
            elif r.get('quality') not in ('MEDIUM','HIGH'):reason='QUALITY_INELIGIBLE'
            else:reason=None
        except (TypeError,ValueError):reason='METADATA_UNVERIFIED'
        if reason:excluded.append({'feature':name,'reason':reason});continue
        values[name]=value
        evidence.append({'feature':name,'value':value,'state':str(r.get('state')),
                         'available_at':available.isoformat(),'as_of':asof.isoformat(),
                         'source':str(r.get('source')),'verification':'PROGRAMME_PIT_PROXY_NOT_AGENCY_CERTIFICATION'})
    return values,evidence,excluded


def news_candidates(news,cutoff):
    required={'published_at','availability_date','title','url','source','point_in_time_safe','pit_status','event_class','is_duplicate'}
    if not required<=set(news):raise ValueError('News provenance columns required.')
    result={key:[] for key in RULES};excluded=[];seen=set()
    for _,r in news.iterrows():
        url=str(r.url);title=str(r.title)
        try:
            published=utc(r.published_at);available=utc(r.availability_date)
            if available<published:reason='AVAILABILITY_BEFORE_PUBLICATION'
            elif published>cutoff or available>cutoff:reason='FUTURE'
            elif cutoff-available>pd.Timedelta(days=7):reason='STALE'
            elif not truth(r.point_in_time_safe) or r.pit_status not in ('PIT_SAFE','PIT_SAFE_BY_PUBLICATION_TIME'):reason='PIT_INELIGIBLE'
            elif 'quality_gate' in news and str(r.quality_gate)!='ELIGIBLE':reason='QUALITY_INELIGIBLE'
            elif str(r.event_class)=='ADMINISTRATIVE':reason='ADMINISTRATIVE'
            elif truth(r.is_duplicate) or url in seen:reason='DUPLICATE'
            elif urlparse(url).scheme!='https' or not urlparse(url).netloc:reason='SOURCE_URL_UNVERIFIED'
            else:reason=None
        except (ValueError,TypeError):reason='METADATA_UNVERIFIED'
        if reason:excluded.append({'url':url,'reason':reason});continue
        seen.add(url)
        # Conservative: a negated/easing headline never asserts an adverse event.
        if NEGATION.search(title):excluded.append({'url':url,'reason':'NEGATION_OR_EASING_REQUIRES_REVIEW'});continue
        for key,(_,pattern) in RULES.items():
            if re.search(pattern,title,re.I):
                result[key].append({'title':title,'url':url,'source':str(r.source),
                                    'published_at':published.isoformat(),'available_at':available.isoformat(),
                                    'verification':'TITLE_CANDIDATE_REQUIRES_CONTEXT_REVIEW'})
    return result,excluded


def price_context(frame,cutoff):
    # Published-price validation must not import research/acquisition dependencies.
    required={'observation_date','availability_date','Open','High','Low','Close'}
    if not required<=set(frame):raise ValueError('Explicit daily OHLC and availability required.')
    d=frame.copy()
    d['date']=pd.to_datetime(d.observation_date,utc=True,errors='coerce').dt.normalize()
    d['available']=pd.to_datetime(d.availability_date,utc=True,errors='coerce')
    if d.date.isna().any() or d.date.duplicated().any() or d.available.isna().any():raise ValueError('Invalid/duplicate dates.')
    if (d.available!=d.date+pd.Timedelta(days=1)).any():raise ValueError('Invalid availability proxy.')
    for name in ('Open','High','Low','Close'):
        d[name]=pd.to_numeric(d[name],errors='coerce')
        if not np.isfinite(d[name]).all() or (d[name]<=0).any():raise ValueError('Missing/nonpositive OHLC; no price fabrication.')
    if (d.High<d[['Open','Close','Low']].max(axis=1)).any() or (d.Low>d[['Open','Close','High']].min(axis=1)).any():
        raise ValueError('Inconsistent OHLC ranges.')
    d=d.sort_values('date');d=d[d.available<=cutoff].reset_index(drop=True)
    if d.empty:raise ValueError('No price observation available at cutoff.')
    last=d.iloc[-1];peak=float(d.High.max());past=d.Close
    return {'instrument':str(last.symbol) if 'symbol' in d else 'UNVERIFIED_INSTRUMENT',
            'last_session':last.observation_date,'available_at':last.available.isoformat(),
            'price_status':'STALE' if cutoff-last.available>pd.Timedelta(days=3) else 'AVAILABLE_SESSION_PROXY',
            'reference_peak':peak,'peak_scope':'HIGHEST_HIGH_IN_AVAILABLE_FILE_NOT_CERTIFIED_LIFETIME_ATH',
            'drawdown_at_close_pct':float(max(0,100*(1-float(last.Close)/peak))),
            'return20_pct':float(100*(past.iloc[-1]/past.iloc[-21]-1)) if len(past)>20 else None,
            'vol20_daily_pct':float(past.pct_change().tail(20).std()*100) if len(past)>20 else None,
            'response':'PRICE_PRESSURE_OBSERVED' if len(past)>20 and past.iloc[-1]<past.iloc[-21] else 'NO_20_SESSION_DECLINE_CONFIRMED'}


def assess(root,as_of=None):
    root=Path(root);cutoff=now_utc() if as_of is None else utc(as_of)
    if cutoff>now_utc():raise ValueError('Future assessment forbidden.')
    integrity=publication(root)
    values,features,excluded_features=select_features(pd.read_csv(root/REQUIRED[2]),cutoff)
    candidates,excluded_news=news_candidates(pd.read_csv(root/REQUIRED[1]),cutoff)
    price=price_context(pd.read_csv(root/REQUIRED[0]),cutoff)
    # These are disclosed evidence flags in native programme scales, not trained risk probabilities.
    flags={
      'INFLATION_RATE_PRESSURE':[x for x in features if (x['feature']=='economic_inflation' and x['value']>=.5) or
                                (x['feature']=='fed_stance' and x['state'].replace(' ','_') in ('HAWKISH','MODERATELY_HAWKISH','VERY_HAWKISH'))],
      'GROWTH_SLOWDOWN':[x for x in features if x['feature'] in ('economic_labor','economic_growth') and x['value']<=-.5],
      'CREDIT_FINANCIAL_STRESS':[x for x in features if x['feature']=='financial_stress' and x['value']>=1.]}
    causes=[]
    for key,(name,_) in RULES.items():
        support=flags.get(key,[]);items=candidates[key]
        state=('CORROBORATED_RISK_CANDIDATE' if support and items else 'CONTEXT_RISK_FLAG' if support
               else 'NEWS_CANDIDATE' if items else 'UNVERIFIED')
        causes.append({'cause':key,'label':name,'status':state,'news_evidence':items,
                       'context_evidence':support,'causal_attribution':'NOT_PROVEN',
                       'impact_evidence':'CONTEXT_SUPPORTED' if support else 'NEWS_ONLY' if items else 'INSUFFICIENT',
                       'confidence':'UNCALIBRATED_RULE_LABEL_NOT_PROBABILITY'})
    return {'version':VERSION,'as_of':cutoff.isoformat(),'research_only':True,'publication_integrity':integrity,
            'source_sha256':{n:digest((root/n).read_bytes()) for n in REQUIRED},
            'causes':causes,'context_features':values,'feature_evidence':features,
            'excluded_features':excluded_features,'excluded_news':excluded_news,'observed_market_response':price,
            'impact_assessment':{'scope':'INSUFFICIENT_VERIFIED_BREADTH_AND_EARNINGS',
                                 'persistence':'NEEDS_MULTIPLE_GENUINE_SNAPSHOTS','causal_effect_size':None},
            'probability_status':'NOT_VALIDATED','depth_probabilities':None,
            'limitations':['Headlines detect candidates, not facts, causal magnitude or calibrated likelihood.',
                           'Absence of eligible news is UNVERIFIED, never proof that risk is absent.',
                           'English title rules use the existing programme feeds; global news coverage is incomplete.',
                           'Programme scores and date proxies are not agency-vintage certification.',
                           'Inflation/labor/growth are directional surprise scores, not inflation level or recession probability.',
                           'No direct mapping from cause or score to drawdown percentage.',
                           'Cash-index data cannot stand in for separate ES or broker US500 histories.']}


def load(archive):
    rows=[]
    for p in sorted(Path(archive).glob('snapshots/*.json')):
        r=json.loads(p.read_text());checksum=r.pop('record_sha256',None)
        if checksum!=digest(canonical(r)) or r.get('version')!=VERSION:raise ValueError('Cause archive checksum/version mismatch.')
        if r['snapshot_id']!=digest(canonical(r['payload'])) or p.stem!=r['snapshot_id']:raise ValueError('Cause archive payload mismatch.')
        if utc(r['available_at'])!=utc(r['recorded_at']) or utc(r['payload']['as_of'])>utc(r['recorded_at']) or utc(r['recorded_at'])>now_utc():raise ValueError('Backdated/future archive capture.')
        r['record_sha256']=checksum;rows.append(r)
    return sorted(rows,key=lambda r:(r['available_at'],r['snapshot_id']))


def capture(report,archive):
    destination=Path(archive).resolve()
    if 'public_data' in destination.parts:raise ValueError('Archive must be outside public_data.')
    now=now_utc()
    if utc(report['as_of'])>now:raise ValueError('Future capture forbidden.')
    # Identity is based on source bytes and eligible evidence, not page-render time.
    payload={k:report[k] for k in ('source_sha256','context_features','feature_evidence','causes','observed_market_response')}
    times=[x['available_at'] for x in report['feature_evidence']]+[report['observed_market_response']['available_at']]
    times.extend(x['available_at'] for cause in report['causes'] for x in cause['news_evidence'])
    payload['as_of']=max(map(utc,times)).isoformat()
    identity=digest(canonical(payload));previous=load(destination)
    if any(r['snapshot_id']==identity for r in previous):return {'status':'UNCHANGED','snapshot_id':identity,'snapshot_count':len(previous)}
    rec={'version':VERSION,'snapshot_id':identity,'recorded_at':now.isoformat(),'available_at':now.isoformat(),'payload':payload}
    rec['record_sha256']=digest(canonical(rec));directory=destination/'snapshots';directory.mkdir(parents=True,exist_ok=True)
    tmp=directory/f'.{identity}.{os.getpid()}.tmp';tmp.write_bytes(canonical(rec))
    try:os.link(tmp,directory/f'{identity}.json')
    finally:tmp.unlink(missing_ok=True)
    return {'status':'CAPTURED','snapshot_id':identity,'snapshot_count':len(previous)+1}
