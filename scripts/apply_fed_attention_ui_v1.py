"""Patch the user's current app in place, with backup and strict scope guards."""
import argparse
import ast
from pathlib import Path

IMPORT = 'from executive_attention_v1 import attention_rows, decision_explanation\n'
MARKER = '        # FED_ATTENTION_UI_V1: presentation only; published state unchanged.\n'
BLOCK = '''        # FED_ATTENTION_UI_V1: presentation only; published state unchanged.
        ui_section("Evidence Attention Order", "CORE + FED CONTEXT")
        core_records = evidence.to_dict("records") if isinstance(evidence, pd.DataFrame) and not evidence.empty else []
        for i, row in enumerate(attention_rows(core_records, fed_obj), 1):
            rank_item(i, str(row.get("source", row.get("category", "Evidence"))), row.get("stance", "—"), str(row.get("reason", "")))
        if core_records:
            st.caption(decision_explanation(core_records, safe_value(dec_row, ["state"])))
        else:
            st.info("Decision evidence artifact is not available; only independent Fed context is displayed.")
        st.caption("Attention order is visual only: contradictory → mixed → supportive → contextual. It does not change CORE eligibility, weights or state.")
'''


def patch(source):
    ast.parse(source)
    if MARKER in source:
        if IMPORT not in source: raise ValueError('Partial patch detected; restore backup before proceeding')
        return source
    start = source.index('def executive()')
    end = source.find('\ndef ', start + 1)
    end = len(source) if end == -1 else end
    a = source.index('        ui_section("Evidence Attention Order", "CORE EVIDENCE")', start, end)
    b = source.index('    with right:', a, end)
    old = source[a:b]
    for expected in ('view = evidence.copy()', 'rank_item(', 'CORE eligibility, weights or state.'):
        if expected not in old: raise ValueError('Dashboard structure changed; current app requires manual review')
    # Import after the future directive so both Python 3.11 and 3.12 can compile it.
    future = 'from __future__ import annotations\n'
    if future not in source: raise ValueError('Expected future import not found; no file changed')
    result = source[:a] + BLOCK + source[b:]
    result = result.replace(future, future + IMPORT, 1)
    ast.parse(result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    root = Path(args.root)
    if not (root / 'executive_attention_v1.py').is_file(): raise SystemExit('Missing executive_attention_v1.py')
    target = root / 'app.py'
    source = target.read_text(encoding='utf-8')
    try: updated = patch(source)
    except (ValueError, SyntaxError) as exc: raise SystemExit(f'No files changed: {exc}')
    if updated == source:
        print('Already applied; no changes.')
        return
    backup = root / 'app.py.before-fed-attention.bak'
    if backup.exists(): raise SystemExit('Backup already exists; no files changed. Review the existing backup first.')
    backup.write_bytes(target.read_bytes())
    temp = root / 'app.py.fed-attention.tmp'
    temp.write_text(updated, encoding='utf-8')
    temp.replace(target)
    print('Updated app.py; backup: app.py.before-fed-attention.bak. Decision Engine and public_data unchanged.')


if __name__ == '__main__':
    main()
