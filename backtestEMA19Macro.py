
# ============================================================
# US500 MACRO INTELLIGENCE — V3.8
# STRICT OOS / WALK-FORWARD ABLATION VALIDATION
# ============================================================
# PURPOSE
# -------
# V3.8 validates the V3.7 Decision-Engine ablation contexts
# OUT OF SAMPLE without changing the frozen EMA19 baseline.
#
# AUTHORITATIVE INPUT:
#   V3.7 integrated pipeline
#
# FIXED CONTEXTS:
#   H1_ONLY_CONTEXT
#   C3_REDUNDANT_SUPPORT
#   H4_ONLY_CONTEXT
#   A_WATCH_CONTEXT
#
# IMPORTANT:
#   - No new entry is created.
#   - No stop, target, RR, sizing or R outcome is changed.
#   - No threshold is optimized inside OOS.
#   - V3.7 classifications are frozen before OOS evaluation.
#   - OOS is evaluated chronologically from 2025-01-01 onward.
#
# Validation philosophy:
# strict chronological holdout + expanding walk-forward.
# This is intended to detect whether the in-sample contextual
# information survives outside the discovery sample.
# ============================================================

import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
SOURCE_FILE = BASE_DIR / "backtestEMA19Macro_V3_2_DECISION_ENGINE_ROBUSTNESS(4).py"

OOS_START = pd.Timestamp("2025-01-01")
WALK_YEARS = [2023, 2024, 2025, 2026]


def load_authoritative_v37():
    """Load the frozen V3.7 producer without executing its main block."""
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(
            f"Authoritative V3.7 producer not found: {SOURCE_FILE}"
        )

    spec = importlib.util.spec_from_file_location(
        "us500_macro_v37_authoritative",
        SOURCE_FILE,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load authoritative V3.7 producer.")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def metric_summary(g):
    """Pure reporting function; does not modify trade outcomes."""
    g = g.copy()

    wins = int((g["result"] == "WIN").sum())
    losses = int((g["result"] == "LOSS").sum())
    invalid = int((g["result"] == "INVALID_SL").sum())
    ambiguous = int((g["result"] == "AMBIGUOUS").sum())
    open_trades = int((g["result"] == "OPEN").sum())
    resolved = wins + losses

    r = pd.to_numeric(g["R"], errors="coerce")
    gross_profit = float(r[r > 0].sum())
    gross_loss = abs(float(r[r < 0].sum()))

    return {
        "signals": len(g),
        "valid": len(g) - invalid,
        "invalid_sl": invalid,
        "resolved": resolved,
        "wins": wins,
        "losses": losses,
        "ambiguous": ambiguous,
        "open": open_trades,
        "win_rate": 100.0 * wins / resolved if resolved else np.nan,
        "avg_R": float(r.dropna().mean()) if r.notna().any() else np.nan,
        "total_R": float(r.dropna().sum()) if r.notna().any() else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else np.nan,
    }


def add_v37_labels(module, trades):
    """
    Reproduce the frozen V3.7 counterfactual labels and interaction
    classes. This is classification only.
    """
    df = trades.copy()

    required = [
        "macro_regime",
        "leading_warning",
        "liquidity_momentum",
        "technical_score",
        "technical_status",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError(f"V3.8 missing required V3.7 columns: {missing}")

    comparison = module.v36_build_decision_comparison(df)
    comparison = module.v37_corrected_interaction_classification(comparison)

    return comparison


def frozen_baseline_guard(module, trades):
    """
    Re-run the frozen baseline independently through the authoritative
    producer and require exact signal/result/R integrity.
    """
    baseline = module.build_baseline_trades(
        module.load_market()
    )

    expected = {
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
    s = metric_summary(baseline)

    for k, v in expected.items():
        if k == "total_R":
            if not np.isclose(s[k], v, atol=1e-12):
                raise RuntimeError(
                    f"V3.8 FROZEN BASELINE GUARD FAILED: {k}={s[k]} != {v}"
                )
        elif s[k] != v:
            raise RuntimeError(
                f"V3.8 FROZEN BASELINE GUARD FAILED: {k}={s[k]} != {v}"
            )

    if not np.isclose(s["profit_factor"], 1.9726027397260273, atol=1e-12):
        raise RuntimeError("V3.8 FROZEN BASELINE GUARD FAILED: PF mismatch.")

    left_dates = pd.to_datetime(baseline["signal_date"]).reset_index(drop=True)
    right_dates = pd.to_datetime(trades["signal_date"]).reset_index(drop=True)

    if len(left_dates) != len(right_dates) or not left_dates.equals(right_dates):
        raise RuntimeError(
            "V3.8 SIGNAL DATE GUARD FAILED: V3.7 producer changed the signal set."
        )

    for col in ["result", "R"]:
        left = baseline[col].reset_index(drop=True)
        right = trades[col].reset_index(drop=True)
        if col == "R":
            if not np.allclose(
                pd.to_numeric(left, errors="coerce"),
                pd.to_numeric(right, errors="coerce"),
                equal_nan=True,
            ):
                raise RuntimeError(
                    f"V3.8 RESULT/R GUARD FAILED for {col}."
                )
        elif not left.astype(object).equals(right.astype(object)):
            raise RuntimeError(
                f"V3.8 RESULT GUARD FAILED for {col}."
            )

    print("V3.8 FROZEN SIGNAL/RESULT/R GUARD: PASS")
    return baseline


def decision_reproduction_guard(module, trades):
    """
    Confirm that V3.7 BASE labels are exactly the authoritative
    V3.0/V3.6 decision labels before any OOS analysis.
    """
    actual = trades["V36_DECISION_BASE"].reset_index(drop=True).astype(object)
    expected = pd.Series(
        [module.v30_decision_layer(row)[0] for _, row in trades.iterrows()],
        index=actual.index,
        dtype=object,
    )

    if not np.array_equal(
        actual.to_numpy(dtype=object),
        expected.to_numpy(dtype=object),
    ):
        raise RuntimeError(
            "V3.8 BASE DECISION REPRODUCTION GUARD FAILED."
        )

    print("V3.8 BASE DECISION REPRODUCTION GUARD: PASS")


def context_masks(df):
    """
    Frozen V3.7 context definitions.
    No thresholds are learned or optimized here.
    """
    return {
        "H1_ONLY_CONTEXT": df["V37_INTERACTION_CLASS"].eq("H1_ONLY_CONTEXT"),
        "C3_REDUNDANT_SUPPORT": df["V37_INTERACTION_CLASS"].eq(
            "C3_REDUNDANT_SUPPORT"
        ),
        "H4_ONLY_CONTEXT": df["V37_INTERACTION_CLASS"].eq("H4_ONLY_CONTEXT"),
        "A_WATCH_CONTEXT": (
            df["macro_regime"].eq("A")
            & df["leading_warning"].eq("WATCH")
        ),
    }


def counterfactual_changed_column(df, mode):
    mapping = {
        "H1_ONLY_CONTEXT": "V36_H1_ONLY_CHANGED",
        "C3_REDUNDANT_SUPPORT": "V36_NO_H1_H4_CHANGED",
        "H4_ONLY_CONTEXT": "V36_H4_ONLY_CHANGED",
        "A_WATCH_CONTEXT": "V36_NO_H1_H4_CHANGED",
    }
    return mapping[mode]


def audit_context(df, mode, start=None, end=None):
    """
    Evaluate a pre-specified context over a chronological slice.
    The trade result/R remains the frozen baseline outcome.
    """
    x = df.copy()

    if start is not None:
        x = x[x["signal_date"] >= pd.Timestamp(start)]
    if end is not None:
        x = x[x["signal_date"] < pd.Timestamp(end)]

    masks = context_masks(x)
    context = masks[mode]

    selected = x.loc[context].copy()
    changed_col = counterfactual_changed_column(x, mode)

    # For A_WATCH, changed=True means removing both H1/H4 changes the BASE
    # decision. For interaction classes, the class itself is already frozen.
    selected["OOS_DECISION_SENSITIVE"] = selected[changed_col].astype(bool)

    all_stats = metric_summary(selected)
    changed = selected[selected["OOS_DECISION_SENSITIVE"]].copy()
    unchanged = selected[~selected["OOS_DECISION_SENSITIVE"]].copy()

    changed_stats = metric_summary(changed)
    unchanged_stats = metric_summary(unchanged)

    base_decisions = selected["V36_DECISION_BASE"].astype(str)
    if mode in ("H1_ONLY_CONTEXT", "H4_ONLY_CONTEXT"):
        cf_col = (
            "V36_DECISION_H1_ONLY"
            if mode == "H1_ONLY_CONTEXT"
            else "V36_DECISION_H4_ONLY"
        )
    else:
        cf_col = "V36_DECISION_NO_H1_H4"

    cf_decisions = selected[cf_col].astype(str)
    transitions = int((base_decisions != cf_decisions).sum())

    row = {
        "context": mode,
        "start": selected["signal_date"].min() if len(selected) else pd.NaT,
        "end": selected["signal_date"].max() if len(selected) else pd.NaT,
        "signals": all_stats["signals"],
        "resolved": all_stats["resolved"],
        "wins": all_stats["wins"],
        "losses": all_stats["losses"],
        "win_rate": all_stats["win_rate"],
        "avg_R": all_stats["avg_R"],
        "total_R": all_stats["total_R"],
        "profit_factor": all_stats["profit_factor"],
        "decision_changed": transitions,
        "decision_change_pct": (
            100.0 * transitions / len(selected) if len(selected) else np.nan
        ),
        "changed_resolved": changed_stats["resolved"],
        "changed_wins": changed_stats["wins"],
        "changed_losses": changed_stats["losses"],
        "changed_win_rate": changed_stats["win_rate"],
        "changed_avg_R": changed_stats["avg_R"],
        "changed_total_R": changed_stats["total_R"],
        "changed_profit_factor": changed_stats["profit_factor"],
        "unchanged_resolved": unchanged_stats["resolved"],
        "unchanged_wins": unchanged_stats["wins"],
        "unchanged_losses": unchanged_stats["losses"],
        "unchanged_avg_R": unchanged_stats["avg_R"],
        "unchanged_total_R": unchanged_stats["total_R"],
        "unchanged_profit_factor": unchanged_stats["profit_factor"],
    }
    return row


def strict_oos(module, df):
    """
    One-time frozen holdout:
      discovery: < 2025-01-01
      holdout:   >= 2025-01-01

    No context definition is learned from the holdout.
    """
    rows = []

    contexts = list(context_masks(df).keys())

    for mode in contexts:
        rows.append({
            "sample": "DISCOVERY",
            **audit_context(
                df, mode,
                start=None,
                end=OOS_START,
            ),
        })
        rows.append({
            "sample": "HOLDOUT_OOS",
            **audit_context(
                df, mode,
                start=OOS_START,
                end=None,
            ),
        })

    return pd.DataFrame(rows)


def expanding_walk_forward(df):
    """
    Pure chronology audit.

    Each year is evaluated as the next chronological test segment.
    No parameter optimization occurs. The purpose is to see whether
    frozen V3.7 contexts remain decision-relevant across time.
    """
    rows = []

    contexts = list(context_masks(df).keys())

    for year in WALK_YEARS:
        start = pd.Timestamp(f"{year}-01-01")
        end = pd.Timestamp(f"{year + 1}-01-01")

        for mode in contexts:
            row = audit_context(df, mode, start=start, end=end)
            row["test_year"] = year
            rows.append(row)

    return pd.DataFrame(rows)


def transition_audit(df):
    """
    Counts exact decision transitions in the OOS holdout.
    This is descriptive, not a trading rule.
    """
    oos = df[df["signal_date"] >= OOS_START].copy()

    specs = [
        ("H1_ONLY_CONTEXT", "V36_DECISION_H1_ONLY"),
        ("C3_REDUNDANT_SUPPORT", "V36_DECISION_NO_H1_H4"),
        ("H4_ONLY_CONTEXT", "V36_DECISION_H4_ONLY"),
        ("A_WATCH_CONTEXT", "V36_DECISION_NO_H1_H4"),
    ]

    rows = []
    for mode, cf_col in specs:
        m = context_masks(oos)[mode]
        x = oos.loc[m].copy()

        if x.empty:
            continue

        pairs = (
            x["V36_DECISION_BASE"].astype(str)
            + " -> "
            + x[cf_col].astype(str)
        )

        for transition, count in pairs.value_counts().items():
            rows.append({
                "context": mode,
                "transition": transition,
                "signals": int(count),
            })

    return pd.DataFrame(rows)


def integrity_guards(module, baseline, trades, df, oos):
    # No entry creation: V3.8 must have exactly the same signal dates.
    if len(baseline) != len(trades) or len(trades) != len(df):
        raise RuntimeError("V3.8 NO ENTRY CREATION GUARD FAILED: row count changed.")

    bdates = pd.to_datetime(baseline["signal_date"]).reset_index(drop=True)
    tdates = pd.to_datetime(trades["signal_date"]).reset_index(drop=True)
    ddates = pd.to_datetime(df["signal_date"]).reset_index(drop=True)

    if not bdates.equals(tdates) or not bdates.equals(ddates):
        raise RuntimeError("V3.8 NO ENTRY CREATION GUARD FAILED: dates changed.")

    # OOS chronology guard.
    if len(oos):
        if oos["signal_date"].min() < OOS_START:
            raise RuntimeError("V3.8 OOS CHRONOLOGY GUARD FAILED.")
    print("V3.8 NO ENTRY CREATION: PASS")
    print("V3.8 NO BASELINE MODIFICATION: PASS")
    print("V3.8 OOS CHRONOLOGY GUARD: PASS")


def print_table(title, table):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)
    if table.empty:
        print("NO ROWS")
    else:
        print(table.to_string(index=False))


def main():
    print("\n" + "=" * 78)
    print("US500 MACRO INTELLIGENCE — V3.8")
    print("STRICT OOS / WALK-FORWARD ABLATION VALIDATION")
    print("=" * 78)

    module = load_authoritative_v37()

    # Rebuild the exact authoritative pipeline in memory.
    market = module.load_market()
    market["SMA200"] = market["Close"].rolling(200, min_periods=200).mean()

    baseline = module.build_baseline_trades(market)
    if not module.print_baseline_check(baseline):
        raise RuntimeError("V3.8 STOPPED: frozen baseline failed.")

    fred = module.load_fred()
    trades = module.attach_macro(baseline, fred)
    trades = module.add_drawdown(trades, market)
    trades = module.add_zones(trades)
    trades = module.add_confluence_flags(trades)
    trades = module.add_v31_technical_confirmation(trades, market)

    # These are the exact frozen V3.2 H1/H4 definitions.
    trades["H1_FLAG"] = (
        (trades["macro_regime"] == "A")
        & (trades["leading_warning"] == "WATCH")
    )
    trades["H4_FLAG"] = (
        (trades["macro_regime"] == "A")
        & (trades["liquidity_momentum"] == "DETERIORATING")
    )

    decision_df = add_v37_labels(module, trades)

    # Guards before validation.
    frozen_baseline_guard(module, decision_df)
    decision_reproduction_guard(module, decision_df)

    # V3.7 classification integrity.
    required_v37 = [
        "V36_DECISION_BASE",
        "V36_DECISION_NO_H1_H4",
        "V36_DECISION_H1_ONLY",
        "V36_DECISION_H4_ONLY",
        "V36_NO_H1_H4_CHANGED",
        "V36_H1_ONLY_CHANGED",
        "V36_H4_ONLY_CHANGED",
        "V37_INTERACTION_CLASS",
    ]
    missing = [c for c in required_v37 if c not in decision_df.columns]
    if missing:
        raise RuntimeError(f"V3.8 V3.7 CLASSIFICATION GUARD FAILED: {missing}")

    # Exact one-to-one row alignment.
    for col in ["signal_date", "result", "R"]:
        if col == "R":
            if not np.allclose(
                pd.to_numeric(trades[col], errors="coerce"),
                pd.to_numeric(decision_df[col], errors="coerce"),
                equal_nan=True,
            ):
                raise RuntimeError(f"V3.8 FROZEN COLUMN GUARD FAILED: {col}")
        else:
            if not trades[col].reset_index(drop=True).equals(
                decision_df[col].reset_index(drop=True)
            ):
                raise RuntimeError(f"V3.8 FROZEN COLUMN GUARD FAILED: {col}")

    print("V3.8 V3.7 CLASSIFICATION GUARD: PASS")

    # OOS / walk-forward.
    oos = strict_oos(module, decision_df)
    wf = expanding_walk_forward(decision_df)
    transitions = transition_audit(decision_df)

    integrity_guards(module, baseline, trades, decision_df, decision_df[
        decision_df["signal_date"] >= OOS_START
    ])

    print_table("V3.8 STRICT CHRONOLOGICAL OOS", oos)
    print_table("V3.8 EXPANDING WALK-FORWARD YEAR AUDIT", wf)
    print_table("V3.8 OOS DECISION TRANSITIONS", transitions)

    # Explicit small-N flag; never silently treat tiny OOS groups as evidence.
    oos_report = oos.copy()
    oos_report["small_N_flag"] = oos_report["resolved"] < 5

    wf_report = wf.copy()
    wf_report["small_N_flag"] = wf_report["resolved"] < 5

    # Performance-survival diagnostic:
    # compare OOS average R to discovery average R, but do not rank candidates.
    survival_rows = []
    for mode in context_masks(decision_df).keys():
        d = oos_report[
            (oos_report["context"] == mode)
            & (oos_report["sample"] == "DISCOVERY")
        ].iloc[0]
        h = oos_report[
            (oos_report["context"] == mode)
            & (oos_report["sample"] == "HOLDOUT_OOS")
        ].iloc[0]

        survival_rows.append({
            "context": mode,
            "discovery_resolved": d["resolved"],
            "discovery_avg_R": d["avg_R"],
            "holdout_resolved": h["resolved"],
            "holdout_avg_R": h["avg_R"],
            "avg_R_delta_OOS_minus_IS": (
                h["avg_R"] - d["avg_R"]
                if np.isfinite(h["avg_R"]) and np.isfinite(d["avg_R"])
                else np.nan
            ),
            "discovery_total_R": d["total_R"],
            "holdout_total_R": h["total_R"],
            "holdout_small_N": bool(h["small_N_flag"]),
        })

    survival = pd.DataFrame(survival_rows)

    print_table("V3.8 DISCOVERY → OOS PERFORMANCE SURVIVAL", survival)

    # Final status: PASS means the validation was executed with frozen
    # definitions and all integrity guards passed. It does NOT mean
    # that any context is statistically proven or approved for trading.
    print("\n" + "=" * 78)
    print("V3.8 VALIDATION STATUS")
    print("=" * 78)
    print("V3.8 FROZEN SIGNAL/RESULT/R GUARD: PASS")
    print("V3.8 BASE DECISION REPRODUCTION GUARD: PASS")
    print("V3.8 V3.7 CLASSIFICATION GUARD: PASS")
    print("V3.8 NO ENTRY CREATION: PASS")
    print("V3.8 NO BASELINE MODIFICATION: PASS")
    print("V3.8 OOS CHRONOLOGY GUARD: PASS")
    print("V3.8 VALIDATION COMPLETE")
    print("Research-only. No Decision Engine rule was changed.")
    print("Small-N OOS groups must not be interpreted as evidence.")

    # Reports.
    decision_df.to_csv(
        "macro_backtest_v38_frozen_decision_labels.csv",
        index=False,
    )
    oos_report.to_csv(
        "macro_backtest_v38_strict_oos.csv",
        index=False,
    )
    wf_report.to_csv(
        "macro_backtest_v38_expanding_walk_forward.csv",
        index=False,
    )
    transitions.to_csv(
        "macro_backtest_v38_oos_decision_transitions.csv",
        index=False,
    )
    survival.to_csv(
        "macro_backtest_v38_is_oos_survival.csv",
        index=False,
    )

    print("\nFILES CREATED")
    for name in [
        "macro_backtest_v38_frozen_decision_labels.csv",
        "macro_backtest_v38_strict_oos.csv",
        "macro_backtest_v38_expanding_walk_forward.csv",
        "macro_backtest_v38_oos_decision_transitions.csv",
        "macro_backtest_v38_is_oos_survival.csv",
    ]:
        print(name)


if __name__ == "__main__":
    main()
