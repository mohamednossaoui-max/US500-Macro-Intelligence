US500 Sentiment dynamic_card hotfix only

Replace only: ui_v3.py

Change:
- dynamic_card note now accepts Any and normalizes through _s() before HTML rendering.
- Fixes Sentiment Intelligence crash when unified_sentiment_score is numeric/NaN.
- No CSS/theme, app.py, data, scoring, PIT, Fed, Decision Engine, or navigation changes.

Validation:
- Python compile: PASS
- Existing pytest suite: 91 passed / 0 failed
- Numeric/NaN note regression: PASS
- Static navigation registry check: PASS (20 expected pages)
- dynamic_card microbenchmark with Streamlit output stubbed: see assistant report.

Note: full browser/Streamlit navigation timing could not be executed in the validation runtime because the Streamlit package is not installed there. No claim is made that browser navigation was runtime-tested.
