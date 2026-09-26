"""Central point-in-time (PIT) integrity helpers for US500 Macro Intelligence.

PR-04 contract
--------------
A record may be used in a snapshot only when the information was available to
an analyst on or before that snapshot date.  For economic releases the
availability date is the release date unless an explicit ``available_as_of``
column is supplied.

The helpers are deliberately side-effect free: they do not rewrite source
files and they preserve the caller's DataFrame schema/index.
"""
from __future__ import annotations

from typing import Optional
import pandas as pd


def normalize_as_of_date(value) -> pd.Timestamp:
    """Return a normalized, timezone-naive Timestamp or raise ValueError."""
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        raise ValueError(f"Invalid as-of date: {value!r}")
    # Convert to timezone-naive so comparisons are deterministic across inputs.
    return ts.tz_convert(None).normalize()


def _optional_date(value) -> Optional[pd.Timestamp]:
    if value is None or pd.isna(value):
        return None
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return None
    return ts.tz_convert(None).normalize()


def validate_temporal_order(*, release_date, vintage_date=None,
                            observation_date=None, available_as_of=None) -> bool:
    """Validate temporal ordering without changing existing methodology.

    Existing economic-history files define ``vintage_date`` as information
    known no later than the release.  An explicit availability date may not
    precede the release.  Observation dates, when present, may not occur after
    the date on which the information becomes available.
    """
    release = _optional_date(release_date)
    if release is None:
        return False

    vintage = _optional_date(vintage_date)
    if vintage_date is not None and not pd.isna(vintage_date):
        if vintage is None or vintage > release:
            return False

    available = _optional_date(available_as_of)
    if available_as_of is not None and not pd.isna(available_as_of):
        if available is None or available < release:
            return False
    else:
        available = release

    observation = _optional_date(observation_date)
    if observation_date is not None and not pd.isna(observation_date):
        if observation is None or observation > available:
            return False

    return True


def filter_available_as_of(df: pd.DataFrame, as_of_date, *,
                           release_col: str = "release_date",
                           available_col: str = "available_as_of") -> pd.DataFrame:
    """Return only rows that were knowable by ``as_of_date``.

    If ``available_col`` exists it is authoritative. Otherwise ``release_col``
    is used. Invalid/missing availability dates are excluded (fail closed).
    """
    if release_col not in df.columns:
        raise ValueError(f"Missing required PIT column: {release_col}")

    cutoff = normalize_as_of_date(as_of_date)
    work = df.copy()
    source_col = available_col if available_col in work.columns else release_col
    available = pd.to_datetime(work[source_col], errors="coerce", utc=True)
    available = available.dt.tz_convert(None).dt.normalize()
    return work.loc[available.notna() & (available <= cutoff)].copy()


def latest_available_as_of(df: pd.DataFrame, as_of_date, *,
                           release_col: str = "release_date",
                           available_col: str = "available_as_of") -> pd.DataFrame:
    """Return PIT-safe rows sorted by their effective availability date.

    The caller can select the final row globally or within its own grouping.
    This function intentionally does not infer business keys such as indicator
    or reference period.
    """
    work = filter_available_as_of(
        df, as_of_date, release_col=release_col, available_col=available_col
    )
    source_col = available_col if available_col in work.columns else release_col
    order = pd.to_datetime(work[source_col], errors="coerce", utc=True)
    work = work.assign(_pit_available_order=order)
    work = work.sort_values("_pit_available_order", kind="mergesort")
    return work.drop(columns=["_pit_available_order"])
