# Census Sales Mapping / BLS PDF Correction

The supplied audit(1) proves: DOL claims now VERIFIED/NEW_RELEASE (197000, week ending September 26, release October 1); BEA GDP/PCE and ISM Services remain verified; seven BLS values were fetched but their metadata was blocked at both RSS and HTML; Census returned an empty response; ISM Manufacturing remains blocked by authenticated/licensed redirect.

A mistake in the previous patch was found and corrected: MRTSADV is **Advance Retail Inventories**, not retail sales. Official Census catalog confirms **MARTS** is Advance Monthly Sales for Retail and Food Services. The corrected request retains category 44X72 (Retail Trade and Food Services), data type SM (Sales - Monthly, millions), seasonal adjustment yes. Dataset identity/title is verified at runtime before accepting observations. Empty/non-JSON responses fail explicitly; keys are not logged. No Census value was merged from the wrong mapping; validation had failed closed.

BLS now explicitly tries the official PDF after blocked RSS and current HTML. PDF must have PDF signature, actual embargo date/time, named reference period, API-period parity, and calendar-date/time parity with latest due official release. Calendar alone is not proof of publication. Reasons and source URL are retained; if PDF or calendar also fails, status stays METADATA_UNVERIFIED with no invented date.

Live local tests with simulated RSS+HTML 403 and actual PDF/calendar retrieval passed:
- Employment Situation: September 2026, October 2, 2026 08:30 ET.
- CPI: August 2026, September 11, 2026 08:30 ET.
- PPI: August 2026, September 10, 2026 08:30 ET.
This does not prove GitHub can access those URLs. No new registered API call with the user's key was made locally.

`python -m pytest -q tests`: 283 passed, 19 existing pandas FutureWarnings, 27.39s. Tests cover PDF after both HTML/RSS failures, actual em-dash title syntax, rejecting inventory dataset identity, and updated realistic JSON response fixtures. Prior downstream/PIT/publication tests are included in the corrected working copy's full suite.

No canonical/public publication. No app.py change. All-14 gate remains required. ISM Manufacturing unresolved; authenticated Census request and BLS PDF/calendar access must be confirmed in a fresh GitHub audit.

Official references:
- https://api.census.gov/data/timeseries/eits/marts.json
- https://api.census.gov/data/timeseries/eits/mrtsadv.json
- https://api.census.gov/data/timeseries/eits/marts.html
- https://www2.census.gov/api-documentation/EITS_API_User_Guide_Dec2020.pdf
- https://www.bls.gov/news.release/pdf/empsit.pdf
- https://www.bls.gov/news.release/pdf/cpi.pdf
- https://www.bls.gov/news.release/pdf/ppi.pdf

Install this incremental update over the previous official endpoint repair, keeping paths. Start a NEW `Official Economic Ingestion Audit` run on main and provide its artifact. No new Secret required; CENSUS_API_KEY is used for Census data; BLS_API_KEY remains the registered BLS key. Do not send key values.

ZIP contents:
- economic_official_sources_v1.py — corrected sales mapping/runtime identity, PDF alternate, explicit response failures.
- tests/test_economic_official_ingestion_v1.py — sales catalog fixture and real JSON response bytes.
- tests/test_official_endpoint_alternates.py — sales mapping/identity and PDF regressions.
- US500-Census-BLS-PDF-Correction-Notes.md — this report.
