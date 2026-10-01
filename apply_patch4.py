from __future__ import annotations
from pathlib import Path
import hashlib, shutil, sys, py_compile

APP = Path(__file__).resolve().parent / 'app.py'
BACKUP = Path(__file__).resolve().parent / 'app.py.pre_patch4'
EXPECTED_SHA256 = 'e85fe4c78c4001d4720751568818e8830e019b6756c0bb2f1d31eac86635be10'

FINGERPRINTS = [
    'APP_VERSION = "V6.3"',
    'HEADERS = {"User-Agent": "US500-Macro-Intelligence-Research-Terminal/6.3"}',
    'from ui_v3 import apply_ui_v3, dynamic_card, section as ui_section, alert_item, rank_item',
    'def fed() -> None:', 'def event_news() -> None:', 'def earnings() -> None:',
    'def event_study() -> None:', 'def final_validation() -> None:', 'def data_status() -> None:',
]

def die(msg: str) -> None:
    print(f'PATCH 4 ABORTED: {msg}')
    sys.exit(1)

def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        die(f'{label}: expected exactly 1 match, found {count}. app.py was NOT modified.')
    return text.replace(old, new, 1)

if not APP.exists():
    die('app.py must be in the same folder as apply_patch4.py.')
raw = APP.read_bytes()
sha = hashlib.sha256(raw).hexdigest()
text = raw.decode('utf-8')

if sha != EXPECTED_SHA256:
    die(f'V6.3 file hash mismatch. Expected {EXPECTED_SHA256}, found {sha}. No changes made.')
missing = [x for x in FINGERPRINTS if x not in text]
if missing:
    die('required V6.3 fingerprints are missing: ' + ' | '.join(missing))
if BACKUP.exists():
    die('app.py.pre_patch4 already exists. Rename/remove it only after confirming why; no changes made.')

# Work entirely in memory first. Backend/loaders/PIT/scoring/governance are untouched.
new = text

css_anchor = "@media(max-width:560px){.command-strip{grid-template-columns:1fr}.reaction-row{grid-template-columns:52px 1fr 66px}}\n"
css_add = css_anchor + r'''/* PATCH 4 — presentation-only dynamic research panels */
.research-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:.45rem 0 .85rem}
.research-panel{border:1px solid rgba(128,140,155,.22);border-radius:13px;padding:12px 14px;background:linear-gradient(145deg,rgba(15,34,53,.90),rgba(7,20,33,.90));min-height:92px}
.research-panel .rp-title{font-size:.72rem;font-weight:900;letter-spacing:.055em;color:#9bb0c1;text-transform:uppercase;margin-bottom:7px}
.research-panel .rp-line{display:flex;justify-content:space-between;gap:12px;padding:4px 0;border-bottom:1px solid rgba(128,140,155,.10);font-size:.78rem}
.research-panel .rp-line:last-child{border-bottom:0}.research-panel .rp-k{color:#8298aa}.research-panel .rp-v{font-weight:800;text-align:right;overflow-wrap:anywhere}
@media(max-width:900px){.research-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:560px){.research-grid{grid-template-columns:1fr}}
'''
new = replace_once(new, css_anchor, css_add, 'CSS anchor')

helper_anchor = '''def source_status(text: str) -> str:\n'''
helper = r'''def research_panels(df: Optional[pd.DataFrame], max_rows: int = 6, max_fields: int = 5) -> None:
    """PATCH 4 presentation helper: render published rows as dark research panels.

    Values are displayed exactly from the supplied DataFrame. No scoring, PIT,
    eligibility, governance, ranking, normalization, or backend state is changed.
    """
    if df is None or df.empty:
        st.info("No published rows are available for this research view.")
        return
    view = df.tail(max_rows).iloc[::-1]
    fields = [str(c) for c in view.columns[:max_fields]]
    blocks = []
    for idx, (_, row) in enumerate(view.iterrows(), 1):
        title = fmt(row.get(fields[0])) if fields else f"Record {idx}"
        lines = []
        for field in fields[1:]:
            lines.append(
                "<div class='rp-line'><span class='rp-k'>" + str(field).replace("_", " ") +
                "</span><span class='rp-v'>" + fmt(row.get(field)) + "</span></div>"
            )
        blocks.append("<div class='research-panel'><div class='rp-title'>" + title + "</div>" + "".join(lines) + "</div>")
    st.markdown("<div class='research-grid'>" + "".join(blocks) + "</div>", unsafe_allow_html=True)


def source_status(text: str) -> str:
'''
new = replace_once(new, helper_anchor, helper, 'research_panels helper')

old = '''    st.dataframe(pd.DataFrame(comparison_rows), use_container_width=True, hide_index=True)\n    st.caption("Unavailable or not-yet-published reports remain unavailable; they are never converted into neutral evidence.")\n'''
rep = '''    comparison_df = pd.DataFrame(comparison_rows)\n    research_panels(comparison_df, max_rows=3, max_fields=6)\n    with st.expander("Raw communication comparison", expanded=False):\n        table(comparison_df, 260)\n    st.caption("Unavailable or not-yet-published reports remain unavailable; they are never converted into neutral evidence.")\n'''
new = replace_once(new, old, rep, 'Fed communication comparison')

old = '''    table(df.tail(300) if isinstance(df,pd.DataFrame) else None,560); source("Event News",src)\n'''
rep = '''    if isinstance(df, pd.DataFrame) and not df.empty:\n        st.subheader("Recent Event Research View")\n        research_panels(df, max_rows=6, max_fields=5)\n    with st.expander("Raw Event / News data", expanded=False):\n        table(df.tail(300) if isinstance(df,pd.DataFrame) else None,560)\n    source("Event News",src)\n'''
new = replace_once(new, old, rep, 'Event News raw table')

# Earnings: preserve the four published artifacts, but make each tab visual-first and raw-on-demand.
for old, rep, label in [
('''        table(df.tail(300) if isinstance(df, pd.DataFrame) else None, 560)\n        source("Earnings", src)\n''', '''        research_panels(df, max_rows=6, max_fields=5)\n        with st.expander("Raw earnings events", expanded=False):\n            table(df.tail(300) if isinstance(df, pd.DataFrame) else None, 560)\n        source("Earnings", src)\n''', 'Earnings events'),
('''        table(df)\n        source("Earnings Summary", src)\n''', '''        research_panels(df, max_rows=6, max_fields=5)\n        with st.expander("Raw earnings summary", expanded=False):\n            table(df)\n        source("Earnings Summary", src)\n''', 'Earnings summary'),
('''        table(df)\n        source("Earnings EPS", src)\n''', '''        research_panels(df, max_rows=6, max_fields=5)\n        with st.expander("Raw EPS classes", expanded=False):\n            table(df)\n        source("Earnings EPS", src)\n''', 'Earnings EPS'),
('''        table(df)\n        source("Earnings Sectors", src)\n''', '''        research_panels(df, max_rows=6, max_fields=5)\n        with st.expander("Raw sector data", expanded=False):\n            table(df)\n        source("Earnings Sectors", src)\n''', 'Earnings sectors')]:
    new = replace_once(new, old, rep, label)

old = '''        table(df, 560 if title == "Event x Horizon Summary" else 360)\n        source(title, src)\n'''
rep = '''        research_panels(df, max_rows=6, max_fields=5)\n        with st.expander(f"Raw {title} data", expanded=False):\n            table(df, 560 if title == "Event x Horizon Summary" else 360)\n        source(title, src)\n'''
new = replace_once(new, old, rep, 'Event Study tables')

old = '''    st.subheader("Validation Summary")\n    table(summary, 220)\n    source("Final Validation Summary", summary_src)\n'''
rep = '''    st.subheader("Validation Summary")\n    research_panels(summary, max_rows=6, max_fields=5)\n    with st.expander("Raw validation summary", expanded=False):\n        table(summary, 220)\n    source("Final Validation Summary", summary_src)\n'''
new = replace_once(new, old, rep, 'Final validation summary')

old = '''    st.subheader("Validation Report")\n    table(report, 650)\n    source("Final Validation Report", report_src)\n'''
rep = '''    st.subheader("Validation Report")\n    research_panels(report, max_rows=6, max_fields=5)\n    with st.expander("Raw validation report", expanded=False):\n        table(report, 650)\n    source("Final Validation Report", report_src)\n'''
new = replace_once(new, old, rep, 'Final validation report')

# Validate generated Python before touching app.py.
tmp = APP.with_name('.app.py.patch4.tmp')
tmp.write_text(new, encoding='utf-8')
try:
    py_compile.compile(str(tmp), doraise=True)
except Exception as exc:
    tmp.unlink(missing_ok=True)
    die(f'generated app.py failed Python syntax validation: {exc}')
tmp.unlink(missing_ok=True)

# Backup first, then one atomic-style replacement write.
shutil.copy2(APP, BACKUP)
try:
    APP.write_text(new, encoding='utf-8')
    py_compile.compile(str(APP), doraise=True)
except Exception as exc:
    shutil.copy2(BACKUP, APP)
    die(f'write/validation failed; original app.py restored from backup: {exc}')

print('PATCH 4 APPLIED SUCCESSFULLY')
print(f'Backup: {BACKUP.name}')
print('Scope: presentation only — dynamic dark research panels + raw tables in closed expanders.')
print('Backend / PIT / scoring / governance were not modified by this patch.')
