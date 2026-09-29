import pandas as pd
from .common import row

FRESHNESS_LIMIT_DAYS = {"AAII": 10, "VIX": 5, "COT": 10}


def _latest(path, filename):
    d = pd.read_csv(path / filename)
    return d.iloc[-1]


def _age_days(as_of, available_at):
    return int((pd.Timestamp(as_of) - pd.Timestamp(available_at)).days)


def build(p):
    """Build sentiment evidence with source-true availability and freshness."""
    aaii = _latest(p, "aaii_sentiment_research_v1.csv")
    vix = _latest(p, "vix_sentiment_research_v1.csv")
    cot = _latest(p, "cot_positioning_research_v1.csv")

    as_of = max(
        pd.Timestamp(aaii.availability_date),
        pd.Timestamp(vix.availability_date),
        pd.Timestamp(cot.availability_date),
    )

    out = []
    for x, mod, freq, filename in [
        (aaii, "AAII", "WEEKLY", "aaii_sentiment_research_v1.csv"),
        (vix, "VIX", "DAILY", "vix_sentiment_research_v1.csv"),
    ]:
        age = _age_days(as_of, x.availability_date)
        fresh = 0 <= age <= FRESHNESS_LIMIT_DAYS[mod]
        out.append(row(
            "SENTIMENT_" + mod,
            "SENTIMENT",
            mod,
            state=x.research_regime,
            observation_date=x.observation_date,
            available_at=x.availability_date,
            as_of_date=as_of.strftime("%Y-%m-%d"),
            source_name=x.get("source", ""),
            source_artifact=filename,
            pit_status="PIT_SAFE" if bool(x.point_in_time_safe) else "NOT_PIT_SAFE",
            availability_status="AVAILABLE" if fresh else "STALE",
            expected_frequency=freq,
            limitations=x.get("availability_semantics", ""),
        ) | {
            "freshness_status": "CURRENT" if fresh else "STALE",
            "age_days": age,
        })

    age = _age_days(as_of, cot.availability_date)
    fresh = 0 <= age <= FRESHNESS_LIMIT_DAYS["COT"]
    for ind, col in [
        ("COT Asset Manager", "asset_manager_research_regime"),
        ("COT Leveraged Money", "leveraged_money_research_regime"),
    ]:
        out.append(row(
            "SENTIMENT_COT",
            "SENTIMENT",
            ind,
            state=cot[col],
            observation_date=cot.observation_date,
            available_at=cot.availability_date,
            as_of_date=as_of.strftime("%Y-%m-%d"),
            source_name="CFTC COT",
            source_artifact="cot_positioning_research_v1.csv",
            pit_status="PIT_SAFE" if bool(cot.point_in_time_safe) else "NOT_PIT_SAFE",
            availability_status="AVAILABLE" if fresh else "STALE",
            expected_frequency="WEEKLY",
        ) | {
            "freshness_status": "CURRENT" if fresh else "STALE",
            "age_days": age,
        })
    return out
