import pandas as pd
import pytest
from economic_official_ingestion_v1 import merged_status_reports


def fixture():
    events=pd.DataFrame([dict(indicator='NFP',reference_period='September 2026',release_date='2026-10-02',actual=29000)])
    reports=[dict(indicator='NFP',official_latest_reference_period='September 2026',official_release_date='2026-10-02',official_value=29000,canonical_latest_reference_period='August 2026',canonical_release_date='2026-09-04',canonical_value=162000,status='NEW_RELEASE',reason='New release',revision_detected=True,source_verification='VERIFIED')]
    return events,reports


def test_status_describes_merged_values_and_preserves_before_state():
    events,reports=fixture();updated=merged_status_reports(events,reports)[0]
    assert updated['status']=='CURRENT'
    assert updated['canonical_value']==updated['official_value']==29000
    assert updated['canonical_release_date']==updated['official_release_date']=='2026-10-02'
    assert updated['canonical_latest_reference_period']=='September 2026'
    assert updated['before_merge_canonical_value']==162000
    assert updated['ingestion_status']=='NEW_RELEASE' and updated['revision_detected']
    assert reports[0]['canonical_value']==162000 and reports[0]['status']=='NEW_RELEASE'
    assert merged_status_reports(events,reports)==merged_status_reports(events,reports)


def test_status_cannot_claim_current_without_parity():
    events,reports=fixture();events.loc[0,'actual']=162000
    with pytest.raises(RuntimeError,match='canonical gate'):
        merged_status_reports(events,reports)
