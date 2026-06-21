# Polybot Week 4 Product Experiment Report

**Generated at:** 2026-04-24T21:34:57.379092+00:00

## Summary
- Markets processed: 5
- Alerts generated: 5
- Watch items: 0
- Low confidence items: 0

## Market 1: test_phase1_market_001

**Question:** Will Iran attack Israel by June 2025?
**Current YES:** N/A

**View:** lower
**Confidence:** high
**Should Alert:** Yes
**Severity:** warning

### Alert Draft
```text
Market: Will Iran attack Israel by June 2025?

Current YES: N/A

View: YES probability may fall

Confidence: High

Reason: Matched 31 news items in the window: positive strength 0.85, negative strength 7.85, neutral 21. Top 3 key news by relevance: "Number of amputees set to rise in Gaza as Israel b"; "Explosions by Israeli forces in south Lebanon desp"; "Does Israel’s ‘Yellow Line’ violate the Lebanon ce".

Key News:
  1. ○ [0.90] Number of amputees set to rise in Gaza as Israel blocks aid, NGO warns
     → [C] alias hit: ['israel']; subject+object: ['israel']+['israel']; dedicated entity: ['israel']
  2. ▼ [0.90] Explosions by Israeli forces in south Lebanon despite ceasefire
     → [C] alias hit: ['israel', 'israeli']; subject+object: ['israel']+['israel']; dedicated entity: ['isr
  3. ▼ [0.90] Does Israel’s ‘Yellow Line’ violate the Lebanon ceasefire?
     → [C] alias hit: ['israel']; subject+object: ['israel']+['israel']; dedicated entity: ['israel']

Risk Notes:
  - A large share of matched news is directionally neutral; signals may be noisy.
```

## Market 2: 3719

**Question:** Will an election for the Israeli Knesset occur before August 1, 2022?
**Current YES:** 0%

**View:** lower
**Confidence:** high
**Should Alert:** Yes
**Severity:** warning

### Alert Draft
```text
Market: Will an election for the Israeli Knesset occur before August 1, 2022?

Current YES: 0%

View: YES probability may fall

Confidence: High

Reason: Matched 31 news items in the window: positive strength 0.85, negative strength 7.60, neutral 21. Top 3 key news by relevance: "Number of amputees set to rise in Gaza as Israel b"; "Explosions by Israeli forces in south Lebanon desp"; "Does Israel’s ‘Yellow Line’ violate the Lebanon ce".

Key News:
  1. ○ [0.90] Number of amputees set to rise in Gaza as Israel blocks aid, NGO warns
     → [C] alias hit: ['israel']; subject+object: ['israel']+['israel']; dedicated entity: ['israel']
  2. ▼ [0.90] Explosions by Israeli forces in south Lebanon despite ceasefire
     → [C] alias hit: ['israeli', 'israel']; subject+object: ['israel', 'israeli']+['israel']; dedicated en
  3. ▼ [0.90] Does Israel’s ‘Yellow Line’ violate the Lebanon ceasefire?
     → [C] alias hit: ['israel']; subject+object: ['israel']+['israel']; dedicated entity: ['israel']

Risk Notes:
  - A large share of matched news is directionally neutral; signals may be noisy.
```

## Market 3: 4172

**Question:** Will Benjamin Netanyahu remain prime minister of Israel through June 30, 2021?
**Current YES:** 0%

**View:** lower
**Confidence:** high
**Should Alert:** Yes
**Severity:** warning

### Alert Draft
```text
Market: Will Benjamin Netanyahu remain prime minister of Israel through June 30, 2021?

Current YES: 0%

View: YES probability may fall

Confidence: High

Reason: Matched 31 news items in the window: positive strength 0.80, negative strength 7.60, neutral 21. Top 3 key news by relevance: "Number of amputees set to rise in Gaza as Israel b"; "Explosions by Israeli forces in south Lebanon desp"; "Does Israel’s ‘Yellow Line’ violate the Lebanon ce".

Key News:
  1. ○ [0.90] Number of amputees set to rise in Gaza as Israel blocks aid, NGO warns
     → [C] alias hit: ['israel']; subject+object: ['israel']+['israel']; dedicated entity: ['israel']
  2. ▼ [0.90] Explosions by Israeli forces in south Lebanon despite ceasefire
     → [C] alias hit: ['israel', 'israeli']; subject+object: ['israel']+['israel']; dedicated entity: ['isr
  3. ▼ [0.90] Does Israel’s ‘Yellow Line’ violate the Lebanon ceasefire?
     → [C] alias hit: ['israel']; subject+object: ['israel']+['israel']; dedicated entity: ['israel']

Risk Notes:
  - A large share of matched news is directionally neutral; signals may be noisy.
```

## Market 4: 10083

**Question:** Israel ground offensive in Rafah by April 30?
**Current YES:** 0%

**View:** lower
**Confidence:** high
**Should Alert:** Yes
**Severity:** warning

### Alert Draft
```text
Market: Israel ground offensive in Rafah by April 30?

Current YES: 0%

View: YES probability may fall

Confidence: High

Reason: Matched 31 news items in the window: positive strength 0.80, negative strength 7.60, neutral 21. Top 3 key news by relevance: "Number of amputees set to rise in Gaza as Israel b"; "Explosions by Israeli forces in south Lebanon desp"; "Does Israel’s ‘Yellow Line’ violate the Lebanon ce".

Key News:
  1. ○ [0.90] Number of amputees set to rise in Gaza as Israel blocks aid, NGO warns
     → [C] alias hit: ['israel']; subject+object: ['israel']+['israel']; dedicated entity: ['israel']
  2. ▼ [0.90] Explosions by Israeli forces in south Lebanon despite ceasefire
     → [C] alias hit: ['israel', 'israeli']; subject+object: ['israel']+['israel']; dedicated entity: ['isr
  3. ▼ [0.90] Does Israel’s ‘Yellow Line’ violate the Lebanon ceasefire?
     → [C] alias hit: ['israel']; subject+object: ['israel']+['israel']; dedicated entity: ['israel']

Risk Notes:
  - A large share of matched news is directionally neutral; signals may be noisy.
```

## Market 5: 10084

**Question:** Will Israel invade Lebanon before May?
**Current YES:** 0%

**View:** lower
**Confidence:** high
**Should Alert:** Yes
**Severity:** warning

### Alert Draft
```text
Market: Will Israel invade Lebanon before May?

Current YES: 0%

View: YES probability may fall

Confidence: High

Reason: Matched 31 news items in the window: positive strength 0.80, negative strength 7.60, neutral 21. Top 3 key news by relevance: "Number of amputees set to rise in Gaza as Israel b"; "Explosions by Israeli forces in south Lebanon desp"; "Does Israel’s ‘Yellow Line’ violate the Lebanon ce".

Key News:
  1. ○ [0.90] Number of amputees set to rise in Gaza as Israel blocks aid, NGO warns
     → [C] alias hit: ['israel']; subject+object: ['israel']+['israel']; dedicated entity: ['israel']
  2. ▼ [0.90] Explosions by Israeli forces in south Lebanon despite ceasefire
     → [C] alias hit: ['israel', 'lebanon', 'israeli']; subject+object: ['israel']+['israel']; dedicated en
  3. ▼ [0.90] Does Israel’s ‘Yellow Line’ violate the Lebanon ceasefire?
     → [C] alias hit: ['israel', 'lebanon']; subject+object: ['israel']+['israel', 'military']; dedicated e

Risk Notes:
  - A large share of matched news is directionally neutral; signals may be noisy.
```
