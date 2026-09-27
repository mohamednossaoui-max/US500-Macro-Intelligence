from __future__ import annotations
import streamlit as st
from pathlib import Path

def apply_terminal_theme():
    """Additive UI theme only. Does not modify data, engines, PIT logic, or research gates."""
    css_path = Path(__file__).with_name("terminal_theme.css")
    st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

def status_badge(label: str, value: str, tone: str = "neutral", sub: str = ""):
    safe_tone = tone if tone in {"positive","negative","warning","info","neutral","purple"} else "neutral"
    st.markdown(
        f"""
        <div class="us-card us-status {safe_tone}">
          <div class="us-label">{label}</div>
          <div class="us-value">{value}</div>
          <div class="us-sub">{sub}</div>
        </div>
        """, unsafe_allow_html=True
    )

def metric_card(label: str, value: str, state: str = "", tone: str = "neutral"):
    safe_tone = tone if tone in {"positive","negative","warning","info","neutral","purple"} else "neutral"
    st.markdown(
        f"""
        <div class="us-card us-metric {safe_tone}">
          <div class="us-label">{label}</div>
          <div class="us-metric-value">{value}</div>
          <div class="us-sub">{state}</div>
        </div>
        """, unsafe_allow_html=True
    )

def section_header(title: str, eyebrow: str = ""):
    st.markdown(
        f"""<div class="us-section-head">
        <div><span class="us-eyebrow">{eyebrow}</span><h3>{title}</h3></div>
        </div>""", unsafe_allow_html=True
    )
