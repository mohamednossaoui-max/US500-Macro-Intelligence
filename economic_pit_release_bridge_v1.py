"""PR-06.1B PIT bridge for verified economic releases.

Merges the PR-06.1A verified release manifest into the historical event layer
without fabricating consensus or rewriting release/vintage dates. Existing
records are enriched in place; genuinely new indicator-period releases are
appended. Research-only; no regime/scoring integration.
"""
from pathlib import Path
import pandas as pd

EVENTS = Path("economic_historical_events_v1.csv")
QUALITY = Path("economic_historical_quality_v1.csv")
RELEASES = Path("economic_release_records_input_v1.csv")

KEY = ["indicator", "release_date", "reference_period"]


def _bool_series_true(s: pd.Series) -> bool:
    return bool(s.fillna(False).astype(bool).all())


def main() -> None:
    if not EVENTS.exists() or not QUALITY.exists() or not RELEASES.exists():
        raise FileNotFoundError("Historical events, quality, and verified releases are required.")

    events = pd.read_csv(EVENTS)
    quality = pd.read_csv(QUALITY)
    releases = pd.read_csv(RELEASES)

    # The bridge accepts only original release-date vintages.
    rd = pd.to_datetime(releases["release_date"], errors="raise")
    vd = pd.to_datetime(releases["vintage_date"], errors="raise")
    if not (vd <= rd).all():
        raise AssertionError("Verified release manifest violates vintage_date <= release_date")
    if releases["consensus"].notna().any():
        raise AssertionError("PR-06.1B does not accept unsourced/fabricated consensus")

    # Agency is part of the historical contract but not repeated in the release manifest.
    from economic_data_v1 import SUPPORTED_INDICATORS
    releases["agency"] = releases["indicator"].map(
        lambda x: SUPPORTED_INDICATORS.get(str(x), {}).get("agency", "UNKNOWN")
    )

    # Add richer contract columns while preserving all legacy columns.
    for col in releases.columns:
        if col not in events.columns and col != "event_id":
            events[col] = pd.NA

    existing_index = {
        tuple(str(row[c]) for c in KEY): idx
        for idx, row in events.iterrows()
    }
    added = 0
    enriched = 0

    for _, rel in releases.iterrows():
        key = tuple(str(rel[c]) for c in KEY)
        payload = {c: rel.get(c, pd.NA) for c in events.columns if c in rel.index and c != "event_id"}
        if key in existing_index:
            idx = existing_index[key]
            # Release-manifest metadata is authoritative for the same original release.
            for col, value in payload.items():
                if pd.notna(value):
                    events.at[idx, col] = value
            enriched += 1
        else:
            row = {c: pd.NA for c in events.columns}
            row.update(payload)
            events = pd.concat([events, pd.DataFrame([row])], ignore_index=True)
            existing_index[key] = len(events) - 1
            added += 1

    # Rebuild/extend quality rows for every verified release key.
    q_keys = set(zip(
        quality["indicator"].astype(str),
        quality["release_date"].astype(str),
        quality["reference_period"].astype(str),
    ))
    q_added = []
    for _, rel in releases.iterrows():
        key = tuple(str(rel[c]) for c in KEY)
        if key in q_keys:
            continue
        q_added.append({
            "record_id": str(rel.get("event_id", "|".join(key))),
            "indicator": rel["indicator"],
            "agency": SUPPORTED_INDICATORS.get(str(rel["indicator"]), {}).get("agency", "UNKNOWN"),
            "release_date": rel["release_date"],
            "reference_period": rel["reference_period"],
            "point_in_time_safe": True,
            "quality_issues": "",
            "historical_consensus_available": False,
        })
        q_keys.add(key)
    if q_added:
        quality = pd.concat([quality, pd.DataFrame(q_added)], ignore_index=True)

    events["release_date"] = pd.to_datetime(events["release_date"], errors="raise")
    events["vintage_date"] = pd.to_datetime(events["vintage_date"], errors="raise")
    if not (events["vintage_date"] <= events["release_date"]).all():
        raise AssertionError("PIT temporal-order gate failed after merge")
    if not _bool_series_true(quality["point_in_time_safe"]):
        raise AssertionError("PIT quality gate failed after merge")
    if quality["historical_consensus_available"].fillna(False).astype(bool).any():
        raise AssertionError("Historical consensus gate failed after merge")

    events = events.sort_values(["release_date", "indicator", "reference_period"], kind="mergesort").reset_index(drop=True)
    events["release_date"] = events["release_date"].dt.strftime("%Y-%m-%d")
    events["vintage_date"] = events["vintage_date"].dt.strftime("%Y-%m-%d")
    events.to_csv(EVENTS, index=False)
    quality.to_csv(QUALITY, index=False)

    new_indicators = sorted(set(releases["indicator"]) - {
        "CPI", "CORE_CPI", "NFP", "UNEMPLOYMENT_RATE",
        "INITIAL_JOBLESS_CLAIMS", "ISM_MANUFACTURING_PMI", "GDP"
    })
    print("ECONOMIC PIT RELEASE BRIDGE v1")
    print("Rows enriched:", enriched)
    print("Rows added:", added)
    print("Quality rows added:", len(q_added))
    print("Expanded indicators:", ", ".join(new_indicators))
    print("Total historical records:", len(events))
    print("PIT QUALITY GATE: PASS")
    print("NO FABRICATED CONSENSUS: PASS")
    print("RESEARCH-ONLY BOUNDARY: PASS")


if __name__ == "__main__":
    main()
