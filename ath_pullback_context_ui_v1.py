"""Depth context page. No orders, strategy rules, or uncalibrated predictions."""
import json
import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st

from ath_pullback_context_v1 import audit, bars, classify, loss, study, describe
from ath_cause_context_ui_v1 import render_cause_context


def render_ath_pullback_context(public_data=None):
    st.header('ATH Pullback Context — Drawdown Depth')
    st.write('Assess the context of limited pullbacks, medium pullbacks and crashes over one month, three months and until peak recovery.')
    st.caption('Research classes: below 3% minor move · 3% to below 5% limited · 5% to below 20% medium · 20% or more crash. These are study-defined thresholds.')
    root = Path(public_data) if public_data else Path(__file__).resolve().parent / 'public_data'
    try:
        result, labels = audit(root)
    except (ValueError, OSError, pd.errors.ParserError) as error:
        st.error('Unable to verify study inputs: ' + str(error))
        return
    render_cause_context(root)
    st.info('Forecasts are not calibrated. Current Macro / Fed / Decision snapshots cannot support a complete historical model. The counts below describe available history; they are not probabilities for the next pullback.')
    a, b, c = st.columns(3)
    a.metric('Highest peak in available history', f"{result['reference_peak']:,.2f}")
    b.metric('Drawdown at latest close', f"−{result['drawdown_at_last_close_pct']:.2f}%")
    c.metric('Current observed class', {'NO_MEANINGFUL_PULLBACK':'Minor move', 'LIMITED':'Limited pullback', 'MEDIUM':'Medium pullback', 'CRASH':'Crash'}.get(result['current_observed_class'], result['current_observed_class']))
    st.caption(f"Published source: {', '.join(result['instrument'])} · {result['history_start']} to {result['last_session']}. Cash-index data are not ES or broker US500 prices. Limited history cannot certify a lifetime ATH.")
    for col, name in zip(st.columns(3), ['Until peak recovery', 'Within one month', 'Within three months']):
        col.metric(name, 'Estimate unavailable')
    st.write('Until recovery: drawdown from the reference peak until it is regained. One- and three-month horizons: maximum drawdown within the window, including declines from new peaks reached inside it.')
    render_record_research(root)
    render_model_research(root)
    render_edge_research(root)
    render_macro_edge_research(root)
    with st.expander('Context available before the price snapshot', expanded=True):
        for item in result['context_inventory']:
            st.write(item['file'] + ' — ' + item['status'])
            if 'historical_anchor_count' in item:
                st.caption(f"Date-eligible context at {item['historical_anchors_with_context']} of {item['historical_anchor_count']} sampled peaks. A published research date alone does not verify every historical vintage.")
            if item.get('current_context'):
                st.json(item['current_context'])
        st.caption('Current context is not backcast onto past peaks. Missing eligible context is not replaced with future observations.')
    st.subheader('Historical study — not a forecast')
    rows = []
    for item in result['horizons']:
        rows.append({'Horizon': item['horizon'], 'Samples': item['sample_count'],
                     'Complete, unambiguous': item['complete_unambiguous_count'],
                     'Censored': item['censored_count'], **item['historical_class_counts']})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption('Until recovery: retrospective counts of distinct cycles that reached or may have reached 3%. Monthly horizons use date-selected peaks spaced more than three months apart. Samples differ; their counts are not comparable probabilities. Daily High/Low ordering is unknown, so depth bounds and ambiguous cases are preserved.')
    st.download_button('Download depth and context audit', json.dumps(result, indent=2, ensure_ascii=False),
                       'ath-depth-context-audit.json', 'application/json', key='ath_audit_download')
    st.download_button('Download historical peak measurements', labels.to_csv(index=False),
                       'ath-depth-labels.csv', 'text/csv', key='ath_labels_download')
    with st.expander('Study a separate ES or US500 price file'):
        st.caption('Each instrument uses peaks from its own file. Use completed sessions and documented contract history. An uploaded price file does not automatically provide an economic forecast.')
        for instrument in ['ES', 'US500']:
            file = st.file_uploader(instrument + ': Date, Open, High, Low, Close', type=['csv'], key='ath_file_' + instrument)
            if file is None:
                continue
            try:
                frame = pd.read_csv(file)
                data = bars(frame)
                peak = float(data.high.max())
                depth = loss(peak, data.close.iloc[-1])
                st.write(f'{instrument} · File peak {peak:,.2f} · Closing drawdown {depth:.2f}% · {classify(depth)}')
                st.json(describe(study(frame)))
            except (ValueError, TypeError, pd.errors.ParserError) as error:
                st.error(str(error))


def render_model_research(public_data):
    history=Path(public_data).parent/'research_history'
    path=history/'ath_depth_model_audit_v1.json'
    with st.expander('Does context improve drawdown-depth estimates?',expanded=True):
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
            st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
            st.caption('Lower error is better. Models use the same cases and train only on outcomes completed before each peak. Partial context covers financial stress, sentiment and liquidity. Small samples do not establish high accuracy or crash-prediction ability.')
            st.download_button('Download model-test results',path.read_bytes(),'ath-depth-model-audit.json','application/json',key='ath_model_download')
        except (OSError,ValueError,KeyError,TypeError) as error:
            st.error('Unable to read model audit: '+str(error))


def render_edge_research(public_data):
    path=Path(public_data).parent/'research_history'/'ath_edge_v3'/'edge_v3_audit.json'
    if not path.exists():return
    with st.expander('Extended study: depth after a 3% decline'):
        try:
            report=json.loads(path.read_text())
            st.warning('No confirmed predictive edge. These are research results, not probabilities for the current market.')
            st.caption('This study begins after a closing decline of 3% to below 5% from an available-history closing peak. It is not an ATH-day forecast or an ES/US500 price study.')
            source=Path(public_data)/report['source_file']
            if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest()!=report['source_sha256']:
                st.info('Inputs have changed; displayed results are archival and require recalculation.')
            st.dataframe(pd.DataFrame([{'Horizon':x['horizon'],'Test cases':x['evaluation_predictions'],
                'Crash cases':x['test_class_counts']['CRASH'],
                'Context Brier':x['mean_scores']['market_brier'],
                'Price Brier':x['mean_scores']['price_brier'],
                'Historical-baseline Brier':x['mean_scores']['climatology_brier']} for x in report['analyses']]),
                hide_index=True,use_container_width=True)
            st.caption('Lower error is better. This test period was previously examined in other studies; independent prospective validation is required to establish an edge.')
            st.download_button('Download extended-study audit',path.read_bytes(),'ath-edge-v3-audit.json','application/json',key='ath_edge_download')
        except (OSError,ValueError,KeyError,TypeError) as error:
            st.error('Unable to read extended study: '+str(error))


def render_macro_edge_research(public_data):
    path=Path(public_data).parent/'research_history'/'ath_macro_edge_v4'/'macro_edge_v4_audit.json'
    if not path.exists():return
    with st.expander('Historical economic-vintage context test'):
        try:
            report=json.loads(path.read_text())
            st.warning('The economic model has not demonstrated an edge; no live forecast is published.')
            source=Path(public_data)/'cross_asset_research_v1.csv'
            if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest()!=report['price_source_sha256']:
                st.info('These are archival results; price inputs have changed and require recalculation.')
            st.caption('Employment, unemployment, inflation and industrial-production features use receipts reflecting vintages available before each decision. Current values are not used for past peaks.')
            st.dataframe(pd.DataFrame([{'Horizon':a['horizon'],'Test cases':a['evaluation_predictions'],
                'Economic-context Brier':a['scores']['macro'],'Price Brier':a['scores']['price'],
                'Historical-baseline Brier':a['scores']['climatology']} for a in report['analyses']]),
                hide_index=True,use_container_width=True)
            st.caption('Lower error is better. Research starts after a 3% decline; it is not an ATH-day forecast or a validated calibration.')
        except (OSError,ValueError,KeyError,TypeError) as error:st.error('Unable to read context study: '+str(error))


def render_record_research(public_data):
    path=Path(public_data).parent/'research_history'/'ath_record_high_v6'/'record_high_v6_audit.json'
    if not path.exists():return
    with st.expander('Test from the peak date — before a pullback',expanded=True):
        try:
            report=json.loads(path.read_text())
            st.caption('This test selects closing peaks by date and retains cases where prices keep rising. Cash-index data and available peak history do not certify intraday ATHs or ES/US500 prices.')
            st.warning('No validated live probabilities. Economic context must be available at the peak date itself.')
            source=Path(public_data)/'cross_asset_research_v1.csv'
            if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest()!=report['source_sha256']:
                st.info('Archival results; inputs have changed and require recalculation.')
            for column,item in zip(st.columns(3),report['analyses']):
                score=item['price_and_market_common_sample']
                column.metric(item['horizon'],str(score['evaluations'])+' evaluations')
                column.caption('Full context: '+str(item['full_context_common_sample']['evaluations'])+' evaluations')
            comparisons=[]
            for item in report['analyses']:
                sample=item['full_context_common_sample'];scores=sample['scores']
                if sample['evaluations']:
                    comparisons.append({'Horizon':item['horizon'],'Cases':sample['evaluations'],
                        'Full context':scores.get('full_context'),'Historical baseline':scores.get('climatology')})
            if comparisons:
                st.caption('Brier: lower is better; comparisons use the same cases. Results are exploratory and do not establish an edge.')
                st.dataframe(comparisons,hide_index=True,use_container_width=True)
            if all(x['full_context_feature_rows']==0 for x in report['analyses']):
                st.info('The current archive collected vintages at the start of 3% declines, not at these peak dates. Run ATH Record High Context Audit to acquire them.')
            st.caption('Recovery means regaining the selected reference peak, possibly in the next session. These cases are retained to avoid inflating pullback counts. Monthly horizons measure declines from running peaks within the window.')
            st.download_button('Download peak-date study audit',path.read_bytes(),'ath-record-high-v6-audit.json','application/json',key='ath_record_v6_download')
        except (OSError,ValueError,KeyError,TypeError) as error:st.error('Unable to read peak-date study: '+str(error))
