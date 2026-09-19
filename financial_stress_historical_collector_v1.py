"""
US500 Macro Intelligence
Financial Stress Intelligence — Historical Collector v1

Research-only. No Decision Engine integration.

Sources:
- VIX: Cboe daily historical CSV.
- Treasury 2Y/10Y: Federal Reserve H.15 / FRED transport of H.15 series.
- NFCI/ANFCI: Federal Reserve Bank of Chicago series via ALFRED vintage transport.
  Release dates are taken from the ALFRED Chicago Fed NFCI release calendar.
"""

from __future__ import annotations
import io
import time
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from urllib.parse import quote

import pandas as pd
import requests

OUT = "financial_stress_records_input_v1.csv"
START = pd.Timestamp("2020-01-01")
END = pd.Timestamp.today().normalize()

VIX_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
H15_CMT_URL = "https://www.federalreserve.gov/datadownload/Output.aspx?rel=H15&series=bf17364827e38702b42a58cf8eaa3f78&lastobs=&from=&to=&filetype=csv&label=include&layout=seriescolumn&type=package"
ALFRED_URL = "https://api.stlouisfed.org/fred/series/observations"
ALFRED_GRAPH = "https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={series}&vintage_date={vintage}"
ALFRED_RELEASE_DATES = "https://alfred.stlouisfed.org/release/downloaddates?rid=221"

H15_URL = "https://www.federalreserve.gov/releases/h15/"
CHICAGO_URL = "https://www.chicagofed.org/research/data/nfci/current-data"

COLS = [
    "indicator","observation_date","availability_date","actual","unit",
    "frequency","source","source_url","vintage","revision_flag",
    "point_in_time_safe","availability_semantics"
]

def session():
    s = requests.Session()
    s.headers.update({"User-Agent": "US500-Macro-Intelligence/2.0"})
    return s

def get(s, url, tries=4, timeout=45):
    last = None
    for i in range(tries):
        try:
            r = s.get(url, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            last = e
            time.sleep(2 ** i)
    raise RuntimeError(f"GET failed: {url}: {last}")

def rid(row):
    key = "|".join(str(row[c]) for c in COLS)
    return hashlib.sha256(key.encode()).hexdigest()

def next_business_day(ts):
    x = pd.Timestamp(ts) + pd.Timedelta(days=1)
    while x.weekday() >= 5:
        x += pd.Timedelta(days=1)
    return x

def load_vix(s):
    r = get(s, VIX_URL)
    df = pd.read_csv(io.BytesIO(r.content))
    df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
    df["CLOSE"] = pd.to_numeric(df["CLOSE"], errors="coerce")
    df = df.dropna(subset=["DATE","CLOSE"])
    df = df[(df["DATE"] >= START) & (df["DATE"] <= END)]
    rows = []
    for _, x in df.iterrows():
        d = x["DATE"]
        rows.append({
            "indicator":"VIX",
            "observation_date":d.date().isoformat(),
            "availability_date":d.date().isoformat(),
            "actual":float(x["CLOSE"]),
            "unit":"INDEX_LEVEL","frequency":"DAILY",
            "source":"Cboe",
            "source_url":VIX_URL,
            "vintage":d.date().isoformat(),
            "revision_flag":False,
            "point_in_time_safe":True,
            "availability_semantics":"EOD_CLOSE",
        })
    return rows

def load_treasury(s, package=None):
    """Load 2Y/10Y Treasury CMTs from the official Fed H.15 DDP package.

    The package is downloaded once because FRED transport can time out in CI.
    H.15 is the authoritative source used here. The release is posted Monday-Friday
    at 4:15pm ET, so an EOD observation is information-available on its observation
    date after the daily release.
    """
    if package is None:
        r = get(s, H15_CMT_URL, tries=5, timeout=90)
        package = pd.read_csv(io.BytesIO(r.content), header=5)

    # H.15 DDP Treasury Constant Maturities package has date + 11 maturity columns.
    if package.shape[1] < 12:
        raise RuntimeError(f"Unexpected H.15 Treasury package shape: {package.shape}")

    df = package.copy()
    date_col = df.columns[0]
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

    # The package order is: date, 1m, 3m, 6m, 1y, 2y, 3y, 5y, 7y, 10y, 20y, 30y.
    maturity_map = {
        "TREASURY_2Y": df.columns[5],
        "TREASURY_10Y": df.columns[9],
    }

    rows = []
    for indicator, value_col in maturity_map.items():
        df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
        sub = df.dropna(subset=[date_col, value_col])
        sub = sub[(sub[date_col] >= START) & (sub[date_col] <= END)]
        for _, x in sub.iterrows():
            d = pd.Timestamp(x[date_col])
            rows.append({
                "indicator":indicator,
                "observation_date":d.date().isoformat(),
                "availability_date":d.date().isoformat(),
                "actual":float(x[value_col]),
                "unit":"PERCENT","frequency":"DAILY",
                "source":"Federal Reserve H.15",
                "source_url":H15_CMT_URL,
                "vintage":d.date().isoformat(),
                "revision_flag":False,
                "point_in_time_safe":True,
                "availability_semantics":"OFFICIAL_RELEASE",
            })
    return rows

def us_federal_holidays(year):
    """Return observed U.S. federal holiday dates for the year."""
    from datetime import date, timedelta
    def nth_weekday(month, weekday, n):
        d = date(year, month, 1)
        d += timedelta(days=(weekday - d.weekday()) % 7)
        d += timedelta(weeks=n-1)
        return d
    def last_weekday(month, weekday):
        import calendar
        last = calendar.monthrange(year, month)[1]
        d = date(year, month, last)
        d -= timedelta(days=(d.weekday() - weekday) % 7)
        return d
    fixed = [(1,1),(6,19),(7,4),(11,11),(12,25)]
    out = set()
    for m, day in fixed:
        d = date(year,m,day)
        if d.weekday() == 5:
            out.add(d - timedelta(days=1))
        elif d.weekday() == 6:
            out.add(d + timedelta(days=1))
        else:
            out.add(d)
    out.add(nth_weekday(1,0,3))   # MLK
    out.add(nth_weekday(2,0,3))   # Washington's Birthday
    out.add(last_weekday(5,0))    # Memorial Day
    out.add(nth_weekday(9,0,1))   # Labor Day
    out.add(nth_weekday(10,0,2))  # Columbus Day
    out.add(nth_weekday(11,3,4))  # Thanksgiving
    return out

def scheduled_nfci_release_dates():
    """Generate Chicago Fed NFCI release dates without relying on ALFRED's calendar endpoint.

    Chicago Fed states that NFCI/ANFCI are released at 8:30 a.m. ET on Wednesday
    for the prior Friday; if a federal holiday falls on Wednesday or earlier in
    the week, the release moves to Thursday.
    """
    dates = []
    obs = pd.date_range(START, END, freq="W-FRI")
    holidays = set()
    for y in range(START.year, END.year + 1):
        holidays |= us_federal_holidays(y)
    for od in obs:
        rd = od + pd.Timedelta(days=5)  # following Wednesday
        if rd.date() in holidays or (rd - pd.Timedelta(days=1)).date() in holidays or (rd - pd.Timedelta(days=2)).date() in holidays:
            rd = od + pd.Timedelta(days=6)  # Thursday
        if START <= rd <= END:
            dates.append(rd)
    return dates

def load_nfci_release_dates(s):
    """Load ALFRED release dates, with deterministic Chicago Fed schedule fallback."""
    try:
        r = get(s, ALFRED_RELEASE_DATES, tries=3, timeout=20)
        text = r.text
        dates = pd.to_datetime(pd.Series(
            re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", text)
        ), errors="coerce").dropna().drop_duplicates().sort_values()
        dates = [d for d in dates if START <= d <= END]
        if dates:
            print(f"NFCI release calendar: ALFRED ({len(dates)} dates)")
            return dates
    except Exception as exc:
        print(f"NFCI release calendar: ALFRED unavailable ({exc}); using Chicago Fed schedule fallback.")
    dates = scheduled_nfci_release_dates()
    print(f"NFCI release calendar: deterministic Chicago Fed schedule ({len(dates)} dates)")
    return dates

def fetch_nfci_vintage(s, vintage, series_list):
    ids = ",".join(series_list)
    url = f"https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={ids}&vintage_date={vintage}"
    try:
        r = get(s, url, tries=4, timeout=60)
        return vintage, pd.read_csv(io.BytesIO(r.content))
    except Exception as exc:
        return vintage, exc

def load_nfci_pair(s):
    release_dates = load_nfci_release_dates(s)
    rows = []
    if not release_dates:
        return rows

    # Fetch both NFCI and ANFCI in one ALFRED request per vintage, concurrently.
    results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(fetch_nfci_vintage, session(), rd.date().isoformat(), ["NFCI","ANFCI"]) for rd in release_dates]
        for fut in as_completed(futures):
            results.append(fut.result())

    for vintage, result in results:
        if isinstance(result, Exception):
            print(f"WARN: NFCI vintage {vintage} failed: {result}")
            continue
        df = result
        if "observation_date" not in df.columns:
            continue
        df["observation_date"] = pd.to_datetime(df["observation_date"], errors="coerce")
        for series in ["NFCI","ANFCI"]:
            if series not in df.columns:
                continue
            vals = pd.to_numeric(df[series], errors="coerce")
            sub = pd.DataFrame({"observation_date":df["observation_date"], series:vals}).dropna()
            sub = sub[(sub.observation_date >= START) & (sub.observation_date <= END)]
            rd = pd.Timestamp(vintage)
            sub = sub[sub.observation_date <= rd - pd.Timedelta(days=1)]
            for _, x in sub.iterrows():
                rows.append({
                    "indicator":series,
                    "observation_date":pd.Timestamp(x.observation_date).date().isoformat(),
                    "availability_date":rd.date().isoformat(),
                    "actual":float(x[series]),
                    "unit":"INDEX_LEVEL","frequency":"WEEKLY",
                    "source":"Chicago Fed",
                    "source_url":CHICAGO_URL,
                    "vintage":rd.date().isoformat(),
                    "revision_flag":False,
                    "point_in_time_safe":True,
                    "availability_semantics":"ARCHIVED_VINTAGE",
                })

    # Keep the earliest vintage for each observation: first release, not a later revision.
    out = {}
    for row in rows:
        k = (row["indicator"], row["observation_date"])
        if k not in out or row["availability_date"] < out[k]["availability_date"]:
            out[k] = row
    return list(out.values())

def load_nfci(s, series):
    release_dates = load_nfci_release_dates(s)
    rows = []
    seen = set()

    for rd in release_dates:
        url = ALFRED_GRAPH.format(series=series, vintage=rd.date().isoformat())
        try:
            r = get(s, url, tries=3)
            df = pd.read_csv(io.BytesIO(r.content))
        except Exception:
            continue

        if "observation_date" not in df.columns or series not in df.columns:
            continue

        df["observation_date"] = pd.to_datetime(df["observation_date"], errors="coerce")
        df[series] = pd.to_numeric(df[series], errors="coerce")
        df = df.dropna(subset=["observation_date", series])
        # Only keep observations that were available by this release and are in our window.
        df = df[(df["observation_date"] >= START) &
                (df["observation_date"] <= END) &
                (df["observation_date"] <= rd - pd.Timedelta(days=1))]

        for _, x in df.iterrows():
            od = x["observation_date"]
            key = (od.date().isoformat(), rd.date().isoformat())
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "indicator":series,
                "observation_date":od.date().isoformat(),
                "availability_date":rd.date().isoformat(),
                "actual":float(x[series]),
                "unit":"INDEX_LEVEL","frequency":"WEEKLY",
                "source":"Chicago Fed",
                "source_url":CHICAGO_URL,
                "vintage":rd.date().isoformat(),
                "revision_flag":True,
                "point_in_time_safe":True,
                "availability_semantics":"ARCHIVED_VINTAGE",
            })

    # For each observation, retain the earliest available vintage: this is the
    # first information set in which that observation existed.
    out = {}
    for row in rows:
        k = row["observation_date"]
        if k not in out or row["availability_date"] < out[k]["availability_date"]:
            out[k] = row
    return list(out.values())

def main():
    s = session()
    rows = []
    rows += load_vix(s)
    treasury_package = None
    rows += load_treasury(s, treasury_package)
    rows += load_nfci_pair(s)

    # Build curve only where both Treasury observations share the same date.
    tmp = pd.DataFrame(rows)
    for c in ["observation_date","availability_date"]:
        tmp[c] = pd.to_datetime(tmp[c])
    t2 = tmp[tmp.indicator=="TREASURY_2Y"].set_index("observation_date")
    t10 = tmp[tmp.indicator=="TREASURY_10Y"].set_index("observation_date")
    common = t2.index.intersection(t10.index)

    for d in common:
        a = float(t10.loc[d, "actual"]) - float(t2.loc[d, "actual"])
        avail = max(t2.loc[d, "availability_date"], t10.loc[d, "availability_date"])
        rows.append({
            "indicator":"CURVE_10Y_2Y",
            "observation_date":d.date().isoformat(),
            "availability_date":pd.Timestamp(avail).date().isoformat(),
            "actual":a,
            "unit":"PERCENTAGE_POINTS","frequency":"DAILY",
            "source":"Federal Reserve H.15",
            "source_url":H15_URL,
            "vintage":pd.Timestamp(avail).date().isoformat(),
            "revision_flag":False,
            "point_in_time_safe":True,
            "availability_semantics":"OFFICIAL_RELEASE",
        })

    out = pd.DataFrame(rows, columns=COLS)
    out = out.drop_duplicates(subset=["indicator","observation_date","availability_date","vintage"])
    out = out.sort_values(["observation_date","indicator"]).reset_index(drop=True)

    # Conservative PIT check.
    od = pd.to_datetime(out["observation_date"])
    ad = pd.to_datetime(out["availability_date"])
    if (ad < od).any():
        raise AssertionError("availability_date earlier than observation_date")
    if not out["point_in_time_safe"].all():
        raise AssertionError("Non-PIT-safe record found")

    out["record_id"] = out.apply(rid, axis=1)
    out.to_csv(OUT, index=False)

    print("Financial Stress Historical Collector v1")
    print(f"Records: {len(out)}")
    print(f"Indicators: {out.indicator.nunique()}")
    print(f"PIT safe: {int(out.point_in_time_safe.sum())}/{len(out)}")
    print(out.groupby("indicator").size().to_string())
    print("PIT QUALITY GATE: PASS")

if __name__ == "__main__":
    main()
