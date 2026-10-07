"""Deterministic publication fixtures for ATH frontend contract tests."""
import pandas as pd
import pytest
from scripts.rebuild_publication_manifest import rebuild


@pytest.fixture(scope="session")
def ath_ui_publication(tmp_path_factory):
    # Test a complete publication, independent of the live build phase, its
    # unfinished manifest, and other tests that rewrite repository outputs.
    # These synthetic inputs are only test fixtures, never historical evidence.
    root = tmp_path_factory.mktemp("ath-ui-publication") / "public_data"
    root.mkdir()
    dates = pd.date_range("2024-01-01", periods=30)
    pd.DataFrame({
        "observation_date": dates.strftime("%Y-%m-%d"),
        "availability_date": (dates + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        "Open": 99., "High": 100., "Low": 98., "Close": 99.,
        "symbol": "TEST_FIXTURE",
    }).to_csv(root / "technical_intelligence_research_v1.csv", index=False)
    pd.DataFrame(columns=[
        "published_at", "availability_date", "title", "url", "source",
        "point_in_time_safe", "pit_status", "event_class", "is_duplicate",
    ]).to_csv(root / "event_news_research_v2.csv", index=False)
    pd.DataFrame([{
        "feature": "economic_inflation", "value": .7, "state": "MIXED",
        "as_of": "2024-01-01", "available_at": "2024-01-02",
        "age_days": 1, "freshness": "CURRENT", "pit_status": "PIT_SAFE",
        "quality": "MEDIUM", "eligible": True, "source": "TEST_FIXTURE",
    }]).to_csv(root / "unified_state_vector_v1.csv", index=False)
    rebuild(root, source="isolated-ath-ui-test-fixture")
    return root
