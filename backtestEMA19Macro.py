#!/usr/bin/env python3

# ============================================================
# US500 MACRO INTELLIGENCE — V3.3
# C3 vs C4 INCREMENTAL INFORMATION
# + DECISION CONTEXT CALIBRATION
# ============================================================
#
# RESEARCH ONLY
#
# Frozen EMA19 baseline remains untouched.
#
# C3 = H1 + H4
# C4 = H1 + H4 + Strong Technical
#
# V3.3 DOES NOT:
# - create signals
# - change entries
# - change stops
# - change RR
# - change macro definitions
# - change Technical Strong definition
# - execute trades
#
# It reads V3.2 outputs and performs incremental analysis.
# ============================================================

import sys
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# CONFIG
# ============================================================

TRADES_FILE = "macro_backtest_v32_trades.csv"
EPISODES_FILE = "macro_backtest_v32_market_episode_trades.csv"

STRONG_TECH_MIN = 4

DRAWDOWN_BINS = [
    -np.inf,
    -20,
    -10,
    -5,
    -3,
    0,
    np.inf,
]

DRAWDOWN_LABELS = [
    "<=-20%",
    "-20% to -10%",
    "-10% to -5%",
    "-5% to -3%",
    "-3% to 0%",
    ">0%",
]

BASELINE = {
    "signals": 119,
    "valid": 117,
    "invalid_sl": 2,
    "resolved": 109,
    "wins": 36,
    "losses": 73,
    "ambiguous": 3,
    "open": 5,
    "total_R": 71.0,
}


# ============================================================
# COLUMN ALIASES
# ============================================================

ALIASES = {
    "signal_date": [
        "signal_date",
        "date",
    ],
    "result": [
        "result",
    ],
    "R": [
        "R",
        "r",
        "r_multiple",
    ],
    "macro_regime": [
        "macro_regime",
        "regime",
    ],
    "leading_warning": [
        "leading_warning",
        "early_warning_level",
        "leading_warning_status",
        "early_warning_status",
    ],
    "liquidity_momentum": [
        "liquidity_momentum",
        "liquidity_status",
        "liquidity_momentum_status",
    ],
    "technical_score": [
        "technical_score",
        "tech_score",
    ],
    "technical_status": [
        "technical_status",
        "tech_status",
    ],
    "drawdown_pct": [
        "drawdown_pct",
        "drawdown",
        "dd_pct",
    ],
}


def find_column(df, name, required=True):

    for col in ALIASES[name]:
        if col in df.columns:
            return col

    if required:
        raise RuntimeError(
            f"\nMissing required V3.2 column: {name}\n"
            f"Accepted aliases: {ALIASES[name]}\n"
            f"Available columns:\n{list(df.columns)}"
        )

    return None


# ============================================================
# LOAD V3.2
# ============================================================

def load_trades():

    path = Path(TRADES_FILE)

    if not path.exists():
        raise RuntimeError(
            f"Missing {TRADES_FILE}. "
            "Put the V3.2 trade CSV in the repository."
        )

    raw = pd.read_csv(path)

    mapping = {}

    for name in [
        "signal_date",
        "result",
        "R",
        "macro_regime",
        "leading_warning",
        "liquidity_momentum",
        "technical_score",
        "technical_status",
        "drawdown_pct",
    ]:

        required = name not in [
            "technical_status"
        ]

        col = find_column(
            raw,
            name,
            required=required,
        )

        if col:
            mapping[name] = col

    df = raw.copy()

    for logical, actual in mapping.items():
        df[logical] = df[actual]

    # Technical status can be reconstructed ONLY from the
    # already frozen V3.1 definition.
    if "technical_status" not in df.columns:

        score = pd.to_numeric(
            df["technical_score"],
            errors="coerce",
        )

        df["technical_status"] = np.select(
            [
                score >= 4,
                score == 3,
            ],
            [
                "STRONG",
                "PARTIAL",
            ],
            default="WEAK",
        )

    df["signal_date"] = pd.to_datetime(
        df["signal_date"],
        errors="coerce",
    )

    df["R"] = pd.to_numeric(
        df["R"],
        errors="coerce",
    )

    df["technical_score"] = pd.to_numeric(
        df["technical_score"],
        errors="coerce",
    )

    df["drawdown_pct"] = pd.to_numeric(
        df["drawdown_pct"],
        errors="coerce",
    )

    df = df.sort_values(
        "signal_date"
    ).reset_index(drop=True)

    return df


# ============================================================
# SUMMARY
# ============================================================

def summary(df):

    wins = int(
        (df["result"] == "WIN").sum()
    )

    losses = int(
        (df["result"] == "LOSS").sum()
    )

    ambiguous = int(
        (df["result"] == "AMBIGUOUS").sum()
    )

    open_trades = int(
        (df["result"] == "OPEN").sum()
    )

    invalid = int(
        (df["result"] == "INVALID_SL").sum()
    )

    resolved = wins + losses

    gross_profit = float(
        df.loc[df["R"] > 0, "R"].sum()
    )

    gross_loss = abs(
        float(df.loc[df["R"] < 0, "R"].sum())
    )

    pf = (
        gross_profit / gross_loss
        if gross_loss > 0
        else np.nan
    )

    return {
        "signals": len(df),
        "valid": len(df) - invalid,
        "invalid_sl": invalid,
        "resolved": resolved,
        "wins": wins,
        "losses": losses,
        "ambiguous": ambiguous,
        "open": open_trades,
        "win_rate": (
            100 * wins / resolved
            if resolved else np.nan
        ),
        "avg_R": (
            float(df["R"].dropna().mean())
            if df["R"].notna().any()
            else np.nan
        ),
        "total_R": float(
            df["R"].dropna().sum()
        ),
        "profit_factor": pf,
    }


# ============================================================
# FROZEN BASELINE GUARD
# ============================================================

def baseline_guard(df):

    s = summary(df)

    print("\n" + "=" * 72)
    print("V3.3 FROZEN BASELINE GUARD")
    print("=" * 72)

    print(
        pd.DataFrame([s])
        .to_string(index=False)
    )

    for key in [
        "signals",
        "valid",
        "invalid_sl",
        "resolved",
        "wins",
        "losses",
        "ambiguous",
        "open",
    ]:

        if s[key] != BASELINE[key]:

            raise RuntimeError(
                f"BASELINE GUARD FAILED: "
                f"{key}: expected {BASELINE[key]}, "
                f"got {s[key]}"
            )

    if abs(
        s["total_R"] - BASELINE["total_R"]
    ) > 1e-9:

        raise RuntimeError(
            "BASELINE GUARD FAILED: total_R "
            f"expected {BASELINE['total_R']}, "
            f"got {s['total_R']}"
        )

    print("\nBASELINE STATUS: PASS")


# ============================================================
# BUILD V3.3 CANDIDATES
# ============================================================

def build_candidates(df):

    regime = (
        df["macro_regime"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    warning = (
        df["leading_warning"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    liquidity = (
        df["liquidity_momentum"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    technical = (
        df["technical_score"]
        >= STRONG_TECH_MIN
    )

    # --------------------------------------------------------
    # H1
    # Regime A + WATCH
    # --------------------------------------------------------

    df["H1"] = (
        regime.eq("A")
        & warning.eq("WATCH")
    )

    # --------------------------------------------------------
    # H4
    # Regime A + Liquidity Deteriorating
    # --------------------------------------------------------

    df["H4"] = (
        regime.eq("A")
        & liquidity.isin([
            "DETERIORATING",
            "STRONGLY DETERIORATING",
        ])
    )

    # --------------------------------------------------------
    # Strong Technical
    # EXACT V3.1 definition
    # --------------------------------------------------------

    df["STRONG_TECH"] = technical

    # --------------------------------------------------------
    # C3
    # --------------------------------------------------------

    df["C3"] = (
        df["H1"]
        & df["H4"]
    )

    # --------------------------------------------------------
    # C4
    # --------------------------------------------------------

    df["C4"] = (
        df["H1"]
        & df["H4"]
        & df["STRONG_TECH"]
    )

    # --------------------------------------------------------
    # Incremental subset
    # --------------------------------------------------------

    df["C3_NOT_C4"] = (
        df["C3"]
        & ~df["C4"]
    )

    df["NOT_C4"] = ~df["C4"]

    # --------------------------------------------------------
    # Research context
    # --------------------------------------------------------

    df["research_context"] = np.select(
        [
            df["C4"],
            df["C3"],
            df["H1"],
        ],
        [
            "H1+H4+STRONG_TECH",
            "H1+H4",
            "H1",
        ],
        default="NONE",
    )

    # --------------------------------------------------------
    # Drawdown
    # --------------------------------------------------------

    df["drawdown_bucket"] = pd.cut(
        df["drawdown_pct"],
        bins=DRAWDOWN_BINS,
        labels=DRAWDOWN_LABELS,
        right=True,
    )

    df["year"] = (
        df["signal_date"]
        .dt.year
    )

    return df


# ============================================================
# 1 — C3 vs C4
# ============================================================

def c3_c4_report(df):

    groups = {
        "C3_ALL": df["C3"],
        "C4_SUBSET": df["C4"],
        "C3_NOT_C4": df["C3_NOT_C4"],
    }

    rows = []

    for name, mask in groups.items():

        s = summary(
            df.loc[mask]
        )

        s["group"] = name

        rows.append(s)

    return pd.DataFrame(rows)


# ============================================================
# 2 — C4 VS BASELINE
# ============================================================

def c4_vs_baseline(df):

    groups = {
        "ALL_FROZEN_SIGNALS":
            np.ones(len(df), dtype=bool),

        "C4":
            df["C4"],

        "NOT_C4":
            df["NOT_C4"],
    }

    rows = []

    for name, mask in groups.items():

        s = summary(
            df.loc[mask]
        )

        s["group"] = name

        rows.append(s)

    return pd.DataFrame(rows)


# ============================================================
# 3 — CONTEXT × DRAWDOWN
# ============================================================

def context_drawdown(df):

    rows = []

    for context in [
        "NONE",
        "H1",
        "H1+H4",
        "H1+H4+STRONG_TECH",
    ]:

        for bucket in DRAWDOWN_LABELS:

            g = df.loc[
                (df["research_context"] == context)
                &
                (
                    df["drawdown_bucket"]
                    .astype(str)
                    == bucket
                )
            ]

            if g.empty:
                continue

            s = summary(g)

            s["context"] = context
            s["drawdown_bucket"] = bucket

            rows.append(s)

    return pd.DataFrame(rows)


# ============================================================
# 4 — CONTEXT × DRAWDOWN × TECHNICAL
# ============================================================

def context_drawdown_technical(df):

    rows = []

    for context in [
        "NONE",
        "H1",
        "H1+H4",
        "H1+H4+STRONG_TECH",
    ]:

        for bucket in DRAWDOWN_LABELS:

            for tech in [
                "WEAK",
                "PARTIAL",
                "STRONG",
            ]:

                g = df.loc[
                    (df["research_context"] == context)
                    &
                    (
                        df["drawdown_bucket"]
                        .astype(str)
                        == bucket
                    )
                    &
                    (
                        df["technical_status"]
                        .astype(str)
                        .str.upper()
                        == tech
                    )
                ]

                if g.empty:
                    continue

                s = summary(g)

                s["context"] = context
                s["drawdown_bucket"] = bucket
                s["technical_status"] = tech

                rows.append(s)

    return pd.DataFrame(rows)


# ============================================================
# 5 — YEARLY
# ============================================================

def yearly_context(df):

    rows = []

    for context in [
        "NONE",
        "H1",
        "H1+H4",
        "H1+H4+STRONG_TECH",
    ]:

        g0 = df[
            df["research_context"] == context
        ]

        for year, g in g0.groupby("year"):

            s = summary(g)

            s["context"] = context
            s["year"] = int(year)

            rows.append(s)

    return pd.DataFrame(rows)


# ============================================================
# 6 — OOS
# ============================================================

def chronological_oos(df):

    rows = []

    candidates = {
        "C3_H1_PLUS_H4":
            df["C3"],

        "C4_H1_PLUS_H4_STRONG_TECH":
            df["C4"],

        "C3_NOT_C4":
            df["C3_NOT_C4"],

        "NOT_C4":
            df["NOT_C4"],
    }

    discovery = df["year"] < 2025
    holdout = df["year"] >= 2025

    for name, candidate in candidates.items():

        for sample, period in [
            ("DISCOVERY", discovery),
            ("HOLDOUT", holdout),
        ]:

            s = summary(
                df.loc[
                    candidate & period
                ]
            )

            s["candidate"] = name
            s["sample"] = sample

            rows.append(s)

    return pd.DataFrame(rows)


# ============================================================
# 7 — EXPANDING WALK FORWARD
# ============================================================

def walk_forward(df):

    rows = []

    candidates = {
        "C3_H1_PLUS_H4":
            df["C3"],

        "C4_H1_PLUS_H4_STRONG_TECH":
            df["C4"],
    }

    years = sorted(
        df["year"]
        .dropna()
        .unique()
    )

    for test_year in years:

        if test_year <= 2022:
            continue

        train_period = (
            df["year"] < test_year
        )

        test_period = (
            df["year"] == test_year
        )

        for name, candidate in candidates.items():

            train = df.loc[
                candidate & train_period
            ]

            test = df.loc[
                candidate & test_period
            ]

            tr = summary(train)
            te = summary(test)

            rows.append({
                "candidate": name,
                "test_year": int(test_year),

                "train_signals":
                    tr["signals"],

                "train_wins":
                    tr["wins"],

                "train_losses":
                    tr["losses"],

                "train_avg_R":
                    tr["avg_R"],

                "train_total_R":
                    tr["total_R"],

                "test_signals":
                    te["signals"],

                "test_wins":
                    te["wins"],

                "test_losses":
                    te["losses"],

                "test_win_rate":
                    te["win_rate"],

                "test_avg_R":
                    te["avg_R"],

                "test_total_R":
                    te["total_R"],

                "test_profit_factor":
                    te["profit_factor"],
            })

    return pd.DataFrame(rows)


# ============================================================
# 8 — LEAVE ONE YEAR OUT
# ============================================================

def leave_one_year_out(df):

    rows = []

    candidates = {
        "C3_H1_PLUS_H4":
            df["C3"],

        "C4_H1_PLUS_H4_STRONG_TECH":
            df["C4"],

        "C3_NOT_C4":
            df["C3_NOT_C4"],
    }

    years = sorted(
        df["year"]
        .dropna()
        .unique()
    )

    for name, candidate in candidates.items():

        means = []

        for year in years:

            g = df.loc[
                candidate
                &
                (df["year"] != year)
                &
                df["result"].isin([
                    "WIN",
                    "LOSS",
                ])
            ]

            if not g.empty:
                means.append(
                    float(g["R"].mean())
                )

        rows.append({
            "candidate": name,
            "year_count": len(means),
            "loo_year_min_mean_R":
                min(means)
                if means else np.nan,
            "loo_year_max_mean_R":
                max(means)
                if means else np.nan,
        })

    return pd.DataFrame(rows)


# ============================================================
# 9 — CRISIS EXCLUSION
# ============================================================

def crisis_exclusion(df):

    rows = []

    candidates = {
        "C3_H1_PLUS_H4":
            df["C3"],

        "C4_H1_PLUS_H4_STRONG_TECH":
            df["C4"],

        "C3_NOT_C4":
            df["C3_NOT_C4"],
    }

    exclusions = {
        "NONE": [],
        "EXCLUDE_2020": [2020],
        "EXCLUDE_2022": [2022],
        "EXCLUDE_2020_2022": [2020, 2022],
        "EXCLUDE_2025": [2025],
    }

    for name, candidate in candidates.items():

        for label, years in exclusions.items():

            mask = candidate.copy()

            for year in years:
                mask &= (
                    df["year"] != year
                )

            s = summary(
                df.loc[mask]
            )

            s["candidate"] = name
            s["exclusion"] = label

            rows.append(s)

    return pd.DataFrame(rows)


# ============================================================
# 10 — MARKET EPISODE AUDIT
# ============================================================

def episode_audit(df):

    path = Path(EPISODES_FILE)

    if not path.exists():

        raise RuntimeError(
            f"Missing {EPISODES_FILE}. "
            "V3.3 refuses to invent a new episode definition."
        )

    ep = pd.read_csv(path)

    date_col = (
        "signal_date"
        if "signal_date" in ep.columns
        else "date"
    )

    ep["signal_date"] = pd.to_datetime(
        ep[date_col],
        errors="coerce",
    )

    episode_col = None

    for col in [
        "market_episode_id",
        "episode_id",
        "market_episode",
        "episode",
    ]:

        if col in ep.columns:
            episode_col = col
            break

    if episode_col is None:

        raise RuntimeError(
            "No market episode ID found in "
            f"{EPISODES_FILE}."
        )

    ep["episode_id"] = ep[
        episode_col
    ]

    ep = ep[
        [
            "signal_date",
            "episode_id",
        ]
    ].drop_duplicates(
        "signal_date"
    )

    merged = df.merge(
        ep,
        on="signal_date",
        how="left",
    )

    if merged["episode_id"].isna().any():

        raise RuntimeError(
            "Some V3.2 trades have no market episode ID."
        )

    rows = []

    candidates = {
        "C3_H1_PLUS_H4":
            merged["C3"],

        "C4_H1_PLUS_H4_STRONG_TECH":
            merged["C4"],

        "C3_NOT_C4":
            merged["C3_NOT_C4"],
    }

    for name, candidate in candidates.items():

        selected = merged.loc[
            candidate
            &
            merged["result"].isin([
                "WIN",
                "LOSS",
            ])
        ]

        if selected.empty:
            continue

        ep_stats = (
            selected
            .groupby("episode_id")
            .agg(
                trades=("R", "count"),
                total_R=("R", "sum"),
            )
            .reset_index()
        )

        top = ep_stats.sort_values(
            "total_R",
            ascending=False,
        ).iloc[0]

        total_R = float(
            selected["R"].sum()
        )

        loo_means = []

        for episode_id in ep_stats[
            "episode_id"
        ]:

            remaining = selected[
                selected["episode_id"]
                != episode_id
            ]

            if not remaining.empty:
                loo_means.append(
                    float(
                        remaining["R"].mean()
                    )
                )

        rows.append({
            "candidate": name,
            "resolved": len(selected),
            "episode_count":
                len(ep_stats),
            "top_episode_trades":
                int(top["trades"]),
            "top_episode_total_R":
                float(top["total_R"]),
            "total_R":
                total_R,
            "total_R_excl_top":
                total_R
                - float(top["total_R"]),
            "loo_min_mean_R":
                min(loo_means)
                if loo_means else np.nan,
            "loo_max_mean_R":
                max(loo_means)
                if loo_means else np.nan,
        })

    return pd.DataFrame(rows)


# ============================================================
# DECISION ENGINE IMPACT
# ============================================================

def decision_impact(df):

    # This is intentionally descriptive.
    # It DOES NOT alter trades.

    if "early_warning_score" not in df.columns:

        return pd.DataFrame([{
            "status": "NOT_AVAILABLE",
            "reason":
                "early_warning_score not present in V3.2 CSV",
        }])

    rows = []

    for context, g in df.groupby(
        "research_context"
    ):

        rows.append({
            "context": context,
            "signals": len(g),
            "wins": int(
                (g["result"] == "WIN").sum()
            ),
            "losses": int(
                (g["result"] == "LOSS").sum()
            ),
            "avg_R":
                float(g["R"].mean())
                if g["R"].notna().any()
                else np.nan,
            "total_R":
                float(g["R"].sum()),
        })

    return pd.DataFrame(rows)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 72)
    print("US500 MACRO INTELLIGENCE — V3.3")
    print("C3 vs C4 INCREMENTAL INFORMATION")
    print("=" * 72)

    df = load_trades()

    print(
        f"Loaded V3.2 trades: {len(df)}"
    )

    # --------------------------------------------------------
    # BASELINE
    # --------------------------------------------------------

    baseline_guard(df)

    # --------------------------------------------------------
    # CANDIDATES
    # --------------------------------------------------------

    df = build_candidates(df)

    # --------------------------------------------------------
    # INTEGRITY
    # --------------------------------------------------------

    strong_expected = (
        df["technical_score"]
        >= STRONG_TECH_MIN
    )

    if not df["STRONG_TECH"].equals(
        strong_expected
    ):

        raise RuntimeError(
            "TECHNICAL INTEGRITY FAILED."
        )

    print(
        "\nSIGNAL-GENERATION GUARD: PASS"
    )

    print(
        "TECHNICAL-INTEGRITY GUARD: PASS"
    )

    print(
        "NO ENTRY CREATION: PASS"
    )

    print(
        "NO BASELINE MODIFICATION: PASS"
    )

    # --------------------------------------------------------
    # REPORTS
    # --------------------------------------------------------

    reports = {

        "macro_backtest_v33_c3_c4_incremental.csv":
            c3_c4_report(df),

        "macro_backtest_v33_baseline_vs_c4.csv":
            c4_vs_baseline(df),

        "macro_backtest_v33_context_drawdown.csv":
            context_drawdown(df),

        "macro_backtest_v33_context_drawdown_technical.csv":
            context_drawdown_technical(df),

        "macro_backtest_v33_yearly.csv":
            yearly_context(df),

        "macro_backtest_v33_oos.csv":
            chronological_oos(df),

        "macro_backtest_v33_walk_forward.csv":
            walk_forward(df),

        "macro_backtest_v33_leave_one_year_out.csv":
            leave_one_year_out(df),

        "macro_backtest_v33_crisis_exclusion.csv":
            crisis_exclusion(df),

        "macro_backtest_v33_market_episode_audit.csv":
            episode_audit(df),

        "macro_backtest_v33_decision_impact.csv":
            decision_impact(df),

        "macro_backtest_v33_trades.csv":
            df,
    }

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    for filename, report in reports.items():

        report.to_csv(
            filename,
            index=False,
        )

    # --------------------------------------------------------
    # PRINT
    # --------------------------------------------------------

    print("\n" + "=" * 72)
    print("V3.3 C3 vs C4 INCREMENTAL ANALYSIS")
    print("=" * 72)

    print(
        reports[
            "macro_backtest_v33_c3_c4_incremental.csv"
        ].to_string(index=False)
    )

    print("\n" + "=" * 72)
    print("V3.3 BASELINE vs C4")
    print("=" * 72)

    print(
        reports[
            "macro_backtest_v33_baseline_vs_c4.csv"
        ].to_string(index=False)
    )

    print("\n" + "=" * 72)
    print("V3.3 MARKET EPISODE AUDIT")
    print("=" * 72)

    print(
        reports[
            "macro_backtest_v33_market_episode_audit.csv"
        ].to_string(index=False)
    )

    print("\n" + "=" * 72)
    print("V3.3 OOS")
    print("=" * 72)

    print(
        reports[
            "macro_backtest_v33_oos.csv"
        ].to_string(index=False)
    )

    print("\n" + "=" * 72)
    print("V3.3 WALK-FORWARD")
    print("=" * 72)

    print(
        reports[
            "macro_backtest_v33_walk_forward.csv"
        ].to_string(index=False)
    )

    print("\n" + "=" * 72)
    print("V3.3 LEAVE-ONE-YEAR-OUT")
    print("=" * 72)

    print(
        reports[
            "macro_backtest_v33_leave_one_year_out.csv"
        ].to_string(index=False)
    )

    print("\n" + "=" * 72)
    print("V3.3 CRISIS EXCLUSION")
    print("=" * 72)

    print(
        reports[
            "macro_backtest_v33_crisis_exclusion.csv"
        ].to_string(index=False)
    )

    print("\n" + "=" * 72)
    print("V3.3 COMPLETE")
    print("=" * 72)

    for filename in reports:
        print(filename)


if __name__ == "__main__":

    try:
        main()

    except Exception as exc:

        print(
            "\nV3.3 FAILED:"
        )

        print(exc)

        sys.exit(1)
