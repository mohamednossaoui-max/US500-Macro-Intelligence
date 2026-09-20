#!/usr/bin/env python3
"""
Financial Stress Frequency Sensitivity v1.2
Research-only validation.

Purpose:
- Reconstruct the current daily PIT panel from raw historical records.
- Compare daily calendar rolling z-score windows: 63D, 126D, 252D.
- Build a TRUE native-frequency PIT method using 252 native observations
  per component, then map standardized values to daily as-of dates.
- Validate schema/PIT integrity and generate event/sensitivity outputs.

No trade signals, execution logic, or Decision Engine integration.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import numpy as np
import pandas as pd

INPUT_NAME = "financial_stress_records_input_v1.csv"
OUTPUT_DIR = Path(".")

REQUIRED = [
    "indicator", "observation_date", "availability_date", "actual",
    "unit", "frequency", "source", "source_url", "vintage",
    "revision_flag", "point_in_time_safe", "availability_semantics",
]
INDICATORS = ["VIX", "NFCI", "ANFCI", "TREASURY_2Y", "TREASURY_10Y"]
START_THRESHOLD = 1.0
END_THRESHOLD = 0.0
MIN_PERIODS_DAILY = 60
NATIVE_WINDOW_OBS = 252
MIN_COMPONENTS = 2


def find_input() -> Path:
    candidates = [
        Path("financial_stress_records_input_v1(1).csv"),
        Path("/mnt/data/financial_stress_records_input_v1(1).csv"),
        Path(INPUT_NAME),
        Path("/mnt/data") / INPUT_NAME,
    ]
    for p in candidates:
        if p.exists() and p.is_file() and p.stat().st_size > 1000:
            return p
    raise FileNotFoundError(f"Input not found: {INPUT_NAME}")


def load_validate(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    if df.empty:
        raise ValueError("Input CSV contains zero rows.")

    for c in ["observation_date", "availability_date", "vintage"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
        if df[c].isna().any():
            raise ValueError(f"Invalid datetime values in {c}.")

    df["actual"] = pd.to_numeric(df["actual"], errors="coerce")
    if df["actual"].isna().any():
        raise ValueError("Input contains non-numeric actual values.")

    if not df["point_in_time_safe"].astype(bool).all():
        raise ValueError("Input contains point_in_time_safe=False records.")

    if not (df["availability_date"] >= df["observation_date"]).all():
        raise ValueError("availability_date precedes observation_date.")

    if not set(df["indicator"].unique()).issubset(set(INDICATORS)):
        raise ValueError(f"Unexpected indicators: {sorted(set(df['indicator']) - set(INDICATORS))}")

    return df.sort_values(
        ["indicator", "observation_date", "availability_date", "vintage"]
    ).reset_index(drop=True)


def pit_daily_series(df: pd.DataFrame, indicator: str, dates: pd.DatetimeIndex) -> pd.Series:
    """Latest PIT observation available on each as-of date, without future observations."""
    r = df[df["indicator"] == indicator].copy()
    # No revisions in current raw file. Keep the latest record for any repeated observation.
    r = r.sort_values(["observation_date", "availability_date", "vintage"])
    r = r.drop_duplicates(["observation_date"], keep="last")
    r = r.sort_values(["availability_date", "observation_date"])

    left = pd.DataFrame({"asof_date": dates})
    m = pd.merge_asof(
        left.sort_values("asof_date"),
        r[["availability_date", "observation_date", "actual"]].sort_values("availability_date"),
        left_on="asof_date",
        right_on="availability_date",
        direction="backward",
    )
    # Defensive anti-lookahead check.
    m.loc[m["observation_date"] > m["asof_date"], "actual"] = np.nan
    return m.set_index("asof_date")["actual"].rename(indicator)


def build_daily_pit_panel(df: pd.DataFrame) -> pd.DataFrame:
    dates = pd.date_range(df["observation_date"].min(), df["observation_date"].max(), freq="D")
    panel = pd.DataFrame(index=dates)
    for ind in INDICATORS:
        panel[ind] = pit_daily_series(df, ind, dates)
    panel["YIELD_10Y_2Y_SPREAD"] = panel["TREASURY_10Y"] - panel["TREASURY_2Y"]
    panel["YIELD_CURVE_STRESS"] = -panel["YIELD_10Y_2Y_SPREAD"]
    return panel


def rolling_z_calendar(series: pd.Series, days: int) -> pd.Series:
    r = series.rolling(f"{days}D", min_periods=MIN_PERIODS_DAILY)
    return (series - r.mean()) / r.std(ddof=0)


def score_daily_method(panel: pd.DataFrame, days: int) -> pd.DataFrame:
    out = pd.DataFrame(index=panel.index)
    out["VIX_Z"] = rolling_z_calendar(panel["VIX"], days)
    out["NFCI_Z"] = rolling_z_calendar(panel["NFCI"], days)
    out["ANFCI_Z"] = rolling_z_calendar(panel["ANFCI"], days)
    out["YIELD_CURVE_STRESS_Z"] = rolling_z_calendar(
        panel["YIELD_CURVE_STRESS"], days
    )
    zcols = ["VIX_Z", "NFCI_Z", "ANFCI_Z", "YIELD_CURVE_STRESS_Z"]
    out["stress_component_count"] = out[zcols].notna().sum(axis=1)
    out["composite_stress_score"] = out[zcols].mean(axis=1, skipna=True)
    out.loc[out["stress_component_count"] < MIN_COMPONENTS, "composite_stress_score"] = np.nan
    return out


def native_component_z(df: pd.DataFrame, indicator: str, window_obs: int) -> pd.Series:
    """Native-frequency rolling z-score, then PIT-map by release/availability date."""
    r = df[df["indicator"] == indicator].copy()
    r = r.sort_values(["observation_date", "availability_date", "vintage"])
    r = r.drop_duplicates(["observation_date"], keep="last")

    s = r.set_index("observation_date")["actual"].sort_index()
    roll = s.rolling(window_obs, min_periods=MIN_PERIODS_DAILY)
    z = (s - roll.mean()) / roll.std(ddof=0)

    zdf = z.rename("z").reset_index()
    zdf = zdf.merge(
        r[["observation_date", "availability_date"]],
        on="observation_date",
        how="left",
    ).dropna(subset=["z"]).sort_values("availability_date")

    dates = pd.date_range(df["observation_date"].min(), df["observation_date"].max(), freq="D")
    left = pd.DataFrame({"asof_date": dates})
    m = pd.merge_asof(
        left.sort_values("asof_date"),
        zdf[["availability_date", "observation_date", "z"]].sort_values("availability_date"),
        left_on="asof_date",
        right_on="availability_date",
        direction="backward",
    )
    m.loc[m["observation_date"] > m["asof_date"], "z"] = np.nan
    return m.set_index("asof_date")["z"]


def score_native_method(df: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=panel.index)
    out["VIX_Z"] = native_component_z(df, "VIX", NATIVE_WINDOW_OBS)
    out["NFCI_Z"] = native_component_z(df, "NFCI", NATIVE_WINDOW_OBS)
    out["ANFCI_Z"] = native_component_z(df, "ANFCI", NATIVE_WINDOW_OBS)

    # Yield curve is a derived daily series, so its native frequency is daily.
    s = panel["YIELD_CURVE_STRESS"]
    r = s.rolling(NATIVE_WINDOW_OBS, min_periods=MIN_PERIODS_DAILY)
    out["YIELD_CURVE_STRESS_Z"] = (s - r.mean()) / r.std(ddof=0)

    zcols = ["VIX_Z", "NFCI_Z", "ANFCI_Z", "YIELD_CURVE_STRESS_Z"]
    out["stress_component_count"] = out[zcols].notna().sum(axis=1)
    out["composite_stress_score"] = out[zcols].mean(axis=1, skipna=True)
    out.loc[out["stress_component_count"] < MIN_COMPONENTS, "composite_stress_score"] = np.nan
    return out


def classify(score: float) -> str:
    if pd.isna(score):
        return "INSUFFICIENT_DATA"
    if score >= 2:
        return "EXTREME_RESEARCH_STRESS"
    if score >= 1:
        return "HIGH_RESEARCH_STRESS"
    if score >= 0:
        return "ELEVATED_RESEARCH_STRESS"
    return "LOW_RESEARCH_STRESS"


def build_events(scored: pd.DataFrame, method: str) -> pd.DataFrame:
    s = scored["composite_stress_score"]
    active = False
    event_rows = []
    start = None
    rows = []

    for date, value in s.items():
        if pd.isna(value):
            if active:
                rows.append((date, value))
            continue

        if not active:
            if value >= START_THRESHOLD:
                active = True
                start = date
                rows = [(date, value)]
        else:
            rows.append((date, value))
            if value < END_THRESHOLD:
                vals = pd.Series({d: v for d, v in rows}).dropna()
                peak_date = vals.idxmax()
                peak_value = float(vals.max())
                start_date = vals.index.min()
                end_date = date
                recovery_date = date
                peak_regime = classify(peak_value)

                event_rows.append({
                    "method": method,
                    "start_date": start_date.date().isoformat(),
                    "end_date": end_date.date().isoformat(),
                    "peak_date": peak_date.date().isoformat(),
                    "peak_composite": peak_value,
                    "peak_regime": peak_regime,
                    "mean_composite": float(vals.mean()),
                    "duration_calendar_days": int((end_date - start_date).days + 1),
                    "time_to_peak_calendar_days": int((peak_date - start_date).days),
                    "recovery_date": recovery_date.date().isoformat(),
                    "recovery_duration_calendar_days": int((recovery_date - peak_date).days),
                })
                active = False
                start = None
                rows = []

    if active and rows:
        vals = pd.Series({d: v for d, v in rows}).dropna()
        peak_date = vals.idxmax()
        peak_value = float(vals.max())
        start_date = vals.index.min()
        end_date = vals.index.max()
        event_rows.append({
            "method": method,
            "start_date": start_date.date().isoformat(),
            "end_date": end_date.date().isoformat(),
            "peak_date": peak_date.date().isoformat(),
            "peak_composite": peak_value,
            "peak_regime": classify(peak_value),
            "mean_composite": float(vals.mean()),
            "duration_calendar_days": int((end_date - start_date).days + 1),
            "time_to_peak_calendar_days": int((peak_date - start_date).days),
            "recovery_date": "",
            "recovery_duration_calendar_days": np.nan,
        })

    return pd.DataFrame(event_rows)


def sha256_row(row: pd.Series) -> str:
    payload = "|".join("" if pd.isna(v) else str(v) for v in row.tolist())
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> None:
    path = find_input()
    raw = load_validate(path)
    panel = build_daily_pit_panel(raw)

    method_scores = {
        "A_CURRENT": score_daily_method(panel, 252),
        "B_63D": score_daily_method(panel, 63),
        "C_126D": score_daily_method(panel, 126),
        "D_252D": score_daily_method(panel, 252),
        "E_NATIVE_252OBS": score_native_method(raw, panel),
    }

    # Validation panel: A_CURRENT is the canonical reconstruction.
    validation = method_scores["A_CURRENT"].copy()
    validation["asof_date"] = validation.index
    validation["research_regime"] = validation["composite_stress_score"].map(classify)
    validation["point_in_time_safe"] = True
    validation = validation.reset_index(drop=True)

    events = []
    for method, scores in method_scores.items():
        e = build_events(scores, method)
        if not e.empty:
            events.append(e)
    events_df = pd.concat(events, ignore_index=True) if events else pd.DataFrame()

    # Frequency sensitivity, one row per method.
    base = method_scores["A_CURRENT"]["composite_stress_score"].rename("A")
    sens_rows = []
    for method, scores in method_scores.items():
        s = scores["composite_stress_score"].rename(method)
        joined = pd.concat([base, s], axis=1).dropna()
        corr = float(joined["A"].corr(joined[method])) if len(joined) >= 2 else np.nan
        mad = float((joined["A"] - joined[method]).abs().mean()) if len(joined) else np.nan
        regime = scores["composite_stress_score"].map(classify)
        counts = regime.value_counts()
        ev = build_events(scores, method)
        sens_rows.append({
            "method": method,
            "rows_total": len(scores),
            "scored_rows": int(scores["composite_stress_score"].notna().sum()),
            "frequency_correlation_vs_A": corr,
            "MAD_vs_A": mad,
            "event_count": len(ev),
            "max_composite": float(scores["composite_stress_score"].max()),
            "peak_date": (
                scores["composite_stress_score"].idxmax().date().isoformat()
                if scores["composite_stress_score"].notna().any() else ""
            ),
            "LOW_RESEARCH_STRESS": int(counts.get("LOW_RESEARCH_STRESS", 0)),
            "ELEVATED_RESEARCH_STRESS": int(counts.get("ELEVATED_RESEARCH_STRESS", 0)),
            "HIGH_RESEARCH_STRESS": int(counts.get("HIGH_RESEARCH_STRESS", 0)),
            "EXTREME_RESEARCH_STRESS": int(counts.get("EXTREME_RESEARCH_STRESS", 0)),
            "INSUFFICIENT_DATA": int(counts.get("INSUFFICIENT_DATA", 0)),
        })
    sensitivity = pd.DataFrame(sens_rows)

    # Long-form method panel.
    panel_rows = []
    for method, scores in method_scores.items():
        tmp = scores.copy()
        tmp["asof_date"] = tmp.index
        tmp["method"] = method
        tmp["research_regime"] = tmp["composite_stress_score"].map(classify)
        tmp["point_in_time_safe"] = True
        panel_rows.append(tmp.reset_index(drop=True))
    long_panel = pd.concat(panel_rows, ignore_index=True)

    # Integrity summary.
    summary = pd.DataFrame([{
        "start_date": raw["observation_date"].min().date().isoformat(),
        "end_date": raw["observation_date"].max().date().isoformat(),
        "raw_rows": len(raw),
        "indicators": ",".join(sorted(raw["indicator"].unique())),
        "point_in_time_safe_rows": int(raw["point_in_time_safe"].astype(bool).sum()),
        "revision_flag_true_rows": int(raw["revision_flag"].astype(bool).sum()),
        "availability_before_observation_rows": int(
            (raw["availability_date"] < raw["observation_date"]).sum()
        ),
        "duplicate_indicator_observation_vintage_rows": int(
            raw.duplicated(["indicator", "observation_date", "vintage"]).sum()
        ),
        "event_start_threshold": START_THRESHOLD,
        "event_end_threshold": END_THRESHOLD,
        "native_window_observations": NATIVE_WINDOW_OBS,
        "native_method_note": (
            "252 native observations per component; NFCI/ANFCI remain weekly; "
            "yield-curve stress is derived from daily Treasury PIT series."
        ),
        "research_only": True,
    }])

    out_validation = OUTPUT_DIR / "financial_stress_validation_v1_2.csv"
    out_summary = OUTPUT_DIR / "financial_stress_validation_summary_v1_2.csv"
    out_events = OUTPUT_DIR / "financial_stress_validation_events_v1_2.csv"
    out_sensitivity = OUTPUT_DIR / "financial_stress_frequency_sensitivity_v1_2.csv"

    validation.to_csv(out_validation, index=False)
    summary.to_csv(out_summary, index=False)
    events_df.to_csv(out_events, index=False)
    sensitivity.to_csv(out_sensitivity, index=False)

    print("Financial Stress Frequency Sensitivity v1.2")
    print(f"Input: {path}")
    print(f"Raw rows: {len(raw)}")
    print(f"Research-only: True")
    print(sensitivity.to_string(index=False))
    print(f"Outputs: {out_validation}, {out_summary}, {out_events}, {out_sensitivity}")


if __name__ == "__main__":
    main()
