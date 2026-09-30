from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
P = ROOT / 'public_data'
VERSION = 'HMR1.0'
ANALOG_VERSION = 'HAE1.0'
HORIZONS = (5, 20, 60, 120)
ANNUALIZATION = 252


def load_locked_analogs():
    d = pd.read_csv(P / 'historical_analog_top_v1.csv')
    required = {'historical_date','similarity_pct','coverage_pct','analog_engine_version','outcomes_used_in_selection'}
    missing = required - set(d.columns)
    if missing:
        raise ValueError(f'Missing analog columns: {sorted(missing)}')
    if not d['analog_engine_version'].eq(ANALOG_VERSION).all():
        raise ValueError('Unexpected analog engine version')
    if d['outcomes_used_in_selection'].astype(bool).any():
        raise ValueError('Analog selection is outcome-contaminated')
    return d.copy()


def load_price_history():
    d = pd.read_csv(P / 'technical_intelligence_research_v1.csv')
    d['observation_date'] = pd.to_datetime(d['observation_date'])
    d['availability_date'] = pd.to_datetime(d['availability_date'])
    d['Close'] = pd.to_numeric(d['Close'], errors='coerce')
    d = d.dropna(subset=['observation_date','Close']).sort_values('observation_date')
    d = d.drop_duplicates('observation_date', keep='last').reset_index(drop=True)
    if not d['observation_date'].is_monotonic_increasing:
        raise ValueError('Price history is not chronological')
    return d


def _reaction_for_one(row, prices):
    event_date = pd.Timestamp(row['historical_date'])
    # Conservative anchor: first market session on/after the historical state date.
    # No pre-event close is used and no horizon influences analog selection.
    idxs = prices.index[prices['observation_date'] >= event_date]
    out = dict(row)
    out.update({'reaction_engine_version': VERSION, 'selection_locked': True, 'outcomes_used_in_selection': False})
    if len(idxs) == 0:
        out.update({'anchor_session': pd.NA, 'anchor_close': np.nan})
        for h in HORIZONS:
            for k in (f'return_{h}d_pct', f'max_drawdown_{h}d_pct', f'realized_volatility_{h}d_pct'):
                out[k] = np.nan
            out[f'horizon_{h}d_available'] = False
            out[f'horizon_{h}d_end_session'] = pd.NA
        return out
    i0 = int(idxs[0]); anchor = prices.iloc[i0]; p0 = float(anchor['Close'])
    out['anchor_session'] = anchor['observation_date'].date().isoformat(); out['anchor_close'] = p0
    for h in HORIZONS:
        end_i = i0 + h
        available = end_i < len(prices)
        out[f'horizon_{h}d_available'] = bool(available)
        if not available:
            out[f'horizon_{h}d_end_session'] = pd.NA
            out[f'return_{h}d_pct'] = np.nan; out[f'max_drawdown_{h}d_pct'] = np.nan; out[f'realized_volatility_{h}d_pct'] = np.nan
            continue
        window = prices.iloc[i0:end_i+1].copy()
        pend = float(window.iloc[-1]['Close'])
        out[f'horizon_{h}d_end_session'] = window.iloc[-1]['observation_date'].date().isoformat()
        out[f'return_{h}d_pct'] = round(100.0 * (pend / p0 - 1.0), 6)
        closes = window['Close'].astype(float)
        running_peak = closes.cummax()
        drawdowns = closes / running_peak - 1.0
        out[f'max_drawdown_{h}d_pct'] = round(100.0 * float(drawdowns.min()), 6)
        rets = window['Close'].astype(float).pct_change().dropna()
        vol = rets.std(ddof=1) * np.sqrt(ANNUALIZATION) * 100.0 if len(rets) >= 2 else np.nan
        out[f'realized_volatility_{h}d_pct'] = round(float(vol), 6) if pd.notna(vol) else np.nan
    return out


def build_reactions():
    analogs = load_locked_analogs(); prices = load_price_history()
    rows = [_reaction_for_one(r.to_dict(), prices) for _, r in analogs.iterrows()]
    result = pd.DataFrame(rows)
    # Immutability gate: reaction layer must preserve Stage-10 identity and ranking.
    if result['historical_date'].astype(str).tolist() != analogs['historical_date'].astype(str).tolist():
        raise AssertionError('Analog order changed')
    if not np.allclose(result['similarity_pct'], analogs['similarity_pct'], equal_nan=True):
        raise AssertionError('Analog similarity changed')
    return result


def build_summary(reactions):
    horizons = {}
    for h in HORIZONS:
        col = f'return_{h}d_pct'; avail = reactions[reactions[f'horizon_{h}d_available'].astype(bool)].copy()
        vals = pd.to_numeric(avail[col], errors='coerce').dropna()
        dd = pd.to_numeric(avail[f'max_drawdown_{h}d_pct'], errors='coerce').dropna()
        vol = pd.to_numeric(avail[f'realized_volatility_{h}d_pct'], errors='coerce').dropna()
        horizons[f'{h}d'] = {
            'available_analogs': int(len(vals)),
            'total_analogs': int(len(reactions)),
            'mean_return_pct': round(float(vals.mean()), 6) if len(vals) else None,
            'median_return_pct': round(float(vals.median()), 6) if len(vals) else None,
            'positive_hit_rate_pct': round(float((vals > 0).mean() * 100), 4) if len(vals) else None,
            'min_return_pct': round(float(vals.min()), 6) if len(vals) else None,
            'max_return_pct': round(float(vals.max()), 6) if len(vals) else None,
            'return_std_pct': round(float(vals.std(ddof=1)), 6) if len(vals) > 1 else None,
            'median_max_drawdown_pct': round(float(dd.median()), 6) if len(dd) else None,
            'median_realized_volatility_pct': round(float(vol.median()), 6) if len(vol) else None,
        }
    return {
        'reaction_engine_version': VERSION,
        'analog_engine_version': ANALOG_VERSION,
        'analog_count': int(len(reactions)),
        'analog_selection_locked': True,
        'analog_reranking_by_outcome': False,
        'outcomes_used_in_selection': False,
        'anchor_semantics': 'First US500 trading session on or after historical analog date; forward horizons use subsequent trading sessions.',
        'horizons_trading_days': list(HORIZONS),
        'incomplete_horizons_excluded_from_summary': True,
        'research_only': True,
        'decision_engine_ready': False,
        'forecast_generated': False,
        'trading_signal_generated': False,
        'horizons': horizons,
    }


def main():
    r = build_reactions()
    r.to_csv(P / 'historical_market_reaction_v1.csv', index=False)
    summary = build_summary(r)
    (P / 'historical_market_reaction_summary_v1.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(r[['historical_date','similarity_pct'] + [f'return_{h}d_pct' for h in HORIZONS]].to_string(index=False))
    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()
