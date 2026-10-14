Fed PIT and Quality Gate fix

Replace these files at their matching repository paths:
fed_intelligence.py
fed_beige_evidence_v1.py
fed_snapshot_ui_v1.py
tests/test_fed_beige_evidence_v1.py

No app.py changes, no UI redesign, no replacement of public_data in this package.

Then: GitHub Actions > Fed Intelligence > Run workflow (main).
The existing workflow runs tests, rebuilds the snapshot and publishes the updated JSON/manifest.
Reload Fed snapshot after it finishes.

Expected when all documents, comparisons and freshness checks pass:
PIT: OBSERVATION_CHECKED
Quality Gate: ELIGIBLE
Freshness: CURRENT

OBSERVATION_CHECKED means the validated official transcript was actually retrieved
at the recorded UTC timestamp, with its exact PDF SHA256 captured. Its publication
date remains unknown. Availability starts at retrieval, never at the meeting date.
This does not certify intraday history or prior archived vintages.
Missing, stale, invalid or unverified records still degrade the gate.
Previous snapshots are not silently upgraded: rebuild required.

Validation: 130 tests passed (Fed, publication integrity, PIT and UI regressions).
