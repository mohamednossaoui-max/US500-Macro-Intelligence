# Economic Historical Coverage Expansion — PCE/Core PCE v2

Scope: Economic ingestion/coverage only. No Decision Engine, Fed, UI, or scoring-rule changes.

- Adds a fail-closed BEA archived-news-release collector for PCE and Core PCE.
- Uses the original release page and embargo timestamp; does not use revised current time-series as historical vintages.
- Does not fabricate consensus or convert ambiguous "less than 0.1" wording to a made-up point estimate.
- Seeds verified Dec-2025 through Jul-2026 PCE/Core-PCE original releases so the current snapshot has enough PIT history immediately.
- Updates the v2.3 workflow to expand PCE history before canonical staging and requires >=18 PCE/Core-PCE records when the network collector runs.
- Regenerated Economic Surprise/Regime public artifacts from the expanded canonical input.

Local regression after seeded expansion: 99 passed / 0 failed.
Latest regime snapshot (2026-09-17): all 3 dimensions available; regime MIXED.
