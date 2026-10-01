from __future__ import annotations

import ast
import shutil
import sys
from pathlib import Path


APP = Path("app.py")
BACKUP = Path("app.py.pre_patch4")

PATCH_MARKER = "PATCH 4 CORRECTED — DYNAMIC FED PRESENTATION"


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_app() -> str:
    if not APP.exists():
        fail("app.py was not found.")

    text = APP.read_text(encoding="utf-8")

    required_fingerprints = [
        'APP_VERSION = "V6.3"',
        "def fed() -> None:",
        'st.subheader("Communication — Current vs Previous")',
        'st.subheader("Fed Synthesis")',
        'st.subheader("SEP Pulse — Current vs Previous")',
        'with st.expander("Complete Fed JSON")',
    ]

    missing = [item for item in required_fingerprints if item not in text]

    if missing:
        print("V6.3 fingerprint verification FAILED.")
        for item in missing:
            print(f"  MISSING: {item}")
        fail("app.py does not match the expected V6.3 Fed structure.")

    print("V6.3 fingerprint verification PASSED.")
    return text


def verify_python(text: str, label: str) -> None:
    try:
        ast.parse(text)
    except SyntaxError as exc:
        fail(
            f"{label} is not valid Python: "
            f"{exc.msg} at line {exc.lineno}, column {exc.offset}"
        )


def replace_once(
    text: str,
    start_marker: str,
    end_marker: str,
    replacement: str,
    label: str,
) -> str:
    start_count = text.count(start_marker)
    end_count = text.count(end_marker)

    if start_count != 1:
        fail(
            f"{label}: expected exactly one start marker, "
            f"found {start_count}."
        )

    if end_count != 1:
        fail(
            f"{label}: expected exactly one end marker, "
            f"found {end_count}."
        )

    start = text.index(start_marker)
    end = text.index(end_marker, start)

    if end <= start:
        fail(f"{label}: invalid marker order.")

    return text[:start] + replacement.rstrip() + "\n\n    " + text[end:]


def insert_css(text: str) -> str:
    if PATCH_MARKER in text:
        print("Patch 4 marker already exists; CSS insertion skipped.")
        return text

    anchor = (
        "@media(max-width:560px){.command-strip{grid-template-columns:1fr}"
        ".reaction-row{grid-template-columns:52px 1fr 66px}}\n"
    )

    if text.count(anchor) != 1:
        fail(
            "Could not uniquely locate the V6.3 CSS insertion anchor. "
            "No changes written."
        )

    css = r"""
/* PATCH 4 CORRECTED — DYNAMIC FED PRESENTATION */
.fed-compare-grid{
    display:grid;
    grid-template-columns:repeat(3,minmax(0,1fr));
    gap:10px;
    margin:.45rem 0 .9rem;
}

.fed-compare-card{
    border:1px solid rgba(128,140,155,.24);
    border-radius:13px;
    padding:13px 14px;
    background:linear-gradient(
        145deg,
        rgba(15,34,53,.92),
        rgba(7,20,33,.92)
    );
    min-height:138px;
}

.fed-compare-card .fc-title{
    font-size:.69rem;
    font-weight:900;
    letter-spacing:.065em;
    color:#9bb0c1;
    text-transform:uppercase;
    margin-bottom:9px;
}

.fed-compare-card .fc-tone{
    font-size:1.03rem;
    font-weight:900;
    margin-bottom:8px;
    overflow-wrap:anywhere;
}

.fed-compare-card .fc-row{
    display:flex;
    justify-content:space-between;
    gap:12px;
    padding:4px 0;
    border-bottom:1px solid rgba(128,140,155,.10);
    font-size:.76rem;
}

.fed-compare-card .fc-row:last-child{
    border-bottom:0;
}

.fed-compare-card .fc-k{
    color:#8298aa;
}

.fed-compare-card .fc-v{
    font-weight:800;
    text-align:right;
    overflow-wrap:anywhere;
}

.fed-compare-card .fc-change{
    margin-top:9px;
    padding-top:8px;
    border-top:1px solid rgba(128,140,155,.16);
    font-size:.76rem;
    font-weight:850;
}

@media(max-width:900px){
    .fed-compare-grid{
        grid-template-columns:1fr;
    }
}
"""

    return text.replace(anchor, anchor + css + "\n", 1)


def patch_fed_comparison(text: str) -> str:
    start_marker = (
        '    # --- Communication current vs previous -----------------------------\n'
    )

    end_marker = (
        '# --- Synthesis ------------------------------------------------------'
    )

    replacement = r'''    # --- Communication current vs previous -----------------------------
    # PATCH 4 CORRECTED — presentation only.
    # Published Fed values are displayed unchanged. No score, tone,
    # eligibility, PIT status, weighting, or governance state is recomputed.
    comparison = obj.get("communication_comparison") if isinstance(
        obj.get("communication_comparison"), dict
    ) else {}

    st.subheader("Communication — Current vs Previous")

    comparison_rows = []
    comparison_cards = []

    for key, label in (
        ("statement", "FOMC Statement"),
        ("minutes", "FOMC Minutes"),
        ("chair_press", "Press Conference"),
    ):
        item = comparison.get(key) if isinstance(
            comparison.get(key), dict
        ) else {}

        comp = item.get("comparison") if isinstance(
            item.get("comparison"), dict
        ) else {}

        previous_doc = item.get("previous") if isinstance(
            item.get("previous"), dict
        ) else {}

        current_doc = obj.get(
            "chair_press" if key == "chair_press" else key
        )
        current_doc = current_doc if isinstance(current_doc, dict) else {}

        current_date = item.get("current_date")
        previous_date = item.get("previous_date")
        current_tone = current_doc.get("tone", "UNAVAILABLE")
        previous_tone = previous_doc.get("tone", "UNAVAILABLE")
        change = comp.get("classification", "UNAVAILABLE")

        comparison_rows.append(
            {
                "Report": label,
                "Current": current_date,
                "Previous": previous_date,
                "Current tone": current_tone,
                "Previous tone": previous_tone,
                "Change": change,
            }
        )

        comparison_cards.append(
            "<div class='fed-compare-card'>"
            f"<div class='fc-title'>{fmt(label)}</div>"
            f"<div class='fc-tone'>{fmt(current_tone)}</div>"
            "<div class='fc-row'>"
            "<span class='fc-k'>Current</span>"
            f"<span class='fc-v'>{fmt(current_date)}</span>"
            "</div>"
            "<div class='fc-row'>"
            "<span class='fc-k'>Previous</span>"
            f"<span class='fc-v'>{fmt(previous_date)}</span>"
            "</div>"
            "<div class='fc-row'>"
            "<span class='fc-k'>Previous tone</span>"
            f"<span class='fc-v'>{fmt(previous_tone)}</span>"
            "</div>"
            f"<div class='fc-change'>CHANGE · {fmt(change)}</div>"
            "</div>"
        )

    st.markdown(
        "<div class='fed-compare-grid'>"
        + "".join(comparison_cards)
        + "</div>",
        unsafe_allow_html=True,
    )

    st.caption(
        "Unavailable or not-yet-published reports remain unavailable; "
        "they are never converted into neutral evidence."
    )

    # Raw tabular evidence remains available for audit, but is closed
    # by default so the primary interface stays dynamic and readable.
    with st.expander(
        "Raw communication comparison data",
        expanded=False,
    ):
        st.dataframe(
            pd.DataFrame(comparison_rows),
            use_container_width=True,
            hide_index=True,
        )

    '''

    return replace_once(
        text,
        start_marker,
        end_marker,
        replacement,
        "Fed communication comparison",
    )


def main() -> None:
    print("==============================================")
    print("US500 Macro Intelligence — Corrected Patch 4")
    print("Presentation-only Fed UI patch")
    print("==============================================")

    original = read_app()
    verify_python(original, "Original app.py")

    if PATCH_MARKER in original:
        print("PATCH 4 CORRECTED is already present.")
        print("No second modification will be applied.")
        raise SystemExit(0)

    # Backup BEFORE modification.
    shutil.copy2(APP, BACKUP)

    if not BACKUP.exists():
        fail("Backup creation failed.")

    backup_text = BACKUP.read_text(encoding="utf-8")

    if backup_text != original:
        fail("Backup verification failed.")

    print(f"Backup created: {BACKUP}")

    patched = insert_css(original)
    patched = patch_fed_comparison(patched)

    # Guardrails: research/data architecture must remain present.
    protected_fingerprints = [
        'APP_VERSION = "V6.3"',
        'DATASETS = {',
        '"Fed Intelligence": "fed_intelligence_output_v1.json"',
        "def get_manifest()",
        "def load_named(name: str)",
        "def fed() -> None:",
        'st.subheader("Policy Pulse")',
        'st.subheader("SEP Pulse — Current vs Previous")',
        'st.subheader("Fed Synthesis")',
        'st.subheader("Beige Book Context")',
        'with st.expander("Complete Fed JSON")',
    ]

    missing_after = [
        item for item in protected_fingerprints
        if item not in patched
    ]

    if missing_after:
        fail(
            "Post-patch structural verification failed: "
            + ", ".join(missing_after)
        )

    verify_python(patched, "Patched app.py")

    APP.write_text(patched, encoding="utf-8")

    written = APP.read_text(encoding="utf-8")
    verify_python(written, "Written app.py")

    if PATCH_MARKER not in written:
        fail("Patch marker was not written.")

    if (
        'with st.expander(\n'
        '        "Raw communication comparison data",\n'
        '        expanded=False,\n'
        '    ):'
        not in written
    ):
        fail("Closed raw-data expander was not installed.")

    print()
    print("PATCH 4 CORRECTED APPLIED SUCCESSFULLY")
    print(f"Backup: {BACKUP}")
    print("Changed area: Fed presentation only")
    print("Scoring / PIT / governance / loaders were not modified by this patch.")


if __name__ == "__main__":
    main()
