US500 Macro Intelligence — UI Hotfix Only

Files included:
- app.py
- ui_v3.py

Fixes:
1. Keeps the existing Decision Engine / Research Gate / Fed Intelligence logic unchanged.
2. Keeps the dynamic_card import/function wiring intact (fixes the Sentiment Intelligence crash path shown previously).
3. Replaces white Streamlit dataframe surfaces with deterministic dark institutional HTML tables.
4. Applies the same dark table treatment to Fed comparison/SEP tables and Data Status tables.
5. Adds dark chart-container styling and preserves the V3 cards, alerts, ranking, hover and typography layer.

Validation performed:
- Python syntax compile: PASS
- Repository test suite: 91 passed

Deployment:
Replace ONLY app.py and ui_v3.py in the repository with these files.
Do not delete public_data or any research/decision engine modules.
