from __future__ import annotations
from html import escape
from typing import Any
import math
import streamlit as st


def apply_ui_v3() -> None:
    st.markdown(r'''<style>
:root{--bg:#06101b;--panel:#0a1725;--panel2:#0d1d2e;--line:#18344e;--text:#edf6ff;--muted:#8298aa;--green:#19e6a2;--red:#ff6170;--amber:#ffb84d;--blue:#35a7ff;--purple:#b66cff}
.stApp{background:radial-gradient(900px 420px at 90% -10%,rgba(53,167,255,.12),transparent 55%),radial-gradient(720px 350px at 45% -18%,rgba(182,108,255,.08),transparent 60%),var(--bg);color:var(--text)}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#071421,#08111d);border-right:1px solid var(--line)}
[data-testid="stSidebar"] *{color:#dcecff}.block-container{max-width:1550px;padding-top:1rem;padding-bottom:3rem}
.card,.v3-card{position:relative;overflow:hidden;border:1px solid var(--line)!important;border-radius:14px!important;padding:14px 16px!important;background:linear-gradient(145deg,rgba(15,34,53,.95),rgba(7,20,33,.95))!important;min-height:92px;box-shadow:0 12px 28px rgba(0,0,0,.14);transition:transform .16s ease,border-color .16s ease}
.card:hover,.v3-card:hover{transform:translateY(-2px);border-color:#2c5a7d!important}.card:after,.v3-card:after{content:"";position:absolute;left:0;right:0;bottom:0;height:2px;background:var(--accent,#60798f)}
.v3-positive{--accent:var(--green)}.v3-negative{--accent:var(--red)}.v3-warning{--accent:var(--amber)}.v3-info{--accent:var(--blue)}.v3-purple{--accent:var(--purple)}.v3-neutral{--accent:#8ea4b7}
.label,.v3-label{font-size:.67rem!important;font-weight:850!important;letter-spacing:.09em!important;color:var(--muted)!important;text-transform:uppercase}.value,.v3-value{font-size:1.18rem!important;font-weight:850!important;margin-top:7px;color:var(--text)}.small,.v3-note{color:var(--muted)!important;font-size:.74rem!important;margin-top:5px}
.v3-kicker{font-size:.68rem;font-weight:850;letter-spacing:.13em;color:var(--blue);text-transform:uppercase}.v3-title{font-size:1.95rem;font-weight:900;letter-spacing:-.035em;margin:.15rem 0}.v3-sub{color:var(--muted);font-size:.82rem}.v3-section{margin:1.45rem 0 .55rem;border-bottom:1px solid var(--line);padding-bottom:.4rem}.v3-section b{font-size:1.03rem}.v3-rank{display:flex;gap:10px;align-items:center;padding:10px 12px;border:1px solid var(--line);border-radius:12px;background:rgba(10,23,37,.8);margin:6px 0}.v3-ranknum{font-size:.72rem;color:var(--blue);font-weight:900;min-width:24px}.v3-rankname{font-weight:800;flex:1}.v3-rankvalue{font-variant-numeric:tabular-nums;font-weight:850}.v3-alert{border:1px solid var(--line);border-left:3px solid var(--accent,#8ea4b7);border-radius:11px;padding:10px 12px;background:rgba(10,23,37,.82);margin:7px 0}.v3-alert b{color:var(--accent,#edf6ff)}
/* Streamlit dataframe / table dark surface */
[data-testid="stDataFrame"], [data-testid="stTable"]{border:1px solid var(--line)!important;border-radius:13px!important;overflow:hidden!important;background:#081522!important;box-shadow:0 10px 24px rgba(0,0,0,.12)}
[data-testid="stDataFrame"] *{--gdg-bg-cell:#081522!important;--gdg-bg-header:#0d2133!important;--gdg-text-dark:#eaf4ff!important;--gdg-text-medium:#a7bac9!important;--gdg-border-color:#17344d!important}
[data-testid="stDataFrame"] canvas{filter:none!important}
[data-testid="stMetric"]{background:linear-gradient(145deg,rgba(15,34,53,.94),rgba(7,20,33,.94));border:1px solid var(--line);border-radius:13px;padding:12px 14px}
[data-testid="stAlert"]{border-radius:12px!important;border-color:var(--line)!important}
.stTabs [data-baseweb="tab-list"]{gap:8px;border-bottom:1px solid var(--line)}.stTabs [data-baseweb="tab"]{background:#091827;border:1px solid var(--line);border-radius:9px 9px 0 0;padding:8px 14px}.stTabs [aria-selected="true"]{border-color:#2c6590!important;color:#fff!important}
.stButton>button,.stDownloadButton>button{border-radius:10px;border:1px solid #245077;background:#0c2134;color:#eaf5ff}.stButton>button:hover,.stDownloadButton>button:hover{border-color:var(--blue);color:white}
@media(max-width:700px){.v3-title{font-size:1.5rem}.card,.v3-card{min-height:78px;padding:11px 12px!important}}
</style>''', unsafe_allow_html=True)


def _s(v: Any) -> str:
    if v is None: return "—"
    try:
        if isinstance(v, float) and math.isnan(v): return "—"
    except Exception: pass
    return escape(str(v))


def tone_for(value: Any) -> str:
    s = str(value).strip().upper()
    if any(x in s for x in ("NOT READY","LIMITED","STALE","DEGRADED","WARNING","MIXED")): return "warning"
    if any(x in s for x in ("FAIL","BEARISH","RESTRICTIVE","HIGH STRESS","CONTRADICT")): return "negative"
    if any(x in s for x in ("SUPPORTIVE","CURRENT","PASS","LOW STRESS","PIT_SAFE","TRUE")): return "positive"
    if any(x in s for x in ("HAWKISH","FED","CONTEXTUAL")): return "purple"
    return "info" if s not in ("—","NOT AVAILABLE","NONE") else "neutral"


def dynamic_card(label: str, value: Any, note: Any = "", tone: str | None = None) -> None:
    # Notes can legitimately be numeric (for example the published unified
    # sentiment score).  Escape only after normalising to display text so a
    # float/NaN cannot crash the Sentiment page.
    t = tone or tone_for(value)
    st.markdown(
        f'<div class="v3-card v3-{t}"><div class="v3-label">{_s(label)}</div>'
        f'<div class="v3-value">{_s(value)}</div><div class="v3-note">{_s(note)}</div></div>',
        unsafe_allow_html=True,
    )


def section(title: str, kicker: str = "") -> None:
    st.markdown(f'<div class="v3-section"><span class="v3-kicker">{escape(kicker)}</span><br><b>{escape(title)}</b></div>', unsafe_allow_html=True)


def alert_item(title: str, detail: str, tone: str = "warning") -> None:
    st.markdown(f'<div class="v3-alert v3-{tone}"><b>{escape(title)}</b><div class="v3-note">{escape(detail)}</div></div>', unsafe_allow_html=True)


def rank_item(rank: int, name: str, value: Any, note: str = "") -> None:
    st.markdown(f'<div class="v3-rank"><span class="v3-ranknum">#{rank}</span><span class="v3-rankname">{escape(name)}<div class="v3-note">{escape(note)}</div></span><span class="v3-rankvalue">{_s(value)}</span></div>', unsafe_allow_html=True)
