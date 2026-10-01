from pathlib import Path
import shutil
import sys

path = Path("app.py")
if not path.exists():
    raise SystemExit("ERROR: app.py not found in the current directory.")

text = path.read_text(encoding="utf-8")

pairs = [
    (
        '    def _direction(value: Any) -> tuple[str, str]:\n'
        '        if not isinstance(value, (int, float)):\n'
        '            return "—", "Unavailable"\n'
        '        if value >= 0.15:\n'
        '            return "↑", "Positive directional pressure"\n'
        '        if value <= -0.15:\n'
        '            return "↓", "Negative directional pressure"\n'
        '        return "→", "Near neutral"',
        '    def _direction(value: Any) -> str:\n'
        '        if not isinstance(value, (int, float)):\n'
        '            return "Unavailable"\n'
        '        if value >= 0.15:\n'
        '            return "Positive directional pressure"\n'
        '        if value <= -0.15:\n'
        '            return "Negative directional pressure"\n'
        '        return "Near neutral"'
    ),
    (
        '        arrow, _ = _direction(data["score"])\n'
        '        score_text = f"{data[\'score\']:+.2f}" if isinstance(data["score"], (int, float)) else "—"\n'
        '        headline_parts.append(f"{name} {arrow} {score_text}")',
        '        score_text = f"{data[\'score\']:+.2f}" if isinstance(data["score"], (int, float)) else "—"\n'
        '        headline_parts.append(f"{name} {score_text}")'
    ),
    (
        '            arrow = "▲" if isinstance(shock, (int, float)) and not pd.isna(shock) and shock > 0 else "▼" if isinstance(shock, (int, float)) and not pd.isna(shock) and shock < 0 else "→"\n'
        '            delta_text = f"{delta:+.1f}" if isinstance(delta, (int, float)) and not pd.isna(delta) else "—"',
        '            delta_text = f"{delta:+.1f}" if isinstance(delta, (int, float)) and not pd.isna(delta) else "—"'
    ),
    (
        '                    f"<div class=\'signal-main\'>{fmt(previous, 1)} → {fmt(actual, 1)} &nbsp; {arrow} {delta_text}</div>"',
        '                    f"<div class=\'signal-main\'>{fmt(previous, 1)} to {fmt(actual, 1)} &nbsp; Δ {delta_text}</div>"'
    ),
    (
        '        arrow, direction = _direction(data["score"])',
        '        direction = _direction(data["score"])'
    ),
    (
        '                f"<div class=\'score\'>{arrow} {score_text}</div>"',
        '                f"<div class=\'score\'>{score_text}</div>"'
    ),
    (
        '            arrow = "▲" if delta > 0 else "▼" if delta < 0 else "→"\n'
        '            if key == "unemployment":',
        '            if key == "unemployment":'
    ),
    (
        '                    f"<div class=\'signal-main\'>{fmt(prev,1)} → {fmt(cur,1)} &nbsp; {arrow} {delta:+.1f}</div>"',
        '                    f"<div class=\'signal-main\'>{fmt(prev,1)} to {fmt(cur,1)} &nbsp; Δ {delta:+.1f}</div>"'
    ),
    (
        '        timeline_bits.append(f"{label} {\'✓\' if payload.get(\'available\') else \'⏳\'}")\n'
        '    st.markdown(f"<div class=\'timeline\'>{\' &nbsp; ─── &nbsp; \'.join(timeline_bits)}</div>", unsafe_allow_html=True)',
        '        status = "AVAILABLE" if payload.get("available") else "PENDING"\n'
        '        timeline_bits.append(f"{label} · {status}")\n'
        '    st.markdown(\n'
        '        f"<div class=\'timeline\'>{\' &nbsp; · &nbsp; \'.join(timeline_bits)}</div>",\n'
        '        unsafe_allow_html=True,\n'
        '    )'
    ),
    (
        '        arrow = "▲" if isinstance(delta, (int, float)) and delta > 0 else "▼" if isinstance(delta, (int, float)) and delta < 0 else "→"\n'
        '        delta_text = f"{delta:+.1f}" if isinstance(delta, (int, float)) else "—"',
        '        delta_text = f"{delta:+.1f}" if isinstance(delta, (int, float)) else "—"'
    ),
    (
        '            f"<span class=\'pulse-value\'>{fmt(prev,1)} → {fmt(cur,1)} &nbsp; {arrow}</span>"',
        '            f"<span class=\'pulse-value\'>{fmt(prev,1)} to {fmt(cur,1)}</span>"'
    ),
    (
        '    \'<div class="hero"><h1>US500 Macro Intelligence — Research Terminal V6.2</h1>\'',
        '    f\'<div class="hero"><h1>US500 Macro Intelligence — Research Terminal {APP_VERSION}</h1>\''
    ),
]

missing = [old.splitlines()[0] for old, _ in pairs if old not in text]
if missing:
    print("SAFETY STOP: expected V6.3 blocks do not all match.")
    print("No file was changed.")
    for item in missing:
        print("MISSING:", item)
    sys.exit(2)

backup = Path("app.py.pre_patch3")
if not backup.exists():
    shutil.copy2(path, backup)

for old, new in pairs:
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("PATCH 3 APPLIED SAFELY")
print("Backup: app.py.pre_patch3")
print("Changed: app.py")
