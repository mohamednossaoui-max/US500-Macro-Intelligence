"""Explicit BLS metadata corroboration through the St. Louis Fed FRED API.

BLS remains the value source. FRED release dates, ALFRED vintage dates and an
as-of-release snapshot must all agree. Neither last_updated nor a monthly
observation date is substituted for a release date. No release time is inferred.
"""
from decimal import Decimal
import os
from urllib.parse import urlparse
import pandas as pd

# Reviewed against the official FRED series pages (see patch notes).
SERIES = {
    'NFP': ('PAYEMS', 'All Employees, Total Nonfarm', 'Thousands of Persons'),
    'UNEMPLOYMENT_RATE': ('UNRATE', 'Unemployment Rate', 'Percent'),
    'AVERAGE_HOURLY_EARNINGS': ('CES0500000003', 'Average Hourly Earnings of All Employees, Total Private', 'Dollars per Hour'),
    'CPI': ('CPIAUCSL', 'Consumer Price Index for All Urban Consumers: All Items in U.S. City Average', 'Index 1982-1984=100'),
    'CORE_CPI': ('CPILFESL', 'Consumer Price Index for All Urban Consumers: All Items Less Food and Energy in U.S. City Average', 'Index 1982-1984=100'),
    'PPI_FINAL_DEMAND': ('PPIFIS', 'Producer Price Index by Commodity: Final Demand', 'Index Nov 2009=100'),
    'CORE_PPI': ('PPIFES', 'Producer Price Index by Commodity: Final Demand: Final Demand Less Foods and Energy', 'Index Apr 2010=100'),
}
BASE = 'https://api.stlouisfed.org/fred/'


def corroborate(client, indicator, bls_records, failure, now=None):
    from economic_official_sources_v1 import BLS, MetadataError
    key = os.environ.get('FRED_API_KEY', '').strip()
    if not key:
        raise MetadataError('FRED metadata alternate requires FRED_API_KEY')
    sid, title, units = SERIES[indicator]
    bls_series, group, _, _ = BLS[indicator]
    names = {'empsit': 'Employment Situation', 'cpi': 'Consumer Price Index', 'ppi': 'Producer Price Index'}
    now = pd.Timestamp(now or pd.Timestamp.now(tz='America/New_York'))
    today = now.tz_convert('America/New_York').strftime('%Y-%m-%d')

    def fetch(endpoint, **params):
        payload = client.get(BASE+endpoint, params=dict(api_key=key, file_type='json', **params)).json()
        if not isinstance(payload, dict) or 'error_code' in payload:
            raise MetadataError('FRED metadata response invalid')
        return payload

    meta = fetch('series', series_id=sid).get('seriess', [])
    if len(meta) != 1 or meta[0].get('id') != sid or meta[0].get('title') != title or meta[0].get('units') != units or meta[0].get('frequency') != 'Monthly' or meta[0].get('seasonal_adjustment') != 'Seasonally Adjusted':
        raise MetadataError('FRED series semantics mismatch')
    if group == 'empsit' and bls_series not in meta[0].get('notes', ''):
        raise MetadataError('FRED BLS source-series code mismatch')
    releases = fetch('series/release', series_id=sid).get('releases', [])
    if len(releases) != 1 or releases[0].get('name') != names[group] or urlparse(releases[0].get('link', '')).hostname not in ('www.bls.gov', 'bls.gov'):
        raise MetadataError('FRED release provenance mismatch')
    rid = releases[0]['id']  # Discovered, never a guessed release ID.
    source = fetch('release/sources', release_id=rid).get('sources', [])
    if len(source) != 1 or source[0].get('name') != 'U.S. Bureau of Labor Statistics' or urlparse(source[0].get('link', '')).hostname not in ('www.bls.gov', 'bls.gov'):
        raise MetadataError('FRED release source is not BLS')
    # Include future/no-data dates so publication lag cannot silently pass.
    dates = fetch('release/dates', release_id=rid, sort_order='desc', limit=100,
                  include_release_dates_with_no_data='true').get('release_dates', [])
    if any(str(d.get('release_id')) != str(rid) for d in dates):
        raise MetadataError('FRED release-date identity mismatch')
    days = [pd.Timestamp(d['date']).strftime('%Y-%m-%d') for d in dates]
    due = [d for d in days if d <= today]
    if not due or not any(d > today for d in days):
        raise MetadataError('FRED release calendar lacks current/future coverage')
    rd = max(due)
    vintages = fetch('series/vintagedates', series_id=sid, sort_order='desc', limit=1,
                     realtime_end=today).get('vintage_dates', [])
    if len(vintages) != 1 or vintages[0] != rd:
        raise MetadataError('FRED latest vintage differs from latest source release; refuse lag/revision ambiguity')
    updated = pd.Timestamp(meta[0]['last_updated'])
    if updated.tzinfo is None or updated.tz_convert('America/New_York').strftime('%Y-%m-%d') < rd or updated > now:
        raise MetadataError('FRED series update cannot confirm published release')
    # Match the full BLS API window, including revision baselines, at that vintage.
    records = {f"{d['year']}-{d['period'][1:]}": Decimal(str(d['value']).replace(',', ''))
               for d in bls_records if d['period'].startswith('M') and d['period'] != 'M13'
               and str(d['value']).replace(',', '').replace('.', '', 1).lstrip('-').isdigit()}
    if not records:
        raise MetadataError('No numeric BLS window for FRED corroboration')
    obs = fetch('series/observations', series_id=sid, realtime_start=rd, realtime_end=rd,
                observation_start=min(records)+'-01', units='lin', sort_order='desc', limit=100000)
    rows = obs.get('observations', [])
    if int(obs.get('count', len(rows))) != len(rows):
        raise MetadataError('FRED observation window truncated')
    seen = {}
    for row in rows:
        period = str(pd.Period(row['date'], freq='M'))
        if period in seen:
            raise MetadataError('FRED duplicate reference period')
        seen[period] = row['value']
    if not seen or max(seen) != max(records) or meta[0].get('observation_end') != max(records)+'-01':
        raise MetadataError('BLS/FRED latest reference periods differ')
    for period, value in records.items():
        if period not in seen or seen[period] == '.' or Decimal(seen[period]) != value:
            raise MetadataError('BLS/FRED raw values or revision baselines differ')
    return (pd.Period(max(records), freq='M').strftime('%B %Y'), rd, None,
            'https://fred.stlouisfed.org/series/'+sid,
            dict(metadata_provider='FRED_ALFRED', metadata_verification='BLS_VALUE_FRED_RELEASE_VINTAGE_PARITY',
                 metadata_source_url=BASE+'release/dates', metadata_series=sid,
                 metadata_release_id=rid, source_alternate_reason=failure,
                 fred_vintage_date=vintages[0], fred_last_updated=meta[0]['last_updated'],
                 source='BLS API values; release/vintage corroborated via St. Louis Fed FRED/ALFRED'))
