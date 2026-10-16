"""Exact release clocks where evidence supplies one; no inferred publication hour."""
import re
import pandas as pd

def official_release_at(row):
    value=row.get('release_time')
    if value is None or pd.isna(value):return None
    m=re.fullmatch(r'\s*(\d{1,2}):(\d{2})\s*([AP]M)?\s*(ET|EST|EDT|UTC|GMT)\s*',str(value),re.I)
    if not m:return None
    h,minute=int(m[1]),int(m[2]);ap=(m[3] or '').upper()
    if minute>59 or h>(12 if ap else 23) or (ap and h==0):return None
    if ap:h=h%12+(12 if ap=='PM' else 0)
    day=pd.Timestamp(row['release_date']).normalize()+pd.Timedelta(hours=h,minutes=minute)
    # ET observes DST; explicit EST/EDT is checked against the actual NY offset.
    zone=m[4].upper()
    ts=day.tz_localize('UTC' if zone in {'UTC','GMT'} else 'America/New_York',ambiguous='raise',nonexistent='raise')
    if zone in {'EST','EDT'} and ts.tzname()!=zone:return None
    return ts.tz_convert('UTC')
