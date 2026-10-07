"""Read-only cause evidence inside the existing ATH page; no unvalidated forecasts."""
import json
from pathlib import Path
import streamlit as st
from ath_cause_context_v1 import assess, load
from ath_ui_components_v1 import cards, notice


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
    try:
        r=assess(root)
    except (OSError,ValueError,KeyError,TypeError) as error:
        notice('Risk evidence unavailable','Source validation did not pass. No risk assessment or probability is shown.',True)
        with st.expander('Risk diagnostic details'):st.code(str(error))
        return
    active=[x for x in r['causes'] if x['status']!='UNVERIFIED']
    status_names={'CONTEXT_RISK_FLAG':'Context signal','NEWS_CANDIDATE':'News candidate',
                  'CORROBORATED_RISK_CANDIDATE':'Corroborated candidate'}
    st.subheader('Risk drivers')
    if active:
        cards([('Potential pressure',CAUSE_LABELS[x['cause']],
                status_names.get(x['status'],'Unverified')+' · Does not establish the cause of a decline') for x in active])
    else:
        notice('No supported risk driver','Eligible evidence does not identify a supported case. This does not mean risks are absent.')
    p=r['observed_market_response']
    if p['price_status']=='STALE':
        notice('Stale price snapshot','Latest published session: '+p['last_session']+'. Refresh the price source before interpreting current conditions.',True)
    response='No net decline over the last 20 sessions' if p['response']=='NO_20_SESSION_DECLINE_CONFIRMED' else 'Net decline over the last 20 sessions'
    st.caption(response+' · Price session: '+p['last_session']+'. This observation does not establish the effect of any news event.')
    notice('Drawdown-depth probability: not validated — withheld',
           'There is not enough eligible historical context to publish a reliable probability. One-month, three-month and peak-recovery forecasts remain unavailable.',True)
    st.caption('Research targets: −5%, −10%, −20%, −30% after the first closing decline of 3%, within 63 sessions and before peak recovery.')
    with st.expander('Risk evidence and research readiness',expanded=False):
        for c in active:
            st.write('**'+CAUSE_LABELS[c['cause']]+'** — '+status_names[c['status']])
            for x in c['news_evidence'][:3]:st.markdown('['+x['title'].replace('[','').replace(']','')+']('+x['url']+')')
            feature_names={'economic_inflation':'Inflation surprise score','economic_labor':'Labor surprise score',
                           'economic_growth':'Growth surprise score','fed_stance':'Fed stance score','financial_stress':'Financial stress score'}
            for x in c['context_evidence']:
                st.write(feature_names.get(x['feature'],x['feature'])+f": {x['value']:.3f} · "+x['state'].replace('_',' ').title())
                st.caption('Available: '+x['available_at']+' · '+x['source'])
        unknown=[CAUSE_LABELS[x['cause']] for x in r['causes'] if x['status']=='UNVERIFIED']
        st.write('**Not verified:** '+', '.join(unknown) if unknown else 'All cases have candidate evidence; causal attribution remains unproven.')
        st.caption('A missing case is not evidence of its absence. Headline candidates and score thresholds are not calibrated probabilities.')
        archive=Path(root).parent/'research_history/ath_cause_v1'
        path=archive/'ath_cause_depth_audit_v1.json'
        if path.exists():
            try:
                a=json.loads(path.read_text());receipts=load(archive)
                capture_id=a.get('capture',{}).get('snapshot_id')
                tested=next((x for x in receipts if x['snapshot_id']==capture_id),None)
                outdated=(a['snapshot_count']!=len(receipts) or tested is None or tested['payload']['source_sha256']!=r['source_sha256'])
                st.write(f"Saved research result: {a['events_with_full_context']} event rows with full context; {a['snapshot_count']} snapshots used in that test.")
                st.write(f"Verified archive now contains {len(receipts)} snapshots.")
                if outdated:st.info('The saved test uses older inputs or archive coverage. Rerun the audit and update its saved display summary. These counts are not a current assessment.')
                st.caption('Research status: insufficient historical context' if a['status']=='INSUFFICIENT_HISTORICAL_CAUSE_VINTAGES' else 'Research status: no independently validated edge')
            except (ValueError,KeyError,OSError,TypeError) as error:st.warning('Saved research summary could not be verified: '+str(error))
        st.write(f"Excluded news records: {len(r['excluded_news'])}. Existing news feeds do not provide complete global coverage.")
        for item in r['limitations']:st.caption(item)
        st.download_button('Download current risk evidence',json.dumps(r,ensure_ascii=False,indent=2),
                           'ath-cause-current.json','application/json',key='ath_cause_current_download')
