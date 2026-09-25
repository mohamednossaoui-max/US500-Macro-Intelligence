#!/usr/bin/env python3
"""
Historical Edge — Robustness Validation v1

Research-only robustness diagnostics.

Purpose
-------
Evaluate whether descriptive historical-event relationships remain
reasonably stable under:

1. Temporal sub-period analysis
2. Event-threshold sensitivity
3. Outcome-horizon sensitivity
4. Event sample adequacy
5. Event-overlap awareness
6. Point-in-time safeguard audit

IMPORTANT
---------
This module does NOT:
- generate trading signals
- generate forecasts
- optimize parameters
- rank events
- select a preferred event
- train predictive models
- claim causality
- integrate with the Decision Engine
- perform execution or position sizing

All results are descriptive research diagnostics.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


VERSION = "historical-edge-robustness-v1"

RESEARCH_ONLY = True
DECISION_ENGINE_READY = False
TRADING_SIGNAL = False
FORECAST = False
OPTIMIZATION = False
CAUSAL_CLAIM = False

MIN_COMMON_SAMPLE = 500
MIN_EVENT_OBS = 10
MIN_STABILITY_OBS = 10

EXPECTED_TEMPORAL_PERIODS = [
    "FULL_SAMPLE",
    "2019_2021",
    "2022_2023",
    "2024_2026",
]


HORIZONS = {
    "1D": 1,
    "5D": 5,
    "20D": 20,
}


BASE_EVENTS = {
    "breadth_negative_20d": {
        "column": "breadth_research_state",
        "operator": "eq",
        "threshold": "NEGATIVE_BREADTH",
        "layer": "breadth",
    },
    "breadth_positive_20d": {
        "column": "breadth_research_state",
        "operator": "eq",
        "threshold": "POSITIVE_BREADTH",
        "layer": "breadth",
    },
    "vix_low": {
        "column": "macro_vix",
        "operator": "lt",
        "threshold": 15.0,
        "layer": "stress",
    },
    "vix_elevated": {
        "column": "macro_vix",
        "operator": "ge",
        "threshold": 25.0,
        "layer": "stress",
    },
    "financial_stress_elevated": {
        "column": "macro_financial_stress_composite",
        "operator": "gt",
        "threshold": 0.0,
        "layer": "stress",
    },
    "sentiment_bearish": {
        "column": "sentiment_unified_sentiment_score",
        "operator": "lt",
        "threshold": 40.0,
        "layer": "sentiment",
    },
    "sentiment_bullish": {
        "column": "sentiment_unified_sentiment_score",
        "operator": "gt",
        "threshold": 60.0,
        "layer": "sentiment",
    },
    "technical_drawdown_ge_5": {
        "column": "technical_drawdown_pct",
        "operator": "le",
        "threshold": -5.0,
        "layer": "technical",
    },
    "technical_drawdown_ge_10": {
        "column": "technical_drawdown_pct",
        "operator": "le",
        "threshold": -10.0,
        "layer": "technical",
    },
    "liquidity_20d_change_positive_ge_5": {
        "column": "liquidity_20d_change_pct",
        "operator": "ge",
        "threshold": 5.0,
        "layer": "liquidity",
    },
    "liquidity_20d_change_negative_le_5": {
        "column": "liquidity_20d_change_pct",
        "operator": "le",
        "threshold": -5.0,
        "layer": "liquidity",
    },
}


NUMERIC_SENSITIVITY = {
    "vix_low": {
        "column": "macro_vix",
        "operator": "lt",
        "thresholds": [10.0, 15.0, 20.0],
        "layer": "stress",
    },
    "vix_elevated": {
        "column": "macro_vix",
        "operator": "ge",
        "thresholds": [20.0, 25.0, 30.0],
        "layer": "stress",
    },
    "financial_stress_elevated": {
        "column": "macro_financial_stress_composite",
        "operator": "gt",
        "thresholds": [-0.5, 0.0, 0.5, 1.0],
        "layer": "stress",
    },
    "sentiment_bearish": {
        "column": "sentiment_unified_sentiment_score",
        "operator": "lt",
        "thresholds": [35.0, 40.0, 45.0],
        "layer": "sentiment",
    },
    "sentiment_bullish": {
        "column": "sentiment_unified_sentiment_score",
        "operator": "gt",
        "thresholds": [55.0, 60.0, 65.0],
        "layer": "sentiment",
    },
    "technical_drawdown": {
        "column": "technical_drawdown_pct",
        "operator": "le",
        "thresholds": [-3.0, -5.0, -7.5, -10.0, -15.0],
        "layer": "technical",
    },
    "liquidity_positive": {
        "column": "liquidity_20d_change_pct",
        "operator": "ge",
        "thresholds": [2.5, 5.0, 7.5, 10.0],
        "layer": "liquidity",
    },
    "liquidity_negative": {
        "column": "liquidity_20d_change_pct",
        "operator": "le",
        "thresholds": [-2.5, -5.0, -7.5, -10.0],
        "layer": "liquidity",
    },
}


def load_csv(path: str, label: str) -> pd.DataFrame:

    df = pd.read_csv(
        path,
        low_memory=False,
    )

    if df.empty:
        raise ValueError(
            f"{label}: empty input"
        )

    date_candidates = [
        "study_date",
        "context_date",
        "asof_date",
        "observation_date",
        "date",
    ]

    date_col = next(
        (
            c
            for c in date_candidates
            if c in df.columns
        ),
        None,
    )

    if date_col is None:
        raise ValueError(
            f"{label}: no supported date column"
        )

    df["study_date"] = (
        pd.to_datetime(
            df[date_col],
            errors="coerce",
        )
        .dt.normalize()
    )

    if df["study_date"].isna().any():
        raise ValueError(
            f"{label}: invalid dates detected"
        )

    if df["study_date"].duplicated().any():
        raise ValueError(
            f"{label}: duplicate study dates detected"
        )

    return (
        df
        .sort_values("study_date")
        .reset_index(drop=True)
    )


def assert_bool_if_present(
    df: pd.DataFrame,
    column: str,
    expected: bool,
    label: str,
) -> None:

    if column not in df.columns:
        return

    values = df[column]

    if values.isna().any():
        raise ValueError(
            f"{label}: {column} contains missing values"
        )

    normalized = (
        values
        .astype(str)
        .str.strip()
        .str.lower()
        .map({
            "true": True,
            "false": False,
        })
    )

    if normalized.isna().any():
        raise ValueError(
            f"{label}: {column} contains non-boolean values"
        )

    if not normalized.eq(expected).all():
        raise ValueError(
            f"{label}: safeguard failed for {column}"
        )


def validate_inputs(
    context: pd.DataFrame,
    liquidity: pd.DataFrame,
    breadth: pd.DataFrame,
) -> dict:

    warnings = []

    for df, label in [
        (context, "Research Context"),
        (liquidity, "Liquidity"),
        (breadth, "Market Breadth"),
    ]:

        assert_bool_if_present(
            df,
            "research_only",
            True,
            label,
        )

        assert_bool_if_present(
            df,
            "decision_engine_ready",
            False,
            label,
        )

    if "point_in_time_safe" in context.columns:

        assert_bool_if_present(
            context,
            "point_in_time_safe",
            True,
            "Research Context",
        )

    else:

        warnings.append(
            "Research Context has no point_in_time_safe column"
        )

    if "analysis_pit_perfect" in breadth.columns:

        values = (
            breadth["analysis_pit_perfect"]
            .astype(str)
            .str.lower()
        )

        if not values.eq("false").all():

            warnings.append(
                "Market Breadth analysis_pit_perfect "
                "is not uniformly FALSE"
            )

    return {
        "warnings": warnings,
    }


def download_prices(
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:

    raw = yf.download(
        "^GSPC",
        start=(
            start - pd.Timedelta(days=7)
        ).strftime("%Y-%m-%d"),
        end=(
            end + pd.Timedelta(days=35)
        ).strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=False,
        actions=False,
        threads=False,
    )

    if raw.empty:
        raise ValueError(
            "Unable to download ^GSPC"
        )

    close = raw["Close"]

    if isinstance(
        close,
        pd.DataFrame,
    ):
        close = close.iloc[:, 0]

    idx = pd.to_datetime(
        close.index
    )

    if getattr(
        idx,
        "tz",
        None,
    ) is not None:

        idx = idx.tz_localize(None)

    prices = pd.DataFrame({
        "study_date": idx.normalize(),
        "close": pd.to_numeric(
            close.to_numpy(),
            errors="coerce",
        ),
    }).dropna()

    prices = (
        prices
        .drop_duplicates(
            "study_date"
        )
        .sort_values(
            "study_date"
        )
        .reset_index(
            drop=True
        )
    )

    for horizon, periods in HORIZONS.items():

        prices[
            f"forward_return_{horizon}"
        ] = (
            prices["close"].shift(-periods)
            / prices["close"]
            - 1.0
        )

    return prices


def merge_inputs(
    context: pd.DataFrame,
    liquidity: pd.DataFrame,
    breadth: pd.DataFrame,
) -> pd.DataFrame:

    liq = liquidity.rename(
        columns={
            c: f"liq_{c}"
            for c in liquidity.columns
            if c != "study_date"
        }
    )

    panel = (
        context
        .merge(
            liq,
            on="study_date",
            how="inner",
            validate="one_to_one",
        )
        .merge(
            breadth,
            on="study_date",
            how="inner",
            validate="one_to_one",
            suffixes=(
                "",
                "_breadth",
            ),
        )
    )

    if panel.empty:
        raise ValueError(
            "No common dates across all research layers"
        )

    liq_col = (
        "liq_NET_LIQUIDITY_PROXY_MILLIONS"
    )

    if liq_col not in panel.columns:
        raise ValueError(
            f"Required column missing: {liq_col}"
        )

    liq_series = pd.to_numeric(
        panel[liq_col],
        errors="coerce",
    )

    panel[
        "liquidity_20d_change_pct"
    ] = (
        liq_series.pct_change(20)
        * 100.0
    )

    return (
        panel
        .sort_values("study_date")
        .reset_index(drop=True)
    )


def event_mask(
    df: pd.DataFrame,
    column: str,
    operator: str,
    threshold,
) -> pd.Series:

    if column not in df.columns:

        return pd.Series(
            False,
            index=df.index,
        )

    s = df[column]

    if operator == "eq":

        return s.astype(str).eq(
            str(threshold)
        )

    numeric = pd.to_numeric(
        s,
        errors="coerce",
    )

    if operator == "lt":
        return numeric.lt(threshold)

    if operator == "le":
        return numeric.le(threshold)

    if operator == "gt":
        return numeric.gt(threshold)

    if operator == "ge":
        return numeric.ge(threshold)

    raise ValueError(
        f"Unsupported operator: {operator}"
    )


def onset_series(
    series: pd.Series,
    cooldown: int = 5,
) -> pd.Series:

    arr = (
        series
        .fillna(False)
        .to_numpy(dtype=bool)
    )

    output = np.zeros(
        len(arr),
        dtype=bool,
    )

    previous = False
    last_onset = -10**9

    for i, active in enumerate(arr):

        if (
            active
            and not previous
            and i - last_onset > cooldown
        ):

            output[i] = True
            last_onset = i

        previous = active

    return pd.Series(
        output,
        index=series.index,
    )


def add_event(
    panel: pd.DataFrame,
    name: str,
    definition: dict,
) -> pd.Series:

    active = event_mask(
        panel,
        definition["column"],
        definition["operator"],
        definition["threshold"],
    )

    return onset_series(active)


def evaluate_event(
    panel: pd.DataFrame,
    event_series: pd.Series,
    event_name: str,
    period_name: str,
    definition_name: str,
    threshold,
) -> list[dict]:

    rows = []

    for horizon in HORIZONS:

        outcome_col = (
            f"forward_return_{horizon}"
        )

        valid = pd.to_numeric(
            panel[outcome_col],
            errors="coerce",
        )

        mask = (
            event_series
            & valid.notna()
        )

        event_returns = valid.loc[mask]

        all_returns = valid.dropna()

        non_event_returns = valid.loc[
            (~event_series)
            & valid.notna()
        ]

        n = len(event_returns)

        if n:

            mean_return = (
                event_returns.mean()
                * 100
            )

            median_return = (
                event_returns.median()
                * 100
            )

            positive_share = (
                (event_returns > 0).mean()
                * 100
            )

        else:

            mean_return = np.nan
            median_return = np.nan
            positive_share = np.nan

        all_mean = (
            all_returns.mean() * 100
            if len(all_returns)
            else np.nan
        )

        non_event_mean = (
            non_event_returns.mean()
            * 100
            if len(non_event_returns)
            else np.nan
        )

        difference = (
            mean_return
            - non_event_mean
            if (
                np.isfinite(mean_return)
                and np.isfinite(non_event_mean)
            )
            else np.nan
        )

        rows.append({
            "event_name": event_name,
            "definition": definition_name,
            "threshold": threshold,
            "period": period_name,
            "horizon": horizon,
            "event_observations": n,
            "all_observations": len(
                all_returns
            ),
            "non_event_observations": len(
                non_event_returns
            ),
            "event_mean_return_pct":
                mean_return,
            "event_median_return_pct":
                median_return,
            "event_positive_share_pct":
                positive_share,
            "all_mean_return_pct":
                all_mean,
            "non_event_mean_return_pct":
                non_event_mean,
            "event_minus_non_event_pp":
                difference,
        })

    return rows


def temporal_periods(
    panel: pd.DataFrame,
) -> dict[str, pd.DataFrame]:

    dates = panel["study_date"]

    periods = {}

    periods["FULL_SAMPLE"] = panel.copy()

    periods["2019_2021"] = panel.loc[
        (dates >= pd.Timestamp("2019-01-01"))
        & (
            dates
            <= pd.Timestamp("2021-12-31")
        )
    ].copy()

    periods["2022_2023"] = panel.loc[
        (dates >= pd.Timestamp("2022-01-01"))
        & (
            dates
            <= pd.Timestamp("2023-12-31")
        )
    ].copy()

    periods["2024_2026"] = panel.loc[
        (dates >= pd.Timestamp("2024-01-01"))
        & (
            dates
            <= pd.Timestamp("2026-12-31")
        )
    ].copy()

    return periods


def classify_stability(
    values: list[float],
    observations: list[int],
) -> str:

    valid = [
        float(v)
        for v in values
        if np.isfinite(v)
    ]

    valid_n = [
        int(n)
        for n in observations
        if n is not None
    ]

    if not valid:
        return "INSUFFICIENT_SAMPLE"

    if any(
        n < MIN_STABILITY_OBS
        for n in valid_n
    ):
        return "INSUFFICIENT_SAMPLE"

    signs = [
        np.sign(v)
        for v in valid
        if v != 0
    ]

    if len(signs) >= 3:

        same_sign = (
            all(x > 0 for x in signs)
            or all(x < 0 for x in signs)
        )

        if same_sign:
            return "STABLE"

    if len(valid) >= 2:

        spread = (
            max(valid)
            - min(valid)
        )

        magnitude = max(
            abs(x)
            for x in valid
        )

        if magnitude == 0:
            return "PARTIALLY_STABLE"

        if spread <= max(
            0.50,
            magnitude * 0.50,
        ):
            return "PARTIALLY_STABLE"

    return "SENSITIVE"


def build_temporal_analysis(
    panel: pd.DataFrame,
) -> pd.DataFrame:

    periods = temporal_periods(panel)

    rows = []

    for (
        event_name,
        definition,
    ) in BASE_EVENTS.items():

        for (
            period_name,
            period_df,
        ) in periods.items():

            event = add_event(
                period_df,
                event_name,
                definition,
            )

            rows.extend(
                evaluate_event(
                    period_df,
                    event,
                    event_name,
                    period_name,
                    "BASE",
                    definition["threshold"],
                )
            )

    return pd.DataFrame(rows)


def build_threshold_analysis(
    panel: pd.DataFrame,
) -> pd.DataFrame:

    rows = []

    for (
        event_name,
        definition,
    ) in NUMERIC_SENSITIVITY.items():

        for threshold in definition[
            "thresholds"
        ]:

            event_definition = {
                "column":
                    definition["column"],
                "operator":
                    definition["operator"],
                "threshold":
                    threshold,
            }

            event = add_event(
                panel,
                event_name,
                event_definition,
            )

            rows.extend(
                evaluate_event(
                    panel,
                    event,
                    event_name,
                    "FULL_SAMPLE",
                    "THRESHOLD_SENSITIVITY",
                    threshold,
                )
            )

    return pd.DataFrame(rows)


def build_temporal_stability(
    temporal: pd.DataFrame,
) -> pd.DataFrame:

    rows = []

    for (
        event_name,
        horizon,
    ), group in temporal.groupby(
        [
            "event_name",
            "horizon",
        ]
    ):

        values = (
            group[
                "event_minus_non_event_pp"
            ].tolist()
        )

        observations = (
            group[
                "event_observations"
            ].tolist()
        )

        rows.append({
            "event_name":
                event_name,
            "horizon":
                horizon,
            "period_count":
                len(group),
            "periods_with_data":
                int(
                    np.isfinite(
                        pd.to_numeric(
                            group[
                                "event_minus_non_event_pp"
                            ],
                            errors="coerce",
                        )
                    ).sum()
                ),
            "minimum_event_observations":
                (
                    min(observations)
                    if observations
                    else 0
                ),
            "maximum_event_observations":
                (
                    max(observations)
                    if observations
                    else 0
                ),
            "stability_class":
                classify_stability(
                    values,
                    observations,
                ),
        })

    return pd.DataFrame(rows)


def build_threshold_stability(
    threshold_df: pd.DataFrame,
) -> pd.DataFrame:

    rows = []

    for (
        event_name,
        horizon,
    ), group in threshold_df.groupby(
        [
            "event_name",
            "horizon",
        ]
    ):

        values = (
            group[
                "event_minus_non_event_pp"
            ].tolist()
        )

        observations = (
            group[
                "event_observations"
            ].tolist()
        )

        rows.append({
            "event_name":
                event_name,
            "horizon":
                horizon,
            "threshold_count":
                len(group),
            "thresholds_with_data":
                int(
                    np.isfinite(
                        pd.to_numeric(
                            group[
                                "event_minus_non_event_pp"
                            ],
                            errors="coerce",
                        )
                    ).sum()
                ),
            "minimum_event_observations":
                (
                    min(observations)
                    if observations
                    else 0
                ),
            "maximum_event_observations":
                (
                    max(observations)
                    if observations
                    else 0
                ),
            "threshold_stability_class":
                classify_stability(
                    values,
                    observations,
                ),
        })

    return pd.DataFrame(rows)


def build_horizon_stability(
    temporal: pd.DataFrame,
) -> pd.DataFrame:

    rows = []

    for (
        event_name,
        group,
    ) in temporal.groupby(
        "event_name"
    ):

        horizon_values = {}

        for horizon in HORIZONS:

            subset = group.loc[
                group["horizon"]
                == horizon
            ]

            values = pd.to_numeric(
                subset[
                    "event_minus_non_event_pp"
                ],
                errors="coerce",
            ).dropna()

            horizon_values[horizon] = (
                float(values.mean())
                if len(values)
                else np.nan
            )

        valid = [
            v
            for v in horizon_values.values()
            if np.isfinite(v)
        ]

        rows.append({
            "event_name":
                event_name,
            "horizons_with_data":
                len(valid),
            "mean_1D_difference_pp":
                horizon_values["1D"],
            "mean_5D_difference_pp":
                horizon_values["5D"],
            "mean_20D_difference_pp":
                horizon_values["20D"],
            "horizon_stability_class":
                classify_stability(
                    valid,
                    [
                        MIN_STABILITY_OBS
                    ] * len(valid),
                ),
        })

    return pd.DataFrame(rows)


def build_sample_adequacy(
    panel: pd.DataFrame,
) -> pd.DataFrame:

    rows = []

    for (
        event_name,
        definition,
    ) in BASE_EVENTS.items():

        event = add_event(
            panel,
            event_name,
            definition,
        )

        n = int(event.sum())

        if n < 5:
            category = "INSUFFICIENT"

        elif n < MIN_EVENT_OBS:
            category = "LIMITED"

        elif n < 30:
            category = "MODERATE"

        else:
            category = (
                "ADEQUATE_FOR_DESCRIPTIVE_ANALYSIS"
            )

        rows.append({
            "event_name":
                event_name,
            "event_layer":
                definition["layer"],
            "event_observations":
                n,
            "minimum_basic_diagnostic":
                MIN_EVENT_OBS,
            "sample_adequacy":
                category,
        })

    return pd.DataFrame(rows)


def build_overlap(
    panel: pd.DataFrame,
) -> pd.DataFrame:

    events = {}

    for (
        event_name,
        definition,
    ) in BASE_EVENTS.items():

        events[event_name] = add_event(
            panel,
            event_name,
            definition,
        )

    rows = []

    names = list(
        events.keys()
    )

    for i, left in enumerate(names):

        for right in names[i + 1:]:

            a = events[left]
            b = events[right]

            both = int(
                (a & b).sum()
            )

            union = int(
                (a | b).sum()
            )

            rows.append({
                "event_a":
                    left,
                "event_b":
                    right,
                "event_a_observations":
                    int(a.sum()),
                "event_b_observations":
                    int(b.sum()),
                "overlap_observations":
                    both,
                "union_observations":
                    union,
                "jaccard_overlap":
                    (
                        both / union
                        if union
                        else np.nan
                    ),
            })

    return pd.DataFrame(rows)


def build_pit_audit(
    context: pd.DataFrame,
    liquidity: pd.DataFrame,
    breadth: pd.DataFrame,
) -> pd.DataFrame:

    rows = []

    datasets = [
        (
            "Research Context",
            context,
        ),
        (
            "Liquidity",
            liquidity,
        ),
        (
            "Market Breadth",
            breadth,
        ),
    ]

    for name, df in datasets:

        row = {
            "dataset":
                name,
            "rows":
                len(df),
            "research_only_present":
                "research_only"
                in df.columns,
            "research_only_all_true":
                False,
            "decision_engine_ready_present":
                "decision_engine_ready"
                in df.columns,
            "decision_engine_ready_all_false":
                False,
            "pit_flag_present":
                False,
            "pit_flag_all_safe":
                False,
            "pit_perfect":
                False,
        }

        if "research_only" in df.columns:

            vals = (
                df["research_only"]
                .astype(str)
                .str.lower()
            )

            row[
                "research_only_all_true"
            ] = vals.eq(
                "true"
            ).all()

        if (
            "decision_engine_ready"
            in df.columns
        ):

            vals = (
                df[
                    "decision_engine_ready"
                ]
                .astype(str)
                .str.lower()
            )

            row[
                "decision_engine_ready_all_false"
            ] = vals.eq(
                "false"
            ).all()

        for pit_col in [
            "point_in_time_safe",
            "analysis_pit_perfect",
            "pit_perfect",
        ]:

            if pit_col in df.columns:

                row[
                    "pit_flag_present"
                ] = True

                vals = (
                    df[pit_col]
                    .astype(str)
                    .str.lower()
                )

                row[
                    "pit_flag_all_safe"
                ] = vals.eq(
                    "true"
                ).all()

                row[
                    "pit_perfect"
                ] = row[
                    "pit_flag_all_safe"
                ]

                break

        rows.append(row)

    return pd.DataFrame(rows)


def build_validation(
    panel: pd.DataFrame,
    temporal: pd.DataFrame,
    threshold_df: pd.DataFrame,
    sample_df: pd.DataFrame,
    pit_df: pd.DataFrame,
    warnings: list[str],
) -> dict:

    errors = []

    if len(panel) < MIN_COMMON_SAMPLE:

        errors.append(
            "Common sample below minimum "
            f"of {MIN_COMMON_SAMPLE}"
        )

    if panel[
        "study_date"
    ].duplicated().any():

        errors.append(
            "Duplicate study dates detected"
        )

    if not panel[
        "study_date"
    ].is_monotonic_increasing:

        errors.append(
            "Study dates are not monotonic"
        )

    if len(temporal) == 0:

        errors.append(
            "Temporal robustness output is empty"
        )

    if len(threshold_df) == 0:

        errors.append(
            "Threshold sensitivity output is empty"
        )

    actual_periods = sorted(
        temporal[
            "period"
        ]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    missing_periods = [
        p
        for p in EXPECTED_TEMPORAL_PERIODS
        if p not in actual_periods
    ]

    if missing_periods:

        errors.append(
            "Missing expected temporal periods: "
            + ", ".join(missing_periods)
        )

    unexpected_periods = [
        p
        for p in actual_periods
        if p not in EXPECTED_TEMPORAL_PERIODS
    ]

    if unexpected_periods:

        errors.append(
            "Unexpected temporal periods found: "
            + ", ".join(unexpected_periods)
        )

    pit_perfect = bool(
        pit_df[
            "pit_perfect"
        ].all()
    )

    limited_events = sample_df.loc[
        sample_df[
            "event_observations"
        ] < MIN_EVENT_OBS
    ]

    if not limited_events.empty:

        warnings.append(
            "One or more base events have "
            "limited sample sizes"
        )

    period_rows = {}

    for period_name in EXPECTED_TEMPORAL_PERIODS:

        subset = temporal.loc[
            temporal["period"]
            == period_name
        ]

        period_rows[
            period_name
        ] = int(len(subset))

    return {
        "validator":
            "Historical Edge — "
            "Robustness Validation v1",

        "version":
            VERSION,

        "status":
            (
                "PASS"
                if not errors
                else "FAIL"
            ),

        "validation_pass":
            not errors,

        "errors":
            errors,

        "warnings":
            warnings,

        "common_sample_rows":
            int(len(panel)),

        "date_start":
            (
                panel[
                    "study_date"
                ]
                .min()
                .strftime("%Y-%m-%d")
            ),

        "date_end":
            (
                panel[
                    "study_date"
                ]
                .max()
                .strftime("%Y-%m-%d")
            ),

        "temporal_periods":
            EXPECTED_TEMPORAL_PERIODS,

        "temporal_period_row_counts":
            period_rows,

        "event_definition_count":
            len(BASE_EVENTS),

        "numeric_sensitivity_groups":
            len(NUMERIC_SENSITIVITY),

        "outcome_horizons":
            list(HORIZONS.keys()),

        "research_only":
            RESEARCH_ONLY,

        "decision_engine_ready":
            DECISION_ENGINE_READY,

        "trading_signal":
            TRADING_SIGNAL,

        "forecast":
            FORECAST,

        "optimization":
            OPTIMIZATION,

        "causal_claim":
            CAUSAL_CLAIM,

        "pit_perfect":
            pit_perfect,

        "interpretation":
            (
                "PASS means the robustness diagnostics "
                "executed structurally. Stability labels "
                "describe sensitivity of descriptive "
                "historical relationships across periods, "
                "thresholds and horizons. They do not "
                "establish predictiveness, causality, "
                "economic usefulness, or a preferred event."
            ),
    }


def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--research-context",
        required=True,
    )

    parser.add_argument(
        "--liquidity",
        required=True,
    )

    parser.add_argument(
        "--breadth",
        required=True,
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    args = parser.parse_args()

    output = Path(
        args.output
    )

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    context = load_csv(
        args.research_context,
        "Research Context",
    )

    liquidity = load_csv(
        args.liquidity,
        "Liquidity",
    )

    breadth = load_csv(
        args.breadth,
        "Market Breadth",
    )

    validation_info = validate_inputs(
        context,
        liquidity,
        breadth,
    )

    warnings = list(
        validation_info[
            "warnings"
        ]
    )

    panel = merge_inputs(
        context,
        liquidity,
        breadth,
    )

    prices = download_prices(
        panel[
            "study_date"
        ].min(),
        panel[
            "study_date"
        ].max(),
    )

    panel = (
        panel
        .merge(
            prices,
            on="study_date",
            how="left",
            validate="one_to_one",
        )
        .sort_values(
            "study_date"
        )
        .reset_index(
            drop=True
        )
    )

    temporal = build_temporal_analysis(
        panel
    )

    threshold_df = build_threshold_analysis(
        panel
    )

    temporal_stability = (
        build_temporal_stability(
            temporal
        )
    )

    if temporal_stability.empty:

        warnings.append(
            "Temporal stability output is empty"
        )

    threshold_stability = (
        build_threshold_stability(
            threshold_df
        )
    )

    horizon_stability = (
        build_horizon_stability(
            temporal
        )
    )

    sample_df = build_sample_adequacy(
        panel
    )

    overlap_df = build_overlap(
        panel
    )

    pit_df = build_pit_audit(
        context,
        liquidity,
        breadth,
    )

    temporal.to_csv(
        output
        / "historical_edge_temporal_robustness_v1.csv",
        index=False,
    )

    threshold_df.to_csv(
        output
        / "historical_edge_threshold_sensitivity_v1.csv",
        index=False,
    )

    temporal_stability.to_csv(
        output
        / "historical_edge_temporal_stability_v1.csv",
        index=False,
    )

    threshold_stability.to_csv(
        output
        / "historical_edge_threshold_stability_v1.csv",
        index=False,
    )

    horizon_stability.to_csv(
        output
        / "historical_edge_horizon_stability_v1.csv",
        index=False,
    )

    sample_df.to_csv(
        output
        / "historical_edge_sample_adequacy_v1.csv",
        index=False,
    )

    overlap_df.to_csv(
        output
        / "historical_edge_event_overlap_v1.csv",
        index=False,
    )

    pit_df.to_csv(
        output
        / "historical_edge_pit_audit_v1.csv",
        index=False,
    )

    report = build_validation(
        panel,
        temporal,
        threshold_df,
        sample_df,
        pit_df,
        warnings,
    )

    with open(
        output
        / "historical_edge_robustness_validation_v1.json",
        "w",
        encoding="utf-8",
    ) as fh:

        json.dump(
            report,
            fh,
            indent=2,
            ensure_ascii=False,
        )

    print("=" * 70)
    print(
        "HISTORICAL EDGE — "
        "ROBUSTNESS VALIDATION v1"
    )
    print("=" * 70)

    print(
        f"Common sample: "
        f"{len(panel):,}"
    )

    print(
        f"Date range: "
        f"{panel['study_date'].min().date()} "
        f"-> "
        f"{panel['study_date'].max().date()}"
    )

    print(
        f"Base events: "
        f"{len(BASE_EVENTS)}"
    )

    print(
        f"Temporal rows: "
        f"{len(temporal):,}"
    )

    print(
        f"Threshold rows: "
        f"{len(threshold_df):,}"
    )

    print(
        f"Temporal stability rows: "
        f"{len(temporal_stability):,}"
    )

    print(
        f"Threshold stability rows: "
        f"{len(threshold_stability):,}"
    )

    print(
        f"Horizon stability rows: "
        f"{len(horizon_stability):,}"
    )

    print(
        f"PIT audit rows: "
        f"{len(pit_df):,}"
    )

    print("")
    print(
        "Temporal periods:"
    )

    for period_name in EXPECTED_TEMPORAL_PERIODS:

        count = int(
            (
                temporal["period"]
                == period_name
            ).sum()
        )

        print(
            f"  {period_name}: "
            f"{count:,} rows"
        )

    print("")

    print(
        "Research-only: TRUE"
    )

    print(
        "Decision Engine: FALSE"
    )

    print(
        "Trading signal: FALSE"
    )

    print(
        "Forecast: FALSE"
    )

    print(
        "Optimization: FALSE"
    )

    print(
        "Causal claim: FALSE"
    )

    print(
        "PIT-perfect:",
        report["pit_perfect"],
    )

    print(
        f"FINAL STATUS: "
        f"{report['status']}"
    )

    for warning in warnings:

        print(
            "WARNING:",
            warning,
        )


if __name__ == "__main__":
    main()
