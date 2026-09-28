"""Economic Intelligence canonical-input bridge v2.

Fail-closed bridge used by CI workflows.  It copies the repository's canonical
PIT historical event/quality artifacts from public_data into the workspace
filenames consumed by the existing Surprise/Regime engines.  It deliberately
does not synthesize, refresh, or revise observations.
"""
from pathlib import Path
import shutil
import pandas as pd

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public_data"
EVENTS = "economic_historical_events_v1.csv"
QUALITY = "economic_historical_quality_v1.csv"
REQUIRED_EXTENDED = {"PCE_PRICE_INDEX", "CORE_PCE"}
LEGACY_SEVEN = {
    "CPI", "CORE_CPI", "NFP", "UNEMPLOYMENT_RATE",
    "INITIAL_JOBLESS_CLAIMS", "ISM_MANUFACTURING_PMI", "GDP",
}


def stage_canonical_input() -> dict:
    src_events = PUBLIC / EVENTS
    src_quality = PUBLIC / QUALITY
    if not src_events.exists() or not src_quality.exists():
        raise FileNotFoundError("Canonical Economic artifacts are missing from public_data/")

    df = pd.read_csv(src_events)
    if "indicator" not in df.columns or "release_date" not in df.columns:
        raise ValueError("Canonical Economic events schema is incomplete")
    indicators = set(df["indicator"].dropna().astype(str))
    missing = REQUIRED_EXTENDED - indicators
    if missing:
        raise RuntimeError(f"Canonical Economic universe missing required extended indicators: {sorted(missing)}")
    if indicators <= LEGACY_SEVEN:
        raise RuntimeError("Refusing legacy seven-indicator Economic input")

    q = pd.read_csv(src_quality)
    pit_col = "point_in_time_safe" if "point_in_time_safe" in q.columns else "pit_safe" if "pit_safe" in q.columns else None
    if pit_col is None or not q[pit_col].fillna(False).astype(bool).all():
        raise RuntimeError("Canonical Economic quality artifact is not fully PIT-safe")

    shutil.copy2(src_events, ROOT / EVENTS)
    shutil.copy2(src_quality, ROOT / QUALITY)
    return {
        "records": len(df),
        "indicators": len(indicators),
        "latest_release": str(pd.to_datetime(df["release_date"], errors="coerce").max().date()),
    }


if __name__ == "__main__":
    result = stage_canonical_input()
    print("CANONICAL ECONOMIC INPUT: PASS")
    print(result)
