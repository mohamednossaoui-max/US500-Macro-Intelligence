from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DATA = BASE_DIR / "public_data"
QUALITY_FILE = PUBLIC_DATA / "research_evidence_quality_v1.csv"
QUALITY_SUMMARY_FILE = PUBLIC_DATA / "research_evidence_quality_summary_v1.json"
CONTRACT_FILE = PUBLIC_DATA / "research_evidence_contract_v1.csv"
CONTEXT_SUMMARY_FILE = PUBLIC_DATA / "research_context_summary_v1.csv"

MODULE_GROUPS = {
    "economic": ["ECONOMIC"],
    "fed": ["FED"],
    "financial_stress": ["FINANCIAL_STRESS"],
    "liquidity": ["LIQUIDITY"],
    "sentiment": ["SENTIMENT_AAII", "SENTIMENT_VIX", "SENTIMENT_COT"],
    "technical": ["TECHNICAL"],
    "breadth": ["MARKET_BREADTH"],
    "cross_asset": ["CROSS_ASSET"],
}


def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def _rollup(frame: pd.DataFrame) -> dict[str, object]:
    total = len(frame)
    available = int((frame["availability_status"] == "AVAILABLE").sum())
    eligible = int(frame["decision_engine_eligible"].astype(bool).sum())
    pit_safe = int((frame["pit_status"] == "PIT_SAFE").sum())
    current = int((frame["freshness_status"] == "CURRENT").sum())
    high = int((frame["quality_status"] == "HIGH").sum())
    degraded = int(((frame["availability_status"] == "AVAILABLE") & ~frame["decision_engine_eligible"].astype(bool)).sum())
    pit_limited = int((frame["pit_status"] == "PIT_LIMITED").sum())
    if total == 0:
        quality = "INSUFFICIENT"
        pit = "UNKNOWN"
        freshness = "UNKNOWN"
    else:
        quality = "HIGH" if high == total else ("MEDIUM" if available and eligible else "LOW")
        pit = "PIT_SAFE" if pit_safe == total else ("PIT_LIMITED" if pit_limited else "UNKNOWN")
        freshness = "CURRENT" if current == total else ("AGING" if current else "STALE")
    return {
        "evidence_count": total,
        "available_count": available,
        "eligible_count": eligible,
        "excluded_count": total - eligible,
        "degraded_count": degraded,
        "quality_status": quality,
        "pit_status": pit,
        "freshness_status": freshness,
        "coverage_pct": _pct(available, total),
        "pit_safe_pct": _pct(pit_safe, total),
        "freshness_current_pct": _pct(current, total),
        "high_quality_pct": _pct(high, total),
    }


def integrate() -> pd.DataFrame:
    summary = pd.read_csv(CONTEXT_SUMMARY_FILE, low_memory=False)
    if summary.empty:
        raise RuntimeError("Research Context summary is empty")
    before_state = summary.iloc[-1].to_dict()
    q = pd.read_csv(QUALITY_FILE, low_memory=False)
    contract = pd.read_csv(CONTRACT_FILE, low_memory=False)
    meta = json.loads(QUALITY_SUMMARY_FILE.read_text(encoding="utf-8"))
    latest = summary.index[-1]
    overall = _rollup(q)
    summary.loc[latest, "evidence_as_of_date"] = meta.get("as_of_date", "")
    for key, value in overall.items():
        summary.loc[latest, f"evidence_{key}"] = value
    for prefix, modules in MODULE_GROUPS.items():
        sub = q[q["module"].isin(modules)]
        roll = _rollup(sub)
        for key, value in roll.items():
            summary.loc[latest, f"{prefix}_evidence_{key}"] = value
    # Preserve existing research states/scores exactly: integration is metadata-only.
    protected = [c for c in before_state if not c.startswith("evidence_") and "_evidence_" not in c]
    after = summary.iloc[-1]
    changed = [c for c in protected if str(before_state[c]) != str(after[c])]
    if changed:
        raise RuntimeError(f"Quality integration changed protected Research Context fields: {changed}")
    # Traceability: contract and quality must describe the same evidence IDs.
    if set(contract["evidence_id"]) != set(q["evidence_id"]):
        raise RuntimeError("Evidence contract/quality ID mismatch")
    summary.to_csv(CONTEXT_SUMMARY_FILE, index=False)
    return summary


if __name__ == "__main__":
    out = integrate()
    row = out.iloc[-1]
    print("Research Context quality integration PASS")
    print("Context date:", row.get("context_date"))
    print("Evidence as-of:", row.get("evidence_as_of_date"))
    print("Eligible:", int(row.get("evidence_eligible_count", 0)))
    print("PIT safe %:", row.get("evidence_pit_safe_pct"))
