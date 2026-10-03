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
from economic_indicator_details_v1 import ANNUAL_BLS, annual_bls, percent_change

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
    'RETAIL_SALES':dict(agency='Census',series='MARTS advance monthly sales, category 44X72, SM, seasonally_adj yes',units='percent monthly SA nominal change',url='https://api.census.gov/data/timeseries/eits/marts'),
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
    for name in ('BLS_API_KEY', 'CENSUS_API_KEY', 'BEA_API_KEY', 'FRED_API_KEY'):
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
        if series in ANNUAL_BLS.values():
            if not hasattr(self,'_bls_annual_batch'):
                year=pd.Timestamp.now(tz='UTC').year
                request={'seriesid':list(ANNUAL_BLS.values()),'startyear':str(year-1),'endyear':str(year)}
                if os.environ.get('BLS_API_KEY'):request['registrationkey']=os.environ['BLS_API_KEY']
                response=self.session.post('https://api.bls.gov/publicAPI/v2/timeseries/data/',json=request,timeout=30)
                response.raise_for_status();payload=response.json()
                if payload.get('status')!='REQUEST_SUCCEEDED':raise MetadataError('BLS annual batch failed')
                self.directory.mkdir(parents=True,exist_ok=True)
                (self.directory/'bls-official-annual-batch.json').write_text(json.dumps(payload,sort_keys=True))
                self._bls_annual_batch={x['seriesID']:x for x in payload['Results']['series']}
            if series not in self._bls_annual_batch:raise MetadataError('BLS annual batch omitted required series')
            return {'status':'REQUEST_SUCCEEDED','Results':{'series':[self._bls_annual_batch[series]]}}
        if getattr(self, '_bls_failure', None):
            raise RuntimeError(self._bls_failure)
        if not hasattr(self, '_bls_batch'):
            year=pd.Timestamp.now(tz='UTC').year
            request = {'seriesid': [v[0] for v in BLS.values()],'startyear':str(year-1),'endyear':str(year)}
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

    def post_public_form(self, url, data):
        """Read an official public archive form; never submits credentials."""
        if url != 'https://oui.doleta.gov/unemploy/archive.asp' or set(data) != {'report','year'}:
            raise MetadataError('Unsupported official public form')
        key = url + json.dumps(data, sort_keys=True)
        if key in self.cache:
            return self.cache[key]
        r = self.session.post(url, data=data, timeout=30)
        r.raise_for_status()
        if urlparse(r.url).hostname != 'oui.doleta.gov':
            raise MetadataError('DOL archive cross-host redirect requires review')
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / (hashlib.sha256(key.encode()).hexdigest()+'.bin')).write_bytes(r.content)
        self.cache[key] = r
        return r

    def get(self, url, **kwargs):
        # API keys are never included in evidence filenames or logs.
        key = url + str({k:v for k,v in kwargs.get('params',{}).items() if k not in ('key','registrationkey','UserID','api_key')})
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


def bls_release_context(client, group):
    """Explicit official-page alternate when RSS access fails; API values stay primary."""
    feed_url = f'https://www.bls.gov/feed/{group}.rss'
    try:
        return (*bls_context(client.get(feed_url).content, group), None)
    except requests.HTTPError as exc:
        failure = http_error_diagnostic(exc)
    except (MetadataError, ET.ParseError) as exc:
        failure = str(exc)
    url = f'https://www.bls.gov/news.release/{group}.nr0.htm'
    try:
        try:
            soup = BeautifulSoup(client.get(url).content, 'html.parser')
            pre = soup.find('pre')
            if pre is None:
                raise MetadataError('BLS current release has no official release text')
            text = ' '.join(pre.get_text(' ', strip=True).split())
        except requests.HTTPError as exc:
            failure += '; ' + http_error_diagnostic(exc)
            url = f'https://www.bls.gov/news.release/pdf/{group}.pdf'
            pdf = client.get(url).content
            if not pdf.startswith(b'%PDF'):
                raise MetadataError('BLS official PDF endpoint returned a non-PDF response')
            text = ' '.join(PdfReader(io.BytesIO(pdf)).pages[0].extract_text().split())
        embargo = re.search(r'embargoed until.{0,160}?(\d{1,2}:\d{2})\s*([ap])\.?m\.?\s*\(?(ET)\)?\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s*'+DATE, text, re.I)
        titles = {'empsit': 'THE EMPLOYMENT SITUATION', 'cpi': 'CONSUMER PRICE INDEX', 'ppi': 'PRODUCER PRICE INDEXES'}
        reference = re.search(titles[group]+r'\s*[-–—]\s*'+MONTH+r'\s+(\d{4})', text, re.I)
        if not embargo or not reference:
            raise MetadataError('BLS current release date/reference period unverified')
        rd = date_iso(' '.join(embargo.group(j) for j in (4,5,6)))
        rt = f'{embargo.group(1)} {embargo.group(2).upper()}M ET'
        period = f'{reference.group(1).title()} {reference.group(2)}'
        calendar_url = 'https://www.bls.gov/schedule/news_release/bls.ics'
        calendar_text = client.get(calendar_url).content.decode('utf-8-sig')
        calendar_text = re.sub(r'\r?\n[ \t]', '', calendar_text)
        labels = {'empsit':'Employment Situation', 'cpi':'Consumer Price Index', 'ppi':'Producer Price Index'}
        events = []
        for event in re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', calendar_text, re.S):
            summary = re.search(r'^SUMMARY:(.*)$', event, re.M)
            start = re.search(r'^DTSTART;TZID=(?:US-Eastern|America/New_York):(\d{8}T\d{6})\s*$', event, re.M)
            if summary and summary.group(1).strip() == labels[group] and start:
                events.append(pd.to_datetime(start.group(1), format='%Y%m%dT%H%M%S').tz_localize('America/New_York'))
        now = pd.Timestamp.now(tz='America/New_York')
        due = [d for d in events if d <= now]
        if not due or not any(d > now for d in events):
            raise MetadataError('BLS calendar coverage/latest due release unavailable')
        released = pd.Timestamp(f'{rd} {embargo.group(1)} {embargo.group(2).upper()}M').tz_localize('America/New_York')
        if released != max(due):
            raise MetadataError('BLS published release differs from latest due calendar release')
        return period, rd, rt, url, {'metadata_alternate_reason': failure, 'metadata_source_url': url, 'release_calendar_url': calendar_url}
    except requests.HTTPError as exc:
        raise MetadataError(f'BLS values available; release metadata unavailable: {failure}; {http_error_diagnostic(exc)}') from exc


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
        period,rd,rt,url,metadata_extra = bls_release_context(client,group)
    except (MetadataError, ET.ParseError) as exc:
        from economic_bls_fred_metadata_v1 import corroborate
        failure = str(exc)
        try:
            period,rd,rt,url,metadata_extra = corroborate(client,indicator,records[0]['data'],failure)
        except requests.HTTPError as alternate:
            failure += '; FRED alternate: ' + http_error_diagnostic(alternate)
            return [observation(indicator,values[-1][0],values[-1][1],None,None,MAPPINGS[indicator]['url'],verification_status='METADATA_UNVERIFIED',reason=failure)]
        except (MetadataError, ValueError, KeyError, TypeError, requests.RequestException) as alternate:
            failure += '; FRED alternate: ' + (str(alternate) if isinstance(alternate,MetadataError) else type(alternate).__name__)
            return [observation(indicator,values[-1][0],values[-1][1],None,None,MAPPINGS[indicator]['url'],verification_status='METADATA_UNVERIFIED',reason=failure)]
    if period != values[-1][0]:
        raise MetadataError('BLS API latest period differs from official release feed (publication lag)')
    out=[]
    # Capture current source values, including revisions, without backdating.
    for p,value,footnotes in values:
        out.append(observation(indicator,p,value,rd,rt,url,publication_status='PRELIMINARY' if any(f.get('code')=='P' for f in footnotes) else 'CURRENT_VINTAGE', release_time_verification='VERIFIED' if rt else 'METADATA_UNVERIFIED', original_release_date=None, value_source_url=MAPPINGS[indicator]['url'], latest_official_period=period, **(metadata_extra or {})))
    for index,row in enumerate(out):
        if method=='percent':row['mom']=row['actual']
        if index and pd.Period(row['reference_period'],freq='M')-1==pd.Period(out[index-1]['reference_period'],freq='M'):
            row['previous']=out[index-1]['actual']
    if indicator in ANNUAL_BLS or indicator=='AVERAGE_HOURLY_EARNINGS':
        annual_series=ANNUAL_BLS.get(indicator,series)
        latest_row=out[-1]
        latest_row.update(yoy_source_series=annual_series,yoy_source_url='https://api.bls.gov/publicAPI/v2/timeseries/data/'+annual_series,
                          yoy_method='12-month index change NSA' if indicator in ANNUAL_BLS else '12-month hourly earnings change SA')
        try:
            annual_data=records[0]['data'] if annual_series==series else client.bls_payload(annual_series)['Results']['series'][0]
            if annual_series!=series:
                if annual_data['seriesID']!=annual_series:raise ValueError('Annual series mismatch')
                annual_data=annual_data['data']
            latest_row['yoy']=annual_bls(annual_data,period)
            latest_row['yoy_verification_status']='VERIFIED'
        except (ValueError,KeyError,TypeError,AttributeError,requests.RequestException,RuntimeError) as exc:
            latest_row['yoy']=None
            latest_row['yoy_verification_status']='SOURCE_ERROR' if isinstance(exc,requests.RequestException) else 'METADATA_UNVERIFIED'
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
        return [observation(indicator,row['reference_period'],row['actual'],row['release_date'],row['release_time'],url,**{k:row[k] for k in ('previous','mom','yoy','yoy_method','yoy_verification_status','yoy_source_url') if k in row})]
    text=flat(html)
    rd,rt=release_timestamp(text)
    m=re.search(r'Real gross domestic product\s*\(GDP\)\s*(increased|decreased)\s*(?:at an annual rate of\s*)?(\d+(?:\.\d+)?)\s*percent\s*(?:at an annual rate\s*)?in the\s*(first|second|third|fourth)\s*quarter of\s*(\d{4})',text,re.I)
    if not m:
        raise MetadataError('Real GDP SA annual rate/reference quarter not identified')
    q=['first','second','third','fourth'].index(m.group(3).lower())+1
    return [observation(indicator,f'Q{q} {m.group(4)}',float(m.group(2))*(-1 if m.group(1).lower()=='decreased' else 1),rd,rt,url)]


def collect_claims(client):
    url=MAPPINGS['INITIAL_JOBLESS_CLAIMS']['url']
    alternate = None
    try:
        pdf = client.get(url).content
    except requests.HTTPError as exc:
        failure = http_error_diagnostic(exc)
        index_url = 'https://oui.doleta.gov/unemploy/claims_arch.asp'
        index = BeautifulSoup(client.get(index_url).content, 'html.parser')
        if 'published each week on Thursday' not in index.get_text(' ', strip=True):
            raise MetadataError('DOL official publication schedule unverified')
        now = pd.Timestamp.now(tz='America/New_York')
        regular = now.normalize()-pd.Timedelta(days=(now.weekday()-3)%7)
        if regular+pd.Timedelta(hours=8,minutes=30)>now:
            regular -= pd.Timedelta(days=7)
        scheduled = regular
        for tr in index.find_all('tr'):
            cells = tr.find_all('td')
            if len(cells) < 2:
                continue
            match = re.search(DATE, cells[0].get_text(' ',strip=True))
            if match:
                exception = pd.Timestamp(' '.join(match.groups())).tz_localize('America/New_York')
                # A holiday substitution belongs to the same Monday-Sunday week.
                week_start = exception-pd.Timedelta(days=exception.weekday())
                thursday = week_start+pd.Timedelta(days=3)
                if week_start <= now < week_start+pd.Timedelta(days=7):
                    scheduled = exception if exception+pd.Timedelta(hours=8,minutes=30)<=now else thursday-pd.Timedelta(days=7)
        candidates = []
        for year in {scheduled.year, now.year}:
            archive_url = 'https://oui.doleta.gov/unemploy/archive.asp'
            archive = BeautifulSoup(client.post_public_form(archive_url, {'report':'press','year':str(year)}).content,'html.parser')
            for a in archive.find_all('a',href=True):
                link = urljoin(archive_url,a['href'])
                match = re.fullmatch(r'/press/(\d{4})/(\d{2})(\d{2})(\d{2})\.pdf',urlparse(link).path)
                if urlparse(link).hostname == 'oui.doleta.gov' and match:
                    y,month,day,short_year=map(int,match.groups())
                    if y%100 != short_year:
                        raise MetadataError('DOL archive URL year mismatch')
                    date = pd.Timestamp(f'{y}-{month:02d}-{day:02d}').tz_localize('America/New_York')
                    if date+pd.Timedelta(hours=8,minutes=30)<=now:
                        candidates.append((date,link))
        if not candidates:
            raise MetadataError('DOL official archive has no published release')
        date,url = max(candidates)
        if date != scheduled:
            raise MetadataError('DOL archive is older than latest official scheduled release')
        pdf = client.get(url).content
        alternate = {'source_alternate_reason':failure,'source_discovery_url':index_url,'archive_release_date':date.strftime('%Y-%m-%d')}
    text=' '.join(PdfReader(io.BytesIO(pdf)).pages[0].extract_text().split())
    rd,rt=release_timestamp(text)
    if alternate and rd != alternate['archive_release_date']:
        raise MetadataError('DOL archive and PDF release dates disagree')
    m=re.search(r'In the week ending '+MONTH+r'\s+(\d{1,2})(?:,\s*(\d{4}))?,?\s+the advance figure for seasonally adjusted initial claims was\s+([\d,]+)',text,re.I)
    if not m:
        raise MetadataError('DOL seasonally adjusted advance claims missing')
    year=int(m.group(3) or rd[:4]);week=pd.Timestamp(f'{m.group(1)} {m.group(2)} {year}')
    if week>pd.Timestamp(rd):
        week=week.replace(year=year-1)
    row=observation('INITIAL_JOBLESS_CLAIMS','Week ending '+week.strftime('%B %d, %Y'),int(m.group(4).replace(',','')),rd,rt,url,publication_status='ADVANCE', **(alternate or {}))
    rev=re.search(r"previous week.s level was (?:revised (?:up|down) by [\d,]+ from [\d,]+ to|unrevised at)\s*([\d,]+)",text,re.I)
    rows=[row]
    if rev:
        row['previous']=float(rev.group(1).replace(',',''))
        rows.insert(0,observation('INITIAL_JOBLESS_CLAIMS','Week ending '+(week-timedelta(days=7)).strftime('%B %d, %Y'),row['previous'],rd,rt,url,publication_status='REVISED',latest_official_period=row['reference_period'], **(alternate or {})))
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
    # The official catalog distinguishes MARTS sales from MRTSADV inventories.
    catalog=client.get(base+'.json').json()
    datasets=catalog.get('dataset',[]) if isinstance(catalog,dict) else []
    if len(datasets)!=1 or datasets[0].get('c_dataset')!=['timeseries','eits','marts'] or not datasets[0].get('title','').endswith('Advance Monthly Sales for Retail and Food Services'):
        raise MetadataError('Census dataset is not verified advance retail and food services sales')
    response=client.get(base,params={'get':'cell_value,time_slot_date,time_slot_id,category_code,data_type_code,seasonally_adj','time':'from '+str(int(m.group(2))-1)+'-01 to '+pd.Timestamp.now(tz='UTC').strftime('%Y-%m'),'category_code':'44X72','data_type_code':'SM','seasonally_adj':'yes','for':'us:*','key':key})
    if hasattr(response,'content') and not response.content.strip():
        raise RuntimeError('Census sales API returned an empty response; no official observations verified')
    try:
        payload=response.json()
    except ValueError as exc:
        raise RuntimeError('Census sales API returned non-JSON; check API key activation and endpoint availability') from exc
    if not isinstance(payload,list) or len(payload)<3:
        raise ValueError('Census API missing observations')
    values={}
    for raw in payload[1:]:
        r=dict(zip(payload[0],raw))
        if (r['category_code'],r['data_type_code'],r['seasonally_adj'])!=('44X72','SM','yes'):
            raise ValueError('Census semantic selector mismatch')
        period_value=r.get('time_slot_date') or r.get('time')
        if not period_value:
            raise MetadataError('Census observation reference date unavailable')
        ref_month=pd.Period(period_value,freq='M')
        if ref_month in values:
            raise MetadataError('Duplicate Census reference period')
        values[ref_month]=float(r['cell_value'])
    ref=pd.Period(period,freq='M')
    if max(values)!=ref or ref-1 not in values:
        raise MetadataError('Census release/API reference period mismatch')
    actual=percent_change(values[ref],values[ref-1])
    details=dict(mom=actual,level=values[ref],price_adjusted=False,yoy_method='12-month nominal sales change SA',yoy_source_url=base,yoy_verification_status='METADATA_UNVERIFIED')
    if ref-2 in values:details['previous']=percent_change(values[ref-1],values[ref-2])
    if ref-12 in values:
        details.update(yoy=percent_change(values[ref],values[ref-12]),yoy_verification_status='VERIFIED')
    return [observation('RETAIL_SALES',period,actual,rd,rt,base,metadata_source_url=url,publication_status='REVISED' if notice else 'ADVANCE',**details)]


def ism_latest_release(client, kind):
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
    return released, calendar_url


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
    released, calendar_url = ism_latest_release(client, kind)
    if pd.Period(period,freq='M')!=pd.Period(released,freq='M')-1:
        raise MetadataError('ISM current-report period differs from latest dated calendar release')
    rd=released.strftime('%Y-%m-%d');rt='10:00 ET'

    return [observation(indicator,period,float(val.group(1)),rd,rt,url,metadata_source_url=calendar_url,source_discovery_url=discovery_url)]


def collect_ism_distributed_release(client, indicator, direct_failure):
    """Read ISM's publicly issued press release on its named distributor profile."""
    if indicator != 'ISM_MANUFACTURING_PMI':
        raise MetadataError('Distribution alternate is only verified for manufacturing')
    profile = 'https://www.prnewswire.com/news/institute-for-supply-management/'
    soup = BeautifulSoup(client.get(profile).text, 'html.parser')
    heading = soup.find('h1')
    if heading is None or not heading.get_text(' ',strip=True).startswith('News from Institute for Supply Management'):
        raise MetadataError('ISM distributor issuer profile unavailable')
    candidates = []
    for a in soup.find_all('a',href=True):
        label = a.get_text(' ',strip=True)
        ref = re.search(MONTH+r'\s+(\d{4})\s+ISM[^A-Za-z]*\s+Manufacturing PMI',label,re.I)
        url = urljoin(profile,a['href'])
        if ref and urlparse(url).hostname=='www.prnewswire.com' and urlparse(url).path.startswith('/news-releases/manufacturing-pmi-at-'):
            candidates.append((pd.Period(f'{ref.group(1)} {ref.group(2)}',freq='M'),url))
    if not candidates:
        raise MetadataError('ISM distributor has no manufacturing release')
    latest = max(p for p,u in candidates)
    urls = {u for p,u in candidates if p==latest}
    if len(urls)!=1:
        raise MetadataError('ISM distributor latest release ambiguous')
    url = urls.pop()
    article = BeautifulSoup(client.get(url).text,'html.parser')
    credit = next((h for h in article.find_all('h2') if h.get_text(' ',strip=True)=='News provided by'),None)
    issuer = credit.find_next_sibling('a') if credit else None
    if issuer is None or issuer.get_text(' ',strip=True)!='Institute for Supply Management' or urljoin(url,issuer.get('href',''))!=profile:
        raise MetadataError('Distributed release issuer is not verified ISM')
    headline = article.find('h1')
    title = headline.get_text(' ',strip=True) if headline else ''
    value = re.search(r'^Manufacturing PMI[^\d]{0,20}at\s+(\d+(?:\.\d+)?)%;\s*'+MONTH+r'\s+(\d{4})\s+ISM[^A-Za-z]*\s+Manufacturing PMI',title,re.I)
    if not value or pd.Period(f'{value.group(2)} {value.group(3)}',freq='M')!=latest:
        raise MetadataError('ISM distributed headline/reference period mismatch')
    schema = []
    for script in article.find_all('script',type='application/ld+json'):
        data = json.loads(script.get_text())
        if isinstance(data,dict) and data.get('@type')=='NewsArticle':schema.append(data)
    if len(schema)!=1 or schema[0].get('mainEntityOfPage',{}).get('@id')!=url or schema[0].get('headline')!=title:
        raise MetadataError('ISM distributed publication provenance unavailable')
    stamp = pd.Timestamp(schema[0].get('datePublished'))
    if pd.isna(stamp) or stamp.tzinfo is None:
        raise MetadataError('ISM distributed published timestamp unavailable')
    stamp = stamp.tz_convert('America/New_York')
    released,calendar_url = ism_latest_release(client,'pmi')
    expected = released.tz_localize('America/New_York')+pd.Timedelta(hours=10)
    if stamp!=expected or latest!=pd.Period(released,freq='M')-1:
        raise MetadataError('ISM distributed release differs from latest official dated calendar')
    body = flat(str(article))
    actual = re.search(r'The Manufacturing PMI[^\d]{0,25}registered\s+(\d+(?:\.\d+)?)\s+percent',body,re.I)
    if not actual or float(actual.group(1))!=float(value.group(1)):
        raise MetadataError('ISM distributed headline/body value mismatch')
    return [observation(indicator,latest.strftime('%B %Y'),float(value.group(1)),stamp.strftime('%Y-%m-%d'),'10:00 ET',url,
        source='ISM-issued press release distributed via PR Newswire',source_distribution='PR Newswire',
        source_discovery_url=profile,metadata_source_url=calendar_url,source_alternate_reason=direct_failure,
        release_time_verification='VERIFIED')]


def collect(client,indicator):
    agency=MAPPINGS[indicator]['agency']
    if agency=='BLS':return collect_bls(client,indicator)
    if agency=='BEA':return collect_bea(client,indicator)
    if agency=='DOL':return collect_claims(client)
    if agency=='Census':return collect_retail(client)
    try:
        return collect_ism(client,indicator)
    except (requests.HTTPError,RuntimeError,MetadataError) as exc:
        if indicator!='ISM_MANUFACTURING_PMI':
            raise
        reason=http_error_diagnostic(exc) if isinstance(exc,requests.HTTPError) else str(exc)
        return collect_ism_distributed_release(client,indicator,reason)
