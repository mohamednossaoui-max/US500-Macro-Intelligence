import requests,pandas as pd,numpy as np,yfinance as yf
from config import FRED_SERIES,BLS_SERIES,MARKET_TICKER,FED_URL
FRED="https://api.stlouisfed.org/fred/series/observations"; BLS="https://api.bls.gov/publicAPI/v2/timeseries/data/"
def fred(s,key,start):
 p={"series_id":s,"api_key":key,"file_type":"json","observation_start":str(start),"sort_order":"asc"}; r=requests.get(FRED,params=p,timeout=30); r.raise_for_status(); x=pd.DataFrame(r.json()["observations"]); x["date"]=pd.to_datetime(x["date"]); x["value"]=pd.to_numeric(x["value"],errors="coerce"); return x[["date","value"]].dropna()
def fred_all(key,start): return {k:fred(v,key,start) for k,v in FRED_SERIES.items()}
def bls_all(start,end):
 p={"seriesid":list(BLS_SERIES.values()),"startyear":str(start),"endyear":str(end)}; r=requests.post(BLS,json=p,timeout=30); r.raise_for_status(); out={}
 for s in r.json().get("Results",{}).get("series",[]):
  rows=[]
  for q in s.get("data",[]):
   if q.get("period","").startswith("M"): rows.append((pd.Timestamp(int(q["year"]),int(q["period"][1:]),1),float(q["value"])))
  out[s["seriesID"]]=pd.DataFrame(rows,columns=["date","value"]).sort_values("date")
 return out
def market(start):
 x=yf.download(MARKET_TICKER,start=str(start),auto_adjust=False,progress=False)
 if x.empty:return pd.DataFrame()
 if hasattr(x.columns,"levels"): x.columns=x.columns.get_level_values(0)
 x=x.reset_index(); x.columns=[str(c).lower() for c in x.columns]; return x
def fomc_page():
 r=requests.get(FED_URL,timeout=30,headers={"User-Agent":"US500-Macro-Intelligence/2.0"}); r.raise_for_status(); return r.text
def parse_fomc(html):
 import re
 txt=re.sub(r"<[^>]+>"," ",html); txt=re.sub(r"\s+"," ",txt)
 years=sorted(set(re.findall(r"20(?:26|27)",txt)))
 return {"years_found":years,"source":FED_URL}
