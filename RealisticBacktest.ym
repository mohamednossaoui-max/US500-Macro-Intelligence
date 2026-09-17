"""
US500 REALISTIC BACKTEST AUDIT V1
=================================

Purpose
-------
Audit the frozen US500 EMA19 baseline for execution realism before the
Probability Engine is built.

IMPORTANT:
- This file does NOT modify the frozen baseline logic.
- It does NOT optimize parameters.
- It does NOT create a new trading signal.
- It compares the frozen baseline result with explicitly defined
  execution-realism variants.

Frozen reference:
119 signals / 117 valid / 109 resolved / 36W / 73L / +71R
RR = 4
Daily ^GSPC
Signal:
Close > EMA200
EMA19 > EMA200
Low <= EMA19
Close > EMA19
Consecutive qualifying days are collapsed to one signal.

Frozen stop:
lowest Low of previous 5 completed daily candles
minus 0.5 * previous day's Wilder ATR(14).

Frozen trade resolution:
resolution begins on the day AFTER the signal candle.
TP/SL on the same daily bar => AMBIGUOUS.
"""

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

TICKER = "^GSPC"
START_DATE = "2019-01-01"
RR = 4.0
EMA19 = 19
EMA200 = 200
ATR14 = 14
LOW_LOOKBACK = 5

EXPECTED = {
    "signals": 119,
    "valid": 117,
    "resolved": 109,
    "wins": 36,
    "losses": 73,
    "ambiguous": 3,
    "open": 5,
    "total_R": 71.0,
}

# ---------------------------------------------------------------------
# FROZEN BASELINE
# ---------------------------------------------------------------------

def load_market():
    df = yf.download(
        TICKER,
        start=START_DATE,
        auto_adjust=False,
        progress=False,
    )
    if df.empty:
        raise RuntimeError("Yahoo Finance returned no market data.")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[["Open", "High", "Low", "Close"]].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.sort_index().dropna()

    for c in ["Open", "High", "Low", "Close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna()

    df["EMA19"] = df["Close"].ewm(
        span=EMA19, adjust=False, min_periods=EMA19
    ).mean()

    df["EMA200"] = df["Close"].ewm(
        span=EMA200, adjust=False, min_periods=EMA200
    ).mean()

    pc = df["Close"].shift(1)
    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - pc).abs(),
            (df["Low"] - pc).abs(),
        ],
        axis=1,
    ).max(axis=1)

    df["ATR14_WILDER"] = tr.ewm(
        alpha=1 / ATR14,
        adjust=False,
        min_periods=ATR14,
    ).mean()

    return df


def baseline_condition(df, i):
    r = df.iloc[i]
    return bool(
        pd.notna(r["EMA19"])
        and pd.notna(r["EMA200"])
        and r["Close"] > r["EMA200"]
        and r["EMA19"] > r["EMA200"]
        and r["Low"] <= r["EMA19"]
        and r["Close"] > r["EMA19"]
    )


def build_baseline_signals(df):
    raw = [i for i in range(len(df)) if baseline_condition(df, i)]
    return [
        i for p, i in enumerate(raw)
        if p == 0 or raw[p] - raw[p - 1] > 1
    ]


def baseline_stop(df, i):
    if i < LOW_LOOKBACK + 1:
        return np.nan

    lows = df.iloc[i - LOW_LOOKBACK:i]["Low"]
    atr = df.iloc[i - 1]["ATR14_WILDER"]

    if pd.isna(atr):
        return np.nan

    return float(lows.min() - 0.5 * atr)


# ---------------------------------------------------------------------
# REALISTIC EXECUTION VARIANTS
# ---------------------------------------------------------------------
#
# The audit deliberately keeps the signal and stop unchanged.
#
# V0 FROZEN:
#   Entry = signal close.
#   Future daily bar:
#     if both TP and SL touched -> AMBIGUOUS
#     else TP -> WIN, SL -> LOSS
#
# V1 CONSERVATIVE GAP:
#   Same entry/targets, but if the next day's OPEN is already beyond
#   the stop or target, the exit is assumed at the OPEN rather than at
#   the stop/target price. This prevents impossible fills through gaps.
#
# V2 GAP + COST:
#   V1 plus a configurable round-trip cost expressed in R.
#   Default is 0.00R because a defensible historical cost for ^GSPC
#   cash-index OHLC is not available from the index itself.
#
# V3 WORST-CASE INTRABAR:
#   When both TP and SL are touched on the same daily bar, classify it
#   as LOSS rather than silently choosing TP. This is deliberately
#   conservative, not claimed to be the true intrabar sequence.
#
# These are audit scenarios, not new strategy rules.

def resolve_frozen(df, entry_i, entry, stop):
    if not np.isfinite(stop) or stop >= entry:
        return "INVALID_SL", np.nan, None

    risk = entry - stop
    target = entry + RR * risk

    for j in range(entry_i + 1, len(df)):
        hi = float(df.iloc[j]["High"])
        lo = float(df.iloc[j]["Low"])

        tp = hi >= target
        sl = lo <= stop

        if tp and sl:
            return "AMBIGUOUS", np.nan, j
        if tp:
            return "WIN", RR, j
        if sl:
            return "LOSS", -1.0, j

    return "OPEN", np.nan, None


def resolve_gap_conservative(
    df, entry_i, entry, stop, both_hit="AMBIGUOUS", cost_R=0.0
):
    if not np.isfinite(stop) or stop >= entry:
        return "INVALID_SL", np.nan, None

    risk = entry - stop
    target = entry + RR * risk

    for j in range(entry_i + 1, len(df)):
        op = float(df.iloc[j]["Open"])
        hi = float(df.iloc[j]["High"])
        lo = float(df.iloc[j]["Low"])

        # Gap-through exits: the executable price is the opening price.
        if op <= stop:
            return "LOSS", (op - entry) / risk - cost_R, j

        if op >= target:
            return "WIN", (op - entry) / risk - cost_R, j

        tp = hi >= target
        sl = lo <= stop

        if tp and sl:
            if both_hit == "LOSS":
                return "LOSS", -1.0 - cost_R, j
            return "AMBIGUOUS", np.nan, j

        if tp:
            return "WIN", RR - cost_R, j

        if sl:
            return "LOSS", -1.0 - cost_R, j

    return "OPEN", np.nan, None


def build_trades(df, resolver):
    rows = []

    for i in build_baseline_signals(df):
        entry = float(df.iloc[i]["Close"])
        stop = baseline_stop(df, i)

        result, r_mult, exit_i = resolver(df, i, entry, stop)

        risk = entry - stop if np.isfinite(stop) else np.nan
        target = (
            entry + RR * risk
            if np.isfinite(risk) and risk > 0
            else np.nan
        )

        rows.append(
            {
                "signal_date": df.index[i],
                "signal_index": i,
                "entry": entry,
                "stop": stop,
                "risk_points": risk,
                "target": target,
                "result": result,
                "R": r_mult,
                "exit_date": (
                    df.index[exit_i]
                    if exit_i is not None
                    else pd.NaT
                ),
            }
        )

    return pd.DataFrame(rows)


def summary(g):
    wins = int((g["result"] == "WIN").sum())
    losses = int((g["result"] == "LOSS").sum())
    ambiguous = int((g["result"] == "AMBIGUOUS").sum())
    open_trades = int((g["result"] == "OPEN").sum())
    invalid = int((g["result"] == "INVALID_SL").sum())

    resolved = wins + losses
    r = pd.to_numeric(g["R"], errors="coerce").dropna()

    gross_profit = float(g.loc[g["R"] > 0, "R"].sum())
    gross_loss = abs(float(g.loc[g["R"] < 0, "R"].sum()))

    return {
        "signals": len(g),
        "valid": len(g) - invalid,
        "invalid_sl": invalid,
        "resolved": resolved,
        "wins": wins,
        "losses": losses,
        "ambiguous": ambiguous,
        "open": open_trades,
        "win_rate": 100 * wins / resolved if resolved else np.nan,
        "avg_R": float(r.mean()) if len(r) else np.nan,
        "total_R": float(r.sum()) if len(r) else 0.0,
        "profit_factor": (
            gross_profit / gross_loss
            if gross_loss
            else np.nan
        ),
    }


def frozen_guard(trades):
    s = summary(trades)

    checks = {
        "signals": s["signals"] == EXPECTED["signals"],
        "valid": s["valid"] == EXPECTED["valid"],
        "resolved": s["resolved"] == EXPECTED["resolved"],
        "wins": s["wins"] == EXPECTED["wins"],
        "losses": s["losses"] == EXPECTED["losses"],
        "ambiguous": s["ambiguous"] == EXPECTED["ambiguous"],
        "open": s["open"] == EXPECTED["open"],
        "total_R": abs(s["total_R"] - EXPECTED["total_R"]) < 1e-9,
    }

    return all(checks.values()), checks, s


def compare(a, b):
    return {
        "signals": a["signals"],
        "resolved_A": a["resolved"],
        "resolved_B": b["resolved"],
        "wins_A": a["wins"],
        "wins_B": b["wins"],
        "losses_A": a["losses"],
        "losses_B": b["losses"],
        "total_R_A": a["total_R"],
        "total_R_B": b["total_R"],
        "delta_total_R": b["total_R"] - a["total_R"],
        "avg_R_A": a["avg_R"],
        "avg_R_B": b["avg_R"],
        "delta_avg_R": b["avg_R"] - a["avg_R"],
        "pf_A": a["profit_factor"],
        "pf_B": b["profit_factor"],
    }


def main():
    print("=" * 80)
    print("US500 REALISTIC BACKTEST AUDIT V1")
    print("=" * 80)
    print("Frozen baseline is used as the signal/stop reference.")
    print("No optimization. No new signal logic. No Decision Engine changes.")

    df = load_market()

    frozen = build_trades(
        df,
        lambda d, i, e, s: resolve_frozen(d, i, e, s),
    )

    ok, checks, frozen_summary = frozen_guard(frozen)

    print("\nFROZEN BASELINE REPRODUCTION")
    print(pd.Series(frozen_summary).to_string())
    print("\nFROZEN GUARD:", "PASS" if ok else "FAIL")
    if not ok:
        print("Checks:", checks)
        raise RuntimeError(
            "The realistic audit stopped because the frozen baseline "
            "could not be reproduced exactly."
        )

    conservative_gap = build_trades(
        df,
        lambda d, i, e, s: resolve_gap_conservative(
            d, i, e, s, both_hit="AMBIGUOUS", cost_R=0.0
        ),
    )

    conservative_gap_worst_case = build_trades(
        df,
        lambda d, i, e, s: resolve_gap_conservative(
            d, i, e, s, both_hit="LOSS", cost_R=0.0
        ),
    )

    print("\n" + "=" * 80)
    print("EXECUTION REALISM SCENARIOS")
    print("=" * 80)

    scenarios = {
        "FROZEN": frozen,
        "GAP_CONSERVATIVE": conservative_gap,
        "GAP_PLUS_WORST_CASE_AMBIGUOUS": conservative_gap_worst_case,
    }

    rows = []
    for name, trades in scenarios.items():
        s = summary(trades)
        rows.append(
            {
                "scenario": name,
                **s,
            }
        )

    scenario_df = pd.DataFrame(rows)
    print(scenario_df.to_string(index=False))

    print("\n" + "=" * 80)
    print("FROZEN vs CONSERVATIVE GAP")
    print("=" * 80)
    print(
        pd.Series(
            compare(frozen_summary, summary(conservative_gap))
        ).to_string()
    )

    print("\n" + "=" * 80)
    print("AMBIGUOUS-BAR SENSITIVITY")
    print("=" * 80)
    print(
        pd.Series(
            compare(
                conservative_gap,
                summary(conservative_gap_worst_case),
            )
        ).to_string()
    )

    # -----------------------------------------------------------------
    # Trade-level audit flags
    # -----------------------------------------------------------------
    audit = frozen[
        [
            "signal_date",
            "entry",
            "stop",
            "target",
            "result",
            "R",
            "exit_date",
        ]
    ].copy()

    audit["exit_date"] = pd.to_datetime(audit["exit_date"])

    gap_flags = []
    for _, tr in frozen.iterrows():
        if pd.isna(tr["exit_date"]):
            gap_flags.append(False)
            continue

        exit_i = df.index.get_loc(pd.Timestamp(tr["exit_date"]))
        op = float(df.iloc[exit_i]["Open"])

        gap_flags.append(
            op <= float(tr["stop"])
            or op >= float(tr["target"])
        )

    audit["exit_gap_through_level"] = gap_flags

    audit.to_csv(
        "realistic_backtest_trade_level_audit.csv",
        index=False,
    )

    scenario_df.to_csv(
        "realistic_backtest_scenario_summary.csv",
        index=False,
    )

    print("\nFILES CREATED")
    print("realistic_backtest_trade_level_audit.csv")
    print("realistic_backtest_scenario_summary.csv")

    print("\n" + "=" * 80)
    print("AUDIT STATUS")
    print("=" * 80)
    print("FROZEN SIGNAL/RESULT REPRODUCTION: PASS")
    print("FROZEN BASELINE: NOT MODIFIED")
    print("PARAMETER OPTIMIZATION: NONE")
    print("DECISION ENGINE: NOT MODIFIED")
    print("TRADE EXECUTION: RESEARCH ONLY")
    print("NEXT STEP: inspect the scenario deltas before Probability Engine.")


if __name__ == "__main__":
    main()
