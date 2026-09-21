"""
US500 Macro Intelligence
Sentiment Engine v1

Research-only unified sentiment layer.

Inputs:
    cot_positioning_research_v1.csv
    aaii_sentiment_research_v1.csv
    vix_sentiment_research_v1.csv

Outputs:
    sentiment_engine_research_v1.csv
    sentiment_engine_research_summary_v1.csv
    sentiment_engine_extremes_v1.csv

Design:
    - Point-in-time as-of reconstruction
    - Uses availability_date, not observation_date
    - No look-ahead
    - COT + AAII + VIX
    - Unified normalized sentiment score: 0-100
    - Descriptive historical regimes only

Score interpretation:
    0   = most bearish historical sentiment
    50  = neutral
    100 = most bullish historical sentiment

COT:
    Asset Manager percentile -> bullish
    Leveraged Money percentile -> inverse

AAII:
    Bull-Bear Spread percentile -> bullish

VIX:
    VIX percentile inverted -> bullish

Research-only:
    - No trading signal
    - No forecast
    - No market prediction
    - No Decision Engine integration
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

COT_INPUT = Path(
    "cot_positioning_research_v1.csv"
)

AAII_INPUT = Path(
    "aaii_sentiment_research_v1.csv"
)

VIX_INPUT = Path(
    "vix_sentiment_research_v1.csv"
)

OUTPUT = Path(
    "sentiment_engine_research_v1.csv"
)

SUMMARY = Path(
    "sentiment_engine_research_summary_v1.csv"
)

EXTREMES = Path(
    "sentiment_engine_extremes_v1.csv"
)

MIN_COMPONENTS = 2

RESEARCH_ONLY = True

DECISION_ENGINE_READY = False

SENTIMENT_SCORE_GENERATED = True

POINT_IN_TIME_SAFE = True


# ============================================================
# HELPERS
# ============================================================

def fail(message: str) -> None:

    print()
    print("=" * 72)
    print("SENTIMENT ENGINE V1: FAIL")
    print("=" * 72)
    print(message)
    print("=" * 72)

    sys.exit(1)


def load_csv(path: Path) -> pd.DataFrame:

    if not path.exists():
        fail(f"Input file not found: {path}")

    try:
        df = pd.read_csv(path)
    except Exception as exc:
        fail(f"Unable to read {path}: {exc}")

    if df.empty:
        fail(f"Input contains zero rows: {path}")

    return df


def validate_common_pit(
    df: pd.DataFrame,
    name: str,
) -> pd.DataFrame:

    required = [
        "observation_date",
        "availability_date",
        "point_in_time_safe",
        "research_only",
        "decision_engine_ready",
    ]

    missing = [
        c for c in required
        if c not in df.columns
    ]

    if missing:
        fail(
            f"{name}: missing columns: {missing}"
        )

    df["observation_date"] = pd.to_datetime(
        df["observation_date"],
        errors="coerce",
    )

    df["availability_date"] = pd.to_datetime(
        df["availability_date"],
        errors="coerce",
    )

    if df["observation_date"].isna().any():
        fail(f"{name}: invalid observation_date.")

    if df["availability_date"].isna().any():
        fail(f"{name}: invalid availability_date.")

    if not (
        df["availability_date"]
        > df["observation_date"]
    ).all():
        fail(
            f"{name}: PIT validation failed."
        )

    if not df[
        "point_in_time_safe"
    ].astype(bool).all():
        fail(
            f"{name}: non-PIT-safe rows detected."
        )

    if not df[
        "research_only"
    ].astype(bool).all():
        fail(
            f"{name}: non-research rows detected."
        )

    if df[
        "decision_engine_ready"
    ].astype(bool).any():
        fail(
            f"{name}: Decision Engine integration detected."
        )

    df = (
        df
        .sort_values("availability_date")
        .reset_index(drop=True)
    )

    if df[
        "availability_date"
    ].duplicated().any():
        fail(
            f"{name}: duplicate availability dates."
        )

    return df


# ============================================================
# LOAD INPUTS
# ============================================================

print("=" * 72)
print("SENTIMENT ENGINE V1")
print("=" * 72)

cot = load_csv(COT_INPUT)
aaii = load_csv(AAII_INPUT)
vix = load_csv(VIX_INPUT)

print(
    f"COT rows:  {len(cot):,}"
)

print(
    f"AAII rows: {len(aaii):,}"
)

print(
    f"VIX rows:  {len(vix):,}"
)


# ============================================================
# VALIDATE INPUTS
# ============================================================

cot = validate_common_pit(
    cot,
    "COT",
)

aaii = validate_common_pit(
    aaii,
    "AAII",
)

vix = validate_common_pit(
    vix,
    "VIX",
)


# ============================================================
# REQUIRED ANALYZER COLUMNS
# ============================================================

cot_required = [
    "asset_manager_net_percentile",
    "leveraged_money_net_percentile",
]

aaii_required = [
    "bull_bear_spread_percentile",
]

vix_required = [
    "VIX_percentile",
]

for column in cot_required:

    if column not in cot.columns:
        fail(
            f"COT missing analyzer column: {column}"
        )

for column in aaii_required:

    if column not in aaii.columns:
        fail(
            f"AAII missing analyzer column: {column}"
        )

for column in vix_required:

    if column not in vix.columns:
        fail(
            f"VIX missing analyzer column: {column}"
        )


# ============================================================
# NORMALIZE SOURCE SCORES
# ============================================================

# COT:
# Asset Manager high percentile = bullish
# Leveraged Money high percentile = bearish
#
# Therefore:
#
# COT score =
# mean(
#     Asset Manager percentile,
#     100 - Leveraged Money percentile
# )

cot["cot_asset_manager_score"] = (
    pd.to_numeric(
        cot["asset_manager_net_percentile"],
        errors="coerce",
    )
)

cot["cot_leveraged_money_score"] = (
    100.0
    -
    pd.to_numeric(
        cot["leveraged_money_net_percentile"],
        errors="coerce",
    )
)

cot["cot_sentiment_score"] = (
    cot[
        [
            "cot_asset_manager_score",
            "cot_leveraged_money_score",
        ]
    ]
    .mean(axis=1, skipna=True)
)


# AAII:
# High Bull-Bear spread percentile = bullish

aaii["aaii_sentiment_score"] = (
    pd.to_numeric(
        aaii["bull_bear_spread_percentile"],
        errors="coerce",
    )
)


# VIX:
# High VIX = fear/bearish
# Low VIX = less fear/bullish
#
# Therefore invert percentile.

vix["vix_sentiment_score"] = (
    100.0
    -
    pd.to_numeric(
        vix["VIX_percentile"],
        errors="coerce",
    )
)


# ============================================================
# PREPARE AS-OF TABLES
# ============================================================

cot_asof = cot[
    [
        "availability_date",
        "observation_date",
        "cot_asset_manager_score",
        "cot_leveraged_money_score",
        "cot_sentiment_score",
    ]
].rename(
    columns={
        "availability_date":
            "cot_availability_date",

        "observation_date":
            "cot_observation_date",
    }
)

aaii_asof = aaii[
    [
        "availability_date",
        "observation_date",
        "aaii_sentiment_score",
    ]
].rename(
    columns={
        "availability_date":
            "aaii_availability_date",

        "observation_date":
            "aaii_observation_date",
    }
)

vix_asof = vix[
    [
        "availability_date",
        "observation_date",
        "vix_sentiment_score",
    ]
].rename(
    columns={
        "availability_date":
            "vix_availability_date",

        "observation_date":
            "vix_observation_date",
    }
)


# ============================================================
# AS-OF CALENDAR
# ============================================================

start_date = min(
    cot["availability_date"].min(),
    aaii["availability_date"].min(),
    vix["availability_date"].min(),
)

end_date = max(
    cot["availability_date"].max(),
    aaii["availability_date"].max(),
    vix["availability_date"].max(),
)

calendar = pd.DataFrame(
    {
        "asof_date":
            pd.date_range(
                start=start_date,
                end=end_date,
                freq="D",
            )
    }
)


# ============================================================
# POINT-IN-TIME AS-OF RECONSTRUCTION
# ============================================================

def asof_merge(
    left: pd.DataFrame,
    right: pd.DataFrame,
    right_date_column: str,
) -> pd.DataFrame:

    return pd.merge_asof(
        left.sort_values("asof_date"),
        right.sort_values(right_date_column),
        left_on="asof_date",
        right_on=right_date_column,
        direction="backward",
    )


result = asof_merge(
    calendar,
    cot_asof,
    "cot_availability_date",
)

result = asof_merge(
    result,
    aaii_asof,
    "aaii_availability_date",
)

result = asof_merge(
    result,
    vix_asof,
    "vix_availability_date",
)


# ============================================================
# COMPONENT AVAILABILITY
# ============================================================

result["cot_available"] = (
    result["cot_sentiment_score"]
    .notna()
)

result["aaii_available"] = (
    result["aaii_sentiment_score"]
    .notna()
)

result["vix_available"] = (
    result["vix_sentiment_score"]
    .notna()
)

result["available_component_count"] = (
    result[
        [
            "cot_available",
            "aaii_available",
            "vix_available",
        ]
    ]
    .sum(axis=1)
)


# ============================================================
# UNIFIED SCORE
# ============================================================

component_columns = [
    "cot_sentiment_score",
    "aaii_sentiment_score",
    "vix_sentiment_score",
]

result["unified_sentiment_score"] = (
    result[
        component_columns
    ]
    .mean(
        axis=1,
        skipna=True,
    )
)

result.loc[
    result["available_component_count"]
    < MIN_COMPONENTS,
    "unified_sentiment_score",
] = np.nan


# ============================================================
# RESEARCH REGIME
# ============================================================

score = result[
    "unified_sentiment_score"
]

conditions = [
    score >= 80,
    score >= 60,
    score <= 20,
    score <= 40,
]

choices = [
    "EXTREME_BULLISH",
    "BULLISH",
    "EXTREME_BEARISH",
    "BEARISH",
]

result["research_regime"] = np.select(
    conditions,
    choices,
    default="NEUTRAL",
)

result.loc[
    score.isna(),
    "research_regime",
] = "INSUFFICIENT_DATA"


# ============================================================
# EXTREME FLAG
# ============================================================

result["extreme_sentiment"] = (
    (
        result["unified_sentiment_score"]
        >= 80
    )
    |
    (
        result["unified_sentiment_score"]
        <= 20
    )
)


# ============================================================
# METADATA
# ============================================================

result["point_in_time_safe"] = True

result["research_only"] = True

result["decision_engine_ready"] = False

result["sentiment_score_generated"] = True

result["trading_signal_generated"] = False

result["forecast_generated"] = False


# ============================================================
# VALIDATE FINAL OUTPUT
# ============================================================

if result.empty:
    fail("Unified sentiment output is empty.")

if not result[
    "point_in_time_safe"
].all():
    fail(
        "Final output contains non-PIT-safe rows."
    )

if not result[
    "research_only"
].all():
    fail(
        "Final output contains non-research rows."
    )

if result[
    "decision_engine_ready"
].any():
    fail(
        "Decision Engine flag detected."
    )

if result[
    "trading_signal_generated"
].any():
    fail(
        "Trading signal generated."
    )

if result[
    "forecast_generated"
].any():
    fail(
        "Forecast generated."
    )

valid_scores = result[
    "unified_sentiment_score"
].dropna()

if (
    (valid_scores < 0)
    |
    (valid_scores > 100)
).any():
    fail(
        "Unified sentiment score outside 0-100."
    )


allowed_regimes = {
    "EXTREME_BULLISH",
    "BULLISH",
    "NEUTRAL",
    "BEARISH",
    "EXTREME_BEARISH",
    "INSUFFICIENT_DATA",
}

unexpected = (
    set(
        result["research_regime"]
        .dropna()
        .unique()
    )
    -
    allowed_regimes
)

if unexpected:
    fail(
        f"Unexpected research regimes: {unexpected}"
    )


# ============================================================
# OUTPUT COLUMNS
# ============================================================

output_columns = [
    "asof_date",

    "cot_observation_date",
    "cot_availability_date",
    "cot_asset_manager_score",
    "cot_leveraged_money_score",
    "cot_sentiment_score",

    "aaii_observation_date",
    "aaii_availability_date",
    "aaii_sentiment_score",

    "vix_observation_date",
    "vix_availability_date",
    "vix_sentiment_score",

    "cot_available",
    "aaii_available",
    "vix_available",

    "available_component_count",

    "unified_sentiment_score",

    "research_regime",
    "extreme_sentiment",

    "point_in_time_safe",
    "research_only",
    "decision_engine_ready",
    "sentiment_score_generated",
    "trading_signal_generated",
    "forecast_generated",
]

result = result[
    output_columns
]


# ============================================================
# SUMMARY
# ============================================================

latest = result.iloc[-1]

regime_counts = (
    result[
        "research_regime"
    ]
    .value_counts()
)

summary_rows = [

    {
        "metric": "total_asof_rows",
        "value": len(result),
    },

    {
        "metric": "first_asof_date",
        "value": result[
            "asof_date"
        ].min().strftime("%Y-%m-%d"),
    },

    {
        "metric": "last_asof_date",
        "value": result[
            "asof_date"
        ].max().strftime("%Y-%m-%d"),
    },

    {
        "metric": "minimum_components",
        "value": MIN_COMPONENTS,
    },

    {
        "metric": "latest_unified_sentiment_score",
        "value": latest[
            "unified_sentiment_score"
        ],
    },

    {
        "metric": "latest_research_regime",
        "value": latest[
            "research_regime"
        ],
    },

    {
        "metric": "latest_component_count",
        "value": latest[
            "available_component_count"
        ],
    },

    {
        "metric": "point_in_time_safe",
        "value": True,
    },

    {
        "metric": "research_only",
        "value": True,
    },

    {
        "metric": "decision_engine_ready",
        "value": False,
    },

    {
        "metric": "sentiment_score_generated",
        "value": True,
    },

    {
        "metric": "trading_signal_generated",
        "value": False,
    },

    {
        "metric": "forecast_generated",
        "value": False,
    },
]

for regime in [
    "EXTREME_BULLISH",
    "BULLISH",
    "NEUTRAL",
    "BEARISH",
    "EXTREME_BEARISH",
    "INSUFFICIENT_DATA",
]:

    summary_rows.append(
        {
            "metric":
                f"regime_{regime}_rows",

            "value":
                int(
                    regime_counts.get(
                        regime,
                        0,
                    )
                ),
        }
    )

summary = pd.DataFrame(
    summary_rows
)


# ============================================================
# EXTREMES
# ============================================================

extremes = result[
    result["extreme_sentiment"]
].copy()


# ============================================================
# SAVE
# ============================================================

result.to_csv(
    OUTPUT,
    index=False,
)

summary.to_csv(
    SUMMARY,
    index=False,
)

extremes.to_csv(
    EXTREMES,
    index=False,
)


# ============================================================
# REPORT
# ============================================================

print()
print("=" * 72)
print("SENTIMENT ENGINE V1 — RESULT")
print("=" * 72)

print(
    f"As-of rows: {len(result):,}"
)

print(
    f"Date range: "
    f"{result['asof_date'].min().date()} "
    f"→ "
    f"{result['asof_date'].max().date()}"
)

print()
print("Latest as-of state:")

print(
    f"  Date: "
    f"{latest['asof_date'].date()}"
)

print(
    f"  COT score: "
    f"{latest['cot_sentiment_score']}"
)

print(
    f"  AAII score: "
    f"{latest['aaii_sentiment_score']}"
)

print(
    f"  VIX score: "
    f"{latest['vix_sentiment_score']}"
)

print(
    f"  Components: "
    f"{int(latest['available_component_count'])}"
)

print(
    f"  Unified score: "
    f"{latest['unified_sentiment_score']}"
)

print(
    f"  Research regime: "
    f"{latest['research_regime']}"
)

print()
print("Point-in-time safe: TRUE")
print("Research-only: TRUE")
print("Decision Engine: DISABLED")
print("Trading signal: NONE")
print("Forecast: NONE")

print("=" * 72)
print()
print(
    "PASS: Sentiment Engine v1 completed."
)
