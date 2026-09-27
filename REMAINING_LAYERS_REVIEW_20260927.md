# Remaining Layers Unified Review — 2026-09-27

Scope: Event/News, Earnings, Decision Engine, Historical Event Study, Historical Edge, Final Validation, Data Status, Data Explorer, Methodology.

## Implemented
- Added a unified research-only PIT/evidence-quality contract (`remaining_layers_quality_v1.py`).
- Event/News publication now carries PIT, freshness, quality-gate, decision-role and research-only metadata.
- Earnings reaction publication is explicitly `PIT_LIMITED`, `DEGRADED`, and `CONTEXTUAL`; post-event reactions are not treated as contemporaneous decision evidence.
- Decision Engine semantics are preserved; quality metadata is kept separate from direction/state semantics.
- Historical Event Study empty conditional output now preserves its schema instead of publishing an unreadable zero-byte CSV.
- Historical Edge is explicitly `EXCLUDED / UNAVAILABLE` until dedicated `historical_edge_*` artifacts are actually published; the UI no longer presents Event Study as if it were Historical Edge.
- Final validator accepts the existing COT+AAII+VIX primary components as the Unified Sentiment representation instead of requiring a fabricated aggregate artifact.
- Data Status exposes the unified quality contract; Methodology documents eligible/degraded/excluded and contextual boundaries.
- Added CI workflow and acceptance tests for the remaining-layer quality contract.

## Validation
- Targeted quality tests: 5 passed.
- Full pytest regression: 62 passed.
- Final end-to-end validation: PASS WITH REVIEW — 276 PASS, 10 REVIEW, 0 FAIL.
- Research-only boundary active; trading signals, execution and forecasting remain disabled.

## Deliberately not fabricated
- No dedicated Historical Edge artifact was invented.
- Event/News and Earnings were not silently promoted into Decision Engine scoring.
- Missing/excluded evidence is not converted to neutral or zero.

The remaining REVIEW items are provenance/record-identity warnings in legacy published artifacts, not mandatory invariant failures.
