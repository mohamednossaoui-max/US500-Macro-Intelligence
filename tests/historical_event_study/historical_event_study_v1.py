#!/usr/bin/env python3
"""Historical Event Study v1 — research-only, no signals/forecast/Decision Engine."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
HORIZONS={"1D":1,"5D":5,"20D":20}
EVENTS={
"breadth_negative_20d":("breadth_research_state","eq","NEGATIVE_BREADTH","Market Breadth Analyzer v1"),
"breadth_positive_20d":("breadth_research_state","eq","POSITIVE_BREADTH","Market Breadth Analyzer v1"),
"vix_low":("macro_vix","lt",15.0,"Research Context v1"),"vix_elevated":("macro_vix","ge",25.0,"Research Context v1"),
"financial_stress_elevated":("macro_financial_stress_composite","gt",0.0,"Research Context v1"),
"sentiment_bearish":("sentiment_unified_sentiment_score","lt",40.0,"Sentiment Engine v1"),"sentiment_bullish":("sentiment_unified_sentiment_score","gt",60.0,"Sentiment Engine v1"),
"technical_drawdown_ge_5":("technical_drawdown_pct","le",-5.0,"Technical Intelligence v1"),"technical_drawdown_ge_10":("technical_drawdown_pct","le",-10.0,"Technical Intelligence v1"),
"liquidity_20d_change_positive_ge_5":("liquidity_20d_change_pct","ge",5.0,"Liquidity Intelligence v1"),"liquidity_20d_change_negative_le_5":("liquidity_20d_change_pct","le",-5.0,"Liquidity Intelligence v1")}
def load(p):
 d=pd.read_csv(p,low_memory=False)
 if d.empty: raise ValueError(f"Empty input: {p}")
 for c in ("study_date","context_date","asof_date","observation_date"):
  if c in d.columns: d["study_date"]=pd.to_datetime(d[c],errors="coerce").dt.normalize(); break
 else: raise ValueError("No supported date column found")
 if d.study_date.isna().any() or d.study_date.duplicated().any(): raise ValueError("Invalid or duplicate study dates")
 return d.sort_values("study_date").reset_index(drop=True)
def allbool(d,c,v,n):
 if c in d.columns and not d[c].eq(v).all(): raise ValueError(f"{n}: safeguard failed: {c}")
def validate(c,l,b):
 for d,n in ((c,"Research Context"),(l,"Liquidity"),(b,"Market Breadth")): allbool(d,"research_only",True,n); allbool(d,"decision_engine_ready",False,n)
 allbool(c,"point_in_time_safe",True,"Research Context")
 for x in ("trading_signal_generated","forecast_generated"): allbool(c,x,False,"Research Context")
 for x in ("trading_signal","forecast","trading_signal_generated","forecast_generated"): allbool(l,x,False,"Liquidity")
 for x in ("trading_signal","forecast","analysis_pit_perfect"): allbool(b,x,False,"Market Breadth")
def prices(start,end):
 x=yf.download("^GSPC",start=(start-pd.Timedelta(days=5)).strftime("%Y-%m-%d"),end=(end+pd.Timedelta(days=35)).strftime("%Y-%m-%d"),progress=False,auto_adjust=False,actions=False,threads=False)
 if x.empty: raise ValueError("Unable to download ^GSPC")
 close=x["Close"]; close=close.iloc[:,0] if isinstance(close,pd.DataFrame) else close
 idx=pd.to_datetime(close.index)
 if getattr(idx,"tz",None) is not None: idx=idx.tz_localize(None)
 o=pd.DataFrame({"study_date":idx.normalize(),"close":pd.to_numeric(close.to_numpy(),errors="coerce")}).dropna().drop_duplicates("study_date").sort_values("study_date")
 for h,n in HORIZONS.items(): o[f"forward_return_{h}"]=o.close.shift(-n)/o.close-1
 return o
def merge(c,l,b):
 l=l.rename(columns={x:"liq_"+x for x in l.columns if x!="study_date"})
 x=c.merge(l,on="study_date",how="inner",validate="one_to_one").merge(b,on="study_date",how="inner",validate="one_to_one",suffixes=("","_breadth"))
 if x.empty: raise ValueError("No common dates across inputs")
 x["liquidity_20d_change_pct"]=pd.to_numeric(x.get("liq_NET_LIQUIDITY_PROXY_MILLIONS"),errors="coerce").pct_change(20)*100
 return x
def flag(d,col,op,val):
 if col not in d: return pd.Series(False,index=d.index)
 s=d[col]
 if op=="eq": return s.astype(str).eq(str(val))
 s=pd.to_numeric(s,errors="coerce")
 return {"lt":s<val,"le":s<=val,"gt":s>val,"ge":s>=val}[op].fillna(False)
def onset(s,cooldown=5):
 a=s.to_numpy(bool); r=np.zeros(len(a),bool); last=-99999; prev=False
 for i,v in enumerate(a):
  if v and not prev and i-last>cooldown: r[i]=True; last=i
  prev=v
 return pd.Series(r,index=s.index)
def summarize(d):
 rows=[]; evrows=[]
 for name,(col,op,val,source) in EVENTS.items():
  f=flag(d,col,op,val); d["event_"+name]=f; d["onset_"+name]=onset(f); ev=d[d["onset_"+name]]
  for h in HORIZONS:
   e=pd.to_numeric(ev[f"forward_return_{h}"],errors="coerce").dropna(); a=pd.to_numeric(d[f"forward_return_{h}"],errors="coerce").dropna(); ne=pd.to_numeric(d.loc[~f,f"forward_return_{h}"],errors="coerce").dropna()
   me=e.mean() if len(e) else np.nan; ma=a.mean() if len(a) else np.nan; mn=ne.mean() if len(ne) else np.nan
   rows.append({"event_name":name,"source_layer":source,"definition_column":col,"operator":op,"threshold":val,"horizon":h,"event_onsets":len(ev),"event_observations":len(e),"all_observations":len(a),"non_event_observations":len(ne),"event_mean_return_pct":me*100,"event_median_return_pct":e.median()*100 if len(e) else np.nan,"event_positive_share_pct":(e>0).mean()*100 if len(e) else np.nan,"all_mean_return_pct":ma*100,"non_event_mean_return_pct":mn*100,"event_minus_all_pp":(me-ma)*100 if np.isfinite(me) and np.isfinite(ma) else np.nan,"event_minus_non_event_pp":(me-mn)*100 if np.isfinite(me) and np.isfinite(mn) else np.nan})
  for _,r in ev.iterrows():
   z={"study_date":r.study_date.strftime("%Y-%m-%d"),"event_name":name,"source_layer":source,"definition_column":col,"operator":op,"threshold":val}
   for h in HORIZONS: z[f"forward_return_{h}_pct"]=r[f"forward_return_{h}"]*100 if pd.notna(r[f"forward_return_{h}"]) else np.nan
   evrows.append(z)
 return pd.DataFrame(rows),pd.DataFrame(evrows)
def main():
 p=argparse.ArgumentParser(); p.add_argument("--research-context",required=True); p.add_argument("--liquidity",required=True); p.add_argument("--breadth",required=True); p.add_argument("--output",required=True); a=p.parse_args(); out=Path(a.output); out.mkdir(parents=True,exist_ok=True)
 c,l,b=load(a.research_context),load(a.liquidity),load(a.breadth); validate(c,l,b); panel=merge(c,l,b); panel=panel.merge(prices(panel.study_date.min(),panel.study_date.max()),on="study_date",how="left",validate="one_to_one"); summary,events=summarize(panel)
 summary.to_csv(out/"historical_event_study_summary_v1.csv",index=False); events.to_csv(out/"historical_event_study_events_v1.csv",index=False)
 base=[]
 for h in HORIZONS:
  s=pd.to_numeric(panel[f"forward_return_{h}"],errors="coerce").dropna(); base.append({"horizon":h,"observations":len(s),"mean_return_pct":s.mean()*100,"median_return_pct":s.median()*100,"positive_share_pct":(s>0).mean()*100})
 pd.DataFrame(base).to_csv(out/"historical_event_study_baseline_v1.csv",index=False)
 errors=[]; warnings=[]
 if len(panel)<500: errors.append("Common sample below 500 observations")
 if "point_in_time_safe" in panel and not panel.point_in_time_safe.eq(True).all(): errors.append("Research Context PIT safeguard failed")
 for n in EVENTS:
  if int(panel["event_"+n].sum())<5: warnings.append(f"{n}: fewer than 5 event days")
 report={"validator":"Historical Event Study v1","status":"PASS" if not errors else "FAIL","validation_pass":not errors,"errors":errors,"warnings":warnings,"common_sample_rows":len(panel),"date_start":panel.study_date.min().strftime("%Y-%m-%d"),"date_end":panel.study_date.max().strftime("%Y-%m-%d"),"event_definition_count":len(EVENTS),"outcome_horizons":list(HORIZONS),"research_only":True,"decision_engine_ready":False,"trading_signal":False,"forecast":False,"pit_perfect":False,"breadth_pit_perfect":False,"interpretation":"PASS means structural execution only; it does not establish causality, predictiveness, usefulness, or preference for any event or layer."}
 with open(out/"historical_event_study_validation_v1.json","w",encoding="utf-8") as f: json.dump(report,f,indent=2,ensure_ascii=False)
 print("HISTORICAL EVENT STUDY v1"); print(f"Common sample: {len(panel):,}"); print(f"Date range: {panel.study_date.min().date()} -> {panel.study_date.max().date()}"); print(f"Event definitions: {len(EVENTS)}"); print("Research-only: TRUE"); print("Decision Engine: FALSE"); print("Trading signal: FALSE"); print("Forecast: FALSE"); print("PIT-perfect: FALSE"); print("FINAL STATUS: "+report["status"])
 for w in warnings: print("WARNING: "+w)
if __name__=="__main__": main()
