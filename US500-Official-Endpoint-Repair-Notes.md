# Official Economic Endpoint Repair — 2026-10-02

## Proven root causes from the supplied audit
- Registered BLS batch succeeded. The seven BLS failures were HTTP 403 at the three RSS metadata feeds, not API failures.
- Census request included `time` in `get`, although the official variable is predicate-only. Its range also lacked an explicit upper bound. Updated request selects `time_slot_date` and `time_slot_id`, and uses an explicit dynamic range. Same verified universe: 44X72, SM, seasonally adjusted yes.
- DOL current PDF returned HTTP 403 in GitHub.
- ISM manufacturing redirected to authenticated/licensed access. A separate local probe returned CAPTCHA; no circumvention implemented.

## Fixes
- BLS: explicit alternate current published release text plus official ICS calendar. Requires actual embargo date/time, named reference month/year, API-period parity, latest due calendar-event parity and calendar coverage. Calendar alone never proves publication. Alternate reason is retained in observation metadata. Missing metadata remains METADATA_UNVERIFIED.
- DOL: explicit alternate official public archive form (POST report=press, dynamic year), discovered dated PDF, official publication schedule/holiday substitution, archive/PDF release-date parity. Revisions remain separate observations. Reject stale archive.
- Census: correct query and reference date field; reject semantic mismatch, duplicate periods and release/API mismatch.
- Includes prior diagnostic sanitization, BLS historical '-' gap handling and requests-install workflow fix, consolidated for manual upload.

## Verification and limits
- `python -m pytest -q tests`: 278 passed, 19 existing pandas FutureWarnings, 28.55s. Includes Publication/PIT/Economic/Research/Decision/Fed tests and offline end-to-end regression.
- Live alternate tests simulated only the blocked RSS/current-PDF responses; published BLS release pages, official calendar, DOL archive form and discovered PDF were fetched over HTTP. All three BLS release groups and DOL passed.
- Seven BLS value tests replayed the successful official batch supplied by the user (audit retrieved_at 2026-10-02T22:07:48 UTC), joined to live official publication metadata. No new authenticated BLS API request was made; no local access to GitHub Secrets.
- Census authenticated corrected request must be verified in GitHub. No local key was provided.
- ISM manufacturing remains unresolved for automated direct retrieval. No provider substitution, paid access or fabricated values.
- No live all-14 merge/publication was attempted. The production all-14 gate remains closed until every source passes. No app.py or public_data change in this ZIP.

## Source verification matrix
| Indicator | Result in this repair validation | Reference period | Release date | Value |
|---|---|---|---|---|
| NFP | User API evidence + live official metadata VERIFIED | September 2026 | 2026-10-02 | 29000.0 |
| UNEMPLOYMENT_RATE | User API evidence + live official metadata VERIFIED | September 2026 | 2026-10-02 | 4.2 |
| AVERAGE_HOURLY_EARNINGS | User API evidence + live official metadata VERIFIED | September 2026 | 2026-10-02 | 0.1 |
| CPI | User API evidence + live official metadata VERIFIED | August 2026 | 2026-09-11 | 0.4 |
| CORE_CPI | User API evidence + live official metadata VERIFIED | August 2026 | 2026-09-11 | 0.3 |
| PPI_FINAL_DEMAND | User API evidence + live official metadata VERIFIED | August 2026 | 2026-09-10 | 0.4 |
| CORE_PPI | User API evidence + live official metadata VERIFIED | August 2026 | 2026-09-10 | 0.2 |
| GDP | Supplied audit: REVISION | Q2 2026 | 2026-09-30 | 2.2 |
| PCE_PRICE_INDEX | Supplied audit: NEW_RELEASE | August 2026 | 2026-09-30 | 0.3 |
| CORE_PCE | Supplied audit: NEW_RELEASE | August 2026 | 2026-09-30 | 0.2 |
| RETAIL_SALES | Corrected API query; authenticated live validation pending | Unverified | Unverified | Unverified |
| INITIAL_JOBLESS_CLAIMS | Live official archive alternate VERIFIED | Week ending September 26, 2026 | 2026-10-01 | 197000; previous revised 198000 |
| ISM_MANUFACTURING_PMI | SOURCE_ERROR: licensed redirect/CAPTCHA | Unverified | Unverified | Unverified |
| ISM_SERVICES_PMI | Supplied audit: CURRENT | August 2026 | 2026-09-03 | 55.4 |

Canonical/public state before and after: unchanged for every indicator. Values above have not been published by this repair.

## Contents / installation
Replace files at their exact archive-relative paths. Start a NEW `Official Economic Ingestion Audit` run on main. Upload its artifact for verification. Do not rerun an old commit snapshot.

- `economic_official_sources_v1.py`
- `economic_official_ingestion_v1.py`
- `economic_observation_order_v1.py`
- `point_in_time.py`
- `economic_bls_employment_ingestion_v1.py`
- `.github/workflows/official-economic-ingestion-audit.yml`
- `.github/workflows/economic-14-official-source-audit.yml`
- `.github/workflows/test-bls-employment-ingestion.yml`
- `tests/test_official_endpoint_alternates.py`
- `tests/test_official_http_diagnostics.py`
- `tests/test_bls_missing_observations.py`
