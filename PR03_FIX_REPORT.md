# PR-03 Publication Integrity Fix Report

## Canonical ownership
- `public_data/manifest.json` is the only publication manifest used by runtime code.
- The retired `public_data/public_data_manifest.json` is treated only as a forbidden legacy file by integrity guards/tests.

## Files changed
- `scripts/verify_publication_integrity.py`
- `tests/test_publication_integrity.py`
- `app.py`
- `public_data/manifest.json`
- `.github/workflows/us500-full-research-pipeline.yml`
- `.github/workflows/publish_research_data_v1.yml`

## Safety fixes
- Verifier now returns exit code 1 on missing/mismatched artifacts or legacy-manifest presence.
- Runtime legacy fallback was removed from `app.py`.
- Legacy manifest was removed from the canonical manifest payload list.
- Full research pipeline no longer retains/copies publication-manifest JSON artifacts.
- Publisher excludes publication manifest metadata from payload hashing.
- Tests now enforce canonical-only behavior and legacy retirement.

## Local validation
- `python -m pytest -q tests/test_publication_integrity.py` -> 9 passed.
- `python scripts/verify_publication_integrity.py` -> 77/77 match, 0 mismatch, 0 missing.
- `python -m py_compile app.py scripts/verify_publication_integrity.py tests/test_publication_integrity.py` -> passed.
- No production reference to `public_data_manifest.json` remains outside the dedicated retirement guard/verifier/test.

## Expected canonical count
The canonical manifest now contains 77 payload artifacts. The previous count of 78 included the retired legacy manifest itself, which was the source of the contradictory `MISSING: public_data_manifest.json` failure.
