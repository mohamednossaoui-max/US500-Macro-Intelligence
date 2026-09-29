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
    d = pd.read_csv(p / 'market_breadth_analysis_v1.csv')
    x = d.iloc[-1]
    # The breadth record is only known through its last reconstructed market date.
    # Compare that date with the current Research Context date; never reset age to zero.
    context_date = _context_date(p, x.asof_date)
    pit = 'PIT_LIMITED' if not bool(x.pit_perfect) else 'PIT_SAFE'
    limitations = (
        'Historical constituent membership is a free-public reconstruction; '
        f'pit_perfect={str(bool(x.pit_perfect)).lower()}; '
        f'membership_quality={x.membership_quality}; price_pit_perfect={str(bool(x.price_pit_perfect)).lower()}'
    )
    return [row(
        'MARKET_BREADTH', 'BREADTH', 'Breadth State',
        state=x.breadth_research_state, value=x.coverage_pct, unit='coverage %',
        observation_date=x.asof_date,
        available_at=x.asof_date,
        as_of_date=context_date,
        source_name=x.membership_source,
        source_artifact='market_breadth_analysis_v1.csv',
        pit_status=pit,
        expected_frequency='DAILY',
        limitations=limitations,
    )]
