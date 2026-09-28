from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_economic_universe_is_not_legacy_seven():
    df = pd.read_csv(ROOT / "public_data" / "economic_historical_events_v1.csv")
    indicators = set(df["indicator"].dropna().astype(str))
    assert {"PCE_PRICE_INDEX", "CORE_PCE"} <= indicators
    assert len(indicators) > 7


def test_workflows_stage_canonical_input_not_legacy_expansion():
    for name in ["economic_intelligence_full_pipeline_v2.2.yml", "economic_intelligence_full_pipeline_v2.3_refresh.yml"]:
        text = (ROOT / ".github" / "workflows" / name).read_text()
        assert "python economic_canonical_input_v2.py" in text
        assert "run: python economic_historical_expansion_v2.2.py" not in text
