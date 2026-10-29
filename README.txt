Replace the collector in the repository root and add the test under tests/. Run: python -m pytest tests/test_financial_stress_fred_day.py -q
Validated: 3 passed. Then rerun financial-stress-historical-v1. After it succeeds, rerun the master publication pipeline.
Fix: cap realtime_end to min(requested END, America/Chicago day); if FRED explicitly rejects it with an earlier server day, lower the cap before retry. Initial Release Only output_type=4 is preserved. No public_data changes. No live authenticated FRED request or publication was run.
