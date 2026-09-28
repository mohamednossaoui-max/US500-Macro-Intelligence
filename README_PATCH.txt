Economic Data Foundation v2 — corrected files only.

Changes:
- expanded the ingestion registry to all 14 supported Economic Intelligence indicators;
- added a fail-closed PIT/coverage validator for the canonical public_data artifacts;
- made the historical refresh operate on canonical public_data artifacts rather than root-level duplicate files;
- changed the legacy GitHub workflow universe gate from exact equality to required-core subset, so verified expanded official series are not rejected;
- no scoring, Macro Context, Decision Engine, Fed Intelligence, UI, or public_data values changed.

Validation on supplied baseline: 95 passed, 0 failed; Python compile PASS; foundation validator PASS (504 records, 14 indicators, 11 independent families).
