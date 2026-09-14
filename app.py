import os,streamlit as st,pandas as pd
from datetime import date,datetime
from config import MARKET_TICKER,FRED_API_KEY,REFRESH_MINUTES
from data import fred_all,bls_all,market,fomc_page,parse_fomc
from engine import latest,state,analyze,warnings,classify,decision,sl_tp,PULLBACKS
from db import init,save_snapshot,save_alert,history,alerts
st.set_page_config(page_title="US500 Macro Intelligence PRODUCTION",layout="wide")
init(); st.title("US500 Macro Intelligence — PRODUCTION")
st.caption("Macro → Early Warning → Regime → Pullback → Risk/Reward | Decision support only")
with st.sidebar:
 key=st.text_input("FRED API key",value=FRED_API_KEY,type="password",help="يمكن حفظه في Streamlit Secrets باسم FRED_API_KEY.")
 start=st.date_input("History start",date(2015,1,1)); fed=st.selectbox("Fed stance (temporary manual input)",["Neutral","Dovish","Hawkish"])
 if st.button("REFRESH NOW",type="primary"): st.session_state.force=True
 st.caption(f"Market feed: {MARKET_TICKER} | Refresh target: {REFRESH_MINUTES} min")
if "force" in st.session_state or "f" not in st.session_state:
 if not key: st.info("ضع FRED_API_KEY في Secrets/Environment أو أدخل المفتاح هنا ثم REFRESH NOW."); st.stop()
 try:
  with st.spinner("Updating official macro + market data..."):
   st.session_state.f=fred_all(key,start); st.session_state.b=bls_all(start.year,date.today().year); st.session_state.m=market(start); st.session_state.ts=datetime.now(); st.session_state.fomc=parse_fomc(fomc_page())
  st.session_state.pop("force",None)
 except Exception as e: st.error(f"Update failed: {e}"); st.stop()
f=st.session_state.f;m=st.session_state.m; price,ath,dd,atr=state(m); score,reg,meta=analyze(f,fed); w=warnings(f,score); dec=decision(score,dd,w); pb=classify(dd,score,reg)
save_snapshot((st.session_state.ts.isoformat(),price,ath,dd,score,reg,dec,str(meta)))
if score<=-3: save_alert("MACRO",f"Macro score {score}: {reg}")
if dd<=-10: save_alert("DRAWDOWN",f"US500 drawdown {dd:.2f}%")
cols=st.columns(7)
for c,l,v in zip(cols,["US500","ATH","Drawdown","Macro","Regime","Pullback","Decision"],[f"{price:.2f}",f"{ath:.2f}",f"{dd:.2f}%",f"{score:+d}/10",reg.split("—")[0].strip(),pb.split("—")[0].strip(),dec]): c.metric(l,v)
if dec=="DEFENSIVE": st.error("🔴 DEFENSIVE — لا نفترض أن الهبوط فرصة شراء.")
elif dec.startswith("WAIT"): st.warning("🟡 WAIT / CONFIRM — نحتاج تأكيداً إضافياً.")
else: st.success("🟢 SUPPORTIVE — التصحيح أقرب إلى Pullback داخل الاتجاه.")
t1,t2,t3,t4,t5,t6=st.tabs(["LIVE","EARLY WARNING","MACRO","TRADING","EVENTS","HISTORY"])
with t1:
 st.subheader("الخلاصة التنفيذية"); st.write(f"**Regime:** {reg}"); st.write(f"**Pullback:** {pb}"); st.write(f"**Why:** score={score:+d}, drawdown={dd:.2f}%, VIX={meta['vix']:.2f}, HY spread={meta['credit']:.2f}")
 st.write("**Base scenario:** "+("استمرار الاتجاه مع تصحيح محدود" if score>=3 else "تذبذب/تصحيح مع الحاجة لتأكيد" if score>-4 else "خطر هبوطي مرتفع، الأولوية لحماية رأس المال"))
 st.write("**Next trigger:** تدهور متزامن في النمو + العمل + الائتمان/التقلب يرفع مستوى الخطر أسرع من عمق الهبوط وحده.")
with t2:
 if w:
  for x in w: st.warning(x)
 else: st.success("No major early-warning cluster detected.")
 st.info("الهدف من Early Warning هو اكتشاف تغير النظام قبل أن يصل Drawdown إلى -10% أو -20%.")
with t3:
 rows=[]
 for n,k in [("10Y","US10Y"),("2Y","US2Y"),("VIX","VIX"),("DXY","DXY"),("PCE","PCE"),("Core PCE","CORE_PCE"),("Unemployment","UNRATE"),("HY Spread","HY_SPREAD"),("Industrial Production","INDPRO"),("Retail Sales","RETAIL")]: rows.append([n,latest(f[k])])
 st.dataframe(pd.DataFrame(rows,columns=["Indicator","Latest"]),use_container_width=True,hide_index=True)
with t4:
 entry=st.number_input("Entry price",value=float(price),step=1.0); sl,tp,risk=sl_tp(m,entry); st.metric("SL",f"{sl:.2f}"); st.metric("TP 1:4",f"{tp:.2f}"); st.write(f"Risk points: **{risk:.2f}**"); st.code("SL = Lowest Low of previous 5 completed Daily candles − 0.5 × ATR(14)\nTP = Entry + 4R")
 st.dataframe(pd.DataFrame({"Pullback":[f"-{x}%" for x in PULLBACKS],"Price":[ath*(1-x/100) for x in PULLBACKS]}),use_container_width=True,hide_index=True)
with t5:
 st.subheader("FOMC / Events"); st.write("Official Fed source fetched:",st.session_state.fomc.get("source")); st.write("Years detected:",st.session_state.fomc.get("years_found")); st.warning("Actual/Forecast/Previous consensus is intentionally not fabricated. It requires a reliable calendar/consensus provider.")
with t6:
 st.subheader("Saved engine history"); st.dataframe(pd.DataFrame(history(),columns=["Time","Price","Drawdown","Score","Regime","Decision"]),use_container_width=True,hide_index=True); st.subheader("Alerts"); st.dataframe(pd.DataFrame(alerts(),columns=["Time","Type","Message"]),use_container_width=True,hide_index=True)
