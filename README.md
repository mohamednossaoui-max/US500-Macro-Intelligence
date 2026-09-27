# US500 Dashboard Visual Upgrade V1

Chosen direction: **Hybrid of Option 1 + Option 4 + Option 6**.

- Option 1 supplies the professional dark research-terminal structure.
- Option 4 supplies dynamic cards, visual hierarchy and interaction.
- Option 6 supplies institutional contrast and dense evidence presentation.

## Safety / scope
This package is deliberately **UI-only**. It does not replace or modify:
Decision Engine logic, Research Gate semantics, PIT logic, evidence eligibility,
Fed Intelligence, published artifacts, forecasts/trading permissions, or existing tests.

## Files
- `ui/terminal_theme.py` — reusable Streamlit UI components.
- `ui/terminal_theme.css` — institutional dark theme.
- `dashboard_preview.py` — standalone preview/integration reference.

## Integration
1. Copy `ui/` into the repository root.
2. Import `apply_terminal_theme` in the existing `app.py`.
3. Call `apply_terminal_theme()` after `st.set_page_config(...)`.
4. Migrate the Executive Dashboard cards incrementally, keeping all existing data reads and state calculations unchanged.

Do **not** replace the current `app.py` with `dashboard_preview.py`; it is a visual preview/reference only.
