"""Read one Fed artifact without Streamlit's stacked data caches."""
import hashlib
import json
from datetime import date, datetime, timezone

from fed_beige_evidence_v1 import snapshot_quality


def load_snapshot(local_path, remote_url, get):
    if local_path.is_file():
        try:
            raw = local_path.read_bytes()
            origin = "LOCAL"
        except OSError:
            return None, "UNREADABLE LOCAL FED SNAPSHOT"
    else:
        try:
            response = get(remote_url)
            response.raise_for_status()
            raw, origin = response.content, "GITHUB RAW"
        except Exception:
            return None, "FED SNAPSHOT UNAVAILABLE"
    try:
        obj = json.loads(raw.decode("utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("Expected a JSON object")
        return obj, f"{origin} · snapshot {hashlib.sha256(raw).hexdigest()[:12]}"
    except (ValueError, UnicodeDecodeError):
        return None, "UNREADABLE FED SNAPSHOT"


def display_quality(obj, today=None):
    today = today or datetime.now(timezone.utc).date()
    quality = dict(obj.get("quality") or {})
    quality.update(snapshot_quality(obj, today))
    if quality["freshness_status"] != "CURRENT" or quality["pit_status"] != "DATE_CHECKED":
        checks = quality.get("document_checks") or {}
        problems = ", ".join(f"{key}: {value}" for key, value in checks.items() if value != "CURRENT")
        note = ("Snapshot predates today's verification." if quality["freshness_status"] == "STALE" else
                "Date/source checks: " + (problems or "not yet verified") +
                ". A missing publication date does not mean missing document text.")
        quality.update(quality_gate="DEGRADED", quality_status="UNVERIFIED", quality_reason=note)
    return quality


def issue_month(beige):
    # Legacy first-of-month identifiers are presented as a month, never a day.
    return beige.get("issue_month") or str(beige.get("issue_date") or "Unavailable")[:7]
