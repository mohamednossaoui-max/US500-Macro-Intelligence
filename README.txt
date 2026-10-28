US500 Press Conference Scope Fix

Cause confirmed in the supplied 2026-10-28 snapshot:
Both texts are available. Previous scope is FULL_TRANSCRIPT_CHAIR_REMARKS;
current scope is OPENING_STATEMENT. Comparison status is SCOPE_MISMATCH.
The compact UI incorrectly rendered both sides as Unavailable.

Apply: copy these files into the repository root, preserving tests/ paths.
No app.py change is required. No public_data files are included or modified.
Run:
python -m pytest tests/test_fed_report_comparison_v2.py tests/test_fed_communication_dates_v1.py tests/test_fed_intelligence.py tests/test_fed_beige_evidence_v1.py -q
Validated locally: 90 passed.

Then rerun the existing master publication pipeline with Fed included, so it
rebuilds the Fed artifact, dependent layers and canonical manifest together.
A test-only run does not publish new data. Do not manually replace the published
Fed JSON without rebuilding its manifest and dependents.

Behavior: full/full comparisons remain full scope. Mixed opening/full scopes
use only the opening chair turn on BOTH sides, ending at the first journalist
speaker. If an opening cannot be extracted, comparison stays blocked.
No invented release dates; unknown publication dates remain unknown.
The detailed comparison displays its scope; compact cards preserve their layout
and display per-side availability accurately even for older saved artifacts.
PRELIMINARY PDF page headers are removed like FINAL headers.

Live retrieval/publication was not executed. Results depend on official PDFs
being retrievable and on the existing pipeline publishing the rebuilt snapshot.

V2: Compact cards show numeric facts only when both sides have the selected fact; otherwise both show Text retrieved. Supports explicit has decided / leave unchanged / hold decisions and decisions without a numeric range. Missing figures are never copied from another document. This is a cumulative patch including the prior scope fix. No live retrieval or publication was performed.

V3: Live official PDF retrieved successfully from https://www.federalreserve.gov/mediacenter/files/FOMCpresconf20261028.pdf . It has 4 pages and explicitly says target RATE, not target RANGE. The extractor now supports both. Regression test uses the actual extracted PDF text. Expected current HOLD and 3.75-4.00%; previous RAISE and 3.75-4.00%. No current vote is invented. Rebuild and publish using the existing master pipeline with Fed included after replacing files.
