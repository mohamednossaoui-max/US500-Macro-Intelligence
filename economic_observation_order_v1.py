"""Deterministic reference-period and knowledge-time ordering, without source I/O."""
import pandas as pd

def period_key(value):
    import re
    value=str(value).strip()
    m=re.match(r'(Q[1-4]\s+\d{4})',value)
    if m:return m.group(1)
    if value.lower().startswith('week ending'):
        return 'W:'+pd.Timestamp(value[11:].strip()).strftime('%Y-%m-%d')
    try:return str(pd.Period(value,freq='M'))
    except ValueError:return value


def latest(df,indicator,period=None):
    rows=df[df.indicator==indicator].copy()
    if period is not None:
        rows=rows[rows.reference_period.map(period_key)==period_key(period)]
    if rows.empty:return None
    # Availability is authoritative for revised snapshots.
    order=pd.to_datetime(rows.get('available_as_of',rows.release_date),errors='coerce',utc=True).fillna(pd.to_datetime(rows.release_date,utc=True))
    def reference_order(ref):
        key=period_key(ref)
        if key.startswith('W:'):return pd.Timestamp(key[2:]).value
        if key.startswith('Q'):
            quarter,year=key.split();return pd.Period(year+quarter,freq='Q').end_time.value
        return pd.Period(key,freq='M').end_time.value
    rows=rows.assign(_reference=rows.reference_period.map(reference_order),_order=order,_n=range(len(rows))).sort_values(['_reference','_order','release_date','_n'],kind='mergesort')
    return rows.iloc[-1]

