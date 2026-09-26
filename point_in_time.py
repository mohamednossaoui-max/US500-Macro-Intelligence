"""Central point-in-time (PIT) integrity helpers for US500 Macro Intelligence.

PR-04 contract
--------------
A record may be used in a snapshot only when the information was available to
an analyst on or before that snapshot date. For economic releases, the
availability date is ``available_as_of`` when explicitly populated for that
row; otherwise it falls back to ``release_date``.

The helpers are side-effect free: they do not rewrite source files and they
preserve the caller's DataFrame schema/index.
"""
from __future__ import annotations

from typing import Optional
import pandas as pd


def normalize_as_of_date(value) -> pd.Timestamp:
    """Return a normalized, timezone-naive Timestamp or raise ValueError."""
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        raise ValueError(f"Invalid as-of date: {value!r}")
    return ts.tz_convert(None).normalize()


def _optional_date(value) -> Optional[pd.Timestamp]:
    if value is None or pd.isna(value):
        return None
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return None
    return ts.tz_convert(None).normalize()


def _effective_availability(df: pd.DataFrame, *, release_col: str,
                            available_col: str) -> pd.Series:
    """Return row-level effective availability with backward-compatible fallback."""
    if release_col not in df.columns:
        raise ValueError(f"Missing required PIT column: {release_col}")

    release = pd.to_datetime(df[release_col], errors="coerce", utc=True)
    if available_col in df.columns:
        explicit = pd.to_datetime(df[available_col], errors="coerce", utc=True)
        effective = explicit.fillna(release)
    else:
        effective = release
    return effective.dt.tz_convert(None).dt.normalize()


def validate_temporal_order(*, release_date, vintage_date=None,
                            observation_date=None, available_as_of=None) -> bool:
    """Validate temporal ordering without changing existing methodology.

    ``vintage_date`` must be known no later than release. An explicitly
    populated ``available_as_of`` may not precede release. ``observation_date``
    may not occur after the effective availability date.
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
    """Return rows knowable by ``as_of_date``.

    Availability is resolved per row. A populated ``available_as_of`` is
    authoritative; a missing/invalid value falls back to that row's
    ``release_date``. Rows with neither a valid explicit availability nor a
    valid release date fail closed and are excluded.
    """
    cutoff = normalize_as_of_date(as_of_date)
    work = df.copy()
    effective = _effective_availability(
        work, release_col=release_col, available_col=available_col
    )
    return work.loc[effective.notna() & (effective <= cutoff)].copy()


def latest_available_as_of(df: pd.DataFrame, as_of_date, *,
                           release_col: str = "release_date",
                           available_col: str = "available_as_of") -> pd.DataFrame:
    """Return PIT-safe rows sorted by effective availability date."""
    work = filter_available_as_of(
        df, as_of_date, release_col=release_col, available_col=available_col
    )
    order = _effective_availability(
        work, release_col=release_col, available_col=available_col
    )
    work = work.assign(_pit_available_order=order)
    work = work.sort_values("_pit_available_order", kind="mergesort")
    return work.drop(columns=["_pit_available_order"])
