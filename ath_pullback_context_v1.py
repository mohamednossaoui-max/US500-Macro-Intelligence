"""Read-only depth research. Observations and forward labels are not forecasts.

Daily OHLC cannot establish the order of a high and a low in one session.
Report bounds, keep censored labels, and never backcast a current macro snapshot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

CLASSES = ('NO_MEANINGFUL_PULLBACK', 'LIMITED', 'MEDIUM', 'CRASH')
HORIZONS = (1, 3)  # calendar months, not assumed trading-session counts


def classify(depth):
    if depth is None or not math.isfinite(float(depth)) or not 0 <= depth <= 100:
        raise ValueError('Depth must be a finite loss percentage between 0 and 100.')
    return ('NO_MEANINGFUL_PULLBACK' if depth < 3 else
            'LIMITED' if depth < 5 else 'MEDIUM' if depth < 20 else 'CRASH')


def bars(frame, as_of=None):
    data = frame.copy().rename(columns={'observation_date': 'Date'})
    data.columns = [str(c).strip().lower() for c in data.columns]
    fields = ['date', 'open', 'high', 'low', 'close']
    if not data.columns.is_unique or not set(fields).issubset(data):
        raise ValueError('Daily Date, Open, High, Low, Close are required.')
    data['date'] = pd.to_datetime(data.date, utc=True, errors='coerce').dt.normalize()
    if data.date.isna().any() or data.date.duplicated().any():
        raise ValueError('Invalid or duplicate session date.')
    for key in fields[1:]:
        data[key] = pd.to_numeric(data[key], errors='coerce')
        if not data[key].map(lambda x: pd.notna(x) and math.isfinite(x) and x > 0).all():
            raise ValueError('OHLC must be finite and positive.')
    if ((data.high < data[['open', 'close', 'low']].max(axis=1)) |
            (data.low > data[['open', 'close', 'high']].min(axis=1))).any():
        raise ValueError('Inconsistent OHLC.')
    data = data.sort_values('date').reset_index(drop=True)
    if as_of is not None:
        data = data[data.date <= pd.to_datetime(as_of, utc=True).normalize()]
    if data.empty:
        raise ValueError('No completed daily sessions available.')
    return data[fields].reset_index(drop=True)


def loss(peak, low):
    return round(max(0.0, 100 * (1 - float(low) / float(peak))), 10)


def label(data, index, months=None):
    """Anchor known at day's end; measurements begin on the NEXT session.

    Recovery-bar Low may precede or follow High: episode lower bound excludes
    it, upper bound includes it. Fixed-horizon rolling-peak lower bound uses
    prior-session peaks, upper bound also allows the current day's High first.
    """
    origin = data.iloc[index]
    anchor, date = float(origin.high), origin.date
    future = data.iloc[index + 1:]
    end = None
    if months is None:
        recovered = future[future.high >= anchor]
        end = recovered.date.iloc[0] if not recovered.empty else None
        window = future if end is None else future[future.date <= end]
        before = window if end is None else window[window.date < end]
        lower = loss(anchor, before.low.min()) if not before.empty else 0.0
        upper = loss(anchor, window.low.min()) if not window.empty else 0.0
        anchor_lower, anchor_upper = lower, upper
        complete = end is not None
    else:
        if months not in HORIZONS:
            raise ValueError('Only one and three calendar months are supported.')
        end = date + pd.DateOffset(months=months)
        window = future[future.date <= end]
        complete = data.date.iloc[-1] >= end
        peak, lower, upper = anchor, 0.0, 0.0
        for row in window.itertuples():
            lower = max(lower, loss(peak, row.low))
            peak = max(peak, float(row.high))
            upper = max(upper, loss(peak, row.low))
        anchor_lower = anchor_upper = loss(anchor, window.low.min()) if not window.empty else 0.0
    return {'peak_date': date.date().isoformat(), 'reference_peak': anchor,
            'horizon': 'UNTIL_RECOVERY' if months is None else f'{months}M',
            'label_end': None if end is None else end.date().isoformat(),
            'complete': bool(complete), 'status': 'COMPLETE' if complete else 'CENSORED',
            'depth_lower_pct': lower, 'depth_upper_pct': upper,
            'anchor_depth_lower_pct': anchor_lower, 'anchor_depth_upper_pct': anchor_upper,
            'class_lower': classify(lower), 'class_upper': classify(upper),
            'intraday_ambiguous': classify(lower) != classify(upper),
            'metric': 'ANCHOR_TO_RECOVERY' if months is None else 'ROLLING_PEAK_WITHIN_HORIZON'}


def study(frame, as_of=None, warmup=252):
    """Forward labels at record highs in AVAILABLE history, not proven ATHs.

    Independent descriptive sample is selected using dates alone: choose the
    first eligible record, then wait at least three calendar months. Selection
    is not based on how far the market subsequently falls. All records remain
    in the audit. Censored/ambiguous labels do not count as resolved classes.
    """
    data = bars(frame, as_of)
    if not isinstance(warmup, int) or warmup < 1:
        raise ValueError('Warmup must be at least one prior session.')
    prior = data.high.cummax().shift(1)
    indices = data.index[(data.high > prior) & (data.index >= warmup)]
    rows, eligible_after = [], None
    for index in indices:
        date = data.iloc[index].date
        independent = eligible_after is None or date > eligible_after
        if independent:
            eligible_after = date + pd.DateOffset(months=3)
        for months in (None, *HORIZONS):
            item = label(data, index, months)
            item['descriptive_sample'] = independent
            rows.append(item)
    return pd.DataFrame(rows)


def available_before(frame, column, cutoff):
    """Strict-before availability, never substitute observation date."""
    if column not in frame:
        raise ValueError('Availability metadata is required.')
    data = frame.copy()
    dates = pd.to_datetime(data[column], errors='coerce', utc=True)
    if dates.isna().any() or dates.duplicated().any():
        raise ValueError('Invalid or duplicate availability metadata.')
    data['_available'] = dates
    data = data[data._available < pd.to_datetime(cutoff, utc=True)].sort_values('_available')
    return None if data.empty else data.iloc[-1].drop(labels=['_available']).to_dict()


def describe(labels):
    output = []
    for horizon in ('UNTIL_RECOVERY', '1M', '3M'):
        sample = labels[labels.horizon.eq(horizon) & labels.descriptive_sample] if not labels.empty else labels
        definition = 'Date-selected record highs spaced more than three calendar months apart'
        if horizon == 'UNTIL_RECOVERY' and not labels.empty:
            # Retrospective episode census, explicitly conditional on >=3%
            # having occurred. Never feed this outcome-conditioned selection
            # into a forecast or claim it describes ALL record-high days.
            candidates = labels[labels.horizon.eq(horizon) & labels.depth_upper_pct.ge(3)]
            selected, previous_end = [], None
            for index, row in candidates.iterrows():
                if previous_end is None or row.peak_date > previous_end:
                    selected.append(index)
                    previous_end = row.label_end or '9999-12-31'
            sample = candidates.loc[selected]
            definition = 'Retrospective nonoverlapping episodes with observed or possible depth >=3%; not an ATH-day forecast sample'
        resolved = sample[sample.complete & ~sample.intraday_ambiguous] if not sample.empty else sample
        counts = {key: int(resolved.class_lower.eq(key).sum()) if not resolved.empty else 0 for key in CLASSES}
        output.append({'horizon': horizon, 'sample_count': len(sample),
                       'sample_definition': definition,
                       'complete_unambiguous_count': len(resolved),
                       'censored_count': int((~sample.complete).sum()) if not sample.empty else 0,
                       'ambiguous_complete_count': int((sample.complete & sample.intraday_ambiguous).sum()) if not sample.empty else 0,
                       'historical_class_counts': counts,
                       'forecast_class': None, 'forecast_probabilities': None,
                       'forecast_status': 'INSUFFICIENT_PIT_CONTEXT_AND_CALIBRATION'})
    return output


def audit(public_data, as_of=None):
    public_data = Path(public_data)
    price = public_data / 'technical_intelligence_research_v1.csv'
    original = pd.read_csv(price)
    data = bars(original, as_of)
    # Context is eligible at next calendar day's start, matching the published
    # price layer's conservative +1-day availability proxy. Not a live quote.
    cutoff = data.date.iloc[-1] + pd.Timedelta(days=1)
    labels = study(original, as_of)
    layers = []
    for name, date_column, fields in (
            ('macro_context_v1.csv', 'context_date', ['economic_regime', 'fed_score', 'statement_tone', 'financial_stress_regime']),
            ('decision_engine_research_v1.csv', 'as_of_date', ['state', 'overall_evidence_pit_status']),
            ('financial_stress_research_v1.csv', 'asof_date', ['research_regime', 'composite_stress_score']),
            ('liquidity_intelligence_research_v1.csv', 'asof_date', ['NET_LIQUIDITY_PROXY_MILLIONS']),
            ('sentiment_engine_research_v1.csv', 'asof_date', ['research_regime', 'unified_sentiment_score']),
            ('technical_intelligence_research_v1.csv', 'availability_date', ['technical_regime', 'RSI14', 'ATR14_pct'])):
        path = public_data / name
        item = {'file': name, 'used_as_historical_predictor': False}
        if not path.exists():
            item['status'] = 'MISSING'
        else:
            frame = pd.read_csv(path)
            item['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            item['rows'] = len(frame)
            try:
                latest = available_before(frame, date_column, cutoff)
                item['status'] = 'AVAILABLE_BEFORE_PRICE_CUTOFF' if latest else 'NO_ELIGIBLE_CONTEXT'
                item['current_context'] = None if latest is None else {
                    key: None if pd.isna(latest.get(key)) else latest.get(key)
                    for key in [date_column, *fields]}
                anchors = labels[labels.horizon.eq('3M') & labels.descriptive_sample].peak_date if not labels.empty else []
                coverage = []
                for anchor in anchors:
                    row = available_before(frame, date_column, anchor)
                    coverage.append(row is not None and any(pd.notna(row.get(key)) for key in fields))
                item['historical_anchor_count'] = len(coverage)
                item['historical_anchors_with_context'] = sum(coverage)
                item['timestamp_verification'] = 'PUBLISHED_RESEARCH_DATE_PROXY_NOT_INDEPENDENT_VINTAGE_PROOF'
            except ValueError as error:
                item.update(status='METADATA_UNVERIFIED', reason=str(error))
        layers.append(item)
    peak = float(data.high.max())
    tickers = sorted(original.get('ticker', pd.Series(dtype=str)).dropna().unique().tolist())
    result = {'version': 'ath_pullback_context_v1', 'mode': 'READ_ONLY',
              'instrument': tickers, 'instrument_semantics': 'Published cash-index history; not ES or broker US500',
              'history_start': data.date.iloc[0].date().isoformat(),
              'last_session': data.date.iloc[-1].date().isoformat(),
              'price_sha256': hashlib.sha256(price.read_bytes()).hexdigest(),
              'reference_peak': peak, 'peak_verification': 'AVAILABLE_HISTORY_ONLY',
              'drawdown_at_last_close_pct': loss(peak, data.close.iloc[-1]),
              'current_observed_class': classify(loss(peak, data.close.iloc[-1])),
              'horizons': describe(labels), 'context_inventory': layers,
              'forecast_status': 'INSUFFICIENT_PIT_CONTEXT_AND_CALIBRATION',
              'limitations': ['No validated predictive model or out-of-sample incremental edge.',
                              'Current Macro/Fed/Decision snapshots are not historical feature archives.',
                              'A truncated file cannot prove a true all-time high.',
                              'Daily high/low order is unknown; depth bounds are retained.',
                              'Historical source revisions and exact publication timestamps are not independently verified.',
                              'One-month and three-month depths allow new peaks inside the horizon.',
                              'Incomplete horizons are censored; descriptive counts are not forecast probabilities.'],
              'research_only': True, 'execution': False}
    return result, labels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--public-data', type=Path, default=Path('public_data'))
    parser.add_argument('--output', type=Path, default=Path('ath_pullback_research'))
    parser.add_argument('--as-of')
    args = parser.parse_args()
    public = args.public_data.resolve()
    destination = args.output.resolve()
    if destination == public or public in destination.parents:
        parser.error('Read-only audit outputs must be outside public_data.')
    result, labels = audit(public, args.as_of)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'depth_context_audit.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    labels.to_csv(destination / 'depth_labels.csv', index=False)
    print(json.dumps({'forecast_status': result['forecast_status'], 'last_session': result['last_session'],
                      'horizons': result['horizons']}, indent=2))


if __name__ == '__main__':
    main()
