Replace liquidity_historical_collector_v1.py in the repository root and add tests/test_liquidity_fred_day.py.
Run: python -m pytest tests/test_liquidity_fred_day.py -q
Validated: 4 passed; combined with Financial Stress date regression tests: 7 passed.
Rerun Liquidity Historical v1 using the updated main branch, then rerun the master publication pipeline after success. Re-running an old job may reuse its old commit; use a new workflow dispatch on updated main.
The request caps realtime_end to the earlier of the requested cutoff and America/Chicago day; an explicit FRED server-day rejection lowers that cutoff before retry. Historical cutoffs remain bounded. Initial-release observation parameters and vintage dates are unchanged. No public_data files changed. No live authenticated request or deployment performed.
