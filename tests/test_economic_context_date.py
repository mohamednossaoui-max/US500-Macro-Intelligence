from datetime import date
import pytest
from macro_context_v1 import resolve_context_date


def test_legacy_default_remains_fed_date():
 assert resolve_context_date('2026-09-01')==date(2026,9,1)


def test_verified_refresh_advances_context_without_backdating():
 assert resolve_context_date('2026-09-01','2026-09-02',today=date(2026,9,3))==date(2026,9,2)
 assert resolve_context_date('2026-09-02','2026-09-01',today=date(2026,9,3))==date(2026,9,2)


@pytest.mark.parametrize('invalid',['invalid','2026-09-04'])
def test_invalid_future_dates_fail_closed(invalid):
 with pytest.raises(ValueError):resolve_context_date('2026-09-01',invalid,today=date(2026,9,3))


from macro_context_v1 import verified_economic_context_date
from economic_official_sources_v1 import MAPPINGS


def status():
 return {'source_verification':'VERIFIED','as_of_date':'2026-09-02','indicators':[{'indicator':i,'status':'CURRENT','source_verification':'VERIFIED'} for i in MAPPINGS]}


def test_master_direct_run_recognizes_complete_status():
 assert verified_economic_context_date(status())=='2026-09-02'


@pytest.mark.parametrize('case',['failed','incomplete','duplicate'])
def test_unverified_status_cannot_advance_context(case):
 s=status()
 if case=='failed':s['indicators'][0]['source_verification']='METADATA_UNVERIFIED'
 if case=='incomplete':s['indicators'].pop()
 if case=='duplicate':s['indicators'][0]['indicator']=s['indicators'][1]['indicator']
 assert verified_economic_context_date(s) is None


def test_verified_status_requires_context_date():
 s=status();s.pop('as_of_date')
 with pytest.raises(ValueError):verified_economic_context_date(s)
