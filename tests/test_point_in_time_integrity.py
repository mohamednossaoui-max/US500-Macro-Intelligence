from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from point_in_time import (
    filter_available_as_of,
    latest_available_as_of,
    validate_temporal_order,
)

ROOT = Path(__file__).resolve().parents[1]


def _load_surprise_engine():
    path = ROOT / "economic_surprise_engine_v1.1.py"
    spec = importlib.util.spec_from_file_location("economic_surprise_engine_pr04", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_future_release_is_blocked():
    df = pd.DataFrame({
        "release_date": ["2026-07-05"],
        "actual": [1.0],
    })
    out = filter_available_as_of(df, "2026-07-04")
    assert out.empty


def test_release_is_available_on_release_date():
    df = pd.DataFrame({
        "release_date": ["2026-07-05"],
        "actual": [1.0],
    })
    out = filter_available_as_of(df, "2026-07-05")
    assert len(out) == 1


def test_future_revision_is_blocked_by_explicit_availability():
    df = pd.DataFrame({
        "release_date": ["2026-07-05", "2026-08-01"],
        "available_as_of": ["2026-07-05", "2026-08-01"],
        "actual": [2.0, 2.4],
    })
    out = latest_available_as_of(df, "2026-07-20")
    assert out["actual"].tolist() == [2.0]


def test_temporal_order_rejects_future_vintage():
    assert not validate_temporal_order(
        release_date="2026-07-05", vintage_date="2026-07-06"
    )
    assert validate_temporal_order(
        release_date="2026-07-05", vintage_date="2026-07-05"
    )


def test_zscore_at_t_is_unchanged_by_future_release():
    engine = _load_surprise_engine()
    base = pd.DataFrame({
        "indicator": ["CPI"] * 5,
        "release_date": pd.to_datetime([
            "2026-01-01", "2026-02-01", "2026-03-01",
            "2026-04-01", "2026-05-01",
        ]),
        "directional_release_shock": [1.0, 2.0, 3.0, 4.0, 5.0],
    })
    z1, _ = engine.calculate_prior_zscore(base)

    future = pd.concat([base, pd.DataFrame({
        "indicator": ["CPI"],
        "release_date": pd.to_datetime(["2026-06-01"]),
        "directional_release_shock": [1000.0],
    })], ignore_index=True)
    z2, _ = engine.calculate_prior_zscore(future)

    np.testing.assert_allclose(
        z1.to_numpy(), z2.iloc[:len(base)].to_numpy(), equal_nan=True
    )
