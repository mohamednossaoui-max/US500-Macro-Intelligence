# ============================================================
# US500 EMA19 SIGNAL ENGINE
# REVERSE ENGINEERING DIAGNOSTIC V3
# ============================================================
# Clean V3 only. Do NOT append V2 code below this file.
#
# Reference baseline:
# signals=119, valid=117, invalid_sl=2, resolved=109,
# wins=36, losses=73, ambiguous=3, open=5, total_R=+71R,
# profit_factor~=1.973
# ============================================================

import itertools
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

REF = {
    "signals": 119, "valid": 117, "invalid_sl": 2,
    "resolved": 109, "wins": 36, "losses": 73,
    "ambiguous": 3, "open": 5
}

REF_YEAR = {
    2019: {"signals":1,"wins":1,"losses":0},
    2020: {"signals":16,"wins":10,"losses":5,"ambiguous":1},
    2021: {"signals":26,"wins":9,"losses":16,"ambiguous":1},
    2022: {"signals":5,"wins":0,"losses":5},
    2023: {"signals":15,"wins":6,"losses":9},
    2024: {"signals":17,"wins":6,"losses":10,"ambiguous":1},
    2025: {"signals":19,"wins":4,"losses":15},
    2026: {"signals":18,"wins":0,"losses":13,"open":5},
}


def load_data():
    df = yf.download(
        TICKER, start=START_DATE, auto_adjust=False, progress=False
    )
    if df.empty:
        raise RuntimeError("Yahoo Finance returned no data.")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[["Open","High","Low","Close"]].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.sort_index().dropna()

    df["EMA19"] = df["Close"].ewm(
        span=EMA19, adjust=False, min_periods=EMA19
    ).mean()
    df["EMA200"] = df["Close"].ewm(
        span=EMA200, adjust=False, min_periods=EMA200
    ).mean()

    pc = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - pc).abs(),
        (df["Low"] - pc).abs()
    ], axis=1).max(axis=1)
    df["TR"] = tr

    # Candidate ATR definitions for reverse engineering.
    df["ATR_WILDER"] = tr.ewm(
        alpha=1/ATR14, adjust=False, min_periods=ATR14
    ).mean()
    df["ATR_SMA"] = tr.rolling(
        ATR14, min_periods=ATR14
    ).mean()
    df["ATR_WILDER_ADJUST"] = tr.ewm(
        alpha=1/ATR14, adjust=True, min_periods=ATR14
    ).mean()

    return df


def condition(df, i, name):
    r = df.iloc[i]

    if not (
        pd.notna(r["EMA19"]) and pd.notna(r["EMA200"])
        and r["Close"] > r["EMA200"]
        and r["EMA19"] > r["EMA200"]
    ):
        return False

    touch = r["Low"] <= r["EMA19"]

    if name == "TOUCH":
        return touch
    if name == "TOUCH_CLOSE_ABOVE":
        return touch and r["Close"] > r["EMA19"]
    if name == "OPEN_ABOVE_TOUCH":
        return touch and r["Open"] > r["EMA19"]
    if name == "BULLISH_TOUCH":
        return touch and r["Close"] > r["Open"]
    if name == "PREVIOUS_CLOSE_ABOVE":
        return i >= 1 and touch and df.iloc[i-1]["Close"] > df.iloc[i-1]["EMA19"]
    if name == "PREVIOUS_CLOSE_ABOVE_CURRENT_CLOSE":
        return (
            i >= 1 and touch
            and df.iloc[i-1]["Close"] > df.iloc[i-1]["EMA19"]
            and r["Close"] > df.iloc[i-1]["Close"]
        )
    if name == "SLOPE_POSITIVE":
        return i >= 1 and touch and r["EMA19"] > df.iloc[i-1]["EMA19"]
    if name == "SLOPE_POSITIVE_CLOSE_ABOVE":
        return (
            i >= 1 and touch
            and r["EMA19"] > df.iloc[i-1]["EMA19"]
            and r["Close"] > r["EMA19"]
        )
    raise ValueError(name)


def spacing(df, i, raw, pos, name):
    if name == "ALL":
        return True

    if name.startswith("ROW_GAP_"):
        n = int(name.rsplit("_",1)[1])
        return pos == 0 or raw[pos] - raw[pos-1] > n

    if name == "FIRST_EPISODE":
        return pos == 0 or raw[pos] - raw[pos-1] > 1

    if name == "LAST_EPISODE":
        return pos == len(raw)-1 or raw[pos+1] - raw[pos] > 1

    if name == "RESET_CLOSE_ABOVE":
        return i == 0 or df.iloc[i-1]["Close"] <= df.iloc[i-1]["EMA19"]

    if name == "RESET_LOW_ABOVE":
        return i == 0 or df.iloc[i-1]["Low"] > df.iloc[i-1]["EMA19"]

    if name == "RESET_TWO_CLOSES":
        return (
            i < 2
            or (
                df.iloc[i-1]["Close"] <= df.iloc[i-1]["EMA19"]
                and df.iloc[i-2]["Close"] <= df.iloc[i-2]["EMA19"]
            )
        )

    raise ValueError(name)


def stop_price(df, i, atr_col):
    if i < LOW_LOOKBACK + 1:
        return np.nan

    lows = df.iloc[i-LOW_LOOKBACK:i]["Low"]
    atr = df.iloc[i-1][atr_col]

    if pd.isna(atr):
        return np.nan

    return float(lows.min() - 0.5 * atr)


def resolve(df, entry_i, entry, stop):
    if not np.isfinite(stop) or stop >= entry:
        return "INVALID_SL", np.nan, None

    risk = entry - stop
    target = entry + RR * risk

    # Entry candle is excluded from TP/SL evaluation.
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


def run_config(df, cond, space, position, atr_col):
    raw = [
        i for i in range(len(df))
        if condition(df, i, cond)
    ]

    selected = [
        i for p, i in enumerate(raw)
        if spacing(df, i, raw, p, space)
    ]

    trades = []
    active_exit = None

    for i in selected:
        if position != "OVERLAP" and active_exit is not None:
            if i <= active_exit:
                continue

        entry = float(df.iloc[i]["Close"])
        stop = stop_price(df, i, atr_col)
        result, r_mult, exit_i = resolve(df, i, entry, stop)

        trades.append({
            "date": df.index[i],
            "year": int(df.index[i].year),
            "signal_i": i,
            "entry": entry,
            "stop": stop,
            "result": result,
            "R": r_mult,
            "exit_date": df.index[exit_i] if exit_i is not None else pd.NaT,
            "condition": cond,
            "spacing": space,
            "position_mode": position,
            "atr_method": atr_col
        })

        if position != "OVERLAP":
            active_exit = exit_i
            if result == "OPEN":
                active_exit = len(df) + 99999

    return pd.DataFrame(trades)


def summary(t):
    if t.empty:
        return {k:0 for k in [
            "signals","valid","invalid_sl","resolved",
            "wins","losses","ambiguous","open"
        ]} | {"win_rate":np.nan,"avg_R":np.nan,
              "total_R":0.0,"profit_factor":np.nan}

    wins = int((t.result=="WIN").sum())
    losses = int((t.result=="LOSS").sum())
    amb = int((t.result=="AMBIGUOUS").sum())
    op = int((t.result=="OPEN").sum())
    inv = int((t.result=="INVALID_SL").sum())
    resolved = wins + losses
    valid = len(t) - inv

    gp = float(t.loc[t.R > 0, "R"].sum())
    gl = abs(float(t.loc[t.R < 0, "R"].sum()))
    pf = gp/gl if gl else np.nan

    return {
        "signals":len(t), "valid":valid, "invalid_sl":inv,
        "resolved":resolved, "wins":wins, "losses":losses,
        "ambiguous":amb, "open":op,
        "win_rate":100*wins/resolved if resolved else np.nan,
        "avg_R":float(t.R.dropna().mean()) if t.R.notna().any() else np.nan,
        "total_R":float(t.R.dropna().sum()),
        "profit_factor":pf
    }


def yearly(t):
    if t.empty:
        return pd.DataFrame()
    rows = []
    for y, g in t.groupby("year"):
        s = summary(g)
        s["year"] = y
        rows.append(s)
    return pd.DataFrame(rows).sort_values("year")


def distance(s):
    d = sum(abs(s[k]-v) for k,v in REF.items())
    if np.isfinite(s["total_R"]):
        d += abs(s["total_R"]-71)*0.05
    if np.isfinite(s["profit_factor"]):
        d += abs(s["profit_factor"]-1.973)*2
    return d


def year_score(y):
    if y.empty:
        return -999999
    yy = y.set_index("year")
    exact = 0
    dist = 0
    for year, ref in REF_YEAR.items():
        if year not in yy.index:
            dist += sum(ref.values())
            continue
        row = yy.loc[year]
        same = True
        for k,v in ref.items():
            actual = int(row[k]) if k in row else 0
            dist += abs(actual-v)
            same &= actual == v
        exact += int(same)
    return exact*1000 - dist


def main():
    print("="*72)
    print("US500 EMA19 SIGNAL ENGINE")
    print("REVERSE ENGINEERING DIAGNOSTIC V3")
    print("="*72)

    df = load_data()
    print(f"Rows: {len(df)} | {df.index.min().date()} -> {df.index.max().date()}")

    conditions = [
        "TOUCH","TOUCH_CLOSE_ABOVE","OPEN_ABOVE_TOUCH",
        "BULLISH_TOUCH","PREVIOUS_CLOSE_ABOVE",
        "PREVIOUS_CLOSE_ABOVE_CURRENT_CLOSE","SLOPE_POSITIVE",
        "SLOPE_POSITIVE_CLOSE_ABOVE"
    ]
    spacings = [
        "ALL","ROW_GAP_1","ROW_GAP_2","ROW_GAP_3",
        "ROW_GAP_4","ROW_GAP_5","ROW_GAP_6","ROW_GAP_7",
        "ROW_GAP_8","FIRST_EPISODE","LAST_EPISODE",
        "RESET_CLOSE_ABOVE","RESET_LOW_ABOVE","RESET_TWO_CLOSES"
    ]
    positions = ["OVERLAP","ONE_TRADE","ONE_TRADE_EXIT_DAY"]
    atrs = ["ATR_WILDER","ATR_SMA","ATR_WILDER_ADJUST"]

    summaries = []
    yearly_rows = []
    signal_rows = []

    for atr, cond, space, pos in itertools.product(
        atrs, conditions, spacings, positions
    ):
        t = run_config(df, cond, space, pos, atr)
        s = summary(t)
        y = yearly(t)

        s.update({
            "atr_method":atr,
            "condition":cond,
            "spacing":space,
            "position_mode":pos,
            "reference_distance":distance(s),
            "yearly_match_score":year_score(y)
        })
        summaries.append(s)

        if not y.empty:
            y["atr_method"]=atr
            y["condition"]=cond
            y["spacing"]=space
            y["position_mode"]=pos
            yearly_rows.append(y)

        if not t.empty:
            signal_rows.append(t)

    sdf = pd.DataFrame(summaries)
    ydf = pd.concat(yearly_rows, ignore_index=True) if yearly_rows else pd.DataFrame()
    tdf = pd.concat(signal_rows, ignore_index=True) if signal_rows else pd.DataFrame()

    top = sdf.sort_values(
        ["yearly_match_score","reference_distance"],
        ascending=[False,True]
    ).head(20)

    print()
    print("="*72)
    print("TOP 20 V3 CONFIGURATIONS")
    print("="*72)
    cols = [
        "atr_method","condition","spacing","position_mode",
        "signals","valid","invalid_sl","resolved","wins",
        "losses","ambiguous","open","win_rate","avg_R",
        "total_R","profit_factor","yearly_match_score",
        "reference_distance"
    ]
    print(top[cols].to_string(index=False))

    best = top.iloc[0]
    print()
    print("="*72)
    print("REFERENCE MATCH ANALYSIS")
    print("="*72)
    print("REFERENCE:", REF)
    print("BEST CONFIGURATION:")
    for c in cols:
        print(f"{c:22s}: {best[c]}")

    by = ydf[
        (ydf.atr_method==best.atr_method) &
        (ydf.condition==best.condition) &
        (ydf.spacing==best.spacing) &
        (ydf.position_mode==best.position_mode)
    ] if not ydf.empty else pd.DataFrame()

    print()
    print("="*72)
    print("BEST YEARLY MATCH")
    print("="*72)
    if not by.empty:
        print(by[
            ["year","signals","valid","invalid_sl","resolved",
             "wins","losses","ambiguous","open","total_R"]
        ].to_string(index=False))
    else:
        print("No yearly rows.")

    print()
    print("="*72)
    print("OUTPUT FILES")
    print("="*72)

    sdf.to_csv("signal_diagnostics_v3_summary.csv", index=False)
    ydf.to_csv("signal_diagnostics_v3_yearly.csv", index=False)
    tdf.to_csv("signal_diagnostics_v3_signals.csv", index=False)

    print("signal_diagnostics_v3_summary.csv")
    print("signal_diagnostics_v3_yearly.csv")
    print("signal_diagnostics_v3_signals.csv")

    print()
    print("="*72)
    print("DIAGNOSTIC V3 COMPLETE")
    print("="*72)


if __name__ == "__main__":
    main()
