#!/usr/bin/env python3
"""
Financial Stress Methodology Review v1.3
Research-only.

Purpose:
1) Reconstruct the current calendar-day methodology from raw PIT records.
2) Compare 63D / 126D / 252D calendar-day rolling z-scores.
3) Compare a native-observation method.
4) Add frequency-aware normalization:
      DAILY  -> 252 native observations
      WEEKLY -> 52 native observations
   while preserving Point-in-Time availability.
5) Report regime/event statistics on market trading-session dates.

No Decision Engine, no trade signals, no execution logic.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import numpy as np
import pandas as pd

RAW_NAME = "financial_stress_records_input_v1.csv"

OUTPUT_VALIDATION = "financial_stress_validation_v1_3.csv"
OUTPUT_SUMMARY = "financial_stress_validation_summary_v1_3.csv"
OUTPUT_EVENTS = "financial_stress_validation_events_v1_3.csv"
OUTPUT_SENSITIVITY = "financial_stress_frequency_sensitivity_v1_3.csv"

INDICATORS = ["VIX", "TREASURY_2Y", "TREASURY_10Y", "NFCI", "ANFCI"]
Z_COLUMNS = ["VIX_Z", "NFCI_Z", "ANFCI_Z", "YIELD_CURVE_STRESS_Z"]


def find_raw_file() -> Path:
    candidates = [
        Path(RAW_NAME),
        Path("raw_collector_artifact") / RAW_NAME,
    ]

    # Prefer a non-empty exact-name file.
    for p in candidates:
        if p.exists() and p.is_file() and p.stat().st_size > 200:
            return p

    # Also support ChatGPT/user-uploaded copies such as
    # financial_stress_records_input_v1(1).csv.
    found = []
    for base in [Path("."), Path("/mnt/data")]:
        found.extend(base.glob("financial_stress_records_input_v1*.csv"))
        found.extend(base.glob("**/financial_stress_records_input_v1*.csv"))

    nonempty = [
        p for p in found
        if p.is_file() and p.stat().st_size > 200
    ]

    if nonempty:
        # Prefer the largest copy; this avoids accidentally selecting
        # a header-only CSV.
        return max(nonempty, key=lambda x: x.stat().st_size)

    raise FileNotFoundError(
        f"Could not find a non-empty {RAW_NAME} or a matching uploaded copy."
    )


def load_and_validate(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    required = [
        "indicator", "observation_date", "availability_date", "actual",
        "unit", "frequency", "source", "source_url", "vintage",
        "revision_flag", "point_in_time_safe", "availability_semantics",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError(f"Missing required columns: {missing}")

    if df.empty:
        raise RuntimeError("Raw PIT input contains zero rows.")

    for c in ["observation_date", "availability_date", "vintage"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")

    if df[["observation_date", "availability_date"]].isna().any().any():
        raise RuntimeError("Invalid observation/availability dates found.")

    if (df["availability_date"] < df["observation_date"]).any():
        raise RuntimeError("PIT violation: availability_date < observation_date.")

    if not df["point_in_time_safe"].astype(str).str.lower().isin(
        ["true", "1", "yes"]
    ).all():
        raise RuntimeError("Raw input contains non-PIT-safe records.")

    if not set(df["indicator"].unique()).issuperset(INDICATORS):
        raise RuntimeError(
            f"Missing expected indicators. Found: {sorted(df['indicator'].unique())}"
        )

    # Generic duplicate check. Multiple vintages are allowed; exact duplicates are not.
    dup_cols = ["indicator", "observation_date", "availability_date", "vintage"]
    if df.duplicated(dup_cols).any():
        raise RuntimeError("Duplicate indicator/observation/availability/vintage rows found.")

    return df.sort_values(["indicator", "observation_date", "availability_date", "vintage"]).reset_index(drop=True)



def _prepare_indicator(df: pd.DataFrame, indicator: str) -> pd.DataFrame:
    x = df[df["indicator"] == indicator].copy()
    x = x.sort_values(["availability_date", "observation_date", "vintage"]).reset_index(drop=True)

    if x.empty:
        raise RuntimeError(f"No rows found for indicator {indicator}.")

    # The current collector has no revisions and monotonic release order.
    # Fail closed if that changes rather than risk an invalid PIT reconstruction.
    if bool(x["revision_flag"].any()):
        raise RuntimeError(
            f"{indicator}: revision_flag=True detected. "
            "v1.3 requires a revision-aware PIT routine before continuing."
        )

    if not x["availability_date"].is_monotonic_increasing:
        raise RuntimeError(
            f"{indicator}: availability_date is not monotonic; "
            "v1.3 cannot safely use the fast PIT path."
        )

    if not x["observation_date"].is_unique:
        raise RuntimeError(
            f"{indicator}: duplicate observation dates detected without revisions."
        )

    return x


def calendar_panel(df: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Fast PIT calendar panel using release availability dates."""
    left = pd.DataFrame({"asof_date": pd.DatetimeIndex(dates)})
    panel = pd.DataFrame(index=pd.DatetimeIndex(dates))

    for ind in INDICATORS:
        x = _prepare_indicator(df, ind)[
            ["availability_date", "observation_date", "actual"]
        ].sort_values("availability_date")

        m = pd.merge_asof(
            left,
            x,
            left_on="asof_date",
            right_on="availability_date",
            direction="backward",
            allow_exact_matches=True,
        )

        # Explicit anti-lookahead check.
        m.loc[m["observation_date"] > m["asof_date"], "actual"] = np.nan
        panel[ind] = m["actual"].to_numpy()

    return panel


def calendar_method(panel: pd.DataFrame, window: int) -> tuple[pd.Series, pd.DataFrame]:
    """Current-style calendar-day rolling z-score method."""
    z = pd.DataFrame(index=panel.index)

    for ind, col in [
        ("VIX", "VIX_Z"),
        ("NFCI", "NFCI_Z"),
        ("ANFCI", "ANFCI_Z"),
    ]:
        r = panel[ind].rolling(window, min_periods=60)
        z[col] = (panel[ind] - r.mean()) / r.std(ddof=0)

    stress = -(panel["TREASURY_10Y"] - panel["TREASURY_2Y"])
    r = stress.rolling(window, min_periods=60)
    z["YIELD_CURVE_STRESS_Z"] = (stress - r.mean()) / r.std(ddof=0)

    count = z.notna().sum(axis=1)
    score = z.mean(axis=1, skipna=True)
    score[count < 2] = np.nan
    return score, z


def native_method(
    df: pd.DataFrame,
    asof_dates: pd.DatetimeIndex,
    weekly_window: int,
    daily_window: int = 252,
    weekly_min: int = 20,
) -> tuple[pd.Series, pd.DataFrame]:
    """
    Native-observation PIT method.

    z-scores are calculated on each indicator's own native observations.
    The resulting observation-level z-score is then mapped to each as-of
    date using availability_date, preserving PIT semantics.
    """
    left = pd.DataFrame({"asof_date": pd.DatetimeIndex(asof_dates)})
    z_panel = pd.DataFrame(index=pd.DatetimeIndex(asof_dates))

    for ind in ["VIX", "NFCI", "ANFCI"]:
        x = _prepare_indicator(df, ind).copy()
        freq = str(x.iloc[0]["frequency"]).upper()
        n = daily_window if freq == "DAILY" else weekly_window
        min_required = 60 if freq == "DAILY" else weekly_min

        s = x["actual"].astype(float)
        roll = s.rolling(n, min_periods=min_required)
        sd = roll.std(ddof=0)
        z = (s - roll.mean()) / sd

        release = x[["availability_date", "observation_date"]].copy()
        release["z"] = z.to_numpy()
        release = release.sort_values("availability_date")

        m = pd.merge_asof(
            left,
            release,
            left_on="asof_date",
            right_on="availability_date",
            direction="backward",
            allow_exact_matches=True,
        )

        m.loc[m["observation_date"] > m["asof_date"], "z"] = np.nan
        z_panel[f"{ind}_Z"] = m["z"].to_numpy()

    # Yield curve is a daily native series: merge the two Treasury observations
    # by observation date, then calculate the 252-observation z-score.
    y10 = _prepare_indicator(df, "TREASURY_10Y")[
        ["observation_date", "availability_date", "actual"]
    ].rename(columns={"actual": "y10"})
    y2 = _prepare_indicator(df, "TREASURY_2Y")[
        ["observation_date", "availability_date", "actual"]
    ].rename(columns={"actual": "y2"})

    spread = y10.merge(y2, on="observation_date", how="inner", suffixes=("_10Y", "_2Y"))
    spread = spread.sort_values("observation_date").reset_index(drop=True)
    spread["availability_date"] = spread[["availability_date_10Y", "availability_date_2Y"]].max(axis=1)
    spread["stress"] = -(spread["y10"] - spread["y2"])

    r = spread["stress"].rolling(daily_window, min_periods=60)
    spread["z"] = (spread["stress"] - r.mean()) / r.std(ddof=0)

    release = spread[["availability_date", "observation_date", "z"]].sort_values("availability_date")
    m = pd.merge_asof(
        left,
        release,
        left_on="asof_date",
        right_on="availability_date",
        direction="backward",
        allow_exact_matches=True,
    )
    m.loc[m["observation_date"] > m["asof_date"], "z"] = np.nan
    z_panel["YIELD_CURVE_STRESS_Z"] = m["z"].to_numpy()

    count = z_panel.notna().sum(axis=1)
    score = z_panel.mean(axis=1, skipna=True)
    score[count < 2] = np.nan
    z_panel["stress_component_count"] = count
    z_panel["composite_stress_score"] = score

    return score, z_panel


def add_regime(score: pd.Series) -> pd.Series:
    def regime(x):
        if pd.isna(x):
            return "INSUFFICIENT_DATA"
        if x >= 2:
            return "EXTREME_RESEARCH_STRESS"
        if x >= 1:
            return "HIGH_RESEARCH_STRESS"
        if x >= 0:
            return "ELEVATED_RESEARCH_STRESS"
        return "LOW_RESEARCH_STRESS"

    return score.map(regime)


def event_table(score: pd.Series, method: str) -> pd.DataFrame:
    """
    Hysteresis event detection on trading-session dates:
      start >= 1.0
      continue >= 0.0
      end < 0.0 or missing score.
    """
    s = score.sort_index()
    events = []
    i = 0

    while i < len(s):
        v = s.iloc[i]

        if pd.isna(v) or v < 1.0:
            i += 1
            continue

        start_i = i
        j = i
        while j + 1 < len(s):
            nxt = s.iloc[j + 1]
            if pd.isna(nxt) or nxt < 0.0:
                break
            j += 1

        segment = s.iloc[start_i:j + 1]
        peak_date = segment.idxmax()
        peak = float(segment.max())

        recovery_date = None
        for k in range(j + 1, len(s)):
            if pd.notna(s.iloc[k]) and s.iloc[k] < 0.0:
                recovery_date = s.index[k]
                break

        start_date = s.index[start_i]
        end_date = s.index[j]

        events.append({
            "method": method,
            "start_date": start_date,
            "end_date": end_date,
            "peak_date": peak_date,
            "peak_composite": peak,
            "peak_regime": add_regime(pd.Series([peak])).iloc[0],
            "mean_composite": float(segment.mean()),
            "duration_trading_sessions": int(len(segment)),
            "time_to_peak_sessions": int(segment.index.get_loc(peak_date)),
            "recovery_date": recovery_date,
            "recovery_duration_sessions": (
                int(s.index.get_loc(recovery_date) - j)
                if recovery_date is not None else np.nan
            ),
        })

        i = j + 1

    return pd.DataFrame(events)


def main():
    raw_path = find_raw_file()
    df = load_and_validate(raw_path)

    min_date = df["observation_date"].min()
    max_date = df["observation_date"].max()

    calendar_dates = pd.date_range(min_date, max_date, freq="D")

    # Market-session dates are the union of original DAILY observations.
    session_dates = pd.DatetimeIndex(
        sorted(
            df.loc[
                df["frequency"].astype(str).str.upper().eq("DAILY"),
                "observation_date",
            ].dropna().unique()
        )
    )

    panel = calendar_panel(df, calendar_dates)

    methods = {}

    # A/B/C/D: calendar-day methods.
    for label, window in [
        ("A_CURRENT_252D", 252),
        ("B_63D", 63),
        ("C_126D", 126),
        ("D_252D", 252),
    ]:
        score, z = calendar_method(panel, window)
        methods[label] = {
            "calendar_score": score,
            "score": score.reindex(session_dates),
            "z": z.reindex(session_dates),
        }

    # E: native observation count, 252 for both daily and weekly.
    e_score, e_z = native_method(
        df, session_dates, weekly_window=252, daily_window=252, weekly_min=60
    )
    methods["E_NATIVE_252OBS"] = {
        "calendar_score": e_score,
        "score": e_score,
        "z": e_z,
    }

    # F: frequency-aware: 252 daily observations ~= 1 year,
    # 52 weekly observations ~= 1 year.
    f_score, f_z = native_method(
        df, session_dates, weekly_window=52, daily_window=252, weekly_min=20
    )
    methods["F_FREQUENCY_AWARE"] = {
        "calendar_score": f_score,
        "score": f_score,
        "z": f_z,
    }

    # Build validation panel.
    validation = pd.DataFrame(index=session_dates)
    validation.index.name = "asof_date"

    for name, obj in methods.items():
        validation[name] = obj["score"]

    for name, obj in methods.items():
        validation[f"{name}_REGIME"] = add_regime(obj["score"])

    validation["point_in_time_safe"] = True
    validation["record_id"] = [
        hashlib.sha256(
            f"{d.date()}|financial_stress_methodology_v1_3".encode()
        ).hexdigest()
        for d in validation.index
    ]

    # Sensitivity summary versus A on overlapping scored sessions.
    base = validation["A_CURRENT_252D"]
    sens_rows = []

    for name in methods:
        x = validation[name]
        mask = base.notna() & x.notna()
        if mask.any():
            corr = float(base[mask].corr(x[mask]))
            mad = float((base[mask] - x[mask]).abs().mean())
        else:
            corr = np.nan
            mad = np.nan

        sens_rows.append({
            "method": name,
            "rows": int(x.notna().sum()),
            "correlation_vs_A": corr,
            "MAD_vs_A": mad,
            "peak_composite": float(x.max()) if x.notna().any() else np.nan,
            "peak_date": x.idxmax().date().isoformat() if x.notna().any() else None,
            "extreme_count": int((add_regime(x) == "EXTREME_RESEARCH_STRESS").sum()),
            "high_count": int((add_regime(x) == "HIGH_RESEARCH_STRESS").sum()),
            "elevated_count": int((add_regime(x) == "ELEVATED_RESEARCH_STRESS").sum()),
            "low_count": int((add_regime(x) == "LOW_RESEARCH_STRESS").sum()),
            "insufficient_count": int(x.isna().sum()),
        })

    sensitivity = pd.DataFrame(sens_rows)

    # Events use trading-session dates for every method.
    event_frames = [
        event_table(validation[name], name)
        for name in methods
    ]
    events = pd.concat(event_frames, ignore_index=True) if event_frames else pd.DataFrame()

    # Summary.
    summary = {
        "methodology_version": "v1.3",
        "start_date": str(validation.index.min().date()),
        "end_date": str(validation.index.max().date()),
        "raw_rows": int(len(df)),
        "daily_session_rows": int(len(session_dates)),
        "calendar_rows_used_for_A_to_D": int(len(calendar_dates)),
        "point_in_time_safe_raw_rows": int(df["point_in_time_safe"].sum()),
        "raw_revision_flag_true": int(df["revision_flag"].sum()),
        "pit_unsafe_rows": int((~df["point_in_time_safe"]).sum()),
        "frequency_aware_daily_window": 252,
        "frequency_aware_weekly_window": 52,
        "event_start_threshold": 1.0,
        "event_end_threshold": 0.0,
        "event_calendar_vs_session_note": (
            "Regime scores A-D are calendar-day constructions; "
            "event statistics are measured only on original DAILY market-session dates."
        ),
        "research_only": True,
        "event_count_A_CURRENT_252D": int(
            len(event_table(validation["A_CURRENT_252D"], "A_CURRENT_252D"))
        ),
        "event_count_F_FREQUENCY_AWARE": int(
            len(event_table(validation["F_FREQUENCY_AWARE"], "F_FREQUENCY_AWARE"))
        ),
    }

    summary_df = pd.DataFrame([summary])

    validation.reset_index().to_csv(OUTPUT_VALIDATION, index=False)
    summary_df.to_csv(OUTPUT_SUMMARY, index=False)
    events.to_csv(OUTPUT_EVENTS, index=False)
    sensitivity.to_csv(OUTPUT_SENSITIVITY, index=False)

    print("Financial Stress Methodology Review v1.3 completed.")
    print(f"Raw rows: {len(df)}")
    print(f"Market-session rows: {len(session_dates)}")
    print()
    print(sensitivity.to_string(index=False))
    print()
    print(f"Events A: {summary['event_count_A_CURRENT_252D']}")
    print(f"Events F: {summary['event_count_F_FREQUENCY_AWARE']}")
    print("Research-only: True")


if __name__ == "__main__":
    main()
