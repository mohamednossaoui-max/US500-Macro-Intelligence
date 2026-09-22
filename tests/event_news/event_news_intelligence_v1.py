#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"

HTTP_RETRIES = 4
HTTP_BACKOFF = 2.0
GDELT_PACING_SECONDS = 2.5

SEC_UNIVERSE = {
    "MSFT":"0000789019","AAPL":"0000320193","NVDA":"0001045810","AMZN":"0001018724",
    "META":"0001326801","GOOGL":"0001652044","JPM":"0000019617","JNJ":"0000200406",
    "XOM":"0000034088","WMT":"0000104169",
}

GDELT_QUERIES = {
    "fed": '("Federal Reserve" OR FOMC OR "Fed Chair" OR Powell) (rates OR policy OR inflation OR meeting)',
    "inflation": '(CPI OR "consumer price index" OR PPI OR "producer price index") (inflation OR prices OR Federal Reserve)',
    "labor": '("nonfarm payrolls" OR "jobless claims" OR unemployment OR employment) (US OR U.S. OR "United States")',
    "growth": '(GDP OR "economic growth" OR PMI OR ISM OR recession) ("United States" OR US OR U.S.)',
    "market": '("S&P 500" OR SP500 OR "US stocks" OR equities) (market OR index OR trading OR earnings)',
    "geopolitical": '(tariff OR tariffs OR sanctions OR "trade war" OR conflict OR ceasefire) (US OR U.S. OR America)',
    "energy": '(oil OR crude OR OPEC OR gasoline OR energy) (US OR U.S. OR prices OR supply)',
}

TOPIC_TERMS = {
    "fed": ["federal reserve","fomc","powell","interest rate","interest rates"],
    "inflation": ["inflation","cpi","ppi","consumer prices","producer prices"],
    "labor": ["nonfarm payrolls","employment","unemployment","jobless claims"],
    "growth": ["gdp","recession","economic growth","pmi","ism"],
    "market": ["s&p 500","sp500","equities","stocks","volatility"],
    "geopolitical": ["war","sanctions","tariff","tariffs","conflict","ceasefire"],
    "energy": ["oil","crude oil","opec","gasoline","energy"],
}

def http_json(url, headers=None):
    h = {
        "User-Agent": "US500-Macro-Intelligence https://github.com/mohamednossaoui-max/US500-Macro-Intelligence",
        "Accept-Encoding": "gzip, deflate",
    }
    if headers:
        h.update(headers)
    last_exc = None
    for attempt in range(HTTP_RETRIES):
        try:
            req = Request(url, headers=h)
            with urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:
            last_exc = exc
            if attempt < HTTP_RETRIES - 1:
                time.sleep(HTTP_BACKOFF * (2 ** attempt))
    raise last_exc

def gdelt_articles(topic, query):
    params = {
        "query": f"({query})",
        "mode": "artlist",
        "format": "json",
        "maxrecords": 100,
        "timespan": "3months",
        "sort": "datedesc",
    }
    return http_json(GDELT_URL + "?" + urlencode(params)).get("articles", [])

def title_relevant(title, topic):
    t = str(title).lower()
    return any(term in t for term in TOPIC_TERMS[topic])

def normalize_gdelt(rows, topic):
    out=[]
    for r in rows:
        url=str(r.get("url") or "").strip()
        title=str(r.get("title") or "").strip()
        if not url or not title:
            continue
        raw=str(r.get("seendate") or "")
        dt=pd.to_datetime(raw, format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce")
        if pd.isna(dt):
            dt=pd.to_datetime(raw, utc=True, errors="coerce")
        if pd.isna(dt):
            continue
        eid=hashlib.sha256(url.encode()).hexdigest()[:20]
        out.append({
            "event_id":eid,"source_type":"GDELT","source":str(r.get("domain") or ""),
            "topic":topic,"published_at":dt.isoformat(),"availability_date":dt.date().isoformat(),
            "title":title,"url":url,"language":str(r.get("language") or ""),
            "country":str(r.get("sourcecountry") or ""),
            "tone":pd.to_numeric(r.get("tone"),errors="coerce"),
            "topic_relevance_title":title_relevant(title,topic),
            "point_in_time_safe":True,
        })
    return out

def fetch_sec(ticker,cik):
    data=http_json(SEC_SUBMISSIONS.format(cik=cik), headers={"User-Agent":"US500-Macro-Intelligence/1.0 research-only; GitHub Actions"})
    recent=data.get("filings",{}).get("recent",{})
    keys=["form","filingDate","accessionNumber","primaryDocument","acceptanceDateTime"]
    n=len(recent.get("form",[]))
    out=[]
    for i in range(n):
        form=recent["form"][i]
        if form not in {"8-K","10-Q","10-K","10-Q/A","10-K/A"}:
            continue
        acc=recent["accessionNumber"][i] or ""
        doc=recent["primaryDocument"][i] or ""
        accepted=recent["acceptanceDateTime"][i] or ""
        filing_date=recent["filingDate"][i] or ""
        availability=(accepted[:10] if accepted else filing_date)
        acc_clean=acc.replace("-","")
        url=(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{doc}" if doc else "")
        eid=hashlib.sha256((ticker+acc+form).encode()).hexdigest()[:20]
        out.append({
            "event_id":eid,"source_type":"SEC","source":"SEC EDGAR","topic":"corporate_filing",
            "published_at":accepted or availability,"availability_date":availability,
            "title":f"{ticker} {form}","url":url,"language":"en","country":"US",
            "tone":np.nan,"ticker":ticker,"form":form,
            "topic_relevance_title":True,"point_in_time_safe":bool(availability),
        })
    return out

def validate(df, output, query_status, sec_status):
    checks=[]
    def add(name, passed, detail=""):
        checks.append({"check":name,"pass":bool(passed),"detail":detail})

    required=["event_id","source_type","source","topic","published_at","availability_date","title","url"]
    add("required_columns", all(c in df.columns for c in required), str([c for c in required if c not in df.columns]))
    add("unique_event_ids", len(df)>0 and df.event_id.nunique()==len(df), f"rows={len(df)}")

    pub=pd.to_datetime(df.published_at,utc=True,errors="coerce") if len(df) else pd.Series(dtype="datetime64[ns, UTC]")
    add("published_timestamps_parse", len(df)>0 and bool(pub.notna().all()), "")
    add("point_in_time_safe", len(df)>0 and bool(df.point_in_time_safe.fillna(False).all()), "")
    add("urls_valid", len(df)>0 and bool(df.url.astype(str).str.startswith(("http://","https://")).all()), "")
    add("known_sources_only", len(df)==0 or set(df.source_type.dropna().unique()).issubset({"GDELT","SEC"}), "")

    gd=df[df.source_type=="GDELT"] if len(df) else df
    sec=df[df.source_type=="SEC"] if len(df) else df
    topic_counts=gd.topic.value_counts().to_dict() if len(gd) else {}
    topics_present=set(topic_counts)
    add("gdelt_topics_covered", len(topics_present)>=4, json.dumps(topic_counts,sort_keys=True))
    if len(gd):
        relevance=float(gd.topic_relevance_title.fillna(False).mean())
    else:
        relevance=0.0
    add("gdelt_title_relevance", relevance>=0.30, f"relevant_pct={relevance*100:.2f}")
    add("sec_events_present", True, f"sec_rows={len(sec)} (informational; SEC availability may be blocked in hosted CI)")
    successful_topics=sum(1 for v in query_status.values() if v.get("ok",False))
    add("query_execution_visible", successful_topics>=4, f"successful_topics={successful_topics}/7; {json.dumps(query_status,sort_keys=True)}")
    sec_ok=sum(1 for v in sec_status.values() if v.get("ok",False))
    add("sec_execution_visible", True, f"successful_tickers={sec_ok}/10; informational only because SEC may return 403 in hosted CI; {json.dumps(sec_status,sort_keys=True)}")

    errors=[x for x in checks if not x["pass"]]
    warnings=[
        "GDELT DOC article-list coverage is rolling; this is not a complete historical news archive.",
        "SEC universe is a fixed research sample, not point-in-time S&P 500 membership reconstruction.",
        "Title relevance is a conservative semantic sanity check; it does not prove article-level factual relevance."
    ]
    report={
        "validator":"Event / News Intelligence v1",
        "status":"PASS" if not errors else "FAIL",
        "validation_pass":not errors,
        "errors":errors,
        "warnings":warnings,
        "rows":int(len(df)),
        "date_start":str(df.availability_date.min()) if len(df) else None,
        "date_end":str(df.availability_date.max()) if len(df) else None,
        "source_counts":df.source_type.value_counts().to_dict() if len(df) else {},
        "topic_counts":df.topic.value_counts().to_dict() if len(df) else {},
        "query_status":query_status,
        "sec_status":sec_status,
        "research_only":True,"decision_engine_ready":False,"trading_signal":False,
        "forecast":False,"pit_perfect":False,"point_in_time_reconstructed":False,
        "interpretation":"PASS is structural/data-quality validation only. News coverage and filing activity are descriptive and do not establish causality, predictiveness, trading usefulness, or preference."
    }
    (output/"event_news_validation_v1.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",default="event_news_intelligence_v1")
    args=ap.parse_args()
    out=Path(args.output); out.mkdir(parents=True,exist_ok=True)

    records=[]; query_status={}
    for topic,query in GDELT_QUERIES.items():
        try:
            rows=gdelt_articles(topic,query)
            norm=normalize_gdelt(rows,topic)
            records.extend(norm)
            query_status[topic]={"ok":True,"raw_rows":len(rows),"normalized_rows":len(norm)}
        except Exception as e:
            query_status[topic]={"ok":False,"raw_rows":0,"normalized_rows":0,"error":repr(e)}
        finally:
            time.sleep(GDELT_PACING_SECONDS)

    sec_status={}; 
    for ticker,cik in SEC_UNIVERSE.items():
        try:
            rows=fetch_sec(ticker,cik)
            records.extend(rows)
            sec_status[ticker]={"ok":True,"rows":len(rows)}
            time.sleep(0.2)
        except Exception as e:
            sec_status[ticker]={"ok":False,"rows":0,"error":repr(e)}

    df=pd.DataFrame(records)
    if len(df):
        df=df.drop_duplicates("event_id").sort_values(["availability_date","published_at"],kind="stable")
        for c,v in [("research_only",True),("decision_engine_ready",False),("trading_signal",False),
                    ("forecast",False),("pit_perfect",False),("point_in_time_reconstructed",False)]:
            df[c]=v
    else:
        df=pd.DataFrame(columns=["event_id","source_type","source","topic","published_at","availability_date",
                                 "title","url","language","country","tone","ticker","form",
                                 "topic_relevance_title","point_in_time_safe","research_only",
                                 "decision_engine_ready","trading_signal","forecast","pit_perfect",
                                 "point_in_time_reconstructed"])
    df.to_csv(out/"event_news_research_v1.csv",index=False)
    summary={"rows":len(df),"sources":df.source_type.value_counts().to_dict() if len(df) else {},
             "topics":df.topic.value_counts().to_dict() if len(df) else {},
             "query_status":query_status,"sec_status":sec_status,
             "research_only":True,"decision_engine_ready":False,"trading_signal":False,"forecast":False}
    (out/"event_news_research_summary_v1.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    report=validate(df,out,query_status,sec_status)
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if report["validation_pass"] else 1)

if __name__=="__main__":
    main()
