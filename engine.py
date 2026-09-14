import numpy as np,pandas as pd
PULLBACKS=[3,5,10,20,30]
def latest(x): return np.nan if x is None or x.empty else float(x.iloc[-1]["value"])
def delta(x,n=1): return np.nan if x is None or len(x)<=n else float(x.iloc[-1]["value"]-x.iloc[-1-n]["value"])
def pct_delta(x,n=1):
 v=latest(x); d=delta(x,n); return np.nan if not v or np.isnan(v) else d/v*100
def state(m):
 p=float(m.close.iloc[-1]); ath=float(m.close.cummax().iloc[-1]); pc=m.close.shift(1); tr=pd.concat([(m.high-m.low).abs(),(m.high-pc).abs(),(m.low-pc).abs()],axis=1).max(axis=1); atr=float(tr.rolling(14).mean().iloc[-1]); return p,ath,(p/ath-1)*100,atr
def analyze(f,fed):
 g=0
 # Growth: industrial production and retail momentum
 g += int(np.sign(pct_delta(f["INDPRO"],3))) + int(np.sign(pct_delta(f["RETAIL"],3)))
 # Labor: falling unemployment positive, rising negative
 g += -int(np.sign(delta(f["UNRATE"],3)))
 # Inflation: slowing PCE positive, accelerating negative
 g += -int(np.sign(pct_delta(f["PCE"],3)))
 vix=latest(f["VIX"]); credit=latest(f["HY_SPREAD"]); y10=latest(f["US10Y"])
 score=g + (2 if fed=="Dovish" else -2 if fed=="Hawkish" else 0)
 score += -2 if vix>=30 else -1 if vix>=25 else 1 if vix<18 else 0
 score += -2 if credit>=5 else -1 if credit>=4 else 1 if credit<3.5 else 0
 score=int(np.clip(score,-10,10))
 if vix>=35 or credit>=6: reg="F — Liquidity / Financial Shock"
 elif score<=-4: reg="E — Recession / Bear Risk"
 elif fed=="Hawkish" and pct_delta(f["PCE"],3)>0: reg="C — Inflation / Rates Shock"
 elif score<0: reg="D — Mixed Macro Stress"
 elif score<3: reg="B — Growth Scare / Mixed"
 else: reg="A — Healthy / Supportive"
 return score,reg,{"growth":g,"vix":vix,"credit":credit,"10y":y10,"fed":fed}
def warnings(f,score):
 w=[]; v=latest(f["VIX"]); c=latest(f["HY_SPREAD"])
 if v>=25:w.append("VIX elevated")
 if c>=4:w.append("High-yield credit spread elevated")
 if pct_delta(f["INDPRO"],3)<0:w.append("Industrial production momentum weakening")
 if pct_delta(f["RETAIL"],3)<0:w.append("Retail-sales momentum weakening")
 if delta(f["UNRATE"],3)>0:w.append("Unemployment trend rising")
 if pct_delta(f["PCE"],3)>0:w.append("PCE trend accelerating")
 if score<=-3:w.append("Macro score entering risk zone")
 return w
def classify(dd,score,reg):
 if reg.startswith("F"): return "F — Liquidity / Financial Shock"
 if reg.startswith("E"): return "E — Recession / Bear Risk"
 if reg.startswith("C"): return "C — Inflation / Rates Shock"
 if dd<=-10 and score<0:return "D — Mixed Macro Stress"
 if score<3:return "B — Growth Scare / Mixed"
 return "A — Healthy / Supportive"
def decision(score,dd,w):
 if score<=-4 or dd<=-20 or len(w)>=5:return "DEFENSIVE"
 if score<3 or dd<=-10 or len(w)>=3:return "WAIT / CONFIRM"
 return "SUPPORTIVE"
def sl_tp(m,entry):
 pc=m.close.shift(1); tr=pd.concat([(m.high-m.low).abs(),(m.high-pc).abs(),(m.low-pc).abs()],axis=1).max(axis=1); atr=float(tr.rolling(14).mean().iloc[-1]); low=float(m.low.iloc[-6:-1].min()); sl=low-.5*atr; risk=entry-sl; return sl,entry+4*risk,risk
