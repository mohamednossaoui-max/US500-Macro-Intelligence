from __future__ import annotations
import pandas as pd
from .common import row


def _context_date(p, fallback):
    f = p / 'research_context_summary_v1.csv'
    if f.exists():
        d = pd.read_csv(f, low_memory=False)
        if not d.empty and 'context_date' in d.columns:
            v = pd.to_datetime(d.iloc[-1]['context_date'], errors='coerce')
            if pd.notna(v):
                return v.date().isoformat()
    return str(fallback)


def build(p):
    d = pd.read_csv(p / 'technical_intelligence_research_v1.csv')
    # Freeze one canonical Research Context clock for this build.
    # Select the newest Technical row that was actually available by that clock;
    # never take a newer row and then relabel it as contemporaneous evidence.
    fallback = d.iloc[-1].availability_date
    context_date = _context_date(p, fallback)
    context_ts = pd.to_datetime(context_date, errors='coerce')
    availability = pd.to_datetime(d['availability_date'], errors='coerce')
    eligible = d.loc[availability.notna() & (availability <= context_ts)].copy()
    if eligible.empty:
        # Preserve strict PIT semantics: expose no Technical evidence rather than
        # silently using a row that was not yet available at context_date.
        return []
    x = eligible.iloc[-1]
    out = []
    for dim, ind, state, val, unit in [
        ('TREND', 'Trend Structure', x.trend_structure, x.Close, 'index'),
        ('MOMENTUM', 'RSI14', '', x.RSI14, 'index'),
        ('RISK_VOLATILITY', 'Realized Volatility 20D', '', x.realized_volatility_20d_pct, '%'),
    ]:
        out.append(row(
            'TECHNICAL', dim, ind, state=state, value=val, unit=unit,
            observation_date=x.observation_date,
            available_at=x.availability_date,
            as_of_date=context_date,
            source_name=x.source,
            source_artifact='technical_intelligence_research_v1.csv',
            pit_status='PIT_SAFE' if x.point_in_time_safe else 'NOT_PIT_SAFE',
            expected_frequency='DAILY',
            limitations=x.availability_semantics,
        ))
    return out
