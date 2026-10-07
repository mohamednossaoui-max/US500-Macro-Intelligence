"""Read-only cause evidence inside the existing ATH page; no unvalidated forecasts."""
import json
from pathlib import Path
import streamlit as st
from ath_cause_context_v1 import assess


CAUSE_LABELS={
    'VALUATION_PROFIT_TAKING':'Valuation / profit-taking pressure',
    'INFLATION_RATE_PRESSURE':'Inflation / monetary tightening',
    'GROWTH_SLOWDOWN':'Economic slowdown',
    'EARNINGS_PRESSURE':'Earnings pressure',
    'TRADE_POLICY_SHOCK':'Tariffs / trade restrictions',
    'CREDIT_FINANCIAL_STRESS':'Credit / banking stress',
    'FORCED_DELEVERAGING':'Forced selling / deleveraging',
    'SUPPLY_GEOPOLITICAL_SHOCK':'Supply / geopolitical shock'
}


def render_cause_context(root):
    st.subheader('What may be putting pressure on the market?')
    try:
        r=assess(root)
    except (OSError,ValueError,KeyError,TypeError) as e:
        st.error('Unable to verify risk evidence: '+str(e));return
    active=[x for x in r['causes'] if x['status']!='UNVERIFIED']
    st.caption('News identifies risk candidates; data may corroborate them or remain insufficient. This does not prove the cause or magnitude of a decline.')
    if not active:st.info('No supported case in the eligible evidence; this does not prove that risks are absent.')
    for c in active:
        st.write('**'+CAUSE_LABELS[c['cause']]+'** — '+c['status'])
        for x in c['news_evidence'][:3]:st.markdown('['+x['title'].replace('[','').replace(']','')+']('+x['url']+')')
        if c['context_evidence']:
            st.caption('Numerical support: '+' · '.join(f"{x['feature']}={x['value']:.3f}" for x in c['context_evidence']))
        st.caption('Evidence strength: '+c['impact_evidence']+' · Causal attribution is unproven.')
    p=r['observed_market_response']
    if p['price_status']=='STALE':st.warning('Price snapshot is stale; last session '+p['last_session']+'. No live-price reading is available.')
    st.caption('Observed response: '+p['response']+' · Last session '+p['last_session']+' · Insufficient verified evidence on the breadth and persistence of the impact.')
    st.write('**Drawdown-depth probability: not validated — withheld**')
    st.caption('Research targets: −5%, −10%, −20%, −30% after the first close at −3% from the file peak, within 63 sessions and before peak recovery. A news label is not converted into a probability.')
    path=Path(root).parent/'research_history/ath_cause_v1/ath_cause_depth_audit_v1.json'
    if path.exists():
        try:
            a=json.loads(path.read_text());st.caption('Archive test: '+a['status']+' · Snapshots '+str(a['snapshot_count'])+' · Full-context rows '+str(a['events_with_full_context']))
        except (ValueError,KeyError,OSError) as e:st.warning('Unable to read test results: '+str(e))
    with st.expander('Unverified cases and evidence limitations'):
        for c in r['causes']:
            if c['status']=='UNVERIFIED':st.write(CAUSE_LABELS[c['cause']]+' — Unverified does not mean absent.')
        st.json({'excluded_features':r['excluded_features'],'excluded_news_count':len(r['excluded_news']),
                 'limitations':r['limitations']})
    st.download_button('Download current risk evidence',json.dumps(r,ensure_ascii=False,indent=2),
                       'ath-cause-current.json','application/json',key='ath_cause_current_download')
