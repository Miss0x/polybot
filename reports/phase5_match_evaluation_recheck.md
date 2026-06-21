# Phase 5 Match Evaluation Baseline

- Board: `iran_conflict`
- Gold version: `phase5_baseline_v1`
- Total cases: **12**
- Passed: **12**
- Failed: **0**

## Metrics

| Metric | Value |
|---|---:|
| Matched accuracy | 100.00% |
| Event type accuracy | 100.00% |
| Evidence type accuracy | 100.00% |
| Direction accuracy | 100.00% |
| False positives | 0 |
| False negatives | 0 |

## Cases

| Case | Pass | Expected | Actual | Extracted events | Errors |
|---|---:|---|---|---|---|
| `peace_deal_direct_yes` | YES | matched=True; event=peace_deal_signed; evidence=direct; dir=1 | matched=True; event=peace_deal_signed; evidence=direct; dir=1 | diplomatic_contact, peace_deal_signed | - |
| `diplomatic_meeting_direct_yes` | YES | matched=True; event=diplomatic_contact; evidence=direct; dir=1 | matched=True; event=diplomatic_contact; evidence=direct; dir=1 | diplomatic_contact | - |
| `peace_deal_context_from_meeting` | YES | matched=True; event=diplomatic_contact; evidence=context; dir=1 | matched=True; event=diplomatic_contact; evidence=context; dir=1 | diplomatic_contact | - |
| `war_declaration_direct_yes` | YES | matched=True; event=war_declared; evidence=direct; dir=1 | matched=True; event=war_declared; evidence=direct; dir=1 | war_declared, domestic_political_change | - |
| `war_declaration_negative_for_peace` | YES | matched=True; event=war_declared; evidence=direct; dir=-1 | matched=True; event=war_declared; evidence=direct; dir=-1 | war_declared, domestic_political_change | - |
| `hormuz_direct_negative` | YES | matched=True; event=maritime_incident; evidence=direct; dir=-1 | matched=True; event=maritime_incident; evidence=direct; dir=-1 | maritime_incident, regime_change | - |
| `military_operations_end_direct_yes` | YES | matched=True; event=military_operations_end; evidence=direct; dir=1 | matched=True; event=military_operations_end; evidence=direct; dir=1 | military_operations_end | - |
| `regime_fall_direct_yes` | YES | matched=True; event=regime_change; evidence=direct; dir=1 | matched=True; event=regime_change; evidence=direct; dir=1 | regime_change | - |
| `nuclear_deal_direct_yes` | YES | matched=True; event=nuclear_deal; evidence=direct; dir=1 | matched=True; event=nuclear_deal; evidence=direct; dir=1 | nuclear_deal | - |
| `nuclear_weapon_direct_yes` | YES | matched=True; event=nuclear_development; evidence=direct; dir=1 | matched=True; event=nuclear_development; evidence=direct; dir=1 | nuclear_development | - |
| `gaza_war_irrelevant_to_us_iran_peace` | YES | matched=False; event=None; evidence=None; dir=0 | matched=False; event=None; evidence=None; dir=0 | war_declared | - |
| `lebanon_airstrike_irrelevant_to_regime_fall` | YES | matched=False; event=None; evidence=None; dir=0 | matched=False; event=None; evidence=None; dir=0 | military_strike | - |

## Failed Case Details

No failed cases.