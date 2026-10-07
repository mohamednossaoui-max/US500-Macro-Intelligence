"""Depth context page. No orders, strategy rules, or uncalibrated predictions."""
import json
import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st

from ath_pullback_context_v1 import audit, bars, classify, loss, study, describe
from ath_cause_context_ui_v1 import render_cause_context
from ath_ui_components_v1 import cards, notice, styles, research_table


def render_ath_pullback_context(public_data=None):
    with st.container(key='ath_page'):
        styles()
        _render_ath_page(public_data)


def _render_ath_page(public_data=None):
    st.header('ATH Pullback Context')
    st.write('Market context, observed drawdown and research readiness.')
    root=Path(public_data) if public_data else Path(__file__).resolve().parent/'public_data'
    try:
        result,labels=audit(root)
    except (ValueError,OSError,pd.errors.ParserError) as error:
        notice('Study unavailable','Published inputs could not be verified. No assessment is shown.',True)
        with st.expander('Diagnostic details'):st.code(str(error))
        return
    names={'NO_MEANINGFUL_PULLBACK':'Minor move','LIMITED':'Limited pullback','MEDIUM':'Medium pullback','CRASH':'Crash'}
    cards([('Reference peak',f"{result['reference_peak']:,.2f}",'Highest high in the available file'),
           ('Observed drawdown',f"−{result['drawdown_at_last_close_pct']:.2f}%",'At the latest published close'),
           ('Observed class',names.get(result['current_observed_class'],result['current_observed_class']),
            'Describes the move already observed')])
    st.caption(f"{', '.join(result['instrument'])} · Last published session: {result['last_session']} · Cash-index proxy, not ES or broker US500.")
    render_cause_context(root)
    with st.expander('Research archive and model comparisons',expanded=False):
        st.caption('Historical results are exploratory. They are not live forecasts, and some inputs may have changed.')
        tabs=st.tabs(['Peak-date test','Context model','After 3%','Economic vintages','Historical counts'])
        with tabs[0]:render_record_research(root,expandable=False)
        with tabs[1]:render_model_research(root,expandable=False)
        with tabs[2]:render_edge_research(root,expandable=False)
        with tabs[3]:render_macro_edge_research(root,expandable=False)
        with tabs[4]:
            rows=[{'Horizon':x['horizon'],'Samples':x['sample_count'],
                   'Complete':x['complete_unambiguous_count'],'Censored':x['censored_count'],
                   **x['historical_class_counts']} for x in result['horizons']]
            research_table(pd.DataFrame(rows),hide_index=True,use_container_width=True)
            st.caption('Recovery cycles and monthly peak samples differ. Counts are not comparable probabilities. Unknown daily High/Low ordering is preserved in depth bounds.')
    with st.expander('Methodology and source diagnostics',expanded=False):
        st.write('Study classes: below 3% minor move; 3% to below 5% limited; 5% to below 20% medium; 20% or more crash.')
        st.write('Recovery studies use a frozen reference peak. Monthly studies include declines from new peaks within the window. A limited file cannot certify a lifetime ATH.')
        st.write('Current context is not backcast onto historical peaks. Missing evidence is never replaced with future data.')
        for item in result['context_inventory']:
            st.write(item['file']+' — '+item['status'])
            if 'historical_anchor_count' in item:
                st.caption(f"Date-eligible context at {item['historical_anchors_with_context']} of {item['historical_anchor_count']} sampled peaks.")
            if item.get('current_context'):st.json(item['current_context'])
    with st.expander('Downloads and separate ES / US500 files',expanded=False):
        st.download_button('Download depth audit',json.dumps(result,indent=2,ensure_ascii=False),
                           'ath-depth-context-audit.json','application/json',key='ath_audit_download')
        st.download_button('Download historical measurements',labels.to_csv(index=False),
                           'ath-depth-labels.csv','text/csv',key='ath_labels_download')
        st.caption('Each uploaded instrument uses its own peaks. Use completed sessions and documented contract history. Uploading prices does not create an economic forecast.')
        for instrument in ['ES','US500']:
            file=st.file_uploader(instrument+': Date, Open, High, Low, Close',type=['csv'],key='ath_file_'+instrument)
            if file is None:continue
            try:
                frame=pd.read_csv(file);data=bars(frame);peak=float(data.high.max());depth=loss(peak,data.close.iloc[-1])
                cards([(instrument+' file peak',f'{peak:,.2f}','Peak in this file'),
                       ('Closing drawdown',f'{depth:.2f}%','Observed, not forecast'),
                       ('Observed class',names[classify(depth)],'Study-defined class')])
                st.json(describe(study(frame)))
            except (ValueError,TypeError,pd.errors.ParserError) as error:st.error(str(error))


def render_model_research(public_data, expandable=True):
    history=Path(public_data).parent/'research_history'
    path=history/'ath_depth_model_audit_v1.json'
    with (st.expander('Does context improve drawdown-depth estimates?',expanded=False) if expandable else st.container()):
        if not path.exists():
            st.info('Model-test results are not published in this version. No validated forecast is available.')
            return
        try:
            report=json.loads(path.read_text())
            st.warning('Predictive edge is unproven — live probabilities are withheld.')
            st.caption(f"Context archive: {report['source_snapshot_count']} snapshots · Cash-index study, not ES or broker US500.")
            if report.get('source_hashes'):
                changed=[name for name,sha in report['source_hashes'].items()
                         if not (Path(public_data)/name).exists() or hashlib.sha256((Path(public_data)/name).read_bytes()).hexdigest()!=sha]
                if changed:
                    st.info('Inputs have changed since this test; results below are archival and require recalculation.')
            rows=[]
            for item in report['analyses']:
                scores=item['partial_context_common_sample']
                rows.append({'Horizon':item['horizon'],'Temporal evaluations':scores['evaluations'],
                             'Price-only Brier':scores['price_brier'],
                             'Partial-context Brier':scores['context_brier'],
                             'Historical-baseline Brier':scores['climatology_brier'],
                             'Full-context evaluations':item['full_context_common_sample']['evaluations']})
            research_table(pd.DataFrame(rows),hide_index=True,use_container_width=True)
            st.caption('Lower error is better. Models use the same cases and train only on outcomes completed before each peak. Partial context covers financial stress, sentiment and liquidity. Small samples do not establish high accuracy or crash-prediction ability.')
            st.download_button('Download model-test results',path.read_bytes(),'ath-depth-model-audit.json','application/json',key='ath_model_download')
        except (OSError,ValueError,KeyError,TypeError) as error:
            st.error('Unable to read model audit: '+str(error))


def render_edge_research(public_data, expandable=True):
    path=Path(public_data).parent/'research_history'/'ath_edge_v3'/'edge_v3_audit.json'
    if not path.exists():return
    with (st.expander('Extended study: depth after a 3% decline',expanded=False) if expandable else st.container()):
        try:
            report=json.loads(path.read_text())
            st.warning('No confirmed predictive edge. These are research results, not probabilities for the current market.')
            st.caption('This study begins after a closing decline of 3% to below 5% from an available-history closing peak. It is not an ATH-day forecast or an ES/US500 price study.')
            source=Path(public_data)/report['source_file']
            if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest()!=report['source_sha256']:
                st.info('Inputs have changed; displayed results are archival and require recalculation.')
            research_table(pd.DataFrame([{'Horizon':x['horizon'],'Test cases':x['evaluation_predictions'],
                'Crash cases':x['test_class_counts']['CRASH'],
                'Context Brier':x['mean_scores']['market_brier'],
                'Price Brier':x['mean_scores']['price_brier'],
                'Historical-baseline Brier':x['mean_scores']['climatology_brier']} for x in report['analyses']]),
                hide_index=True,use_container_width=True)
            st.caption('Lower error is better. This test period was previously examined in other studies; independent prospective validation is required to establish an edge.')
            st.download_button('Download extended-study audit',path.read_bytes(),'ath-edge-v3-audit.json','application/json',key='ath_edge_download')
        except (OSError,ValueError,KeyError,TypeError) as error:
            st.error('Unable to read extended study: '+str(error))


def render_macro_edge_research(public_data, expandable=True):
    path=Path(public_data).parent/'research_history'/'ath_macro_edge_v4'/'macro_edge_v4_audit.json'
    if not path.exists():return
    with (st.expander('Historical economic-vintage context test',expanded=False) if expandable else st.container()):
        try:
            report=json.loads(path.read_text())
            st.warning('The economic model has not demonstrated an edge; no live forecast is published.')
            source=Path(public_data)/'cross_asset_research_v1.csv'
            if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest()!=report['price_source_sha256']:
                st.info('These are archival results; price inputs have changed and require recalculation.')
            st.caption('Employment, unemployment, inflation and industrial-production features use receipts reflecting vintages available before each decision. Current values are not used for past peaks.')
            research_table(pd.DataFrame([{'Horizon':a['horizon'],'Test cases':a['evaluation_predictions'],
                'Economic-context Brier':a['scores']['macro'],'Price Brier':a['scores']['price'],
                'Historical-baseline Brier':a['scores']['climatology']} for a in report['analyses']]),
                hide_index=True,use_container_width=True)
            st.caption('Lower error is better. Research starts after a 3% decline; it is not an ATH-day forecast or a validated calibration.')
        except (OSError,ValueError,KeyError,TypeError) as error:st.error('Unable to read context study: '+str(error))


def render_record_research(public_data, expandable=True):
    path=Path(public_data).parent/'research_history'/'ath_record_high_v6'/'record_high_v6_audit.json'
    if not path.exists():return
    with (st.expander('Test from the peak date — before a pullback',expanded=False) if expandable else st.container()):
        try:
            report=json.loads(path.read_text())
            st.caption('This test selects closing peaks by date and retains cases where prices keep rising. Cash-index data and available peak history do not certify intraday ATHs or ES/US500 prices.')
            st.warning('No validated live probabilities. Economic context must be available at the peak date itself.')
            source=Path(public_data)/'cross_asset_research_v1.csv'
            if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest()!=report['source_sha256']:
                st.info('Archival results; inputs have changed and require recalculation.')
            for column,item in zip(st.columns(3),report['analyses']):
                score=item['price_and_market_common_sample']
                column.metric(item['horizon']+' evaluations',score['evaluations'])
                column.caption('Full context: '+str(item['full_context_common_sample']['evaluations'])+' evaluations')
            comparisons=[]
            for item in report['analyses']:
                sample=item['full_context_common_sample'];scores=sample['scores']
                if sample['evaluations']:
                    comparisons.append({'Horizon':item['horizon'],'Cases':sample['evaluations'],
                        'Full context':scores.get('full_context'),'Historical baseline':scores.get('climatology')})
            if comparisons:
                st.caption('Brier: lower is better; comparisons use the same cases. Results are exploratory and do not establish an edge.')
                research_table(comparisons,hide_index=True,use_container_width=True)
            if all(x['full_context_feature_rows']==0 for x in report['analyses']):
                st.info('The current archive collected vintages at the start of 3% declines, not at these peak dates. Run ATH Record High Context Audit to acquire them.')
            st.caption('Recovery means regaining the selected reference peak, possibly in the next session. These cases are retained to avoid inflating pullback counts. Monthly horizons measure declines from running peaks within the window.')
            st.download_button('Download peak-date study audit',path.read_bytes(),'ath-record-high-v6-audit.json','application/json',key='ath_record_v6_download')
        except (OSError,ValueError,KeyError,TypeError) as error:st.error('Unable to read peak-date study: '+str(error))
