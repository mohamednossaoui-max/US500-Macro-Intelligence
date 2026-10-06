"""Exploratory conditional drawdown research. No live forecast or execution.

Fixed closing peak; target must occur before recovery or 63 subsequent sessions.
All selection/features use the prefix; outcomes mature before training eligibility.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

FEATURES = ['return20', 'vol20', 'distance_ma60', 'days_from_peak']
PROTOCOL = {
    'version': 'ATH_SEQUENTIAL_V9', 'stages_pct': [0, 3, 5, 10],
    'targets_pct': [5, 10, 20], 'horizon_sessions': 63, 'warmup_sessions': 252,
    'ath_sampling_sessions': 63, 'minimum_training_cases': 30,
    'ridge_penalty': 10.0, 'evaluation_start': '2019-01-01',
    'features': FEATURES, 'models': ['conditional_climatology', 'price_context'],
    'label': 'At ATH: rolling-peak drawdown over 63 sessions. At pullback stages: frozen-peak target before recovery or 63 sessions.',
    'availability': 'Conservative next-calendar-day proxy, not certified publication time.',
    'scope': 'Cash index available-history closing records; not intraday ATH, ES or broker US500.',
    'status': 'EXPLORATORY; previously inspected years, no independent holdout.',
    'live_forecast': None, 'execution': False, 'research_only': True,
}


def history(frame):
    required = {'observation_date', 'availability_date', 'SP500'}
    if not required.issubset(frame):
        raise ValueError('Price history and explicit availability are required.')
    data = frame[sorted(required)].copy()
    data['date'] = pd.to_datetime(data.observation_date, utc=True, errors='coerce').dt.normalize()
    data['available'] = pd.to_datetime(data.availability_date, utc=True, errors='coerce')
    data['SP500'] = pd.to_numeric(data.SP500, errors='coerce')
    if data.date.isna().any() or data.available.isna().any() or data.date.duplicated().any():
        raise ValueError('Invalid or duplicate price dates.')
    if not np.isfinite(data.SP500).all() or (data.SP500 <= 0).any():
        raise ValueError('Missing/nonpositive price; do not silently remove sessions.')
    if (data.available != data.date + pd.Timedelta(days=1)).any():
        raise ValueError('Expected explicit conservative next-day availability.')
    return data.sort_values('date').reset_index(drop=True)


def features(data, i, peak_date):
    closes = data.SP500.iloc[:i+1]
    return {'return20': float(100*(closes.iloc[-1]/closes.iloc[-21]-1)),
            'vol20': float(100*closes.pct_change().tail(20).std()),
            'distance_ma60': float(100*(closes.iloc[-1]/closes.tail(60).mean()-1)),
            'days_from_peak': float((data.date.iloc[i]-peak_date).days)}


def landmarks(data):
    """First crossing per peak cycle; gap beyond a target is never forecast as future."""
    peak = -np.inf; peak_date = None; seen = set(); last_ath = -10**9; rows = []
    for i, row in data.iterrows():
        price = float(row.SP500)
        record = price > peak
        if record:
            peak = price; peak_date = row.date; seen = set()
        drawdown = max(0., 100*(1-price/peak))
        selected = []
        if record and i-last_ath >= PROTOCOL['ath_sampling_sessions']:
            if i >= PROTOCOL['warmup_sessions']:
                selected.append(0); last_ath = i
        for stage in (3, 5, 10):
            if drawdown + 1e-9 >= stage and stage not in seen:
                seen.add(stage)
                if i >= PROTOCOL['warmup_sessions']: selected.append(stage)
        for stage in selected:
            rows.append({'event_id': f'{row.date.date()}:{stage}',
                         'cycle_id': peak_date.date().isoformat(), 'index': i,
                         'decision_at': row.available.isoformat(), 'stage_pct': stage,
                         'observed_depth_pct': drawdown, 'peak': peak,
                         **features(data, i, peak_date)})
    return pd.DataFrame(rows)


def outcomes(data, anchors):
    rows = []
    for _, anchor in anchors.iterrows():
        i = int(anchor['index']); stop = i+PROTOCOL['horizon_sessions']
        window = data.iloc[i+1:min(stop+1, len(data))]
        recoveries = window[window.SP500 >= anchor.peak]
        if anchor.stage_pct > 0 and not recoveries.empty:
            stop = int(recoveries.index[0]); window = window.loc[:stop]
        complete = stop < len(data)
        end = data.available.iloc[stop].isoformat() if complete else None
        if anchor.stage_pct == 0:
            peak = float(anchor.peak); worst = 0.
            for price in window.SP500:
                peak = max(peak,float(price)); worst = max(worst,100*(1-float(price)/peak))
        else:
            worst = max(0., 100*(1-float(window.SP500.min())/anchor.peak)) if len(window) else 0.
        for target in PROTOCOL['targets_pct']:
            if target <= anchor.stage_pct: continue
            row = anchor.to_dict(); row.pop('index')
            already = anchor.observed_depth_pct + 1e-9 >= target
            row.update(target_pct=target, eligible=not already,
                       exclusion='TARGET_ALREADY_REACHED_AT_DECISION' if already else '',
                       complete=complete, label_available_at=end,
                       hit=int(worst+1e-9 >= target) if complete else None)
            rows.append(row)
    return pd.DataFrame(rows)


def probability(train, event):
    x = train[FEATURES].to_numpy(float); q = event[FEATURES].to_numpy(float)
    if not np.isfinite(x).all() or not np.isfinite(q).all():
        raise ValueError('Missing predictors cannot be imputed.')
    center = x.mean(axis=0); scale = x.std(axis=0); scale[scale < 1e-12] = 1
    x = (x-center)/scale; q = (q-center)/scale
    base = float((train.hit.sum()+1)/(len(train)+2))
    weights = np.linalg.solve(x.T@x+PROTOCOL['ridge_penalty']*np.eye(len(FEATURES)),
                              x.T@(train.hit.to_numpy(float)-base))
    return base, float(np.clip(base+q@weights, .001, .999))


def evaluate(events):
    predictions = []
    if events.empty: return predictions
    usable = events[events.eligible & events.complete].sort_values(['decision_at','stage_pct','target_pct'])
    for _, event in usable.iterrows():
        train = usable[(usable.stage_pct == event.stage_pct) & (usable.target_pct == event.target_pct)
                       & (usable.decision_at < event.decision_at)
                       & (usable.label_available_at < event.decision_at)
                       & (usable.cycle_id != event.cycle_id)]
        if len(train) < PROTOCOL['minimum_training_cases']: continue
        base, model = probability(train, event)
        predictions.append({'event_id': event.event_id, 'cycle_id': event.cycle_id,
                            'decision_at': event.decision_at, 'stage_pct': int(event.stage_pct),
                            'target_pct': int(event.target_pct), 'hit': int(event.hit),
                            'training_count': len(train),
                            'latest_training_label_at': train.label_available_at.max(),
                            'development': event.decision_at < PROTOCOL['evaluation_start'],
                            'baseline_probability': base, 'model_probability': model,
                            'baseline_brier': (base-event.hit)**2, 'model_brier': (model-event.hit)**2})
    return predictions


def summarize(predictions):
    summaries = []
    for stage in PROTOCOL['stages_pct']:
        for target in PROTOCOL['targets_pct']:
            if target <= stage: continue
            cases = [r for r in predictions if not r['development'] and r['stage_pct']==stage and r['target_pct']==target]
            calibration = []
            for model in ('baseline', 'model'):
                for lo, hi in ((0,.2),(.2,.4),(.4,.6),(.6,.8),(.8,1.01)):
                    bucket = [r for r in cases if lo <= r[model+'_probability'] < hi]
                    calibration.append({'model': model, 'lower': lo, 'upper': min(hi,1), 'count': len(bucket),
                                        'mean_probability': float(np.mean([r[model+'_probability'] for r in bucket])) if bucket else None,
                                        'observed_rate': float(np.mean([r['hit'] for r in bucket])) if bucket else None})
            summaries.append({'stage_pct': stage, 'target_pct': target, 'evaluations': len(cases),
                              'hits': sum(r['hit'] for r in cases),
                              'baseline_brier': float(np.mean([r['baseline_brier'] for r in cases])) if cases else None,
                              'model_brier': float(np.mean([r['model_brier'] for r in cases])) if cases else None,
                              'calibration': calibration, 'status': 'NO_CONFIRMED_EDGE',
                              'high_confidence_probability': None})
    return summaries


def run(path, output, observed_session_only=False):
    path = Path(path); output = Path(output)
    if 'public_data' in output.resolve().parts:
        raise ValueError('Research output must be outside public_data.')
    raw = pd.read_csv(path)
    if not {'observation_date','availability_date','SP500'}.issubset(raw):
        raise ValueError('Price history and explicit availability are required.')
    missing = raw.SP500.isna()
    exclusions = raw.loc[missing, ['observation_date','availability_date']].to_dict('records')
    if missing.any() and not observed_session_only:
        raise ValueError('Missing cash observations; explicit --observed-session-only required for partial-history research.')
    data = history(raw.loc[~missing] if observed_session_only else raw)
    anchors = landmarks(data); events = outcomes(data, anchors)
    predictions = evaluate(events)
    audit = {'protocol': PROTOCOL, 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
             'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'history_start': data.date.iloc[0].isoformat(), 'history_end': data.date.iloc[-1].isoformat(),
             'input_rows': len(raw), 'cash_observations': len(data),
             'excluded_rows': exclusions, 'observed_session_only': observed_session_only,
             'calendar_verification': 'UNVERIFIED_OBSERVED_SESSIONS_ONLY',
             'landmarks': len(anchors), 'comparisons': summarize(predictions),
             'status': 'NO_CONFIRMED_EDGE', 'live_forecast': None,
             'limitations': ['Fixed peak and close crossings differ from intraday touches.',
                             'Historical cash prices are current provider history, not certified historical price vintages.',
                             'Stages and targets are correlated; counts cannot be pooled as independent trials.',
                             'No breadth/credit historical feature is fabricated; price-only candidate first.',
                             'Calibration bins are descriptive, not a high-confidence live certificate.',
                             'No uninspected independent holdout; prospective evaluation remains required.']}
    output.mkdir(parents=True, exist_ok=True)
    events.to_csv(output/'sequential_v9_events.csv', index=False)
    (output/'sequential_v9_predictions.json').write_text(json.dumps(predictions, indent=2, allow_nan=False))
    (output/'sequential_v9_audit.json').write_text(json.dumps(audit, indent=2, allow_nan=False))
    return audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prices', type=Path, default=Path('public_data/cross_asset_research_v1.csv'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--observed-session-only', action='store_true',
                        help='Explicit research permission to exclude missing cash prices; calendar completeness unverified.')
    args = parser.parse_args()
    print(json.dumps(run(args.prices,args.output,args.observed_session_only), indent=2, allow_nan=False))


if __name__ == '__main__': main()
