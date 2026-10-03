# US500 — BLS metadata alternate via FRED/ALFRED

## Installation (Arabic)
استبدل الملفات الموجودة في الحزمة في نفس المسارات، وأضف الملف الجديد economic_bls_fred_metadata_v1.py في جذر المشروع.
احتفظ بقيمة Secret الموجودة FRED_API_KEY؛ لا ترسلها في المحادثة. يُستخدم المفتاح فقط في environment، ولا يُدرج في المخرجات أو أسماء evidence.
شغّل Official Economic Ingestion Audit واختر ubuntu-latest. لا تحتاج self-hosted أو إبقاء الكمبيوتر مفتوحًا.
إن كان تشغيل سابق ينتظر self-hosted، ألغِ ذلك التشغيل وانتقل إلى تشغيل Audit جديد على ubuntu-latest.
نزّل official-economic-ingestion-audit artifact بعد انتهاء التشغيل.
لا تعتبر البيانات منشورة قبل نجاح المؤشرات الـ14 ثم validated merge/downstream/publication validation.

## Change and verification policy
BLS API remains the source of actual values. Only when direct BLS release metadata cannot be verified, an explicit St. Louis Fed FRED/ALFRED metadata route is attempted.
The route discovers the release ID from series/release, confirms the issuing source is BLS and validates series title, units, monthly frequency and seasonal adjustment. Employment series also require the exact original BLS series code in FRED notes.
It requires the latest due source release date from release/dates (including future/no-data dates), future calendar coverage, an identical latest ALFRED series vintage, a series update confirming availability, the same latest reference period, and exact raw-value parity across the complete numeric BLS API window at the release-date vintage.
Source release date, vintage date, reference month, FRED last_updated and retrieved_at remain distinct fields. No release time is inferred. Last_updated is a corroboration check and never defines release_date.
FRED is a distribution/corroboration provider, not the original issuing agency. Evidence explicitly records metadata_provider=FRED_ALFRED, metadata_verification=BLS_VALUE_FRED_RELEASE_VINTAGE_PARITY, metadata_series, metadata_release_id, fred_vintage_date, fred_last_updated and the direct BLS failure reason. Audit comparison exposes the provider.
If FRED is delayed, has no future calendar coverage, lacks matching vintage, disagrees with BLS values/revisions, fails authentication/network access or the key is absent, the indicator remains METADATA_UNVERIFIED with no invented release date. All-14 merge validation is unchanged.
NFP remains a monthly SA payroll-level difference multiplied by 1000, never the payroll level itself. Historical vintages and idempotent merge behavior are unchanged.

## Source mapping checked against official FRED pages
| Indicator | Original BLS series | FRED distribution series |
|---|---|---|
| NFP | CES0000000001 | PAYEMS |
| UNEMPLOYMENT_RATE | LNS14000000 | UNRATE |
| AVERAGE_HOURLY_EARNINGS | CES0500000003 | CES0500000003 |
| CPI | CUSR0000SA0 | CPIAUCSL |
| CORE_CPI | CUSR0000SA0L1E | CPILFESL |
| PPI_FINAL_DEMAND | WPSFD4 | PPIFIS |
| CORE_PPI | WPSFD49104 | PPIFES |

Source pages: https://fred.stlouisfed.org/series/PAYEMS , /UNRATE , /CES0500000003 , /CPIAUCSL , /CPILFESL , /PPIFIS , /PPIFES .
Release-date documentation: https://fred.stlouisfed.org/docs/api/fred/release_dates.html
Vintage documentation: https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html
As-of observations: https://fred.stlouisfed.org/docs/api/fred/series_observations.html
API key setup: https://fred.stlouisfed.org/docs/api/api_key.html — sign in to a FRED account and request an application API key; set GitHub repository secret FRED_API_KEY.
FRED_API_KEY is mandatory for this alternate only; direct BLS metadata can work without it. Existing BLS_API_KEY and CENSUS_API_KEY settings remain in place.

## Actual validation
- python -m pytest -q tests/test_bls_fred_metadata.py tests/test_official_endpoint_alternates.py tests/test_official_http_diagnostics.py tests/test_economic_official_ingestion_v1.py: 72 passed, 19 existing pandas FutureWarnings.
- python -m pytest -q tests: 312 passed, 19 existing pandas FutureWarnings, 20.94s. Includes Economic, PR-03, PR-04 PIT, Research, Decision and Fed regression tests; existing mocked end-to-end validation remains passing.
- python scripts/verify_publication_integrity.py --public-data public_data: Total 101, Match 101, Mismatch 0, Missing 0, Error 0.
- py_compile: PASS for the new adapter and modified ingestion modules.
- Five modified workflows parsed and FRED_API_KEY environment bindings verified.
- app.py matches original uploaded ZIP byte-for-byte.
- Public and canonical dataset bytes restored to the validated checkpoint after test execution. No live observations merged/published by this patch.

## Limitations and current state
The user's audit of 2026-10-03 confirms seven indicators verified through BEA/Census/DOL/ISM; the seven BLS indicators have API values but blocked direct release metadata.
No user's FRED key is available locally. A real network request reaches the FRED API, which correctly returns 400 without a key; this is connectivity evidence only, not authenticated ingestion success.
The alternate has 24 new fixture tests, including wrong source/series, publication lag, incorrect values or revision baselines, ambiguous vintage, missing key, HTTP failure and secret-safe evidence caching.
Authenticated all-14 live ingestion/merge/publication is still pending the GitHub Audit. No claim of 14 CURRENT or live end-to-end publication is made.
Release time remains unverified through this alternate, because the FRED date API does not prove the original agency's release time. It is not replaced with FRED update time.
FRED can lag BLS, and uncertain releases/revisions deliberately fail closed. No Trading Economics subscription, proxy, CAPTCHA bypass, local runner, new frontend changes or git mutations are required.

## Files included
- economic_bls_fred_metadata_v1.py
- economic_official_sources_v1.py
- economic_official_ingestion_v1.py
- tests/test_bls_fred_metadata.py
- .github/workflows/official-economic-ingestion-audit.yml
- .github/workflows/economic-14-official-source-audit.yml
- .github/workflows/official-economic-validated-refresh.yml
- .github/workflows/economic_intelligence_full_pipeline_v2.2.yml
- .github/workflows/economic_intelligence_full_pipeline_v2.3_refresh.yml
- US500-BLS-FRED-Metadata-Notes.md
