#!/usr/bin/env python3
"""
Historical Event Study v2
Research-only diagnostics.

Purpose:
- Extend Historical Event Study v1 with event overlap, sample adequacy,
  conditional event diagnostics, cross-layer redundancy, and controlled
  association diagnostics.
- No trading signals.
- No forecast.
- No Decision Engine integration.
- No optimization or event ranking.
- Results are descriptive/research diagnostics only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


HORIZONS = {"1D": 1, "5D": 5, "20D": 20}

EVENTS = {
    "breadth_negative_20d": (
        "breadth_research_state", "eq", "NEGATIVE_BREADTH",
        "Market Breadth Analyzer v1", "breadth"
    ),
    "breadth_positive_20d": (
        "breadth_research_state", "eq", "POSITIVE_BREADTH",
        "Market Breadth Analyzer v1", "breadth"
    ),
    "vix_low": (
        "macro_vix", "lt", 15.0,
        "Research Context v1", "stress"
    ),
    "vix_elevated": (
        "macro_vix", "ge", 25.0,
        "Research Context v1", "stress"
    ),
    "financial_stress_elevated": (
        "macro_financial_stress_composite", "gt", 0.0,
        "Research Context v1", "stress"
    ),
    "sentiment_bearish": (
        "sentiment_unified_sentiment_score", "lt", 40.0,
        "Sentiment Engine v1", "sentiment"
    ),
    "sentiment_bullish": (
        "sentiment_unified_sentiment_score", "gt", 60.0,
        "Sentiment Engine v1", "sentiment"
    ),
    "technical_drawdown_ge_5": (
        "technical_drawdown_pct", "le", -5.0,
        "Technical Intelligence v1", "technical"
    ),
    "technical_drawdown_ge_10": (
        "technical_drawdown_pct", "le", -10.0,
        "Technical Intelligence v1", "technical"
    ),
    "liquidity_20d_change_positive_ge_5": (
        "liquidity_20d_change_pct", "ge", 5.0,
        "Liquidity Intelligence v1", "liquidity"
    ),
    "liquidity_20d_change_negative_le_5": (
        "liquidity_20d_change_pct", "le", -5.0,
        "Liquidity Intelligence v1", "liquidity"
    ),
}

# Cross-layer controls used only when they exist and have enough data.
CONTROL_CANDIDATES = [
    ("macro_vix", "stress"),
    ("macro_financial_stress_composite", "stress"),
    ("sentiment_unified_sentiment_score", "sentiment"),
    ("technical_drawdown_pct", "technical"),
    ("technical_RSI14", "technical"),
    ("technical_ATR14_pct", "technical"),
    ("technical_ROC20_pct", "technical"),
    ("macro_inflation_score", "macro"),
    ("macro_labor_score", "macro"),
    ("macro_growth_score", "macro"),
    ("macro_fed_score", "macro"),
    ("macro_yield_10y_2y_spread", "macro"),
    ("liq_NET_LIQUIDITY_PROXY_MILLIONS", "liquidity"),
    ("liquidity_20d_change_pct", "liquidity"),
]

MIN_EVENT_OBS = 10
MIN_PAIR_OBS = 10
MIN_CONTROL_OBS = 100


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    if df.empty:
        raise ValueError(f"Empty input: {path}")

    date_candidates = ["study_date", "context_date", "asof_date", "observation_date"]
    date_col = next((c for c in date_candidates if c in df.columns), None)
    if date_col is None:
        raise ValueError(f"No supported date column in {path}")

    df["study_date"] = pd.to_datetime(
        df[date_col], errors="coerce"
    ).dt.normalize()

    if df["study_date"].isna().any():
        raise ValueError(f"Invalid dates in {path}")

    if df["study_date"].duplicated().any():
        raise ValueError(f"Duplicate study dates in {path}")

    return df.sort_values("study_date").reset_index(drop=True)


def assert_all_bool(df: pd.DataFrame, col: str, value: bool, label: str) -> None:
    if col in df.columns and not df[col].eq(value).all():
        raise ValueError(f"{label}: safeguard failed: {col}")


def validate_inputs(context: pd.DataFrame, liquidity: pd.DataFrame,
                    breadth: pd.DataFrame) -> None:
    for df, label in (
        (context, "Research Context"),
        (liquidity, "Liquidity"),
        (breadth, "Market Breadth"),
    ):
        assert_all_bool(df, "research_only", True, label)
        assert_all_bool(df, "decision_engine_ready", False, label)

    assert_all_bool(context, "point_in_time_safe", True, "Research Context")

    for col in ("trading_signal_generated", "forecast_generated"):
        assert_all_bool(context, col, False, "Research Context")

    for col in ("trading_signal", "forecast",
                "trading_signal_generated", "forecast_generated"):
        assert_all_bool(liquidity, col, False, "Liquidity")

    for col in ("trading_signal", "forecast", "analysis_pit_perfect"):
        assert_all_bool(breadth, col, False, "Market Breadth")


def download_prices(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    raw = yf.download(
        "^GSPC",
        start=(start - pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
        end=(end + pd.Timedelta(days=35)).strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=False,
        actions=False,
        threads=False,
    )

    if raw.empty:
        raise ValueError("Unable to download ^GSPC")

    close = raw["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    idx = pd.to_datetime(close.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)

    out = pd.DataFrame({
        "study_date": idx.normalize(),
        "close": pd.to_numeric(close.to_numpy(), errors="coerce"),
    }).dropna()

    out = (
        out.drop_duplicates("study_date")
        .sort_values("study_date")
        .reset_index(drop=True)
    )

    for horizon, periods in HORIZONS.items():
        out[f"forward_return_{horizon}"] = (
            out["close"].shift(-periods) / out["close"] - 1.0
        )

    return out


def merge_inputs(context: pd.DataFrame,
                 liquidity: pd.DataFrame,
                 breadth: pd.DataFrame) -> pd.DataFrame:
    liq = liquidity.rename(
        columns={c: f"liq_{c}" for c in liquidity.columns if c != "study_date"}
    )

    panel = (
        context
        .merge(liq, on="study_date", how="inner", validate="one_to_one")
        .merge(
            breadth,
            on="study_date",
            how="inner",
            validate="one_to_one",
            suffixes=("", "_breadth"),
        )
    )

    if panel.empty:
        raise ValueError("No common dates across Research Context, Liquidity, and Breadth")

    liq_col = "liq_NET_LIQUIDITY_PROXY_MILLIONS"
    if liq_col not in panel.columns:
        raise ValueError(f"Required liquidity column missing: {liq_col}")

    liq_series = pd.to_numeric(panel[liq_col], errors="coerce")
    panel["liquidity_20d_change_pct"] = liq_series.pct_change(20) * 100.0

    return panel.sort_values("study_date").reset_index(drop=True)


def event_flag(df: pd.DataFrame, col: str, op: str, value) -> pd.Series:
    if col not in df.columns:
        return pd.Series(False, index=df.index)

    s = df[col]

    if op == "eq":
        return s.astype(str).eq(str(value))

    s = pd.to_numeric(s, errors="coerce")
    mapping = {
        "lt": s < value,
        "le": s <= value,
        "gt": s > value,
        "ge": s >= value,
    }
    if op not in mapping:
        raise ValueError(f"Unsupported operator: {op}")

    return mapping[op].fillna(False)


def onset_series(series: pd.Series, cooldown: int = 5) -> pd.Series:
    arr = series.to_numpy(dtype=bool)
    out = np.zeros(len(arr), dtype=bool)
    last_onset = -10**9
    previous = False

    for i, active in enumerate(arr):
        if active and not previous and (i - last_onset > cooldown):
            out[i] = True
            last_onset = i
        previous = active

    return pd.Series(out, index=series.index)


def add_event_flags(panel: pd.DataFrame) -> pd.DataFrame:
    for name, (column, operator, threshold, _, _) in EVENTS.items():
        panel[f"event_{name}"] = event_flag(
            panel, column, operator, threshold
        )
        panel[f"onset_{name}"] = onset_series(
            panel[f"event_{name}"]
        )
    return panel


def safe_mean(series: pd.Series) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    return float(s.mean()) if len(s) else np.nan


def event_summary(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for name, (column, operator, threshold, source, layer) in EVENTS.items():
        mask = panel[f"onset_{name}"]
        event_df = panel.loc[mask]

        for horizon in HORIZONS:
            outcome = f"forward_return_{horizon}"
            all_returns = pd.to_numeric(panel[outcome], errors="coerce")
            event_returns = pd.to_numeric(
                event_df[outcome], errors="coerce"
            ).dropna()
            non_event_returns = pd.to_numeric(
                panel.loc[~mask, outcome], errors="coerce"
            ).dropna()

            event_mean = safe_mean(event_returns)
            all_mean = safe_mean(all_returns)
            non_event_mean = safe_mean(non_event_returns)

            rows.append({
                "event_name": name,
                "source_layer": source,
                "event_layer": layer,
                "definition_column": column,
                "operator": operator,
                "threshold": threshold,
                "horizon": horizon,
                "event_observations": len(event_returns),
                "all_observations": int(all_returns.notna().sum()),
                "non_event_observations": len(non_event_returns),
                "event_mean_return_pct": event_mean * 100 if np.isfinite(event_mean) else np.nan,
                "event_median_return_pct": (
                    event_returns.median() * 100 if len(event_returns) else np.nan
                ),
                "event_positive_share_pct": (
                    (event_returns > 0).mean() * 100 if len(event_returns) else np.nan
                ),
                "all_mean_return_pct": all_mean * 100 if np.isfinite(all_mean) else np.nan,
                "non_event_mean_return_pct": (
                    non_event_mean * 100 if np.isfinite(non_event_mean) else np.nan
                ),
                "event_minus_all_pp": (
                    (event_mean - all_mean) * 100
                    if np.isfinite(event_mean) and np.isfinite(all_mean)
                    else np.nan
                ),
                "event_minus_non_event_pp": (
                    (event_mean - non_event_mean) * 100
                    if np.isfinite(event_mean) and np.isfinite(non_event_mean)
                    else np.nan
                ),
            })

    return pd.DataFrame(rows)


def event_overlap(panel: pd.DataFrame) -> pd.DataFrame:
    names = list(EVENTS.keys())
    rows = []

    for i, left in enumerate(names):
        left_mask = panel[f"onset_{left}"]

        for right in names[i:]:
            right_mask = panel[f"onset_{right}"]
            both = int((left_mask & right_mask).sum())
            left_n = int(left_mask.sum())
            right_n = int(right_mask.sum())
            union = int((left_mask | right_mask).sum())

            jaccard = both / union if union else np.nan

            rows.append({
                "event_a": left,
                "event_b": right,
                "event_a_observations": left_n,
                "event_b_observations": right_n,
                "overlap_observations": both,
                "union_observations": union,
                "jaccard_overlap": jaccard,
            })

    return pd.DataFrame(rows)


def numeric_correlations(panel: pd.DataFrame) -> pd.DataFrame:
    candidates = [
        ("macro_vix", "stress"),
        ("macro_financial_stress_composite", "stress"),
        ("sentiment_unified_sentiment_score", "sentiment"),
        ("technical_drawdown_pct", "technical"),
        ("technical_RSI14", "technical"),
        ("technical_ATR14_pct", "technical"),
        ("technical_ROC20_pct", "technical"),
        ("macro_inflation_score", "macro"),
        ("macro_labor_score", "macro"),
        ("macro_growth_score", "macro"),
        ("macro_fed_score", "macro"),
        ("macro_yield_10y_2y_spread", "macro"),
        ("liq_NET_LIQUIDITY_PROXY_MILLIONS", "liquidity"),
        ("liquidity_20d_change_pct", "liquidity"),
    ]

    available = []
    for col, layer in candidates:
        if col in panel.columns:
            s = pd.to_numeric(panel[col], errors="coerce")
            if s.notna().sum() >= MIN_CONTROL_OBS:
                available.append((col, layer))

    rows = []

    for i, (a, layer_a) in enumerate(available):
        sa = pd.to_numeric(panel[a], errors="coerce")

        for b, layer_b in available[i + 1:]:
            sb = pd.to_numeric(panel[b], errors="coerce")
            mask = sa.notna() & sb.notna()

            if mask.sum() < MIN_CONTROL_OBS:
                continue

            corr = sa[mask].corr(sb[mask])

            rows.append({
                "feature_a": a,
                "layer_a": layer_a,
                "feature_b": b,
                "layer_b": layer_b,
                "observations": int(mask.sum()),
                "pearson_correlation": float(corr) if pd.notna(corr) else np.nan,
                "absolute_correlation": (
                    abs(float(corr)) if pd.notna(corr) else np.nan
                ),
            })

    return pd.DataFrame(rows)


def conditional_event_diagnostics(panel: pd.DataFrame) -> pd.DataFrame:
    """
    For each event, condition on one cross-layer binary event at a time.
    This is descriptive only and intentionally excludes controls from the
    same conceptual layer as the event to reduce tautological conditioning.
    """

    rows = []

    event_names = list(EVENTS.keys())

    for event_name in event_names:
        event_layer = EVENTS[event_name][4]
        event_mask = panel[f"onset_{event_name}"]

        event_n = int(event_mask.sum())
        if event_n < MIN_EVENT_OBS:
            continue

        for control_name in event_names:
            if control_name == event_name:
                continue

            control_layer = EVENTS[control_name][4]

            # Same-layer conditioning can become tautological/redundant.
            if control_layer == event_layer:
                continue

            control_mask = panel[f"onset_{control_name}"]

            for horizon in HORIZONS:
                outcome = f"forward_return_{horizon}"

                both = pd.to_numeric(
                    panel.loc[event_mask & control_mask, outcome],
                    errors="coerce"
                ).dropna()

                event_only = pd.to_numeric(
                    panel.loc[event_mask & ~control_mask, outcome],
                    errors="coerce"
                ).dropna()

                if len(both) < MIN_PAIR_OBS or len(event_only) < MIN_PAIR_OBS:
                    continue

                rows.append({
                    "event_name": event_name,
                    "event_layer": event_layer,
                    "conditioning_event": control_name,
                    "conditioning_layer": control_layer,
                    "horizon": horizon,
                    "event_and_condition_observations": len(both),
                    "event_only_observations": len(event_only),
                    "event_and_condition_mean_return_pct": both.mean() * 100,
                    "event_only_mean_return_pct": event_only.mean() * 100,
                    "conditional_difference_pp": (
                        (both.mean() - event_only.mean()) * 100
                    ),
                })

    return pd.DataFrame(rows)


def controlled_association(panel: pd.DataFrame) -> pd.DataFrame:
    """
    Descriptive OLS diagnostic:
        forward return ~ event flag + available cross-layer controls

    The event's own source layer is excluded from controls.
    No p-values or optimization are used; this is not a predictive model.
    """

    rows = []

    for event_name, (_, _, _, _, event_layer) in EVENTS.items():
        event_mask = panel[f"onset_{event_name}"].astype(float)

        controls = []
        control_layers = []

        for col, layer in CONTROL_CANDIDATES:
            if layer == event_layer:
                continue
            if col not in panel.columns:
                continue

            s = pd.to_numeric(panel[col], errors="coerce")
            if s.notna().sum() >= MIN_CONTROL_OBS:
                controls.append(col)
                control_layers.append(layer)

        # Keep the diagnostic compact and deterministic.
        controls = controls[:8]
        control_layers = control_layers[:8]

        if not controls:
            continue

        for horizon in HORIZONS:
            outcome_col = f"forward_return_{horizon}"

            frame = pd.DataFrame({
                "event": event_mask,
                "outcome": pd.to_numeric(panel[outcome_col], errors="coerce"),
            }, index=panel.index)

            for col in controls:
                frame[col] = pd.to_numeric(panel[col], errors="coerce")

            frame = frame.dropna()

            if len(frame) < MIN_CONTROL_OBS:
                continue

            y = frame["outcome"].to_numpy(dtype=float)
            x_event = frame["event"].to_numpy(dtype=float)

            # Baseline: intercept + controls.
            X0 = np.column_stack([
                np.ones(len(frame)),
                frame[controls].to_numpy(dtype=float),
            ])

            # Full: intercept + controls + event.
            X1 = np.column_stack([
                np.ones(len(frame)),
                frame[controls].to_numpy(dtype=float),
                x_event,
            ])

            beta0 = np.linalg.lstsq(X0, y, rcond=None)[0]
            beta1 = np.linalg.lstsq(X1, y, rcond=None)[0]

            resid0 = y - X0 @ beta0
            resid1 = y - X1 @ beta1

            sse0 = float(np.sum(resid0 ** 2))
            sse1 = float(np.sum(resid1 ** 2))

            tss = float(np.sum((y - y.mean()) ** 2))

            r2_0 = 1.0 - sse0 / tss if tss > 0 else np.nan
            r2_1 = 1.0 - sse1 / tss if tss > 0 else np.nan

            event_coefficient = float(beta1[-1])

            rows.append({
                "event_name": event_name,
                "event_layer": event_layer,
                "horizon": horizon,
                "observations": len(frame),
                "control_count": len(controls),
                "controls": "|".join(controls),
                "event_coefficient_pct": event_coefficient * 100,
                "baseline_r2": r2_0,
                "controlled_r2": r2_1,
                "incremental_r2": (
                    r2_1 - r2_0
                    if np.isfinite(r2_0) and np.isfinite(r2_1)
                    else np.nan
                ),
                "interpretation": (
                    "descriptive controlled association only; "
                    "not predictive and not causal"
                ),
            })

    return pd.DataFrame(rows)


def event_sample_adequacy(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for name, (_, _, _, source, layer) in EVENTS.items():
        n = int(panel[f"onset_{name}"].sum())

        if n < 5:
            category = "INSUFFICIENT"
        elif n < MIN_EVENT_OBS:
            category = "LIMITED"
        elif n < 30:
            category = "MODERATE"
        else:
            category = "ADEQUATE_FOR_DESCRIPTIVE_ANALYSIS"

        rows.append({
            "event_name": name,
            "source_layer": source,
            "event_layer": layer,
            "event_observations": n,
            "minimum_for_basic_diagnostic": MIN_EVENT_OBS,
            "sample_adequacy": category,
        })

    return pd.DataFrame(rows)


def baseline(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for horizon in HORIZONS:
        s = pd.to_numeric(
            panel[f"forward_return_{horizon}"], errors="coerce"
        ).dropna()

        rows.append({
            "horizon": horizon,
            "observations": len(s),
            "mean_return_pct": s.mean() * 100,
            "median_return_pct": s.median() * 100,
            "positive_share_pct": (s > 0).mean() * 100,
        })

    return pd.DataFrame(rows)


def build_validation(panel: pd.DataFrame,
                     sample: pd.DataFrame,
                     errors: list[str],
                     warnings: list[str]) -> dict:
    return {
        "validator": "Historical Event Study v2",
        "status": "PASS" if not errors else "FAIL",
        "validation_pass": not errors,
        "errors": errors,
        "warnings": warnings,
        "common_sample_rows": int(len(panel)),
        "date_start": panel["study_date"].min().strftime("%Y-%m-%d"),
        "date_end": panel["study_date"].max().strftime("%Y-%m-%d"),
        "event_definition_count": len(EVENTS),
        "outcome_horizons": list(HORIZONS),
        "sample_adequacy_minimum": MIN_EVENT_OBS,
        "pair_diagnostic_minimum": MIN_PAIR_OBS,
        "research_only": True,
        "decision_engine_ready": False,
        "trading_signal": False,
        "forecast": False,
        "pit_perfect": False,
        "breadth_pit_perfect": False,
        "interpretation": (
            "PASS means structural execution only. V2 outputs descriptive "
            "event overlap, redundancy, conditional and controlled "
            "association diagnostics. It does not establish causality, "
            "predictiveness, usefulness, or preference for any event/layer."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--research-context", required=True)
    parser.add_argument("--liquidity", required=True)
    parser.add_argument("--breadth", required=True)
    parser.add_argument("--output", required=True)

    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    context = load_csv(args.research_context)
    liquidity = load_csv(args.liquidity)
    breadth = load_csv(args.breadth)

    validate_inputs(context, liquidity, breadth)

    panel = merge_inputs(context, liquidity, breadth)

    prices = download_prices(
        panel["study_date"].min(),
        panel["study_date"].max(),
    )

    panel = (
        panel
        .merge(
            prices,
            on="study_date",
            how="left",
            validate="one_to_one",
        )
        .sort_values("study_date")
        .reset_index(drop=True)
    )

    panel = add_event_flags(panel)

    summary = event_summary(panel)
    overlap = event_overlap(panel)
    correlations = numeric_correlations(panel)
    conditional = conditional_event_diagnostics(panel)
    controlled = controlled_association(panel)
    adequacy = event_sample_adequacy(panel)
    base = baseline(panel)

    summary.to_csv(
        out / "historical_event_study_summary_v2.csv",
        index=False,
    )

    overlap.to_csv(
        out / "historical_event_study_event_overlap_v2.csv",
        index=False,
    )

    correlations.to_csv(
        out / "historical_event_study_feature_redundancy_v2.csv",
        index=False,
    )

    conditional.to_csv(
        out / "historical_event_study_conditional_events_v2.csv",
        index=False,
    )

    controlled.to_csv(
        out / "historical_event_study_controlled_associations_v2.csv",
        index=False,
    )

    adequacy.to_csv(
        out / "historical_event_study_sample_adequacy_v2.csv",
        index=False,
    )

    base.to_csv(
        out / "historical_event_study_baseline_v2.csv",
        index=False,
    )

    errors: list[str] = []
    warnings: list[str] = []

    if len(panel) < 500:
        errors.append("Common sample below 500 observations")

    if not panel["study_date"].is_monotonic_increasing:
        errors.append("Study dates are not sorted")

    if panel["study_date"].duplicated().any():
        errors.append("Duplicate study dates detected")

    if "point_in_time_safe" in panel.columns:
        if not panel["point_in_time_safe"].eq(True).all():
            errors.append("Research Context PIT safeguard failed")

    if panel["forward_return_20D"].notna().sum() < 500:
        warnings.append("20D outcome sample below 500 observations")

    for name in EVENTS:
        n = int(panel[f"onset_{name}"].sum())
        if n < 5:
            warnings.append(f"{name}: fewer than 5 event observations")
        elif n < MIN_EVENT_OBS:
            warnings.append(
                f"{name}: limited event sample ({n})"
            )

    report = build_validation(
        panel,
        adequacy,
        errors,
        warnings,
    )

    with open(
        out / "historical_event_study_validation_v2.json",
        "w",
        encoding="utf-8",
    ) as fh:
        json.dump(
            report,
            fh,
            indent=2,
            ensure_ascii=False,
        )

    print("==============================================")
    print("HISTORICAL EVENT STUDY v2")
    print("==============================================")
    print(f"Common sample: {len(panel):,}")
    print(
        f"Date range: "
        f"{panel['study_date'].min().date()} -> "
        f"{panel['study_date'].max().date()}"
    )
    print(f"Event definitions: {len(EVENTS)}")
    print(f"Overlap rows: {len(overlap):,}")
    print(f"Redundancy rows: {len(correlations):,}")
    print(f"Conditional rows: {len(conditional):,}")
    print(f"Controlled-association rows: {len(controlled):,}")
    print("Research-only: TRUE")
    print("Decision Engine: FALSE")
    print("Trading signal: FALSE")
    print("Forecast: FALSE")
    print("PIT-perfect: FALSE")
    print(f"FINAL STATUS: {report['status']}")

    for warning in warnings:
        print("WARNING:", warning)


if __name__ == "__main__":
    main()
