from __future__ import annotations

import hashlib
import py_compile
import shutil
from pathlib import Path

APP = Path("app.py")
BACKUP = Path("app.py.pre_patch4")
EXPECTED_SHA256 = "fa65e47102e8509e4c841e66d317768fea307ce12c00c3da8c9f23eed58b7298"

def die(message: str) -> None:
    print(f"ERROR: {message}")
    raise SystemExit(1)

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        die(f"{label}: expected exactly 1 match, found {count}. app.py was not changed.")
    return text.replace(old, new, 1)

if not APP.is_file():
    die("app.py not found beside apply_patch4_corrected.py.")

actual = sha256(APP)
if actual != EXPECTED_SHA256:
    die(
        "Safety fingerprint mismatch.\n"
        f"Expected: {EXPECTED_SHA256}\n"
        f"Actual:   {actual}\n"
        "This corrected Patch 4 is locked to the verified V6.3/Patch-4 baseline."
    )

original = APP.read_text(encoding="utf-8")

fingerprints = [
    'APP_VERSION = "V6.3"',
    "def research_panels(",
    "def research_context() -> None:",
    "def macro_context() -> None:",
    "def fed() -> None:",
    "def event_news() -> None:",
    "def earnings() -> None:",
    "def event_study() -> None:",
    "def historical_edge() -> None:",
    "def final_validation() -> None:",
    "def data_status() -> None:",
    "def explorer() -> None:",
]
missing = [x for x in fingerprints if x not in original]
if missing:
    die("Missing V6.3 fingerprints: " + " | ".join(missing))

if not BACKUP.exists():
    shutil.copy2(APP, BACKUP)
    print("Created backup: app.py.pre_patch4")
else:
    print("Preserved existing backup: app.py.pre_patch4")

patched = original

patched = replace_once(
    patched,
    '    table(df, 300)\n    source("Research Context Summary", src)\n\n    st.subheader("Research Context Extremes")\n    table(extremes, 420)\n    source("Research Context Extremes", extremes_src)\n',
    '    st.subheader("Published Context Snapshot")\n    research_panels(df, max_rows=3, max_fields=6)\n    with st.expander("Raw Research Context Summary", expanded=False):\n        table(df, 300)\n    source("Research Context Summary", src)\n\n    st.subheader("Research Context Extremes")\n    research_panels(extremes, max_rows=6, max_fields=5)\n    with st.expander("Raw Research Context Extremes", expanded=False):\n        table(extremes, 420)\n    source("Research Context Extremes", extremes_src)\n',
    "Research Context",
)

patched = replace_once(
    patched,
    '    table(df, 280)\n    source("Macro Context", src)\n',
    '    st.subheader("Published Macro Snapshot")\n    research_panels(df, max_rows=4, max_fields=6)\n    with st.expander("Raw Macro Context", expanded=False):\n        table(df, 280)\n    source("Macro Context", src)\n',
    "Macro Context",
)

patched = replace_once(
    patched,
    '    st.dataframe(pd.DataFrame(comparison_rows), use_container_width=True, hide_index=True)\n    st.caption("Unavailable or not-yet-published reports remain unavailable; they are never converted into neutral evidence.")\n',
    '    comparison_df = pd.DataFrame(comparison_rows)\n    research_panels(comparison_df, max_rows=3, max_fields=6)\n    with st.expander("Raw communication comparison", expanded=False):\n        table(comparison_df, 260)\n    st.caption("Unavailable or not-yet-published reports remain unavailable; they are never converted into neutral evidence.")\n',
    "Fed communication comparison",
)

patched = replace_once(
    patched,
    '    st.subheader("Published Event Study Evidence")\n    table(summary, 560)\n    source("Event Study Summary", summary_src)\n    table(adequacy, 360)\n    source("Event Study Adequacy", adequacy_src)\n    table(overlap, 360)\n    source("Event Study Overlap", overlap_src)\n',
    '    st.subheader("Published Event Study Evidence")\n\n    st.markdown("**Event / Horizon Summary**")\n    research_panels(summary, max_rows=6, max_fields=5)\n    with st.expander("Raw Event Study Summary", expanded=False):\n        table(summary, 560)\n    source("Event Study Summary", summary_src)\n\n    st.markdown("**Sample Adequacy**")\n    research_panels(adequacy, max_rows=6, max_fields=5)\n    with st.expander("Raw Sample Adequacy", expanded=False):\n        table(adequacy, 360)\n    source("Event Study Adequacy", adequacy_src)\n\n    st.markdown("**Event Overlap**")\n    research_panels(overlap, max_rows=6, max_fields=5)\n    with st.expander("Raw Event Overlap", expanded=False):\n        table(overlap, 360)\n    source("Event Study Overlap", overlap_src)\n',
    "Historical Edge",
)

patched = replace_once(
    patched,
    '    if isinstance(quality,pd.DataFrame):\n        st.subheader("Remaining-Layer Quality Contract")\n        table(quality,420); source("Remaining Layers Quality",qsrc)\n',
    '    if isinstance(quality,pd.DataFrame):\n        st.subheader("Remaining-Layer Quality Contract")\n        research_panels(quality, max_rows=6, max_fields=5)\n        with st.expander("Raw Remaining-Layer Quality Contract", expanded=False):\n            table(quality,420)\n        source("Remaining Layers Quality",qsrc)\n',
    "Data Status quality",
)

patched = replace_once(
    patched,
    '    table(pd.DataFrame(rows), 650)\n\n    configured_files = set(DATASETS.values())\n',
    '    status_df = pd.DataFrame(rows)\n    st.subheader("Publication Map")\n    research_panels(status_df, max_rows=9, max_fields=3)\n    with st.expander("Raw dataset publication map", expanded=False):\n        table(status_df, 650)\n\n    configured_files = set(DATASETS.values())\n',
    "Data Status publication map",
)

patched = replace_once(
    patched,
    '        st.dataframe(\n            pd.DataFrame({"File": extra_published}),\n            use_container_width=True,\n            hide_index=True,\n        )\n',
    '        extra_df = pd.DataFrame({"File": extra_published})\n        research_panels(extra_df, max_rows=9, max_fields=1)\n        with st.expander("Raw unmapped artifact list", expanded=False):\n            table(extra_df, 360)\n',
    "Data Status unmapped artifacts",
)

explorer_start = patched.index("def explorer() -> None:")
methodology_start = patched.index("def methodology() -> None:")
if "research_panels(" in patched[explorer_start:methodology_start]:
    die("Safety check failed: Data Explorer was unexpectedly converted.")

if patched == original:
    die("No changes were produced.")

tmp = Path("app.py.patch4_corrected.tmp")
tmp.write_text(patched, encoding="utf-8")
try:
    py_compile.compile(str(tmp), doraise=True)
except Exception as exc:
    tmp.unlink(missing_ok=True)
    die(f"Patched Python syntax failed before app.py replacement: {exc}")

tmp.replace(APP)
try:
    py_compile.compile(str(APP), doraise=True)
except Exception as exc:
    APP.write_text(original, encoding="utf-8")
    die(f"Post-write syntax verification failed; app.py restored. {exc}")

print("PATCH 4 CORRECTED APPLIED SUCCESSFULLY")
print("Presentation-only targets updated: Research Context, Macro Context, Fed comparison, Historical Edge, Data Status.")
print("Existing dynamic views retained: Event / News, Earnings, Historical Event Study, Final Validation.")
print("Data Explorer remains raw/tabular by design.")
print("Backend / PIT / scoring / governance were not modified by this patch.")
