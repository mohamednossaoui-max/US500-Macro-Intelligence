import json, os, time, hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import pandas as pd

API_URL = "https://gnews.io/api/v4/search"
API_KEY = os.getenv("GNEWS_API_KEY", "").strip()
LOOKBACK_DAYS = 30
MAX_ARTICLES = 10
RETRIES = 5
RETRY_BASE_SECONDS = 2
BETWEEN_QUERIES_SECONDS = 2
AVAILABILITY_DELAY_HOURS = 12

QUERIES = {
    "fed": '"Federal Reserve" OR FOMC OR "Fed Chair" OR Powell',
    "inflation": 'CPI OR "consumer price index" OR PPI OR "producer price index"',
    "labor": '"nonfarm payrolls" OR "jobless claims" OR unemployment OR employment',
    "growth": 'GDP OR "economic growth" OR PMI OR ISM OR recession',
    "market": '"S&P 500" OR SP500 OR "US stocks" OR equities',
    "geopolitical": 'tariff OR tariffs OR sanctions OR "trade war" OR conflict OR ceasefire',
    "energy": 'oil OR crude OR OPEC OR gasoline OR energy',
}

TERMS = {
    "fed": ["federal reserve","fomc","fed chair","powell","interest rate"],
    "inflation": ["cpi","consumer price","ppi","producer price","inflation"],
    "labor": ["nonfarm payroll","jobless claim","unemployment","employment","jobs"],
    "growth": ["gdp","economic growth","pmi","ism","recession"],
    "market": ["s&p 500","sp500","us stocks","equities","stock market"],
    "geopolitical": ["tariff","sanction","trade war","conflict","ceasefire","geopolitical"],
    "energy": ["oil","crude","opec","gasoline","energy","fuel"],
}

def now():
    return datetime.now(timezone.utc)

def iso(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def parse_dt(x):
    try:
        return datetime.fromisoformat(str(x).replace("Z","+00:00")).astimezone(timezone.utc)
    except Exception:
        return None

def get_json(params):
    if not API_KEY:
        return None, {"ok":False,"status":None,"error":"GNEWS_API_KEY is missing"}
    q = dict(params); q["token"] = API_KEY
    url = API_URL + "?" + urlencode(q)
    last = ""
    for attempt in range(RETRIES):
        try:
            req = Request(url, headers={
                "Accept":"application/json",
                "User-Agent":"US500-Macro-Intelligence/1.0 research-only"
            })
            with urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8")), {
                    "ok":True, "status":getattr(r,"status",200), "error":None
                }
        except HTTPError as e:
            last = f"HTTP {e.code}: {e.reason}"
            if e.code not in (429,500,502,503,504):
                return None, {"ok":False,"status":e.code,"error":last}
        except (URLError, TimeoutError, json.JSONDecodeError) as e:
            last = str(e)
        if attempt < RETRIES-1:
            time.sleep(RETRY_BASE_SECONDS * (2 ** attempt))
    return None, {"ok":False,"status":None,"error":last or "request failed"}

def relevant(topic, article):
    blob = " ".join(str(article.get(k) or "") for k in
                    ("title","description","content")).lower()
    return any(t in blob for t in TERMS[topic])

def make_id(topic, article):
    raw = "|".join([
        topic, str(article.get("url") or ""),
        str(article.get("publishedAt") or ""),
        str(article.get("title") or "")
    ])
    return hashlib.sha256(raw.encode()).hexdigest()[:24]

def fetch(topic, query, start, end):
    data, status = get_json({
        "q":query, "lang":"en", "country":"us", "max":MAX_ARTICLES,
        "from":iso(start), "to":iso(end), "sortby":"publishedAt"
    })
    if not status["ok"]:
        return [], status

    articles = data.get("articles", []) if isinstance(data,dict) else []
    rows = []
    for a in articles:
        published = parse_dt(a.get("publishedAt"))
        url = str(a.get("url") or "").strip()
        if not published or not url.startswith(("http://","https://")):
            continue

        available = published + timedelta(hours=AVAILABILITY_DELAY_HOURS)
        rows.append({
            "event_id":make_id(topic,a),
            "published_at":iso(published),
            "available_at":iso(available),
            "availability_date":available.date().isoformat(),
            "source":"GNEWS",
            "topic":topic,
            "language":"en",
            "country":"US",
            "title":str(a.get("title") or "").strip(),
            "description":str(a.get("description") or "").strip(),
            "url":url,
            "source_name":str((a.get("source") or {}).get("name") or "").strip(),
            "query":query,
            "topic_relevant":relevant(topic,a),
            "pit_safe":available <= now(),
            "research_only":True,
            "decision_engine_ready":False,
            "trading_signal":False,
            "forecast":False,
        })
    status["articles"] = len(articles)
    return rows, status

def validate(df, statuses):
    checks, warnings = [], []

    if df.empty:
        checks.append({"check":"non_empty_events","pass":False,
                       "detail":"No GNews events collected."})
    else:
        checks += [
            {"check":"unique_event_ids","pass":bool(df.event_id.is_unique),
             "detail":f"rows={len(df)} unique={df.event_id.nunique()}"},
            {"check":"published_timestamps_parse",
             "pass":pd.to_datetime(df.published_at,utc=True,errors="coerce").notna().all(),
             "detail":""},
            {"check":"urls_valid",
             "pass":df.url.astype(str).str.match(r"^https?://",na=False).all(),
             "detail":""},
        ]
        pub = pd.to_datetime(df.published_at,utc=True,errors="coerce")
        av = pd.to_datetime(df.available_at,utc=True,errors="coerce")
        pit = av.notna().all() and (av >= pub + pd.Timedelta(hours=12)).all() and df.pit_safe.all()
        checks.append({"check":"point_in_time_safe","pass":bool(pit),
                       "detail":"published_at + 12h conservative availability"})
        checks.append({"check":"research_only_guards",
                       "pass":bool(df.research_only.all() and
                                   (~df.decision_engine_ready).all() and
                                   (~df.trading_signal).all() and
                                   (~df.forecast).all()),
                       "detail":"research_only=true; no signal/forecast/Decision Engine"})

    counts = df.topic.value_counts().to_dict() if not df.empty else {}
    successful = sum(bool(v.get("ok")) for v in statuses.values())
    checks.append({"check":"gnews_topics_covered","pass":successful >= 5,
                   "detail":json.dumps(counts,sort_keys=True)})
    rel = float(df.topic_relevant.mean()*100) if not df.empty else 0.0
    checks.append({"check":"gnews_topic_relevance","pass":rel >= 50,
                   "detail":f"relevant_pct={rel:.2f}"})
    checks.append({"check":"query_execution_visible",
                   "pass":len(statuses)==len(QUERIES) and all("ok" in x for x in statuses.values()),
                   "detail":json.dumps(statuses,sort_keys=True)})

    warnings += [
        "GNews free-tier news history is limited; this is not a complete historical archive.",
        "Availability is conservatively delayed by 12 hours to avoid look-ahead.",
        "Topic labels are query-derived research categories, not trading signals."
    ]
    failed = [x for x in checks if not x["pass"]]
    return {
        "status":"FAIL" if failed else "PASS",
        "errors":failed,
        "checks":checks,
        "warnings":warnings,
        "rows":int(len(df)),
        "date_start":None if df.empty else str(df.published_at.min()),
        "date_end":None if df.empty else str(df.published_at.max()),
        "source_counts":{} if df.empty else df.source.value_counts().to_dict(),
        "topic_counts":counts,
        "query_status":statuses,
        "research_only":True,
        "decision_engine_ready":False,
        "trading_signal":False,
        "forecast":False,
        "pit_perfect":False,
        "point_in_time_reconstructed":False,
        "availability_method":"published_at_plus_12h",
    }

def main():
    end = now()
    start = end - timedelta(days=LOOKBACK_DAYS)
    rows, statuses = [], {}

    for i,(topic,query) in enumerate(QUERIES.items()):
        if i: time.sleep(BETWEEN_QUERIES_SECONDS)
        r,s = fetch(topic,query,start,end)
        rows.extend(r); statuses[topic] = s

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates("event_id").sort_values(
            ["published_at","topic"],ascending=[False,True]
        ).reset_index(drop=True)

    validation = validate(df,statuses)
    df.to_csv("event_news_events_v1.csv",index=False)
    Path("event_news_validation_v1.json").write_text(
        json.dumps(validation,indent=2,ensure_ascii=False),encoding="utf-8"
    )
    print(json.dumps(validation,indent=2,ensure_ascii=False))
    if validation["status"] == "FAIL":
        raise SystemExit(1)

if __name__ == "__main__":
    main()
