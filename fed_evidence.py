"""Offline research experiment. Never imported by the app or publication pipeline."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

SCOPES = {"OFFICIAL_STATEMENT", "OPENING_STATEMENT"}


def instant(value):
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("A full timezone-aware timestamp is required, not a date")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp requires an explicit timezone")
    return result.astimezone(timezone.utc)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fact(value, evidence):
    return {"value": value, "evidence": evidence}


def facts(text, scope):
    """Conservative explicit facts; no weighted tone or direction score."""
    result = {}
    for paragraph in filter(None, (re.sub(r"\s+", " ", p).strip() for p in text.splitlines())):
        numeric = re.sub(r"(\d+)?([¼½¾])", lambda m: str(float(m[1] or 0) + {"¼": .25, "½": .5, "¾": .75}[m[2]]), paragraph)
        numeric = re.sub(r"\b(\d+)[ -](\d+)\s*/\s*(\d+)\b", lambda m: str(float(m[1]) + float(m[2])/float(m[3])), numeric)
        action = re.search(r"(?:Committee|FOMC) (?:has )?(?:decided|voted) to (maintain|raise|increase|reduce|lower)\b", numeric, re.I)
        target = re.search(r"target (?:range|rate).{0,100}?\b(\d+(?:\.\d+)?)\s*(?:to|[–-])\s*(\d+(?:\.\d+)?)\s*percent", numeric, re.I)
        if action:
            result["policy_action"] = fact({"maintain": "HOLD", "raise": "RAISE", "increase": "RAISE", "reduce": "CUT", "lower": "CUT"}[action[1].lower()], paragraph)
            if target and 0 <= float(target[1]) <= float(target[2]) <= 25:
                result["target_range_percent"] = fact([float(target[1]), float(target[2])], paragraph)
        if scope == "OFFICIAL_STATEMENT":
            vote = re.search(r"approved.*?statement.*?by a (\d+)\s*[–-]\s*(\d+) vote", paragraph, re.I)
            if vote:
                result["vote"] = fact([int(vote[1]), int(vote[2])], paragraph)
            dissent = re.search(r"(?:Voting against|voted against|dissent\w*).{0,500}?preferred to (raise|increase|reduce|lower|maintain)\b", paragraph, re.I)
            if dissent:
                preferences = re.findall(r"preferred to (raise|increase|reduce|lower|maintain)\b", paragraph[dissent.start():], re.I)
                directions = {{"raise": "RAISE", "increase": "RAISE", "reduce": "CUT", "lower": "CUT", "maintain": "HOLD"}[p.lower()] for p in preferences}
                if "dissent_preference" in result:
                    directions.add(result["dissent_preference"]["value"])
                    paragraph = result["dissent_preference"]["evidence"] + "\n" + paragraph
                result["dissent_preference"] = fact(next(iter(directions)) if len(directions) == 1 else "MULTIPLE_PREFERENCES", paragraph)
        for key, pattern in {
            "growth": r"economic activity|economic growth|GDP",
            "inflation": r"inflation|PCE|price stability",
            "guidance": r"accumulation of more information|policy stance|forward guidance",
            "financial_conditions": r"financial (?:and credit )?conditions|credit conditions",
        }.items():
            if re.search(pattern, paragraph, re.I):
                result.setdefault(key, {"evidence": []})["evidence"].append(paragraph)
    return result


def validate(document):
    if document["scope"] not in SCOPES:
        raise ValueError("Use like-for-like statements or opening remarks; full Q&A is unsupported")
    source = urlparse(document["source"])
    if source.scheme != "https" or source.hostname != "www.federalreserve.gov":
        raise ValueError("An official Federal Reserve HTTPS source is required")
    date.fromisoformat(document["meeting_date"])
    observed = instant(document["first_seen_at"])
    if date.fromisoformat(document["meeting_date"]) > observed.date():
        raise ValueError("Meeting date cannot be in the future relative to capture")
    if document.get("published_at") and instant(document["published_at"]) > observed:
        raise ValueError("Capture cannot precede the declared publication time")
    if not document["text"].strip() or sha(document["text"]) != document["sha256"]:
        raise ValueError("Empty or hash-mismatched source text")
    if document.get("version_status") not in {"PRELIMINARY", "FINAL", "UNKNOWN"}:
        raise ValueError("Version status must be explicit")
    return observed


def build(manifest, as_of, enabled=False):
    if not enabled:
        return {"status": "DISABLED", "research_only": True}
    cutoff = instant(as_of)
    groups = {}
    for document in manifest["documents"]:
        captured = validate(document)
        # Gate EACH captured version, never backdate revised text to meeting/publication.
        if captured <= cutoff:
            key = (document["scope"], document["meeting_date"])
            if key not in groups or captured > instant(groups[key]["first_seen_at"]):
                groups[key] = document
            elif captured == instant(groups[key]["first_seen_at"]) and document["sha256"] != groups[key]["sha256"]:
                raise ValueError("Conflicting versions at the same capture time")
    comparisons = []
    for scope in sorted(SCOPES):
        documents = sorted((d for (s, _), d in groups.items() if s == scope), key=lambda d: d["meeting_date"])
        pair = documents[-2:]
        row = {"scope": scope, "status": "READY" if len(pair) == 2 else "INSUFFICIENT_AVAILABLE_DOCUMENTS"}
        for label, document in zip(("previous", "current") if len(pair) == 2 else ("current",), pair):
            row[label] = {k: v for k, v in document.items() if k != "text"}
            row[label]["facts"] = facts(document["text"], scope)
        if len(pair) == 2:
            old, new = row["previous"]["facts"], row["current"]["facts"]
            row["changes"] = {key: "NOT_COMPARABLE" if key not in old or key not in new else "UNCHANGED" if old[key].get("value", old[key].get("evidence")) == new[key].get("value", new[key].get("evidence")) else "CHANGED" for key in sorted(old.keys() | new.keys())}
        comparisons.append(row)
    return {"status": "RESEARCH_ONLY", "as_of": cutoff.isoformat(), "availability_basis": "FIRST_OBSERVED_VERSION_CONSERVATIVE", "synthetic": bool(manifest.get("synthetic")), "comparisons": comparisons}


def render(report):
    content = html.escape(json.dumps(report, ensure_ascii=False, indent=2))
    cards = []
    for comparison in report.get("comparisons", []):
        cells = []
        for side in ("previous", "current"):
            doc = comparison.get(side, {})
            evidence = html.escape(json.dumps(doc.get("facts", {}), ensure_ascii=False, indent=2))
            cells.append('<article><h3>' + side + '</h3><p>' + html.escape(doc.get("meeting_date", "Unavailable")) + '</p><p>' + html.escape(doc.get("version_status", "UNKNOWN")) + '</p><pre>' + evidence + '</pre></article>')
        cards.append('<h2>' + html.escape(comparison["scope"]) + '</h2><p>' + comparison["status"] + '</p><section>' + ''.join(cells) + '</section>')
    return '<!doctype html><meta charset="utf-8"><title>Fed evidence experiment</title><style>body{background:#101b2d;color:#eef3fa;font:16px system-ui;max-width:1100px;margin:40px auto;padding:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#192940;padding:16px}strong{color:#e8bc63}section{display:flex;gap:20px}article{flex:1;min-width:0}h2{font-size:20px}@media(max-width:700px){section{display:block}}</style><h1>Fed evidence — isolated research experiment</h1><p><strong>No Decision State, CORE weights or System Health changes.</strong></p><p>SYNTHETIC input is demonstration only. Missing evidence remains unknown. Historical availability uses each version’s first capture.</p>' + ''.join(cards) + '<details><summary>Complete provenance and comparisons</summary><pre>' + content + '</pre></details>'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--as-of")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "output")
    args = parser.parse_args()
    if not args.enable:
        print(json.dumps(build({}, None)))
        return
    if args.input is None or args.as_of is None:
        parser.error("--enable requires --input and --as-of")
    report = build(json.loads(args.input.read_text(encoding="utf-8")), args.as_of, enabled=True)
    # No caller-selected destination can overwrite live app or publication artifacts.
    allowed = (Path(__file__).parent / "output").resolve()
    destination = args.output_dir.resolve()
    if not destination.is_relative_to(allowed):
        parser.error("Output must remain under this experiment's output directory")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (destination / "report.html").write_text(render(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(destination)}))


if __name__ == "__main__":
    main()
