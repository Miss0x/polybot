# Polybot Week 4 Product Experiment Report

**Generated at:** 2026-04-27T02:02:07.782751+00:00

## Summary
- Markets processed: 6
- Alerts generated: 3
- Watch items: 0
- Low confidence items: 2

## Market 1: 1919421

**Question:** US x Iran permanent peace deal by April 30, 2026?
**Current YES:** 2%

**View:** lower
**Confidence:** high
**Should Alert:** Yes
**Severity:** warning

### Alert Draft
```text
Market: US x Iran permanent peace deal by April 30, 2026?

Current YES: 2%

View: YES probability may fall

Confidence: High

Reason: Matched 37 news items in the window: direct=2, context=35, neutral=2. Only direct evidence contributes to core strength: positive 0.00, negative 2.00. Top 2 direct key news by relevance: "‘State of war’: Why Israel has escalated attacks i"; "Lebanon accuses Israel of targeting journalist kil".

Key News:
  1. ▼ [0.95] ‘State of war’: Why Israel has escalated attacks in Gaza
     → event_type=war_declared × market_condition=permanent_peace_deal; evidence=direct; strength=strong; d
  2. ▼ [0.95] Lebanon accuses Israel of targeting journalist killed in air strike
     → event_type=military_strike × market_condition=permanent_peace_deal; evidence=direct; strength=strong

Risk Notes:
  - Most matched news is context-level background; avoid treating it as a strong alert signal.
```

## Market 2: 1707932

**Question:** Will the Iranian regime fall by May 31?
**Current YES:** 4%

**View:** higher
**Confidence:** medium
**Should Alert:** No
**Severity:** info

### Alert Draft
```text
Market: Will the Iranian regime fall by May 31?

Current YES: 4%

View: YES probability may rise

Confidence: Medium

Reason: Matched 3 news items in the window: direct=1, context=2, neutral=2. Only direct evidence contributes to core strength: positive 1.00, negative 0.00. Top 1 direct key news by relevance: "Couple discovers Lebanon home destroyed by Israel ".

Key News:
  1. ▲ [0.95] Couple discovers Lebanon home destroyed by Israel from satellite image
     → event_type=regime_change × market_condition=regime_fall; evidence=direct; strength=strong; direction

Risk Notes:
  - Most matched news is context-level background; avoid treating it as a strong alert signal.
  - A large share of matched news is directionally neutral; signals may be noisy.
```

## Market 3: 1959320

**Question:** US x Iran diplomatic meeting by April 30, 2026?
**Current YES:** 17%

**View:** higher
**Confidence:** high
**Should Alert:** Yes
**Severity:** warning

### Alert Draft
```text
Market: US x Iran diplomatic meeting by April 30, 2026?

Current YES: 17%

View: YES probability may rise

Confidence: High

Reason: Matched 28 news items in the window: direct=11, context=17, neutral=1. Only direct evidence contributes to core strength: positive 8.60, negative 1.60. Top 3 direct key news by relevance: "‘State of war’: Why Israel has escalated attacks i"; "US-Iran conflict: What’s the latest as the Islamab"; "Trump cancels US envoys' trip to Pakistan for talk".

Key News:
  1. ▼ [0.95] ‘State of war’: Why Israel has escalated attacks in Gaza
     → event_type=war_declared × market_condition=diplomatic_meeting; evidence=direct; strength=strong; dir
  2. ▲ [0.95] US-Iran conflict: What’s the latest as the Islamabad talks stall?
     → event_type=diplomatic_contact × market_condition=diplomatic_meeting; evidence=direct; strength=stron
  3. ▲ [0.95] Trump cancels US envoys' trip to Pakistan for talks on Iran war
     → event_type=diplomatic_contact × market_condition=diplomatic_meeting; evidence=direct; strength=stron

Risk Notes:
  - Most matched news is context-level background; avoid treating it as a strong alert signal.
```

## Market 4: 1517835

**Question:** Trump announces end of military operations against Iran by April 30th?
**Current YES:** 4%

**View:** unchanged
**Confidence:** low
**Should Alert:** No
**Severity:** info

### Alert Draft
```text
Market: Trump announces end of military operations against Iran by April 30th?

Current YES: 4%

View: No clear probability change yet

Confidence: Low

Reason: Matched 0 news items in the window: direct=0, context=0, neutral=0. Only direct evidence contributes to core strength: positive 0.00, negative 0.00. No direct news reached the key-news relevance threshold. Context signals may describe the background but are not enough for an alert. Direct aggregate signal strength is below the actionable threshold.

Key News:
  None strong enough for direct alert.

Risk Notes:
  - Direct signal strength is very low; current price may not reflect recent news.
```

## Market 5: 1919425

**Question:** US x Iran permanent peace deal by May 31, 2026?
**Current YES:** 31%

**View:** lower
**Confidence:** high
**Should Alert:** Yes
**Severity:** warning

### Alert Draft
```text
Market: US x Iran permanent peace deal by May 31, 2026?

Current YES: 31%

View: YES probability may fall

Confidence: High

Reason: Matched 37 news items in the window: direct=2, context=35, neutral=2. Only direct evidence contributes to core strength: positive 0.00, negative 2.00. Top 2 direct key news by relevance: "‘State of war’: Why Israel has escalated attacks i"; "Lebanon accuses Israel of targeting journalist kil".

Key News:
  1. ▼ [0.95] ‘State of war’: Why Israel has escalated attacks in Gaza
     → event_type=war_declared × market_condition=permanent_peace_deal; evidence=direct; strength=strong; d
  2. ▼ [0.95] Lebanon accuses Israel of targeting journalist killed in air strike
     → event_type=military_strike × market_condition=permanent_peace_deal; evidence=direct; strength=strong

Risk Notes:
  - Most matched news is context-level background; avoid treating it as a strong alert signal.
```

## Market 6: 1611267

**Question:** Kharg Island no longer under Iranian control by April 30?
**Current YES:** 3%

**View:** unchanged
**Confidence:** low
**Should Alert:** No
**Severity:** info

### Alert Draft
```text
Market: Kharg Island no longer under Iranian control by April 30?

Current YES: 3%

View: No clear probability change yet

Confidence: Low

Reason: Matched 0 news items in the window: direct=0, context=0, neutral=0. Only direct evidence contributes to core strength: positive 0.00, negative 0.00. No direct news reached the key-news relevance threshold. Context signals may describe the background but are not enough for an alert. Direct aggregate signal strength is below the actionable threshold.

Key News:
  None strong enough for direct alert.

Risk Notes:
  - Direct signal strength is very low; current price may not reflect recent news.
```
