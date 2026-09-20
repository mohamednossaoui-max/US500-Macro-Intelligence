"""
Fed Intelligence Artifact Exporter v1

Purpose:
- Run the existing Fed Intelligence engine.
- Export its complete analytical output to JSON.
- Provide a stable artifact for downstream Macro Context research.

Research-only.
No trade execution.
No Decision Engine integration.
No trading signals.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from fed_intelligence import build_fed_intelligence


OUTPUT_FILE = Path("fed_intelligence_output_v1.json")


def json_default(value):
    """
    Convert date/datetime objects to ISO strings for JSON serialization.
    """
    if isinstance(value, (date, datetime)):
        return value.isoformat()

    raise TypeError(
        f"Object of type {type(value).__name__} "
        "is not JSON serializable"
    )


def main():
    """
    Run the existing Fed Intelligence engine
    and write the complete result to JSON.
    """

    print("=" * 60)
    print("FED INTELLIGENCE ARTIFACT EXPORT v1")
    print("=" * 60)

    print("Running existing Fed Intelligence engine...")

    data = build_fed_intelligence()

    OUTPUT_FILE.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            default=json_default
        ),
        encoding="utf-8"
    )

    print()
    print(f"Output file: {OUTPUT_FILE}")
    print(f"Available: {data.get('available')}")
    print(f"As-of date: {data.get('as_of_date')}")
    print(f"Latest FOMC: {data.get('latest_fomc')}")
    print(f"Fed Chair: {data.get('fed_chair')}")
    print(f"Latest SEP: {data.get('latest_sep_date')}")
    print(
        "Beige Book available: "
        f"{data.get('beige_book', {}).get('available')}"
    )

    print()
    print("Research-only: TRUE")
    print("Decision Engine integration: FALSE")
    print("Trade execution: FALSE")
    print("Trading signals: FALSE")

    print()
    print("Fed Intelligence artifact created successfully.")


if __name__ == "__main__":
    main()
