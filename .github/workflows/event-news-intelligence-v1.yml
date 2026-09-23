Run set -euo pipefail

========================================================================
EVENT / NEWS INTELLIGENCE v2
========================================================================
Research-only: YES
Decision Engine: DISABLED
Trading signals: DISABLED
Forecasting: DISABLED

========================================================================
GDELT COLLECTION
========================================================================
GDELT JSON parse failure: JSONDecodeError('Expecting value: line 1 column 1 (char 0)')

========================================================================
OFFICIAL RSS FALLBACK
========================================================================
fed_monetary_policy: OK rows=15
fed_all_press: OK rows=20
bls_employment: FAILED HTTP 403
bls_cpi: FAILED HTTP 403
bls_ppi: FAILED HTTP 403
bls_productivity: FAILED HTTP 403

========================================================================
SEC COLLECTION
========================================================================
SEC_USER_AGENT is missing; SEC collection skipped intentionally.

========================================================================
VALIDATION RESULT
========================================================================
{
  "validator": "Event / News Intelligence v2",
  "version": "2.0",
  "status": "FAIL",
  "validation_pass": false,
  "generated_at": "2026-09-23T00:00:43.597340+00:00",
  "rows": 35,
  "topic_counts": {
    "fed": 35
  },
  "gdelt": {
    "ok": false,
    "rows": 0,
    "error": "JSONDecodeError('Expecting value: line 1 column 1 (char 0)')",
    "query_requests": 1,
    "fallback_required": true
  },
  "official_rss": {
    "ok": true,
    "rows": 35,
    "feeds": {
      "fed_monetary_policy": {
        "ok": true,
        "rows": 15,
        "error": null
      },
      "fed_all_press": {
        "ok": true,
        "rows": 20,
        "error": null
      },
      "bls_employment": {
        "ok": false,
        "rows": 0,
        "error": "HTTP 403"
      },
      "bls_cpi": {
        "ok": false,
        "rows": 0,
        "error": "HTTP 403"
      },
      "bls_ppi": {
        "ok": false,
        "rows": 0,
        "error": "HTTP 403"
      },
      "bls_productivity": {
        "ok": false,
        "rows": 0,
        "error": "HTTP 403"
      }
    }
  },
      "pass": true,
      "detail": "not_applicable_gdelt_unavailable"
    }
  ],
  "errors": [
    {
      "check": "core_topic_coverage",
      "pass": false,
      "detail": "covered=['fed']; minimum=3"
    }
  ],
  "warnings": [
    {
      "check": "gdelt_collection",
      "detail": "GDELT unavailable or rate-limited; official RSS fallback used."
    },
    {
      "check": "sec_collection",
      "detail": "SEC skipped because SEC_USER_AGENT was not configured."
    }
  ],
  "research_only": true,
  "decision_engine_ready": false,
  "trading_signal": false,
  "forecast": false,
  "pit_perfect": false,
  "point_in_time_reconstructed": false,
  "interpretation": "PASS is structural/data-quality validation only. Event and news coverage is descriptive and does not establish causality, predictiveness, trading usefulness, or investment preference."
}

========================================================================
DATASET SUMMARY
========================================================================
rows=35
source_counts={"OFFICIAL_RSS": 35}
topic_counts={"fed": 35}
dataset=event_news_intelligence_v1/event_news_research_v2.csv
validation=event_news_intelligence_v1/event_news_validation_v2.json
summary=event_news_intelligence_v1/event_news_research_summary_v2.json

========================================================================
EXECUTION SUMMARY
========================================================================
GDELT rows: 0
Official RSS rows: 35
SEC rows: 0
Total rows: 35
Research-only: TRUE
Decision Engine: FALSE
Trading Signal: FALSE
Forecast: FALSE

EVENT / NEWS INTELLIGENCE v2 VALIDATION: FAIL
Error: Process completed with exit code 1.
