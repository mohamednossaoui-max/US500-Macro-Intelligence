Fed UI restore: replace app.py and fed_report_comparison_ui_v2.py in the repository root.
Restores the previous Policy Pulse gauge, decision brief, bottom-line card, compact communication cards and synthesis progress bars.
Full current/previous report comparisons remain available inside closed expanders.
No fetching, parsing, date provenance, data snapshots, or other application pages are rolled back.
Validation: 76 tests passed; Fed page AppTest renders without exceptions.
Then run the existing Fed data workflow. This package does not publish or push changes itself.
