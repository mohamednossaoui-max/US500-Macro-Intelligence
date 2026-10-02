"""Official economic adapters. Values and release metadata are separate evidence.

No consensus, cached-value fallback, or inferred release dates. A format change
fails closed. BLS values come from the API; release context comes from its feed.
"""
from __future__ import annotations
import calendar
import hashlib
import io
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

BLS = {
    'NFP': ('CES0000000001', 'empsit', 'difference_thousands', 'jobs, monthly SA change'),
    'UNEMPLOYMENT_RATE': ('LNS14000000', 'empsit', 'level', 'percent SA'),
    'AVERAGE_HOURLY_EARNINGS': ('CES0500000003', 'empsit', 'percent', 'percent monthly SA change, all employees total private'),
    'CPI': ('CUSR0000SA0', 'cpi', 'percent', 'percent monthly SA change, all urban consumers all items'),
    'CORE_CPI': ('CUSR0000SA0L1E', 'cpi', 'percent', 'percent monthly SA change, all items less food and energy'),
    'PPI_FINAL_DEMAND': ('WPSFD4', 'ppi', 'percent', 'percent monthly SA change, final demand'),
    'CORE_PPI': ('WPSFD49104', 'ppi', 'percent', 'percent monthly SA change, final demand less foods and energy'),
}
MAPPINGS = {i: {'agency':'BLS','series':v[0], 'units':v[3], 'url':'https://api.bls.gov/publicAPI/v2/timeseries/data/'+v[0]} for i,v in BLS.items()}
MAPPINGS.update({
    'GDP':dict(agency='BEA',series='NIPA T10101 A191RL / real GDP annualized quarterly growth',units='percent SA annual rate',url='https://www.bea.gov/news/current-releases'),
    'PCE_PRICE_INDEX':dict(agency='BEA',series='Personal Income and Outlays / PCE monthly price change',units='percent monthly change',url='https://www.bea.gov/news/current-releases'),
    'CORE_PCE':dict(agency='BEA',series='Personal Income and Outlays / PCE excluding food and energy monthly price change',units='percent monthly change',url='https://www.bea.gov/news/current-releases'),
    'RETAIL_SALES':dict(agency='Census',series='MRTSADV category 44X72, SM, seasonally_adj yes',units='percent monthly SA nominal change',url='https://api.census.gov/data/timeseries/eits/mrtsadv'),
    'INITIAL_JOBLESS_CLAIMS':dict(agency='DOL',series='UI weekly initial claims SA',units='claims',url='https://www.dol.gov/ui/data.pdf'),
    'ISM_MANUFACTURING_PMI':dict(agency='ISM',series='Manufacturing headline PMI composite',units='diffusion index',url='https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/'),
    'ISM_SERVICES_PMI':dict(agency='ISM',series='Services headline PMI composite',units='diffusion index',url='https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/'),
})
MONTH = r'(January|February|March|April|May|June|July|August|September|October|November|December)'
DATE = MONTH + r'\s+(\d{1,2}),?\s+(\d{4})'

class MetadataError(ValueError):
    pass

def http_error_diagnostic(exc):
    """Describe endpoint/status without response text, query strings or secrets."""
    response = getattr(exc, 'response', None)
    request = getattr(exc, 'request', None)
    if request is None and response is not None:
        request = getattr(response, 'request', None)
    url = getattr(request, 'url', None) or getattr(response, 'url', '') or ''
    parsed = urlparse(url)
    endpoint = (parsed.scheme + '://' + (parsed.hostname or '') + parsed.path
                if parsed.scheme in ('https', 'http') and parsed.hostname else 'unknown endpoint')
    for name in ('BLS_API_KEY', 'CENSUS_API_KEY', 'BEA_API_KEY'):
        secret = os.environ.get(name, '').strip()
        if secret:
            endpoint = endpoint.replace(secret, '[REDACTED]')
    status = getattr(response, 'status_code', None)
    method = getattr(request, 'method', None) or 'UNKNOWN'
    return f'HTTPError status={status if status is not None else "unknown"} method={method} endpoint={endpoint}'


class Client:
    def __init__(self, evidence_dir):
        self.directory = evidence_dir
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'US500-Macro-Intelligence official economic research ingestion/1.0'
        self.cache = {}

    def bls_payload(self, series):
        """One official API request for the seven series reduces rate-limit use."""
        if getattr(self, '_bls_failure', None):
            raise RuntimeError(self._bls_failure)
        if not hasattr(self, '_bls_batch'):
            request = {'seriesid': [v[0] for v in BLS.values()]}
            if os.environ.get('BLS_API_KEY'):
                request['registrationkey'] = os.environ['BLS_API_KEY']
            response = self.session.post('https://api.bls.gov/publicAPI/v2/timeseries/data/', json=request, timeout=30)
            response.raise_for_status()
            payload = response.json()
            if payload.get('status') != 'REQUEST_SUCCEEDED':
                self._bls_failure = 'BLS official batch request failed (check rate limits or BLS_API_KEY)'
                raise RuntimeError(self._bls_failure)
            self.directory.mkdir(parents=True, exist_ok=True)
            (self.directory/'bls-official-batch.json').write_text(json.dumps(payload, sort_keys=True))
            self._bls_batch = {x['seriesID']: x for x in payload['Results']['series']}
        if series not in self._bls_batch:
            raise MetadataError('BLS batch omitted required series')
        return {'status': 'REQUEST_SUCCEEDED', 'Results': {'series': [self._bls_batch[series]]}}

    def get(self, url, **kwargs):
        # API keys are never included in evidence filenames or logs.
        key = url + str({k:v for k,v in kwargs.get('params',{}).items() if k not in ('key','registrationkey','UserID')})
        if key in self.cache:
            return self.cache[key]
        r = self.session.get(url, timeout=30, **kwargs)
        r.raise_for_status()
        expected, actual = urlparse(url).hostname, urlparse(r.url).hostname
        if actual=='ecommerce.ismworld.org':
            raise RuntimeError('ISM official current report redirects to authenticated/licensed access')
        if actual != expected and {actual,expected}!={'www.ismworld.org','ismworld.org'}:
            raise MetadataError('Cross-host redirect requires review')
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / (hashlib.sha256(key.encode()).hexdigest()+'.bin')).write_bytes(r.content)
        self.cache[key] = r
        return r


def flat(html):
    return ' '.join(BeautifulSoup(html, 'html.parser').stripped_strings)


def date_iso(text):
    return pd.Timestamp(text).strftime('%Y-%m-%d')


def release_timestamp(text):
    """Require a source embargo/release line, not a modification date."""
    m = re.search(r'(?:EMBARGOED UNTIL(?: RELEASE AT)?|FOR RELEASE AT|EMBARGOED UNTIL RELEASE AT)\s*([\d:]+)\s*([AP])\.?\s*M\.?\s*\(?([A-Z]{2,7})\)?\s*,?\s*(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s*)?'+DATE, text, re.I)
    if not m:
        raise MetadataError('Official embargo/release timestamp unavailable')
    return date_iso(' '.join(m.group(j) for j in (4,5,6))), m.group(1)+' '+m.group(2).upper()+'M '+m.group(3).upper()


def observation(indicator, period, value, release, time, url, **extra):
    mapping = MAPPINGS[indicator]
    row = dict(indicator=indicator, agency=mapping['agency'], reference_period=period,
               release_date=release, release_time=time, actual=float(value), previous=None,
               revision=None, vintage_date=release, source=mapping['agency']+' official release',
               source_url=url, source_series=mapping['series'], units=mapping['units'],
               publication_status='CURRENT_VINTAGE', verification_status='VERIFIED',
               consensus=None, consensus_source=None)
    row.update(extra)
    return row


def bls_context(xml, group):
    root = ET.fromstring(xml)
    entries = root.findall('{http://www.w3.org/2005/Atom}entry') or root.findall('.//item')
    candidates = []
    for e in entries:
        text = ' '.join(e.itertext())
        stamp = e.findtext('{http://www.w3.org/2005/Atom}published') or e.findtext('pubDate')
        if not stamp:
            raise MetadataError('BLS feed has no published timestamp')
        ts = pd.to_datetime(stamp, utc=True)
        link = e.find('{http://www.w3.org/2005/Atom}link')
        url = link.get('href') if link is not None else e.findtext('link')
        if not url or urlparse(url).hostname not in ('www.bls.gov','bls.gov'):
            raise MetadataError('BLS release provenance unavailable')
        archive = re.search(r'/'+group+r'_(\d{2})(\d{2})(\d{4})\.htm',url)
        month = re.search(r'(?:in|for|during)\s+'+MONTH+r'\b',text,re.I)
        if not archive or not month:
            continue
        rd = pd.Timestamp(f'{archive.group(3)}-{archive.group(1)}-{archive.group(2)}')
        if rd.strftime('%Y-%m-%d') != ts.tz_convert('America/New_York').strftime('%Y-%m-%d'):
            raise MetadataError('BLS archive and feed release dates disagree')
        # The feed explicitly names the month. Its year must be confirmed
        # against the API and cannot be newer than the release date.
        year=rd.year-(list(calendar.month_name).index(month.group(1).title())>rd.month)
        candidates.append((ts, f'{month.group(1).title()} {year}', url))
    if not candidates:
        raise MetadataError('No release/reference period in BLS official feed')
    ts, period, url = max(candidates)
    local = ts.tz_convert('America/New_York')
    return period, local.strftime('%Y-%m-%d'), None, url


def transform_bls(data, method):
    months = {f"{d['year']}-{d['period'][1:]}":d for d in data if re.fullmatch(r'M(0[1-9]|1[0-2])',d['period']) and re.fullmatch(r'-?\d+(?:\.\d+)?',str(d['value']).replace(',',''))}
    result = []
    for p,d in sorted(months.items()):
        period = pd.Period(p,freq='M')
        value = Decimal(str(d['value']).replace(',',''))
        previous = months.get(str(period-1))
        if method != 'level':
            if previous is None:
                continue
            old = Decimal(str(previous['value']).replace(',',''))
            if method == 'difference_thousands':
                value = (value-old)*1000
            else:
                if old <= 0:
                    raise ValueError('Nonpositive index/earnings baseline')
                value = ((value/old-1)*100).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
        result.append((period.strftime('%B %Y'),float(value),d.get('footnotes',[])))
    if not result:
        raise ValueError('No complete BLS observation')
    return result


def collect_bls(client, indicator):
    series,group,method,_ = BLS[indicator]
    data = client.bls_payload(series) if hasattr(client, 'bls_payload') else client.get(MAPPINGS[indicator]['url']).json()
    if data.get('status') != 'REQUEST_SUCCEEDED':
        raise RuntimeError('BLS API request not successful')
    records = data['Results']['series']
    if len(records) != 1 or records[0]['seriesID'] != series:
        raise ValueError('BLS series mismatch')
    values = transform_bls(records[0]['data'],method)
    api_latest=max(f"{d['year']}-{d['period'][1:]}" for d in records[0]['data'] if re.fullmatch(r'M(0[1-9]|1[0-2])',d['period']))
    if pd.Period(values[-1][0],freq='M')!=pd.Period(api_latest,freq='M'):
        raise MetadataError('Latest BLS value unavailable; refuse previous-month fallback')
    # Value available even if metadata endpoint is blocked; never invent dates.
    try:
        period,rd,rt,url = bls_context(client.get(f'https://www.bls.gov/feed/{group}.rss').content,group)
    except (MetadataError, ET.ParseError) as exc:
        return [observation(indicator, values[-1][0],values[-1][1],None,None,MAPPINGS[indicator]['url'],verification_status='METADATA_UNVERIFIED',reason=str(exc))]
    if period != values[-1][0]:
        raise MetadataError('BLS API latest period differs from official release feed (publication lag)')
    out=[]
    # Capture current source values, including revisions, without backdating.
    for p,value,footnotes in values:
        out.append(observation(indicator,p,value,rd,rt,url,publication_status='PRELIMINARY' if any(f.get('code')=='P' for f in footnotes) else 'CURRENT_VINTAGE', release_time_verification='METADATA_UNVERIFIED', original_release_date=None, value_source_url=MAPPINGS[indicator]['url'], latest_official_period=period))
    if len(out)>1:
        out[-1]['previous']=out[-2]['actual']
    return out


def discover_bea(client, kind):
    url='https://www.bea.gov/news/current-releases'
    soup=BeautifulSoup(client.get(url).text,'html.parser')
    for a in soup.find_all('a',href=True):
        label=a.get_text(' ',strip=True)
        if (kind=='pce' and label.startswith('Personal Income and Outlays,')) or (kind=='gdp' and re.match(r'(?:GDP|Gross Domestic Product)\s*\(',label)):
            target=urljoin(url,a['href'])
            if urlparse(target).hostname!='www.bea.gov':
                raise MetadataError('BEA link host mismatch')
            return target
    raise MetadataError('Latest national BEA release not found')


def collect_bea(client,indicator):
    kind='gdp' if indicator=='GDP' else 'pce'
    url=discover_bea(client,kind)
    html=client.get(url).text
    if kind=='pce':
        from economic_pce_historical_backfill_v2 import parse_bea_release
        try:
            rows=parse_bea_release(html,url)
        except ValueError as exc:
            raise MetadataError(str(exc)) from exc
        row=next(r for r in rows if r['indicator']==indicator)
        return [observation(indicator,row['reference_period'],row['actual'],row['release_date'],row['release_time'],url)]
    text=flat(html)
    rd,rt=release_timestamp(text)
    m=re.search(r'Real gross domestic product\s*\(GDP\)\s*(increased|decreased)\s*(?:at an annual rate of\s*)?(\d+(?:\.\d+)?)\s*percent\s*(?:at an annual rate\s*)?in the\s*(first|second|third|fourth)\s*quarter of\s*(\d{4})',text,re.I)
    if not m:
        raise MetadataError('Real GDP SA annual rate/reference quarter not identified')
    q=['first','second','third','fourth'].index(m.group(3).lower())+1
    return [observation(indicator,f'Q{q} {m.group(4)}',float(m.group(2))*(-1 if m.group(1).lower()=='decreased' else 1),rd,rt,url)]


def collect_claims(client):
    url=MAPPINGS['INITIAL_JOBLESS_CLAIMS']['url']
    text=' '.join(PdfReader(io.BytesIO(client.get(url).content)).pages[0].extract_text().split())
    rd,rt=release_timestamp(text)
    m=re.search(r'In the week ending '+MONTH+r'\s+(\d{1,2})(?:,\s*(\d{4}))?,?\s+the advance figure for seasonally adjusted initial claims was\s+([\d,]+)',text,re.I)
    if not m:
        raise MetadataError('DOL seasonally adjusted advance claims missing')
    year=int(m.group(3) or rd[:4]);week=pd.Timestamp(f'{m.group(1)} {m.group(2)} {year}')
    if week>pd.Timestamp(rd):
        week=week.replace(year=year-1)
    row=observation('INITIAL_JOBLESS_CLAIMS','Week ending '+week.strftime('%B %d, %Y'),int(m.group(4).replace(',','')),rd,rt,url,publication_status='ADVANCE')
    rev=re.search(r"previous week.s level was (?:revised (?:up|down) by [\d,]+ from [\d,]+ to|unrevised at)\s*([\d,]+)",text,re.I)
    rows=[row]
    if rev:
        row['previous']=float(rev.group(1).replace(',',''))
        rows.insert(0,observation('INITIAL_JOBLESS_CLAIMS','Week ending '+(week-timedelta(days=7)).strftime('%B %d, %Y'),row['previous'],rd,rt,url,publication_status='REVISED',latest_official_period=row['reference_period']))
    return rows


def collect_retail(client):
    url='https://www.census.gov/retail/marts/www/marts_current.pdf'
    text=' '.join(PdfReader(io.BytesIO(client.get(url).content)).pages[0].extract_text().split())
    rd,rt=release_timestamp(text)
    m=re.search(r'ADVANCE MONTHLY SALES FOR RETAIL AND FOOD SERVICES,\s*'+MONTH+r'\s+(\d{4})',text,re.I)
    if not m:
        raise MetadataError('Census advance reference period missing')
    period=f'{m.group(1).title()} {m.group(2)}'
    # Current PDF can explicitly be superseded by an annual revision.
    notice=re.search(r'Revised not adjusted estimates and corresponding adjusted estimates were released on\s+'+DATE+r'\s+at\s+([\d:]+)\s*([ap])\.m\.\s*([A-Z]+)',text,re.I)
    if notice:
        rd=date_iso(' '.join(notice.group(j) for j in (1,2,3)));rt=f'{notice.group(4)} {notice.group(5).upper()}M {notice.group(6).upper()}'
    key=os.environ.get('CENSUS_API_KEY')
    if not key:
        return [dict(indicator='RETAIL_SALES',reference_period=period,release_date=rd,release_time=rt,actual=None,verification_status='SOURCE_ERROR',metadata_source_url=url,reason='CENSUS_API_KEY required for current/revised official retail estimates')]
    # Verify runtime category/data type labels; do not silently use a different universe.
    base=MAPPINGS['RETAIL_SALES']['url']
    payload=client.get(base,params={'get':'cell_value,time,category_code,data_type_code,seasonally_adj','time':'from '+str(int(m.group(2))-1)+'-01','category_code':'44X72','data_type_code':'SM','seasonally_adj':'yes','for':'us:*','key':key}).json()
    if not isinstance(payload,list) or len(payload)<3:
        raise ValueError('Census API missing observations')
    values={}
    for raw in payload[1:]:
        r=dict(zip(payload[0],raw))
        if (r['category_code'],r['data_type_code'],r['seasonally_adj'])!=('44X72','SM','yes'):
            raise ValueError('Census semantic selector mismatch')
        values[pd.Period(r['time'],freq='M')]=float(r['cell_value'])
    ref=pd.Period(period,freq='M')
    if max(values)!=ref or ref-1 not in values:
        raise MetadataError('Census release/API reference period mismatch')
    actual=round((values[ref]/values[ref-1]-1)*100,1)
    return [observation('RETAIL_SALES',period,actual,rd,rt,base,metadata_source_url=url,publication_status='REVISED' if notice else 'ADVANCE')]


def collect_ism(client,indicator):
    # Discover the dated public release, never a membership/catalog link.
    base=MAPPINGS[indicator]['url']
    soup=BeautifulSoup(client.get(base).text,'html.parser')
    kind='services' if indicator=='ISM_SERVICES_PMI' else 'pmi'
    labels={'View Report','Read More'} if kind=='pmi' else {'View Report'}
    links=sorted({urljoin(base,a['href']) for a in soup.find_all('a',href=True) if a.get_text(' ',strip=True) in labels and f'/ism-pmi-reports/{kind}/' in a['href']})
    discovery_url=base
    if not links and kind=='pmi':
        discovery_url='https://www.ismworld.org/'
        home=BeautifulSoup(client.get(discovery_url).text,'html.parser')
        links=sorted({urljoin(discovery_url,a['href']) for a in home.find_all('a',href=True) if a.get_text(' ',strip=True) in labels and '/ism-pmi-reports/pmi/' in a['href']})
    if len(links)!=1 or urlparse(links[0]).hostname!='www.ismworld.org':
        raise MetadataError('ISM current report discovery ambiguous')
    url=links[0];html=client.get(url).text;text=flat(html)
    sector='Services' if kind=='services' else 'Manufacturing'
    m=re.search(MONTH+r'\s+(\d{4})\s+(?:ISM[^A-Za-z]*\s+)?'+sector+r'\s+(?:ISM[^A-Za-z]*\s+)?PMI',text,re.I)
    if not m:
        raise MetadataError('ISM report year/month missing')
    period=f'{m.group(1).title()} {m.group(2)}'
    val=re.search(r'(?:The\s+)?'+sector+r'\s+PMI[^\d]{0,100}?(\d{2}\.\d)\s*percent',text,re.I)
    if not val:
        raise MetadataError('ISM headline composite PMI not identified')
    # The current report has no publication date in many ISM templates.
    # Join its explicitly named reference period to the official dated calendar;
    # require it to equal the latest release already due for this sector.
    calendar_url='https://www.ismworld.org/supply-management-news-and-reports/reports/rob-report-calendar/'
    cal=BeautifulSoup(client.get(calendar_url).text,'html.parser')
    dates=[]
    column=2 if kind=='services' else 1
    for tr in cal.find_all('tr'):
        cells=tr.find_all(['td','th'])
        if len(cells)<3:continue
        label=cells[0].get_text(' ',strip=True)
        cm=re.fullmatch(MONTH+r'\s+(\d{4})',label,re.I)
        day=re.match(r'^(\d{1,2})',cells[column].get_text(' ',strip=True))
        if cm and day:
            dates.append(pd.Timestamp(f'{cm.group(1)} {day.group(1)} {cm.group(2)}'))
    now=pd.Timestamp.now(tz='America/New_York')
    due=[d for d in dates if d.tz_localize('America/New_York')+pd.Timedelta(hours=10)<=now]
    if not due:
        raise MetadataError('ISM explicit release calendar unavailable')
    released=max(due)
    if pd.Period(period,freq='M')!=pd.Period(released,freq='M')-1:
        raise MetadataError('ISM current-report period differs from latest dated calendar release')
    rd=released.strftime('%Y-%m-%d');rt='10:00 ET'

    return [observation(indicator,period,float(val.group(1)),rd,rt,url,metadata_source_url=calendar_url,source_discovery_url=discovery_url)]


def collect(client,indicator):
    agency=MAPPINGS[indicator]['agency']
    if agency=='BLS':return collect_bls(client,indicator)
    if agency=='BEA':return collect_bea(client,indicator)
    if agency=='DOL':return collect_claims(client)
    if agency=='Census':return collect_retail(client)
    return collect_ism(client,indicator)
