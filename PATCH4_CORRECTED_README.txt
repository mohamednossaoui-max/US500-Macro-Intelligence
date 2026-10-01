US500 V6.3 — Corrected Patch 4

Files:
- apply_patch4_corrected.py
- .github/workflows/apply-patch4-corrected.yml

GitHub:
1. Add apply_patch4_corrected.py beside app.py.
2. Add the workflow under .github/workflows/.
3. Commit both.
4. Actions > Apply Corrected Patch 4 > Run workflow.

Safety gate:
fa65e47102e8509e4c841e66d317768fea307ce12c00c3da8c9f23eed58b7298

The script preserves an existing app.py.pre_patch4 and never overwrites it.
