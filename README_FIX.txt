Macro Context + Economic Intelligence hardening — corrected files only

Changes:
- Dimension sufficiency now counts independent indicator families, not raw variants.
- CPI + Core CPI alone no longer masquerade as two independent inflation inputs.
- Inflation/Labor/Growth require >=2 fresh independent families before a dimension score is eligible.
- GDP revision gate strengthened: SAME_PERIOD_REVISION must be regime_eligible=False; NEW_PERIOD_RELEASE must be True.
- No Decision Engine, Fed Intelligence, UI, PIT contract, or public_data files changed.

Validation: 93 passed, 0 failed; Python compilation PASS.
