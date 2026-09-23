#!/usr/bin/env python3
"""
Financial Stress Event Robustness Review v1.4
Research-only.

Keeps v1.3 Frequency-Aware scoring fixed and tests only the
event exit threshold: 0.00 / 0.25 / 0.50.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from financial_stress_methodology_review_v1_3 import (
    find_raw_file,
    load_and_validate,
    native_method,
)

OUTPUT_SUMMARY = (
    "financial_stress_event_robustness_summary_v1_4.csv"
)

OUTPUT_EVENTS = (
    "financial_stress_event_robustness_events_v1_4.csv"
)

START_THRESHOLD = 1.0

EXIT_THRESHOLDS = [
    0.00,
    0.25,
    0.50,
]


def detect_events(
    score: pd.Series,
    exit_threshold: float
) -> pd.DataFrame:
    """
    Detect hysteresis events while preserving
    missing-score boundaries.
    """

    # IMPORTANT:
    # Do NOT use score.dropna() here.
    #
    # Missing observations must remain in the series
    # because they represent a boundary between valid
    # scoring periods.
    s = score.sort_index()

    events = []

    i = 0

    while i < len(s):

        # Missing scores cannot start an event.
        if pd.isna(s.iloc[i]) or s.iloc[i] < START_THRESHOLD:
            i += 1
            continue

        start_i = i

        j = i

        while j + 1 < len(s):

            nxt = s.iloc[j + 1]

            # A missing score terminates the event.
            #
            # It must never be treated as continuity.
            if pd.isna(nxt) or nxt < exit_threshold:
                break

            j += 1

        segment = s.iloc[start_i:j + 1]

        peak_date = segment.idxmax()

        recovery_date = None

        for k in range(j + 1, len(s)):

            value = s.iloc[k]

            # Missing score is an event boundary.
            if pd.isna(value):
                break

            if value < exit_threshold:
                recovery_date = s.index[k]
                break

        events.append(
            {
                "exit_threshold":
                    exit_threshold,

                "start_date":
                    s.index[start_i].date().isoformat(),

                "end_date":
                    s.index[j].date().isoformat(),

                "peak_date":
                    peak_date.date().isoformat(),

                "peak_composite":
                    float(segment.max()),

                "mean_composite":
                    float(segment.mean()),

                "duration_trading_sessions":
                    int(len(segment)),

                "time_to_peak_sessions":
                    int(
                        segment.index.get_loc(
                            peak_date
                        )
                    ),

                "recovery_date":
                    (
                        recovery_date.date().isoformat()
                        if recovery_date is not None
                        else None
                    ),

                "recovery_duration_sessions":
                    (
                        int(
                            s.index.get_loc(
                                recovery_date
                            ) - j
                        )
                        if recovery_date is not None
                        else np.nan
                    ),
            }
        )

        i = j + 1

    return pd.DataFrame(events)


def main():

    raw = find_raw_file()

    df = load_and_validate(raw)

    session_dates = pd.DatetimeIndex(
        sorted(
            df.loc[
                df["frequency"]
                .astype(str)
                .str.upper()
                .eq("DAILY"),
                "observation_date",
            ]
            .dropna()
            .unique()
        )
    )

    # v1.3 F Frequency-Aware methodology, unchanged:
    #
    # daily = 252 native observations
    # weekly = 52 native observations
    #
    # weekly_min = 20
    score, _ = native_method(
        df,
        session_dates,
        weekly_window=52,
        daily_window=252,
        weekly_min=20,
    )

    score = score.sort_index()

    events = pd.concat(
        [
            detect_events(
                score,
                threshold
            )
            for threshold in EXIT_THRESHOLDS
        ],
        ignore_index=True,
    )

    summary_rows = []

    for threshold in EXIT_THRESHOLDS:

        e = events[
            events["exit_threshold"] == threshold
        ]

        summary_rows.append(
            {
                "methodology_version":
                    "v1.4",

                "base_method":
                    "F_FREQUENCY_AWARE_v1.3",

                "start_threshold":
                    START_THRESHOLD,

                "exit_threshold":
                    threshold,

                "scored_sessions":
                    int(score.notna().sum()),

                "event_count":
                    int(len(e)),

                "longest_event_sessions":
                    (
                        int(
                            e[
                                "duration_trading_sessions"
                            ].max()
                        )
                        if len(e)
                        else 0
                    ),

                "largest_peak":
                    (
                        float(
                            e[
                                "peak_composite"
                            ].max()
                        )
                        if len(e)
                        else np.nan
                    ),

                "research_only":
                    True,
            }
        )

    pd.DataFrame(
        summary_rows
    ).to_csv(
        OUTPUT_SUMMARY,
        index=False
    )

    events.to_csv(
        OUTPUT_EVENTS,
        index=False
    )

    print(
        "Financial Stress Event Robustness "
        "Review v1.4 completed."
    )

    print(
        pd.DataFrame(
            summary_rows
        ).to_string(index=False)
    )

    print(
        "Research-only: True"
    )


if __name__ == "__main__":
    main()
