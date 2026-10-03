# ISM issuer distribution and audit runner update

The supplied audit(2), retrieved 2026-10-02T22:48:23Z, verifies six indicators: GDP revision, PCE/Core PCE new releases, Retail Sales revision (1.1%, August, September 28), Claims new release (197000), Services CURRENT. Seven BLS API values are available, but RSS/HTML/PDF all return HTTP 403 in the GitHub run; no release date was invented. ISM Manufacturing direct report redirects to licensed access.

## ISM alternate
Reads the primary press release issued by ISM on PR Newswire's named issuer profile, only after direct manufacturing access fails. Dynamically discovers newest manufacturing reference period; requires the exact issuer credit/link, headline/body value parity, published (not modified) timestamp with timezone, article schema/canonical URL parity, and latest-due official ISM calendar period/date/time parity. Preserves agency ISM and labels source/distribution/provenance explicitly. No private/licensed content or CAPTCHA bypass.

Current evidence test: dynamically fetched PR Newswire issuer profile/article plus the official ISM calendar from the user's audit(2) => September 2026, 54.5, October 1 at 10:00 ET. This was an evidence replay, not a fully successful new live collector: a separate live local run encountered a licensed redirect at the ISM calendar. GitHub previously read that calendar successfully, but must verify the new route. If distributor/calendar fail or disagree, fail closed.

## Audit runner
Both existing manual read-only audit workflows now let the user choose ubuntu-latest (default) or self-hosted. Selecting self-hosted DOES NOT create or install a runner. An installed online self-hosted runner is required; otherwise the job queues. No source-access guarantee. No IP-rotation, proxy, CAPTCHA solving or security bypass. No new API key.

To configure on the user's Windows computer: GitHub repository Settings > Actions > Runners > New self-hosted runner; select Windows and architecture shown for the machine; follow the exact GitHub-provided download/configure/run commands locally. Keep the runner online. Then Actions > Official Economic Ingestion Audit > Run workflow > main > runner=self-hosted. Existing repository Secrets are passed into the job; never paste them into source files or share them. This only changes the manual AUDIT execution environment, not production/Master/Autonomous runners. Production integration remains pending successful all-14 source validation.

## Validation
python -m pytest -q tests: 288 passed, 19 existing pandas FutureWarnings, 29.63s. Five distribution regressions verify issuer provenance and reject wrong issuer, wrong publication date, wrong body value and missing publication timestamp.
Both YAML files parsed and verified manual-only, contents:read, audit command, runner choice.
No app.py, canonical, or public_data changes included. No merge or publication; all-14 gate retained.

## Contents
- economic_official_sources_v1.py (cumulative current adapters including corrected MARTS mapping/BLS PDF/DOL archive; new ISM distribution route/calendar helper).
- .github/workflows/official-economic-ingestion-audit.yml
- .github/workflows/economic-14-official-source-audit.yml
- tests/test_ism_issuer_distribution.py
- US500-ISM-Runner-Repair-Notes.md

References:
https://www.prnewswire.com/news/institute-for-supply-management/
https://www.prnewswire.com/news-releases/manufacturing-pmi-at-54-5-september-2026-ism-manufacturing-pmi-report-302894520.html
https://docs.github.com/en/actions/reference/runners/self-hosted-runners

This incremental patch applies over the prior economic endpoint/Census repairs. It is not a claim that all sources or production publication now pass.
