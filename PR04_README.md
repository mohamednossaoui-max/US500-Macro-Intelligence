# PR-04 — Point-in-Time Integrity Standardization

This patch centralizes existing anti-lookahead rules without changing research methodology.

Files:
- `point_in_time.py` (new shared PIT helpers)
- `economic_surprise_engine_v1.1.py` (shared temporal validation)
- `economic_regime_classifier_v1.5.py` (central as-of filtering)
- `macro_context_v1.py` (central as-of filtering)
- `tests/test_point_in_time_integrity.py` (new regression tests)
- `.github/workflows/economic_intelligence_full_pipeline_v2.2.yml` (CI gate)

The patch deliberately does not modify `app.py`, backtests, Fed Intelligence, or public data artifacts.
