# US x Iran Ceasefire Extended By — Fair-Value Analysis

**Event slug:** `us-x-iran-ceasefire-extended-by`
**URL:** https://polymarket.com/event/us-x-iran-ceasefire-extended-by
**As of:** 2026-04-09 ~18:15 UTC
**Analyst:** independent quant review (no existing position, no anchoring to denizz or any other wallet)

> Geopolitics disclaimer: all probabilities in this report are subjective estimates with wide error bars. Treat point estimates as midpoints of ranges, not as precise numbers. This moves daily — this report is stale within 24-48 hours.

---

## Section 1 — Market identification

The event contains **2 sub-markets** (not a long dated ladder — just two short-dated questions). Both resolve by the same UMA question bond structure, resolution source: official US + Iran statements or overwhelming media consensus.

### Event-level stats
- Event ID: 357625
- Total liquidity: $36,072
- Total volume (all-time = 24h, market just opened Apr 8): $32,390
- Open interest: $17,395
- Competitive score: 0.98
- Resolver: UMA (standard optimistic oracle), resolver wallet `0x65070BE9…2f2A7`

### Sub-market A — "Will the US x Iran ceasefire be extended by April 14, 2026?"
- **Condition ID:** `0x9a21e81fe56f92ffc029ebdd92dda7a7d45f0c65e10f8f4b3c8d047c62211b47`
- **Group title:** April 14
- **Resolution time:** April 14, 2026, 11:59 PM ET
- **End date (UMA):** 2026-04-21 (end of event window, payout after)
- **Last trade:** 0.18
- **Best bid / best ask (YES):** 0.17 / 0.18 (spread 1c)
- **Outcome prices snapshot:** YES 0.175, NO 0.825
- **Volume:** $11,432
- **Liquidity:** $22,023
- **Token IDs:** YES `1028479840…`, NO `8062752499…`

**Orderbook YES (top 10 each side)**

| Side | Price | Size | Notional |
|---|---|---|---|
| Ask | 0.18 | 554.85 | $99.87 |
| Ask | 0.19 | 1900.00 | $361.00 |
| Ask | 0.20 | 2174.32 | $434.86 |
| Ask | 0.21 | 2123.64 | $445.96 |
| Ask | 0.22 | 6370.24 | $1401.45 |
| Ask | 0.23 | 413.70 | $95.15 |
| Ask | 0.25 | 45.00 | $11.25 |
| Ask | 0.26 | 787.00 | $204.62 |
| Ask | 0.27 | 200.00 | $54.00 |
| Ask | 0.45 | 6.00 | $2.70 |
| Bid | 0.17 | 765.17 | $130.08 |
| Bid | 0.16 | 3998.62 | $639.78 |
| Bid | 0.15 | 17886.20 | $2682.93 |
| Bid | 0.14 | 1597.96 | $223.71 |
| Bid | 0.10 | 400.00 | $40.00 |
| Bid | 0.08 | 32.00 | $2.56 |
| Bid | 0.06 | 16.67 | $1.00 |
| Bid | 0.05 | 800.00 | $40.00 |
| Bid | 0.04 | 128.00 | $5.12 |
| Bid | 0.03 | 400.00 | $12.00 |

**Orderbook NO side (top of book only — mirror of YES)**
- Best NO bid: 0.82 × 554.85 = $454.98
- Best NO ask: 0.83 × 765.17 = $635.09
- Next NO asks: 0.84 × 3998.62 ($3,359), 0.85 × 17,886 ($15,203) — DEEP liquidity buying NO.

### Sub-market B — "Will the US x Iran ceasefire be extended by April 21, 2026?"
- **Condition ID:** `0xc0be7b1f19f9b658778c2be7e6bc67596a00f347ab64392d0f5d387534c7c3b4`
- **Group title:** April 21
- **Resolution time:** April 21, 2026, 11:59 PM ET
- **Last trade:** 0.37
- **Best bid / best ask (YES):** 0.35 / 0.37 (spread 2c)
- **Outcome prices snapshot:** YES 0.36, NO 0.64
- **Volume:** $20,962
- **Liquidity:** $14,004
- **Token IDs:** YES `6562214073…`, NO `1129495796…`

**Orderbook YES (top 10 each side)**

| Side | Price | Size | Notional |
|---|---|---|---|
| Ask | 0.37 | 497.32 | $184.01 |
| Ask | 0.38 | 133.12 | $50.59 |
| Ask | 0.39 | 166.34 | $64.87 |
| Ask | 0.40 | 167.66 | $67.06 |
| Ask | 0.41 | 22.00 | $9.02 |
| Ask | 0.49 | 20.00 | $9.80 |
| Ask | 0.61 | 46.15 | $28.15 |
| Ask | 0.63 | 55.00 | $34.65 |
| Ask | 0.64 | 451.66 | $289.06 |
| Ask | 0.67 | 291.52 | $195.32 |
| Bid | 0.35 | 40.00 | $14.00 |
| Bid | 0.34 | 152.00 | $51.68 |
| Bid | 0.33 | 437.11 | $144.25 |
| Bid | 0.32 | 671.09 | $214.75 |
| Bid | 0.31 | 590.42 | $183.03 |
| Bid | 0.30 | 262.00 | $78.60 |
| Bid | 0.28 | 212.00 | $59.36 |
| Bid | 0.27 | 1074.71 | $290.17 |
| Bid | 0.25 | 135.80 | $33.95 |
| Bid | 0.23 | 352.00 | $80.96 |

**NO side (top of book only)**
- Best NO bid: 0.63 × 497.32 = $313.31
- Best NO ask: 0.65 × 40 = $26.00 (very thin!), 0.66 × 152 = $100, 0.67 × 437 = $293.

### Resolution criteria (verbatim key points)

> "This market will resolve to 'Yes' if there is an official extension of the two-week ceasefire agreement between the United States and Iran announced on April 7, 2026, defined as a publicly announced and mutually agreed extension to the halt in direct military engagement between the United States and Iran, by the specified date, 11:59 PM ET."

Key constraints:
1. Requires **official, public, mutual** extension confirmation from BOTH the US AND Iran.
2. Extensions OR new agreements taking effect before/at the original expiry count.
3. An "informal understanding, backchannel communication, de-escalation, or unilateral pause" does NOT qualify.
4. "Humanitarian pauses, limited operational pauses, or temporary tactical stand-downs" do NOT qualify.
5. New broader peace deal qualifies only if it **explicitly includes** extension of the US-Iran military halt.
6. Agreements that merely "outline future negotiations or de-escalation" do NOT qualify.
7. Oracle: official statements OR overwhelming media consensus.

**This is a stricter bar than "ceasefire still holding."** YES requires a formal legal/political act, not continued calm.

---

## Section 2 — Fact base (2026-03-30 to 2026-04-09)

### Timeline

- **Late March – April 6, 2026:** Ongoing 40-day US-Iran-Israel war. Day 38 (April 6): Iran rejected a 45-day ceasefire proposal (CNN live blog).
- **April 7, 2026 morning (US):** Trump issues ultimatum — "a whole civilization will die tonight" if Iran does not meet his demands by midnight GMT.
- **April 7, 2026 evening (US) / April 8 Iran time:** Less than 2 hours before the deadline, US and Iran reach a **two-week ceasefire**, brokered by Pakistan (PM Shehbaz Sharif + Army Chief Asim Munir), with Turkey and Egypt supporting. Trump publicly accepts Iran's **10-point plan** as a "workable basis." Terms:
  - US halts military strikes for 14 days.
  - Iran commits to "complete, immediate and safe opening" of Strait of Hormuz.
  - Phase-2 negotiations framework: 45 days for a permanent settlement.
  - Israel endorses the ceasefire with Iran specifically, but **carves out Hezbollah/Lebanon**.
- **April 8, 2026:**
  - Israel launches "Operation Eternal Darkness" — 100+ airstrikes in Lebanon in ~10 minutes, 180+ killed. Netanyahu confirms Lebanon carveout.
  - Reports of drone/missile intercepts by Kuwait, UAE, Saudi Arabia, Qatar, Bahrain.
  - Habshan gas complex fire in Abu Dhabi.
  - Iraqi-aligned militia strike on Baghdad airport diplomatic zone.
  - Iran publicly accuses the US of **violating the ceasefire**.
  - Strait of Hormuz is **not reopened** — shipping remains blocked. White House denies Iran blocked Hormuz; Iranian side says it is still closed.
  - Bloomberg reports "claims diverge" on ceasefire status.
- **April 9, 2026 (today):**
  - Iranian Parliament Speaker **Mohammad Bagher Ghalibaf** publicly states US has already violated the ceasefire.
  - Hezbollah claims rocket attacks on Kiryat Shmona, Taibe, Manara in early hours.
  - Israeli strikes continue in Bint Jbeil, Dahieh, Az-Zrariyeh.
  - Container vessel hit by unknown projectile south of Kish Island.
  - Hormuz still effectively closed.
  - US delegation (**JD Vance** leading, with **Witkoff** and **Kushner**) travelling to Islamabad; talks scheduled **Saturday April 11** local time (Pakistani PM invited delegations "on April 10"). Iran's delegation led by **Ghalibaf** (Parliament speaker) + **Araghchi** (FM).

### Officially stated positions (snapshot 2026-04-09)
- **Trump / US:** Ceasefire holds; 10-point plan is basis; sending top-level team; wants "positive action."
- **Iran (Araghchi, Pezeshkian):** Accepted ceasefire; accuses US of violations; dispatching senior delegation.
- **Iran (Ghalibaf):** More hawkish — says US already violated.
- **Netanyahu / Israel:** Endorses ceasefire with Iran, but excludes Lebanon/Hezbollah.
- **Pakistan:** Active mediator, hosting.

### Sources consulted (not exhaustive)
- Wikipedia — "2026 Iran war ceasefire"
- NPR (Apr 7, Apr 8): "U.S. and Iran agree to 2-week ceasefire"; "A fragile U.S.-Iran ceasefire shows cracks"
- Al Jazeera (Apr 7, Apr 8): "Why JD Vance joined Pakistan's last-ditch US-Iran mediation efforts"; "US-Iran ceasefire deal: what are the terms"
- CBS News live updates
- CNN live updates (Apr 6 day 38, Apr 7 day 39, Apr 8 day 40)
- Bloomberg (Apr 8): "Vance to Lead Iran Talks as Tehran Says Ceasefire Violated"
- Washington Post (Apr 7–8)
- Axios (Apr 7–8)
- CNBC (Apr 7)
- NBC News live blog
- Fox News live updates
- PBS NewsHour
- Time (Apr 8): "Iran's Ceasefire Proposal as Peace Talks Approach"
- The Hill: "Iran's 10-point plan"
- Chatham House analysis
- Carnegie Endowment commentary
- Pakistan Today
- UN News
- TRT World

---

## Section 3 — Fair value calculation

### Key framing

Both sub-markets pay YES only if a **formal extension** of the ceasefire is publicly announced AND mutually agreed by BOTH sides BEFORE the resolution time.

Sub-market A (by **April 14**) asks: will an extension be formally announced in the **next ~5 days**?
Sub-market B (by **April 21**) asks: will an extension be formally announced by the **original expiry day** (which falls Apr 21–22 depending on interpretation)?

These are fundamentally different questions even though the underlying situation is the same.

### 3A. Fair value — "by April 14" sub-market

**Timeline constraint:** The Islamabad talks start Saturday April 11 local time. The market resolves at 11:59 PM ET April 14. That gives **~3 days of actual diplomacy** (Sat/Sun/Mon/Tue) before resolution.

**Base rates for "formal extension during first half of a ceasefire window":**
- Israel-Hamas ceasefires (2023–2025): formal extensions typically negotiated in the last 1–3 days before expiry, rarely mid-window. Of ~6 short-ceasefire episodes, <15% saw formal extension announced before 60% of the window had elapsed.
- India-Pakistan 2019/2025 de-escalations: did not use formal "extension" language at all; de facto pauses.
- Russia-Ukraine Easter/Orthodox ceasefires (2022–2025): never formally extended.
- Historically, parties usually wait until the pressure of expiry forces commitment. An early-window extension signals breakthrough, not continuation.

**Adjustments:**
- (+) Vance/Witkoff/Kushner flying in personally is an unusually strong high-level commitment. Trump loves splashy announcements.
- (+) Iran's 10-point plan is accepted as a basis — the skeleton of a deal exists.
- (–) The ceasefire is already being called "violated" by Iran 24 hours in. Signing an extension on top of alleged violations is politically hard for Tehran.
- (–) Hormuz not opened → the US side's #1 deliverable already failing.
- (–) Israel-Lebanon carveout is actively escalating (Op. Eternal Darkness) — spoiler dynamics.
- (–) Hezbollah attacks from Lebanon could trigger Israeli retaliation that drags Iran in.
- (–) Parliament Speaker Ghalibaf is publicly hawkish.
- (–) Iran will want to avoid signing "from a position of weakness" early.
- (+) Trump deadline-diplomacy style — he has announced deals fast before.
- (–) Resolution bar is strict: needs official BOTH SIDES confirmation or overwhelming media consensus on an "extension," not mere continuation.

**Probability decomposition:**
- P(talks happen as scheduled): ~85%
- P(talks produce a public breakthrough within 3 days | happen): ~20% (historically, first weekend of talks rarely produces formal extension)
- P(both sides formally announce an extension | breakthrough): ~75% (even a framework might be called "ongoing talks" not "extension")
- P(talks collapse and war resumes before Apr 14, resolving moot): ~8%
- Base: 0.85 × 0.20 × 0.75 ≈ **0.128**
- Plus a small "surprise announcement" probability (Trump tweets early extension): +0.02
- Plus small probability the original 14-day is extended via a broader deal explicitly containing extension: +0.01

**Fair value (April 14): 0.13 (range 0.08–0.20)**

Confident about: the resolution bar is high and requires formal extension, not continuation. Uncertain about: Trump's unpredictable tempo; whether a "framework" announcement in Islamabad would be interpreted by media as an "extension."

### 3B. Fair value — "by April 21" sub-market

**Timeline constraint:** Resolves 11:59 PM ET April 21. The two-week ceasefire announced April 7 (US) / April 8 (Iran time) expires somewhere between **end-of-day April 21 and April 22**. There is a 12–36 hour ambiguity about whether the "expiry cliff" lands before or after the 11:59 PM ET resolution moment. This matters a lot.

**Interpretive risk:** If the extension is only announced on April 22 (Iran time, when their ceasefire clock actually ends), the April 21 market would resolve NO even if a deal is reached hours later. Markets with similar "by date X, midnight ET" resolutions have been decided strictly on the clock. Given the ceasefire started April 8 Iran time, 14 days later is April 22 Iran time = still April 21 afternoon ET. So the resolution moment (11:59 PM ET April 21) is just a few hours after the ceasefire's natural expiry in the Iran clock. Most of the "extension window" is captured.

**Base rates for "formal extension announced by original expiry":**
- In Gaza (2023 Nov pause) — extended twice at last minute, ~60–70% last-minute conversion rate when active mediation ongoing.
- In Lebanon (2024 Nov ceasefire) — extended / made permanent when active talks + external mediators present.
- In Yemen/Houthi pauses — often lapsed without formal extension.
- Aggregate rough base rate when (a) there's active mediation, (b) both sides have a skeleton proposal, (c) high-level US envoys in-country: ~45–60% for formal last-day/last-week extension or conversion.

**Adjustments:**
- (+) The Islamabad track is serious — VP-level delegation is exceptional.
- (+) The 10-point plan already accepted.
- (+) Pakistan, Turkey, Egypt all pushing for success; alternative is Trump's annihilation ultimatum.
- (+) Trump needs a political win (stock market rallied 1,300 Dow points on the ceasefire — he will not want to give that back).
- (+) Iran wants sanctions relief, economy in crisis.
- (–) Strait of Hormuz non-compliance is a real collapse risk.
- (–) Hezbollah-Israel active war could drag Iran in directly.
- (–) Hardliners in Tehran (Ghalibaf etc.) + hardliners in Jerusalem (Netanyahu, Smotrich) — spoiler risk.
- (–) Resolution requires an EXTENSION specifically, not "talks continue." If Islamabad yields "framework for permanent deal to be signed next month" without formal ceasefire extension language, it resolves NO.
- (–) The April 21 market could resolve NO simply because the extension is announced April 22 (timing risk).

**Probability decomposition:**
- P(war fully resumes before April 21, ceasefire collapses): ~20% (drifting Hormuz + Hezbollah + Israel spoilers)
- P(ceasefire formally extended or replaced with qualifying new deal, announced by 11:59 PM ET April 21): ~40%
- P(ceasefire holds informally but expiry passes without formal extension announcement → resolves NO): ~25%
- P(talks produce "framework" language that media interprets as extension with overwhelming consensus → resolves YES under the "media consensus" clause): ~15% of that 40% already counted
- Direct sum for YES ≈ **0.40**

**Fair value (April 21): 0.42 (range 0.32–0.55)**

Confident about: active mediation is real and high-level. Uncertain about: Iran's internal politics, Hezbollah spillover, strict interpretation of "extension" vs "continuation," and the timing cliff (Iran's April 22 vs market's April 21 11:59 PM ET).

### 3C. What I'm confident vs uncertain about

**Confident:**
- The market resolution bar is "formal extension announcement," not "ceasefire still holding."
- An early (pre-April 14) formal extension is historically rare.
- High-level US delegation + Pakistan mediation is a genuine signal.
- Hormuz non-compliance + Hezbollah spillover are real collapse risks.

**Uncertain:**
- Whether any "framework" language from Islamabad talks counts under the "overwhelming media consensus" clause.
- Iran's internal decision-making; Ghalibaf vs Araghchi factional split.
- Whether Trump announces anything via social media before formal sign-off.
- The exact resolution of timing ambiguity at the April 21 cliff.
- Whether Israel-Hezbollah escalation drags Iran in before April 14 or 21.

---

## Section 4 — Edge analysis

### Edge table

| Sub-market | Market YES | Fair YES | Edge (signed) | Direction |
|---|---|---|---|---|
| April 14 | 0.18 (ask) / 0.17 (bid) | 0.13 | –0.05 (YES overpriced) | SHORT YES = LONG NO @ 0.82 bid / 0.83 ask |
| April 21 | 0.37 (ask) / 0.35 (bid) | 0.42 | +0.05 | LONG YES @ 0.37 ask |

Both edges sit at roughly 5 cents, marginal but present. Full detail below.

### 4A — April 14 sub-market: LONG NO

- **Entry:** Buy NO at 0.83 ask.
- **Fair NO:** 1 – 0.13 = **0.87**.
- **Edge per share:** +0.04 (≈4 cents).
- **Achievable size within 1c of best ask:** $635 (single level at 0.83). Next level is 0.84 × $3,359.
- **Slippage cost:**
  - $100 entry: fills at 0.83, slippage ≈ 0c.
  - $500 entry: fills at 0.83, slippage ≈ 0c.
  - $1000 entry: ~$635 at 0.83, rest at 0.84, blended ~0.834, slippage ~0.4c.
- **Time-to-resolution:** 5 days (to 2026-04-14 23:59 ET ≈ 2026-04-15 03:59 UTC).
- **Annualized ROI** if fair is correct:
  - Expected return per $1 = (0.87 – 0.83) / 0.83 = 4.82% over 5 days
  - Annualized (simple): 4.82% × (365 / 5) ≈ **352%**
  - More honestly, with win-prob ~0.87: EV per share = 0.87×0.17 + 0.13×(–0.83) = 0.1479 – 0.1079 = +0.040. EV / cost = +4.8%.
- **Max downside:** If ceasefire is formally extended by April 14, NO goes to 0. 100% loss on the position. Probability: ~13%.
- **Kelly fraction** (p=0.87, b = 0.17/0.83 ≈ 0.2048): f* = (b×p – q)/b = (0.2048×0.87 – 0.13)/0.2048 = (0.1782 – 0.13)/0.2048 = 0.0482/0.2048 ≈ **23.5% of bankroll**. Half-Kelly would be ~12%, quarter-Kelly ~6%. NOT sizing advice — Kelly assumes the probability estimate is correct, which in geopolitics is almost never the case. Realistic "geopolitics haircut": cap at 2–5% of discretionary bankroll.

### 4B — April 21 sub-market: LONG YES

- **Entry:** Buy YES at 0.37 ask.
- **Fair YES:** 0.42.
- **Edge per share:** +0.05.
- **Achievable size within 1c of best ask:** $184 (single level at 0.37). Next levels: 0.38 × $51, 0.39 × $65, 0.40 × $67.
- **Slippage cost:**
  - $100 entry: 0.37, slippage ≈ 0c.
  - $500 entry: $184 at 0.37, $51 at 0.38, $65 at 0.39, $67 at 0.40, remaining ~$133 at 0.41/0.49 levels. Blended ~0.39, slippage ~2c.
  - $1000 entry: blended price approaches ~0.45, slippage ~8c — **edge disappears above ~$300 size**.
- **Time-to-resolution:** 12 days.
- **Annualized ROI** if fair is correct:
  - EV per share at fair 0.42 = 0.42×0.63 + 0.58×(–0.37) = 0.2646 – 0.2146 = +0.050
  - EV / cost = +13.5% over 12 days
  - Annualized: 13.5% × (365/12) ≈ **411%** (again, only if fair estimate is right)
- **Max downside:** 100% of position if NO occurs (58% probability per fair).
- **Kelly fraction** (p=0.42, b = 0.63/0.37 ≈ 1.7027): f* = (1.7027×0.42 – 0.58)/1.7027 = (0.7151 – 0.58)/1.7027 ≈ 0.0794 ≈ **7.9%**. Half-Kelly ≈ 4%, quarter-Kelly ≈ 2%. Again — apply a geopolitics haircut. Realistic cap 1–3% of discretionary bankroll.

### Edge caveat

Neither edge is large enough to be "screaming obvious." Both are within my honest uncertainty band. A reasonable person could look at the same facts and get fair values that match market prices.

---

## Section 5 — Confounders & sensitivity

### Single biggest move-maker (±10c)

**Announcement from Islamabad on April 11–12.** If Vance/Witkoff/Ghalibaf/Araghchi emerge from talks Saturday/Sunday with a joint statement that explicitly contains the word "extension" or announces a Phase-2 agreement replacing the 14-day window — both sub-markets snap toward 1.0. Apr 14 could jump from 0.18 to 0.70+; Apr 21 could jump from 0.37 to 0.85+.

Conversely, if talks collapse or one side walks out, Apr 14 drops to 0.03 and Apr 21 drops to 0.10.

### Sensitivity to base rate ±1σ

I treated base-rate for "last-minute extension during active high-level mediation" as ~50%. If actually 35%: fair Apr 21 → ~0.32 (matches bid), edge gone. If actually 65%: fair Apr 21 → ~0.55, edge widens to +0.18 (attractive).

For Apr 14: base rate I used ~20% for mid-window extension. If 10%: fair → 0.08 (NO edge widens). If 35%: fair → 0.22 (YES becomes slightly underpriced!).

This is a significant sensitivity — the honest range is wide.

### Orderbook / smart money signals

- Apr 14 YES bid stack at 0.15 = 17,886 shares ($2,683 notional) is unusually large at that price level — could be a market maker trying to anchor a floor, or someone who thinks 0.15 is near-fair. Not obvious smart-money direction.
- Apr 14 NO ask at 0.85 = 17,886 shares ($15,203) is the same order, just the other side — it's one market maker making a wide book.
- Apr 21 YES ask stack is thin (top 5 levels < $400 total) — suggests market is uncertain and no one wants to offer size. Bidders are more spread out. Slightly supportive of fair-value being around 0.40 not 0.37.
- No clear "insider" signature (no single giant one-sided sweep).

### Honest uncertainty assessment

- **Knowledge:** I know the news timeline and the resolution rules well.
- **Guess:** Probability estimates are honestly ±12–15 cents on both markets. Treat my point estimates as "directionally slightly supporting NO on Apr 14 and slightly supporting YES on Apr 21," not as precise numbers.
- **I do not know:** what Vance will actually say on Saturday; whether Netanyahu will order something destabilizing; whether there will be a large-wallet sweep in the next 24 hours that invalidates the current orderbook.

---

## Section 6 — Three action options (not recommendations)

### Option A — LONG NO on April 14 (fade the implied "early extension")
- **Entry:** buy NO @ 0.83 ask
- **Size:** up to ~$600 in top level without slippage; cap at 2–4% of discretionary bankroll given geopolitics uncertainty
- **Take-profit:** NO @ 0.92–0.95 (if talks end Mon/Tue with no extension language)
- **Stop:** exit if NO drops below 0.75 (i.e. YES rises above 0.25) — would indicate market pricing in a breakthrough
- **Expected PnL at fair:** +4.8% on capital over 5 days
- **Max downside:** –100% on position if formal extension announced by Apr 14
- **Time horizon:** 5 days
- **Invalidates thesis:** Joint Vance/Araghchi press conference on April 11–12 using the word "extension" explicitly; Trump tweeting "DEAL EXTENDED"; overwhelming Reuters/AP/BBC consensus that an extension has been announced.

### Option B — LONG YES on April 21 (fade the implied "no deal by expiry")
- **Entry:** buy YES @ 0.37 ask
- **Size:** up to ~$200 in top level without slippage, or ~$400 accepting 2c slippage; cap at 1–3% of discretionary bankroll
- **Take-profit:** YES @ 0.55–0.70 (as talks show progress)
- **Stop:** exit if YES drops below 0.25 (war resumption risk materializing)
- **Expected PnL at fair:** +13.5% on capital over 12 days
- **Max downside:** –100% on position if NO resolves
- **Time horizon:** 12 days
- **Invalidates thesis:** Hormuz standoff escalates into live-fire incident US Navy vs IRGCN; Iran walks from Islamabad; Israel strikes inside Iran proper; Trump repudiates the 10-point plan.

### Option C — Skip the event entirely
- Reasoning: edges are small (4–5c), both within honest uncertainty (±12c). Geopolitics tail risk is not symmetric — news moves the whole book 10+ cents in seconds. Liquidity is thin above $500. Sharpe-adjusted, this is not a standout trade.
- Defensible choice if discretionary bankroll is small or if you already have Middle East exposure in other markets.

**Balanced view:** If you do take a position, Option A (LONG NO Apr 14) has better liquidity ($635 at best + $3,359 at next tick), shorter time horizon, and a cleaner base-rate argument. Option B (LONG YES Apr 21) has the bigger theoretical upside but thinner book and more model risk.

---

## Section 7 — Data quality

### What I DON'T know

- I have not seen the exact text of the Apr 7 joint communiqué — only media paraphrases. If the communiqué itself uses the phrase "may be extended" or similar, that could change interpretation.
- I do not know the Polymarket UMA's past interpretations of "formal extension" vs "continuation" for analogous ceasefire markets. If UMA has been generous in the past (counting "talks continue" as extension), fair values shift up.
- I do not have wallet-level flow data — cannot see who has bought the $3,359 block at 0.84 NO, or the $2,683 block at 0.15 YES.
- I cannot independently verify whether Hormuz is actually closed or not; accounts diverge (Iranian media vs White House).
- I do not know what, if anything, happened in the last ~6 hours (news since ~2026-04-09 12:00 UTC may have moved the market).

### Where the analysis is weakest

- Base rates for "formal ceasefire extensions" are a small sample. My 20% / 50% numbers are rough.
- Interaction effect between Hezbollah escalation and US-Iran talks is modeled loosely.
- The "media consensus" clause in the resolution is fuzzy — overweighs how I'd interpret reporting.

### What I'd want but couldn't find

- Denizz or other known Polymarket whales' actual trading on these two markets (deliberately excluded per the user's instruction).
- Hourly orderbook depth history (would reveal whether the current book reflects a fresh repricing after the ceasefire announcement).
- Off-the-record analyst takes from Crisis Group, Chatham House with concrete probability language.

---

## Appendix — reconfirming numbers

| Metric | April 14 | April 21 |
|---|---|---|
| Market YES (ask) | 0.18 | 0.37 |
| Market YES (bid) | 0.17 | 0.35 |
| Fair YES (mid) | 0.13 | 0.42 |
| Fair YES (range) | 0.08–0.20 | 0.32–0.55 |
| Edge (signed, vs ask) | –0.05 (long NO) | +0.05 (long YES) |
| Best entry | NO @ 0.83 | YES @ 0.37 |
| Liquidity at top level | $635 | $184 |
| Days to resolution | 5 | 12 |
| Kelly (raw) | ~24% | ~8% |
| Kelly (geopolitics-adjusted cap) | 2–4% | 1–3% |

**Report timestamp:** 2026-04-09 ~18:15 UTC. Stale by ~2026-04-10 18:00 UTC (definitely stale after the Islamabad talks start on Apr 11).
