"""Supplementary release metrics and display; never invent annual rates."""
from decimal import Decimal, ROUND_HALF_UP
from numbers import Real
import math
import pandas as pd

ANNUAL_BLS={'CPI':'CUUR0000SA0','CORE_CPI':'CUUR0000SA0L1E',
            'PPI_FINAL_DEMAND':'WPUFD4','CORE_PPI':'WPUFD49104'}
MONTHLY={'CPI','CORE_CPI','PPI_FINAL_DEMAND','CORE_PPI','PCE_PRICE_INDEX','CORE_PCE','AVERAGE_HOURLY_EARNINGS','RETAIL_SALES'}
DETAIL_FIELDS=('previous','mom','yoy','level','yoy_source_series','yoy_method','yoy_source_url','yoy_verification_status')


def numeric(value):
    return isinstance(value,Real) and math.isfinite(float(value))


def percent_change(current,prior):
    a,b=Decimal(str(current)),Decimal(str(prior))
    if not a.is_finite() or not b.is_finite() or b<=0:
        raise ValueError('Invalid rate baseline')
    return float(((a/b-1)*100).quantize(Decimal('0.1'),rounding=ROUND_HALF_UP))


def annual_bls(data,period):
    months={}
    for row in data:
        p=str(row.get('period',''))
        if len(p)!=3 or p[0]!='M' or not p[1:].isdigit() or not 1<=int(p[1:])<=12:continue
        key=pd.Period(f"{row['year']}-{p[1:]}",freq='M')
        try:value=Decimal(str(row['value']).replace(',',''))
        except Exception:continue
        if not value.is_finite():continue
        if key in months:raise ValueError('Duplicate annual-series period')
        months[key]=value
    ref=pd.Period(period,freq='M')
    if not months or max(months)!=ref or ref-12 not in months:
        raise ValueError('Annual series reference/baseline unavailable')
    return percent_change(months[ref],months[ref-12])


def detail_changed(old,new):
    """Only verified nonmissing enrichment, never erase prior metrics."""
    for field in DETAIL_FIELDS:
        value=new.get(field)
        if value is None or (isinstance(value,Real) and not numeric(value)):continue
        if field.startswith('yoy') and new.get('yoy_verification_status')!='VERIFIED':continue
        prior=old.get(field)
        if str(prior)!=str(value):
            if numeric(prior) and numeric(value) and abs(float(prior)-float(value))<1e-8:continue
            return True
    return False


def card_details(row):
    indicator=str(row.get('indicator',''));actual=row.get('actual');previous=row.get('previous')
    label='Previous (source)' if numeric(previous) else 'Prior published observation'
    if not numeric(previous):previous=row.get('delta_reference_value')
    previous_text='Previous: unavailable'
    reading='Reading: comparison unavailable'
    if numeric(previous) and numeric(actual):
        fmt=(lambda v:f'{v:,.0f}') if indicator in {'NFP','INITIAL_JOBLESS_CLAIMS'} else (lambda v:f'{v:.1f}')
        previous_text=f'{label}: {fmt(previous)} → Current: {fmt(actual)}'
        delta=float(actual)-float(previous)
        if indicator.startswith('ISM_'):
            reading=f"Reading: {'Expansion' if float(actual)>=50 else 'Contraction'}; "
        elif indicator=='GDP':reading='Reading: real GDP annualized quarterly growth; '
        else:reading='Reading: '
        reading+= 'higher than previous' if delta>1e-8 else 'lower than previous' if delta < -1e-8 else 'unchanged versus previous'
    elif indicator.startswith('ISM_') and numeric(actual):
        reading=f"Reading: {'Expansion' if float(actual)>=50 else 'Contraction'}; comparison unavailable"
    elif indicator=='GDP':reading='Reading: real GDP annualized quarterly growth'
    annual=''
    if indicator in MONTHLY and not numeric(row.get('yoy')):
        annual='YoY: unavailable — not source-verified'
    return previous_text,reading,annual
