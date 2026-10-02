"""BLS Employment Situation staging collector v1.

Fetches official BLS time-series observations for Total Nonfarm Payrolls and
Unemployment Rate, derives the monthly NFP change, validates that both series
refer to the same observation month, and writes staging artifacts only.

IMPORTANT:
- This module DOES NOT write to public_data/.
- This module DOES NOT invent an Employment Situation release_date.
- Canonical/PIT merge is a separate step after authoritative release metadata
  has been resolved.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent
STAGING_DIR = ROOT / "staging" / "economic"
STAGING_JSON = STAGING_DIR / "bls_employment_latest_v1.json"
STAGING_CSV = STAGING_DIR / "bls_employment_latest_v1.csv"

BLS_V1_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
BLS_V2_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

PAYROLL_SERIES = "CES0000000001"   # Total nonfarm, thousands, seasonally adjusted
UNEMPLOYMENT_SERIES = "LNS14000000"  # Unemployment rate, percent, seasonally adjusted
REQUIRED_SERIES = {PAYROLL_SERIES, UNEMPLOYMENT_SERIES}
TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class Observation:
    series_id: str
    year: int
    month: int
    period: str
    period_name: str
    value: float
    footnotes: str
    preliminary: bool

    @property
    def month_key(self) -> tuple[int, int]:
        return self.year, self.month

    @property
    def observation_month(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


def _footnotes(item: dict[str, Any]) -> str:
    texts: list[str] = []
    for note in item.get("footnotes") or []:
        if isinstance(note, dict):
            text = str(note.get("text") or "").strip()
            if text:
                texts.append(text)
    return " | ".join(texts)


def _parse_month(period: str) -> int:
    if len(period) != 3 or not period.startswith("M") or not period[1:].isdigit():
        raise ValueError(f"Invalid BLS monthly period: {period!r}")
    month = int(period[1:])
    if not 1 <= month <= 12:
        raise ValueError(f"BLS period is not a calendar month: {period!r}")
    return month


def fetch_bls_series() -> dict[str, Any]:
    """Fetch the two required BLS series. Fail closed on any incomplete response."""
    api_key = os.getenv("BLS_API_KEY", "").strip()
    url = BLS_V2_URL if api_key else BLS_V1_URL
    payload: dict[str, Any] = {"seriesid": sorted(REQUIRED_SERIES)}
    if api_key:
        payload["registrationkey"] = api_key

    response = requests.post(
        url,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "US500-Macro-Intelligence/1.0 (BLS Economic ingestion)",
        },
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()

    if body.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(
            "BLS request failed: " + "; ".join(map(str, body.get("message") or []))
        )

    series = (body.get("Results") or {}).get("series")
    if not isinstance(series, list):
        raise RuntimeError("BLS response is missing Results.series")

    returned = {str(s.get("seriesID")) for s in series if isinstance(s, dict)}
    missing = REQUIRED_SERIES - returned
    if missing:
        raise RuntimeError(f"BLS response missing required series: {sorted(missing)}")

    return body


def parse_monthly_observations(body: dict[str, Any]) -> dict[str, list[Observation]]:
    """Normalize BLS monthly observations and sort newest first."""
    parsed: dict[str, list[Observation]] = {}
    series_list = (body.get("Results") or {}).get("series") or []

    for series in series_list:
        series_id = str(series.get("seriesID") or "")
        if series_id not in REQUIRED_SERIES:
            continue

        observations: list[Observation] = []
        for item in series.get("data") or []:
            period = str(item.get("period") or "")
            if not (period.startswith("M") and period != "M13"):
                continue
            try:
                year = int(item["year"])
                month = _parse_month(period)
                value = float(str(item["value"]).replace(",", ""))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Malformed BLS observation in {series_id}: {item!r}") from exc

            notes = _footnotes(item)
            observations.append(
                Observation(
                    series_id=series_id,
                    year=year,
                    month=month,
                    period=period,
                    period_name=str(item.get("periodName") or ""),
                    value=value,
                    footnotes=notes,
                    preliminary="preliminary" in notes.lower(),
                )
            )

        observations.sort(key=lambda x: x.month_key, reverse=True)
        if not observations:
            raise RuntimeError(f"No monthly observations returned for {series_id}")
        parsed[series_id] = observations

    missing = REQUIRED_SERIES - set(parsed)
    if missing:
        raise RuntimeError(f"No parsed observations for required series: {sorted(missing)}")
    return parsed


def derive_nfp_change(payroll: list[Observation]) -> dict[str, Any]:
    """Derive monthly NFP change from consecutive CES payroll levels.

    CES0000000001 is expressed in thousands of jobs, therefore the level
    difference is multiplied by 1,000 to produce the NFP jobs-change value.
    """
    if len(payroll) < 2:
        raise RuntimeError("At least two payroll observations are required to derive NFP")

    current = payroll[0]
    previous = payroll[1]

    expected_previous = (current.year - 1, 12) if current.month == 1 else (current.year, current.month - 1)
    if previous.month_key != expected_previous:
        raise RuntimeError(
            "Payroll observations are not consecutive: "
            f"current={current.observation_month}, previous={previous.observation_month}"
        )

    nfp_jobs = int(round((current.value - previous.value) * 1000.0))
    return {
        "indicator": "NFP",
        "series_id": PAYROLL_SERIES,
        "observation_month": current.observation_month,
        "reference_period": current.period_name + f" {current.year}",
        "actual": nfp_jobs,
        "current_payroll_level_thousands": current.value,
        "previous_payroll_level_thousands": previous.value,
        "footnotes": current.footnotes,
        "preliminary": current.preliminary,
    }


def build_unemployment_record(unemployment: list[Observation], target_month: str) -> dict[str, Any]:
    """Return unemployment rate for the same observation month as derived NFP."""
    match = next((obs for obs in unemployment if obs.observation_month == target_month), None)
    if match is None:
        raise RuntimeError(f"No unemployment observation matching payroll month {target_month}")

    return {
        "indicator": "UNEMPLOYMENT_RATE",
        "series_id": UNEMPLOYMENT_SERIES,
        "observation_month": match.observation_month,
        "reference_period": match.period_name + f" {match.year}",
        "actual": match.value,
        "footnotes": match.footnotes,
        "preliminary": match.preliminary,
    }


def validate_employment_release(nfp: dict[str, Any], unemployment: dict[str, Any]) -> None:
    """Fail closed if the two indicators cannot form one coherent monthly release."""
    if nfp["observation_month"] != unemployment["observation_month"]:
        raise RuntimeError("NFP and unemployment observations refer to different months")
    if not isinstance(nfp["actual"], int):
        raise RuntimeError("Derived NFP must be an integer number of jobs")
    if not -2_000_000 <= nfp["actual"] <= 5_000_000:
        raise RuntimeError(f"Derived NFP is outside sanity bounds: {nfp['actual']}")
    rate = float(unemployment["actual"])
    if not 0.0 <= rate <= 30.0:
        raise RuntimeError(f"Unemployment rate is outside sanity bounds: {rate}")


def write_staging_artifact(nfp: dict[str, Any], unemployment: dict[str, Any]) -> dict[str, Any]:
    """Write staging-only artifacts. No canonical/public_data mutation occurs here."""
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    artifact = {
        "schema_version": "bls_employment_staging_v1",
        "status": "STAGED_NOT_CANONICAL",
        "fetched_at_utc": fetched_at,
        "source": "U.S. Bureau of Labor Statistics Public Data API",
        "source_url": BLS_V2_URL if os.getenv("BLS_API_KEY", "").strip() else BLS_V1_URL,
        "release_date": None,
        "release_date_status": "UNRESOLVED",
        "pit_safe_for_canonical_merge": False,
        "warning": (
            "BLS time-series observations do not by themselves establish the authoritative "
            "Employment Situation release date. Resolve release metadata before canonical merge."
        ),
        "records": [nfp, unemployment],
    }

    STAGING_JSON.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    fieldnames = [
        "indicator", "series_id", "observation_month", "reference_period", "actual",
        "preliminary", "footnotes", "fetched_at_utc", "release_date",
        "pit_safe_for_canonical_merge",
    ]
    with STAGING_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for record in (nfp, unemployment):
            writer.writerow({
                "indicator": record["indicator"],
                "series_id": record["series_id"],
                "observation_month": record["observation_month"],
                "reference_period": record["reference_period"],
                "actual": record["actual"],
                "preliminary": record["preliminary"],
                "footnotes": record["footnotes"],
                "fetched_at_utc": fetched_at,
                "release_date": "",
                "pit_safe_for_canonical_merge": False,
            })

    return artifact


def main() -> int:
    try:
        raw = fetch_bls_series()
        parsed = parse_monthly_observations(raw)
        nfp = derive_nfp_change(parsed[PAYROLL_SERIES])
        unemployment = build_unemployment_record(
            parsed[UNEMPLOYMENT_SERIES], nfp["observation_month"]
        )
        validate_employment_release(nfp, unemployment)
        artifact = write_staging_artifact(nfp, unemployment)

        print("BLS EMPLOYMENT INGESTION: PASS (STAGING ONLY)")
        print(f"Observation month: {nfp['observation_month']}")
        print(f"Derived NFP: {nfp['actual']}")
        print(f"Unemployment rate: {unemployment['actual']}")
        print(f"JSON: {STAGING_JSON.relative_to(ROOT)}")
        print(f"CSV:  {STAGING_CSV.relative_to(ROOT)}")
        print("Canonical merge: BLOCKED until authoritative release_date is resolved")
        if artifact["pit_safe_for_canonical_merge"]:
            raise AssertionError("Staging artifact must never be marked PIT-safe here")
        return 0
    except Exception as exc:
        print(f"BLS EMPLOYMENT INGESTION: FAIL — {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
