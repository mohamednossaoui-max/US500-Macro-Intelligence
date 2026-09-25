You are working directly inside the GitHub repository:

mohamednossaoui-max/US500-Macro-Intelligence

Your task is to BUILD and IMPLEMENT the next production-ready Streamlit frontend:

US500 MACRO INTELLIGENCE — RESEARCH TERMINAL V6.0

The project is RESEARCH-ONLY.

DO NOT introduce:

* buy/sell signals
* trading recommendations
* entry/exit prices
* stop loss / take profit
* position sizing
* broker integration
* trade execution
* automated trading
* predictive forecasts
* optimization for trading
* causal claims
* ranking of market regimes as “best” or “worst”

The frontend must display research evidence clearly and professionally without converting it into trading instructions.

==================================================

1. FIRST — INSPECT THE EXISTING REPOSITORY
    ==================================================

Before changing anything:

1. Inspect the existing app.py.
2. Inspect public_data/.
3. Inspect public_data/public_data_manifest.json.
4. Inspect the existing GitHub Actions workflows.
5. Inspect the existing Decision Engine files.
6. Inspect the existing Historical Event Study files.
7. Inspect the Historical Edge Robustness files/workflow.
8. Determine the exact current CSV/JSON schemas instead of guessing column names.
9. Do NOT rewrite backend research modules that are already completed.
10. Preserve all existing research logic.

The following stages are already completed and should be treated as CLOSED unless a compatibility fix is absolutely necessary:

* Economic Intelligence
* Financial Stress
* Fed Intelligence
* Event / News Intelligence
* COT Historical
* COT Positioning
* VIX Historical
* VIX Sentiment
* AAII Historical
* AAII Sentiment
* Technical Intelligence
* Liquidity Historical
* Liquidity Intelligence
* Market Breadth
* Cross Asset Intelligence
* Earnings Intelligence
* Macro Context
* Sentiment Engine
* Research Context
* Research Integration Full Validation
* Final End-to-End Validation
* Decision Engine V1
* Historical Event Study V2
* Historical Edge Robustness V1

Do not restart these pipelines.

==================================================
2. CURRENT VERIFIED PIPELINE STATE

Use these verified results in the dashboard where appropriate:

MASTER PIPELINE
Run:
36139637088
Status:
PASS

MACRO CONTEXT
Run:
36181485481
Status:
PASS

SENTIMENT ENGINE
Run:
36183227935
Status:
PASS

RESEARCH INTEGRATION FULL VALIDATION
Run:
36184596061
Status:
PASS

FINAL END-TO-END VALIDATION
Run:
36186001790
Status:
PASS

DECISION ENGINE V1
Run:
36189840012
Status:
PASS

Decision Engine result:

* State: SUPPORTIVE
* Confidence: 1.0
* Evidence count: 4
* Supportive: 2
* Contradictory: 0
* Mixed: 2
* Point-in-time safe: TRUE
* Research only: TRUE
* Trading signal: NONE
* Forecast: NONE
* Execution: FALSE
* Position sizing: FALSE
* Stop loss: NONE
* Take profit: NONE

Decision Engine evidence:

1. Macro Context
    Value: MIXED
    Stance: MIXED
2. Financial Stress
    Value: LOW_RESEARCH_STRESS
    Stance: SUPPORTIVE
3. Sentiment Engine
    Value: NEUTRAL
    Stance: MIXED
4. Technical Intelligence
    Value: BULLISH
    Stance: SUPPORTIVE

HISTORICAL EVENT STUDY V2
Run:
36190915225
Status:
PASS

Verified:

* Common sample: 1,916
* Date range: 2019-01-03 → 2026-08-18
* Event definitions: 11
* Horizons: 1D / 5D / 20D
* Research only: TRUE
* Decision Engine ready: FALSE
* Trading signal: FALSE
* Forecast: FALSE
* PIT-perfect: FALSE

HISTORICAL EDGE ROBUSTNESS V1
Run:
36192353073
Status:
PASS

Verified:

* Common sample: 1,916
* Base events: 11
* Temporal periods: 4
* Temporal rows: 132
* Threshold sensitivity rows: 87
* Temporal stability rows: 33
* Threshold stability rows: 24
* Horizon stability rows: 11
* PIT audit rows: 3
* Research-only: TRUE
* Decision Engine: FALSE
* Trading signal: FALSE
* Forecast: FALSE
* Optimization: FALSE
* Causal claim: FALSE
* PIT-perfect: FALSE

Temporal periods:

* FULL_SAMPLE
* 2019_2021
* 2022_2023
* 2024_2026

Important limitation:
Some historical event definitions have limited sample sizes.

==================================================
3. MAIN PROBLEM TO SOLVE

The existing Streamlit application looks too much like a CSV viewer.

The new V6.0 must look like a professional research terminal.

It must make the research architecture understandable at a glance.

The user should immediately see:

* current research context
* economic regime
* financial stress
* Fed score
* sentiment
* technical regime
* Decision Engine classification
* evidence behind that classification
* Historical Edge status
* robustness status
* system health
* data availability
* PIT limitations

Do not simply display raw tables.

Tables should be secondary.

==================================================
4. TOKEN-FREE REQUIREMENT

CRITICAL:

The application must work WITHOUT a personal GitHub token.

Do NOT require:

* GITHUB_TOKEN
* personal access token
* GitHub secret
* OAuth
* GitHub API authentication

The frontend should primarily read public files using:

https://raw.githubusercontent.com/mohamednossaoui-max/US500-Macro-Intelligence/main/public_data/...

Also support a local:

public_data/

directory as fallback.

Implement:

1. local public_data first
2. public GitHub raw files second
3. graceful “Not published” state if neither exists

Never crash because a dataset is missing.

Never show misleading values.

==================================================
5. FIX THE PREVIOUS BUG

There was a Streamlit error caused by:

dec = latest(DATA["Decision Summary"]) or latest(DATA["Decision Engine"])

because pandas objects cannot be evaluated as booleans.

Never use pandas DataFrame/Series in boolean or expressions.

Use:

dec = latest(DATA["Decision Summary"])
if dec is None:
    dec = latest(DATA["Decision Engine"])

Apply the same principle everywhere.

==================================================
6. BUILD A PROFESSIONAL DASHBOARD

Create a strong Executive Overview.

Top header:

US500 MACRO INTELLIGENCE
RESEARCH TERMINAL V6.0

Show:

As of:
[latest available research date]

Data:
POINT-IN-TIME RESEARCH

Then create six prominent state cards:

ECONOMIC
MIXED

FINANCIAL STRESS
LOW_RESEARCH_STRESS

FED
55.7

SENTIMENT
NEUTRAL

TECHNICAL
BULLISH

DECISION ENGINE
SUPPORTIVE

Do not color these according to “trade direction”.
Use neutral professional UI styling.

==================================================
7. RESEARCH CONTEXT SECTION

Create a visual Research Context panel containing:

Economic
Financial Stress
Sentiment
Technical
Fed
Event / News

Each should show:

* latest value
* source
* date
* freshness where available
* PIT status where available

Example:

Economic
MIXED

Financial Stress
LOW_RESEARCH_STRESS

Sentiment
NEUTRAL

Technical
BULLISH

Fed
55.7

Event / News
FED
2 days old

==================================================
8. EVIDENCE MATRIX

This is extremely important.

Create a professional evidence matrix.

Columns:

Source
Category
Value
Stance
Reason

Populate it from:

decision_engine_research_evidence_v1.csv

Current verified evidence:

Macro Context | economic | MIXED | MIXED
Financial Stress | financial_stress | LOW_RESEARCH_STRESS | SUPPORTIVE
Sentiment Engine | sentiment | NEUTRAL | MIXED
Technical Intelligence | technical | BULLISH | SUPPORTIVE

Show the Decision Engine result above the matrix:

State:
SUPPORTIVE

Confidence:
1.0

Confidence type:
Evidence Coverage

Evidence:
4

Supportive:
2

Contradictory:
0

Mixed:
2

Make clear:

“Confidence represents evidence coverage, not probability.”

==================================================
9. DECISION ENGINE PAGE

Build a proper Decision Engine research page.

Show:

Research classification
SUPPORTIVE

Evidence coverage
1.0

Evidence count
4

Supportive
2

Contradictory
0

Mixed
2

Then show an evidence chain:

Macro Context
↓
Financial Stress
↓
Sentiment
↓
Technical Intelligence
↓
Research Classification

Then show safeguards:

Point-in-time safe
TRUE

Research only
TRUE

Trading signal
NONE

Forecast
NONE

Execution
FALSE

Broker integration
FALSE

Position sizing
FALSE

Stop loss
NONE

Take profit
NONE

Do not convert SUPPORTIVE into BUY/BULLISH TRADE/etc.

==================================================
10. HISTORICAL EDGE PAGE

Create a dedicated Historical Edge page.

Display:

Historical Event Study V2

Common Sample
1,916

Date Range
2019-01-03 → 2026-08-18

Events
11

Horizons
1D / 5D / 20D

Validation
PASS

Then:

Historical Edge Robustness V1

Run:
36192353073

Status:
PASS

Temporal periods:
4

Temporal rows:
132

Threshold rows:
87

PIT Perfect:
FALSE

Show the four periods:

FULL_SAMPLE
2019_2021
2022_2023
2024_2026

Clearly display:

“PIT-perfect = FALSE”

Do NOT hide this limitation.

Also display:

“Some event definitions have limited historical sample sizes.”

Important:

If the detailed Historical Edge Robustness CSV files are NOT present in public_data, do NOT fabricate them.

Instead display:

“Robustness validation completed successfully, but detailed robustness tables are not currently published in public_data.”

If the files become available later, automatically load and display them.

==================================================
11. SYSTEM HEALTH PAGE

Create a professional system health page.

Show:

17 / 17 Core Modules

Validation:
PASS

Research-only:
TRUE

Decision Engine:
PASS

Historical Edge:
PASS

Then show pipeline milestones:

Master Pipeline
36139637088
PASS

Macro Context
36181485481
PASS

Sentiment Engine
36183227935
PASS

Research Integration
36184596061
PASS

Final End-to-End
36186001790
PASS

Decision Engine
36189840012
PASS

Historical Event Study V2
36190915225
PASS

Historical Edge Robustness
36192353073
PASS

Do not claim these are live runs. Label them as “verified pipeline milestones”.

==================================================
12. DATA STATUS PAGE

Create a proper data-status interface.

For every important dataset show:

Dataset
File
Status
Source

Statuses:

AVAILABLE
NOT PUBLISHED

Important files include:

research_context_v1.csv
macro_context_v1.csv
economic_regime_events_v1.csv
economic_surprise_engine_v1.csv
fed_intelligence_output_v1.json
financial_stress_research_v1.csv
liquidity_intelligence_research_v1.csv
cot_positioning_research_v1.csv
aaii_sentiment_research_v1.csv
vix_sentiment_research_v1.csv
sentiment_engine_research_v1.csv
technical_intelligence_research_v1.csv
market_breadth_analysis_v1.csv
cross_asset_research_v1.csv
event_news_research_v2.csv
earnings_market_reaction_v3.csv
decision_engine_research_v1.csv
decision_engine_research_summary_v1.csv
decision_engine_research_evidence_v1.csv
decision_engine_research_v1.json
final_end_to_end_validation_report.csv

Also check dynamically for:

historical_edge_robustness_validation_v1.json
historical_edge_temporal_robustness_v1.csv
historical_edge_threshold_sensitivity_v1.csv
historical_edge_temporal_stability_v1.csv
historical_edge_threshold_stability_v1.csv
historical_edge_horizon_stability_v1.csv
historical_edge_sample_adequacy_v1.csv
historical_edge_event_overlap_v1.csv
historical_edge_pit_audit_v1.csv

==================================================
13. DEDICATED MODULE PAGES

Create individual pages for:

1. Executive Overview
2. Research Context
3. Economic Intelligence
4. Fed Intelligence
5. Financial Stress
6. Liquidity
7. COT Positioning
8. AAII Sentiment
9. VIX Sentiment
10. Unified Sentiment
11. Technical Intelligence
12. Market Breadth
13. Cross-Asset Intelligence
14. Event / News Intelligence
15. Earnings Intelligence
16. Historical Edge
17. Decision Engine
18. Evidence Matrix
19. System Health
20. Methodology & Limitations

The sidebar should be organized logically into groups if Streamlit’s navigation supports it.

Do not create unnecessary backend duplication.

==================================================
14. CHARTS

The current application has too few visualizations.

Add useful descriptive charts where the actual dataset supports them.

Examples:

Economic:

* surprise/composite score over time

Financial Stress:

* composite stress over time
* VIX over time

Liquidity:

* net liquidity proxy
* liquidity change

Sentiment:

* sentiment score over time

Technical:

* drawdown over time

Market Breadth:

* breadth score/state-related numeric series

Cross Asset:

* available composite/risk metrics

Earnings:

* historical reaction series

Do not invent metrics.

If a dataset does not contain a chartable numeric field, show a clear message instead of fabricating one.

Charts must be descriptive only.

==================================================
15. FRESHNESS

Where dates exist, calculate and display:

Latest observation
Data age

For example:

Latest:
2026-09-18

Age:
2 days

Do not call old data “live”.

Use labels such as:

Latest Published Observation
Research As-of Date
Data Age

==================================================
16. POINT-IN-TIME AUDIT

Do not simply display “PIT TRUE”.

Create a small PIT audit area.

Show:

Research Context PIT
Financial Stress PIT
Decision Engine PIT
Historical Edge PIT

Where the actual dataset exposes the corresponding fields.

If a layer does not provide a PIT flag, say:

“Not exposed by this dataset”

Do not infer TRUE.

For Historical Edge specifically, show:

PIT-perfect:
FALSE

and explain that this is a documented validation limitation.

==================================================
17. METHODOLOGY PAGE

Create a professional Methodology & Limitations page.

Include:

Research-only boundary

Point-in-time methodology

Data freshness

Historical Event Study methodology

Historical Edge methodology

Decision Engine methodology

Evidence coverage definition

Limitations

Explicitly state:

“Decision Engine confidence is evidence coverage, not probability.”

“Historical Event Study and Historical Edge are descriptive research diagnostics.”

“PASS means structural validation passed; it does not establish causality, predictiveness, profitability, or usefulness.”

“Some historical event definitions have limited sample sizes.”

“PIT-perfect is FALSE for the current Historical Edge robustness validation.”

==================================================
18. VISUAL DESIGN

The application should NOT look like a raw dataframe browser.

Use:

* professional research-terminal style
* strong hierarchy
* clean cards
* compact metrics
* section headers
* expandable details
* consistent spacing
* responsive layout
* readable typography
* neutral professional colors
* charts
* status badges
* evidence matrix
* clear research labels

Avoid excessive decoration.

Avoid giant empty spaces.

Avoid excessive emojis.

Use emojis only in sidebar/navigation if useful.

==================================================
19. STREAMLIT COMPATIBILITY

Use modern Streamlit APIs where available.

If using:

st.navigation
st.Page

make sure the implementation remains compatible with the Streamlit version declared in requirements.

If compatibility is uncertain, implement the navigation in a robust single-file manner rather than introducing a fragile dependency.

The application must run with:

streamlit run app.py

==================================================
20. ERROR HANDLING

The application must never crash because:

* GitHub raw is temporarily unavailable
* a CSV is missing
* a JSON is missing
* a column name changed
* a dataset is empty
* a date cannot be parsed
* a numeric field contains invalid data

Use graceful fallbacks.

Display:

“Not published”

or:

“Unavailable”

rather than raising an exception.

==================================================
21. DO NOT HARDCODE DATA VALUES WHEN DATA EXISTS

Use actual public_data files whenever available.

The verified pipeline milestone numbers may be displayed as metadata because they are validated historical run references.

But research values such as:

* regime
* scores
* dates
* event values
* sentiment
* technical values

must come from datasets.

Do not hardcode them if the dataset exists.

==================================================
22. PUBLIC DATA MANIFEST

Read:

public_data/public_data_manifest.json

when available.

Display:

* generated_at_utc
* master_run_id
* dataset_count

But clearly distinguish:

“Manifest generation time”

from:

“Latest dataset observation”.

The current known manifest was generated by Master Pipeline run:

36139637088

and may predate later Decision Engine and Historical Edge Robustness outputs.

Do not pretend the manifest is automatically updated after those later workflows.

==================================================
23. DYNAMIC DATA DISCOVERY

Create a reusable data loader.

Recommended behavior:

load local public_data
        ↓
if unavailable
        ↓
load GitHub raw public_data
        ↓
if unavailable
        ↓
show NOT PUBLISHED

Cache requests using Streamlit caching.

Use reasonable timeout values.

No personal token.

==================================================
24. FILE STRUCTURE

Prefer a simple deployment structure:

app.py
requirements.txt
README.md

If you believe additional files are necessary, keep the architecture simple.

Do NOT create unnecessary backend modules.

The main dashboard must remain easy to deploy on Streamlit Cloud.

==================================================
25. REQUIREMENTS.TXT

Make sure requirements include compatible versions of:

streamlit
pandas
requests

Only add other packages if they are actually used.

==================================================
26. README

Create/update README.md with:

* what the dashboard does
* how to run it
* token-free operation
* GitHub raw data source
* architecture overview
* research-only restrictions
* current limitations

==================================================
27. TESTING

Before finishing:

1. Run Python syntax validation.
2. Run import validation.
3. Check that app.py starts without syntax errors.
4. Search the code for dangerous pandas boolean patterns such as:
    df or other
    series or other
5. Verify no GitHub personal token is required.
6. Verify no trading signal logic was added.
7. Verify no forecast logic was added.
8. Verify no SL/TP logic was added.
9. Verify no broker/execution logic was added.
10. Verify missing datasets do not crash the app.
11. Verify all navigation pages render safely.
12. Verify the Decision Engine page reads the evidence CSV.
13. Verify Historical Edge displays the verified run summary.
14. Verify unpublished Historical Edge detailed files are not fabricated.
15. Verify the dashboard works using only public GitHub raw URLs.

==================================================
28. IMPORTANT — DO NOT MODIFY CLOSED BACKEND LOGIC

This task is primarily FRONTEND / STREAMLIT.

Do not rewrite:

Economic Intelligence
Macro Context
Sentiment Engine
Research Context
Decision Engine
Historical Event Study
Historical Edge Robustness

unless you find a direct compatibility issue with the dashboard.

If a compatibility issue exists, make the smallest possible change.

==================================================
29. FINAL OUTPUT REQUIRED

After implementation:

1. Show exactly which files were created/modified.
2. Show the final app.py structure.
3. Show the final requirements.
4. Run validation.
5. Report validation results.
6. If possible, run the Streamlit app or at minimum compile/import-check it.
7. Do not merely describe what should be done — actually implement it in the repository.

The final result must be a complete working:

US500 Macro Intelligence — Research Terminal V6.0

that visually presents the research results rather than simply exposing CSV tables.

The most important success criterion is:

THE USER SHOULD OPEN THE STREAMLIT APP AND IMMEDIATELY SEE THE ACTUAL RESEARCH STATE, EVIDENCE CHAIN, HISTORICAL EDGE STATUS, ROBUSTNESS STATUS, AND SYSTEM HEALTH — WITHOUT NEEDING A GITHUB TOKEN.

Do not ask me to manually rewrite the code. Implement the changes directly in the repository.
