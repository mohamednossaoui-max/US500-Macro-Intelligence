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
    x = d.iloc[-1]
    context_date = _context_date(p, x.availability_date)
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
