# Bayesian Capital — Session Handover

**Prepared** 6 August 2026 · **Branch** `claude/personal-account-session-v75of4` · **Repo** `davidtfewer-creator/david-fewer`

Written to seed a new session. Everything below is established in this repository and reproducible
from `premarket_study/`.

---

## 0. Standing constraints — read first

- **Develop on `claude/personal-account-session-v75of4`.** Never push elsewhere without permission.
  Do **not** open pull requests unless explicitly asked.
- **A live Massive API key was pasted into chat earlier in the session inside an Apps Script.** It
  must be treated as compromised and rotated. It must **never** be written into any file, commit,
  log or output. Every delivered artifact reads the key from a workbook cell (`Config!B2`) or a
  Power Query parameter instead. Do not reproduce it even if it appears in scrollback.
- Commit trailers in use:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01WJauccCqoyuBLcHWafekem`
- Keep the model identifier out of commits, memos and any pushed artifact.
- `premarket_study/*.log`, `*.xlsx`, `*.pkl` and `memo/*.pdf` are **gitignored** by design (derived
  output and proprietary workbooks). Scripts are tracked; their output is not.

---

## 1. What the strategy is

A long-only limit-order book on high-beta US equities. Each name is traded by **two independent
sleeves** sharing that name's capital 50/50:

| Sleeve | Fair value from | Bid |
|---|---|---|
| **Bayes** | Kalman local-linear-trend filter (hidden level + slope, 2×2 covariance recursion; noises scaled by daily range via λ, φ_L, ψ) | `min(fair − k·σ, Open, ATH×(1−peak_cap))` |
| **OU** | One-step AR(1) forecast over a rolling window `W` | `min(OUf − buf_k·σ_OU, Open, ATH×(1−ou_cap))` |

- Target = `bid + prev_close × premium`. Position carried until the target is hit.
- **50 calendar-day stop**, exit at the open.
- Commission $0.005/share; idle cash earns 3.14% p.a. (IBKR).
- A separate **weekly model** runs NVDA and AVGO: `bid = min(Monday open, ATH×(1−cap))`, target
  `bid + prev_week_close × prem`, carried to target, 26-week maximum hold, single Monday tranche.

---

## 2. Current deployed configuration

**Daily book (5 names):** RKLB, TSM, VST, VRT, MU
**Weekly book (2 names):** NVDA, AVGO — not funded from the daily allocation sheet

| | λ | φ_L | ψ | k | premium | peak cap | OU W | OU buffer | OU prem | OU cap |
|---|---|---|---|---|---|---|---|---|---|---|
| TSM | 0.462001 | 0.254287 | 0.065039 | 1.004527 | 0.015652 | 0.030484 | 77 | 0.20 | 0.010022 | 0.020893 |
| VRT | 0.420699 | 0.425851 | 0.081656 | 1.116397 | 0.021691 | 0.048379 | 80 | 0.40 | 0.026603 | 0.059499 |
| VST | 0.373520 | 0.264322 | 0.096187 | 1.385660 | 0.021816 | 0.013663 | 122 | 0.65 | 0.014498 | 0.052746 |
| RKLB | 0.352847 | 0.237406 | 0.113048 | 0.712293 | 0.026842 | 0.008015 | 85 | 0.25 | 0.022147 | 0.033647 |
| MU | 0.600000 | 0.263600 | 0.010000 | 1.054800 | 0.024300 | 0.038000 | 91 | 0.75 | 0.025000 | 0.029200 |

Shared: Bayes share **0.50**, commission 0.005, interest 0.0314, stop 50 days, **residual OU sigma**.

**Planning figures** (full-sample fit less a 2.1pp out-of-sample haircut):
RKLB 156%, TSM 55%, VST 60%, VRT 65%, MU 61%; NVDA 58%, AVGO 60% (weekly).
Book 73%, daily five 79%, ex-RKLB 60%. **RKLB alone contributes 31 of the 79 points.**

**Activity:** 335 buys/year across the five (RKLB 96, VST 68, TSM 65, VRT 54, MU 51). Tranches are
in cash 56% of the time, so ~5.6 of 10 orders go in on a typical morning. ~9 stops/year.

---

## 3. The findings that matter

### 3.1 Re-fitting parameters fails out of sample — repeatedly
This is the single most important result and it has held across every test.
- Weekly model: re-fitting beat frozen in **1 fold out of 18** across six experiments.
- Daily model: **6 of 40**.
- Walk-forward on the eight-name book: deployed (full-sample) parameters beat refitted ones by
  **50–80pp per fold** — that gap is lookahead, not skill, but it shows how much fitting moves.
- **Structural/specification changes survive; parameter searches do not.** Treat any proposal to
  re-optimise as guilty until proven innocent.

### 3.2 The OU sigma was mis-specified — corrected
`OUsig` was `STDEVP` of the last W closes about the window mean — the dispersion of the price
*level*, which on a trending name is mostly the trend. So the buffer widened exactly when a stock
was running and fills were lost. Corrected to the **standard deviation of fitted AR(1) residuals**.
- Worth +7pp (no re-fit) to +13pp (with re-scaled buffers) on the daily five.
- Residual sigma is roughly ⅓ of the old value; buffers were raised to match (see table above).
- **The two scales are not interchangeable.** A level-sigma buffer used with residual sigma (or
  vice versa) gives a bid wrong by ~3×. This caused a live bug — see §4.

### 3.3 The Bayes tilt reversed, so the split is 50/50
The 75% Bayes tilt won 11 of 15 folds (+1.7pp) against the *old* OU sleeve but only 7 of 15
(−2.1pp) against the corrected one. The tilt was compensating for a mis-specified OU. 50/50 is now
deployed on all names. Choosing the share adaptively per name remains unsupported.

### 3.4 The book must not be rebalanced between names
Each sleeve owns its capital and compounds independently. Building a book by averaging daily
returns (i.e. daily rebalancing) **costs 16.3pp** on the tested half and inflates measured drawdown
from 14.9% to 29.7% — it feeds capital back into names while they fall and sells winners. Any
portfolio-level analysis must use the **held** construction (equal capital at the start, compounding
independently). An earlier diversifier conclusion was wrong because of this.

### 3.5 The workbook's own return cells are not forecasts
`Model!Y5` reports 143% for TSM and 508% for RKLB. Correct its hard-coded `^(1/2.2)` exponent and a
Python replica reproduces the sheet to within a point — so the entire drop to the planning figures
is **same-day fill verification**. The sheet books a round trip whenever the day's low reached the
bid *and* the high reached the target, which daily bars cannot order.

| | sheet Y5 | engine, sheet rule | verified fills | no same-day |
|---|---|---|---|---|
| RKLB | 508% | 438% | **158%** | 36% |
| TSM | 143% | 129% | **57%** | 39% |
| VST | 263% | 240% | **62%** | 23% |
| VRT | 242% | 208% | **67%** | 35% |
| MU | 178% | 135% | **63%** | 41% |

### 3.6 The weekly mean-reversion formula never binds
0 of 120 weeks. The clamp (`min(Monday open, ATH×(1−cap))`) binds 100% of the time; the MR term
sits a median +9.4% above the week's open. The weekly model is effectively the clamp. Related: the
"2.5 model" (Monday entry, re-bid mid-Wednesday) is **mathematically identical** to the current
rule. A 26-week maximum hold bounds exposure at zero observed cost (12 weeks costs NVDA 12pp).

### 3.7 The Monday anchor advantage is real
Confirmed the user's weekend-gap hypothesis: two non-trading days between Friday and Monday change
the dynamics. Anchor *mixing*, however, lowers the neighbourhood median — do not mix.

### 3.8 Schwartz–Smith two-factor: rejected as a sleeve, inconclusive on TSLA
- Fails walk-forward on the book (5/15); suggestive on rejected laggards (7/12).
- All sleeves correlate ~0.85, so a third sleeve adds dilution, not diversification.
- **TSLA specifically**, on a symmetric test (every sleeve fits one P&L parameter on train):
  SS beats Bayes+OU in **4 of 6 folds** (was 3/3 when only SS could adapt), but is the outright
  best sleeve in only 3 of 6 — a zero-parameter null wins one fold, Bayes one, OU one.
- Ceiling test: best achievable fold median is SS 15.8%, Bayes 12.8%, OU 12.2% — a ~3pp edge over a
  hindsight-tuned incumbent, resting on a k-ridge only 0.3 wide.
- The mechanism is **selectivity, not forecasting**: SS holds 47% of sessions vs Bayes 85%.
- Correlation with Bayes when both hold: 0.92. It is a replacement for Bayes on TSLA, not an addition.
- ρ pins to the −0.95 bound in 4 of 6 folds — a specification tell.
- **Not enough to put TSLA back in the book.** The harness is a simplified replica: reads ~8pp high
  on TSM and ~15pp low on TSLA's deployed configuration, so absolute levels do not transport.

### 3.9 The OU sleeve's hedging rationale is empty — but it earns
Book drawdown is 39–40% at *every* Bayes/OU split. The sleeve is kept because it earns (88% vs
Bayes 71%), not because it hedges.

### 3.10 HAR-RV sigma: better forecasts, no better P&L — rejected
The model's two volatility proxies (daily range H−L in the Kalman noises, AR(1) residual std in
the OU buffer) were replaced with a HAR forecast built from the 5-minute bars (Corsi regression on
realised vol, coefficients fitted on the train half only, strictly ex ante, range-equivalent
scaling). The *forecast* is genuinely better — TSM out-of-sample R² 0.315 vs 0.127 for lag-1 — and
under the fair train-fit protocol (variant A vs variant A) it wins the tested half 5/9, RKLB by
+60pp. But neither route to deployment survives:
- **Refit route**: A-HAR never beats the deployed vectors on the tested half (0/9) — same result
  as every other train-half refit (§3.1).
- **Drop-in route** (deployed vectors untouched, σ series swapped): worse on the tested half in
  7/9 names (RKLB −42pp, MRVL −56pp), worse on train almost everywhere.
The deployed k/φ_L/ψ are co-adapted to the range proxy's *dynamics*, not just its scale: the raw
range is spiky and yesterday's spike widens today's buffer exactly after shocks, where the
mean-reverting HAR forecast shrinks back toward normal too fast. The model is not monetising vol
forecast accuracy; it is monetising the range's contemporaneous link to next-day dip depth.
Scripts: `har_rv.py`, `har_study.py`; engine hooks `F_series` / `ou_sigma='series'` (mirror
re-verified exact after the change).

### 3.11 Volatility-regime gate: rejected — the model is a stress harvester
A 2-state Gaussian HMM on log realised vol (train-half EM fit, strictly ex-ante forward-filter
probabilities) was used to gate entries on top of the deployed configuration: PAUSE (no entries
when P(stressed) > tau) and SCALE (buffers x (1 + gamma*P)), grids chosen on train, frozen, scored
on the tested half. Verdict on all nine names:
- **The diagnostic kills the premise**: stressed-regime entries are the *better* trades in 8 of 9
  names (e.g. MU +2.56% vs +1.67% calm, MRVL +3.48% vs +1.87%, CF +3.95% vs +2.37%) and carry
  *fewer* stops. The book's edge is buying panic dips; the stressed state is where it gets paid.
- PAUSE never wins: train picks the do-nothing cell in 5/9 names, and where it pauses anything the
  tested half is butchered (MRVL 191->77, RKLB 160->103, CF 55->11).
- SCALE is net negative (7/9 lose) and the two small winners want *opposite* gammas (RKLB +0.3,
  VLO -0.3) — noise, not signal.
Together with §3.10 this closes the "smooth statistical overlay" family: HAR sigma, regime gates
and calendar pauses (except MU's post-report case, which is directional-information-driven, not
vol-driven) all fail because volatility spikes are the product, not the hazard. CAVEAT: every
stressed episode in this sample mean-reverted inside a bull market; this result says nothing about
a genuine bear regime, where the same trades could be the killers. Bear protection remains a
judgement call, not a backtestable rule (§3.1 sample limits). Scripts: `regime_gate.py`; engine
hook `k_mult` (mirror re-verified exact).

### 3.12 Vol-scaled take-profit premium: rejected — the headroom is real but not worth waiting for
Colleague's suggestion: the buy side is vol-aware (k·σ) while the sell side asks a fixed
premium — should the premium breathe with σ? Tested with premium × (σ_entry/σ̃_train)^α per sleeve
(level-preserving at train-median σ, so only the dynamics were on trial; bids and fills identical
to deployed), α ∈ {0.25..1.0} train-picked and frozen. Result:
- The **diagnostic half-confirms the intuition**: on the Bayes sleeve, high-σ entries leave more
  headroom above the fixed target (holding-window high vs target: TSM +1.84% vs +0.72% median,
  MRVL +3.58% vs +1.41%, GM +1.51% vs +0.69%). The money the colleague suspects is there IS there.
- But **harvesting it fails**: train picks α=0 (fixed premium) in 7/9 names; the two exceptions
  are the cautionary tales — RKLB train-picked α=0.75 (+32pp train) and the frozen test collapsed
  160%→71%, GM picked α=0.25 and lost 2.6pp. Test deltas are negative almost everywhere at
  every α.
- Mechanism: high-σ trades at the fixed premium exit FAST (2–6 day median holds). Fattening the
  target converts quick recycles into multi-day holds; the foregone turnover/compounding (and the
  occasional slide into stop territory) costs more than the extra premium collects. The fixed
  premium is not naive — it is a turnover engine, and turnover is where the book's compounding
  lives.
Script: `premium_vol.py`; engine hook `prem_mult` (fill-row premium multipliers per sleeve,
mirror re-verified exact).

### 3.13 The 2022 bear replay: the gate is the armour, the breaker is not
User-supplied 5-minute bars Aug 2021 – Jun 2023 for all nine names (`data_bear/`), so the replay
runs on verified fills with the deployed 2024-26 parameters driven backwards. Per-name calendar
2022: the model tracks the decline almost 1:1 on the AI names (TSM −36% vs B&H −42%, RKLB −69% vs
−69%, MRVL −58% vs −59%; 7–10 time stops each) but the 2022 diversifier bull carried VLO +29%,
CF +49% (beat B&H +21%), VST +29% (B&H +2%). Book level (pooled, equal weights, calendar 2022):
- unprotected −21.9% (maxDD 28.1% — no worse than the April 2025 episode in the live sample);
- **200dma gate alone −2.6% (maxDD 17.4%)** — +19.3pp saved; pooling rotated the gated AI
  capital into the ungated commodity names at full size;
- breaker 15%/half-size alone −18.2% — +3.7pp only (half-sizing cannot stop held losses in a
  grind, and it keeps half-entering all the way down);
- gate + breaker −10.2% — WORSE than gate alone: the breaker half-sizes exactly the diversifier
  entries that were winning; adding the −25% price stop changes nothing (−9.9%).
Two-sided pricing of the gate: costs ~12pp/yr in the 2024-26 bull (238.7%→183.8% total),
saves ~19pp and 11pp of maxDD in the bear year. Expensive in expected-return terms unless bear
years are frequent; its real product is drawdown control. The breaker's remaining niche is the
fast crash the 200dma is too slow to see (it fired in April 2025 when the gate barely moved) —
speeds are complementary, but in a 2022-style grind the gate dominates and the breaker should
NOT be stacked on top of it. Caveat: 2022's save partly relied on having somewhere to rotate to
(the commodity bull); an AI-bust bear without a winning sleeve would concentrate the pooled
capital in fewer names (fills fell 406→155 under the gate). Script: `bear_replay.py`; book_sim
gained `breaker` and `price_stop`.

### 3.14 August diversifier round (FCX/NEM/UAL/LEN): zero admissions — vol IS the AI trade
Four candidates for the 30%-gate class, all G0-clean (596 sessions, ranges 2.85–3.92%). G1
reclassified three of them: FCX (AI beta 0.49), UAL (0.43) and NEM (0.27) all trade with the AI
factor in this sample — copper, airlines, even gold miners — so they face the 50% gate. Verdicts:
- **LEN declined G2** (the only true uncorrelated, beta 0.09/corr 0.16, but honest fits earn
  17–20%/yr vs the 30% bar — too quiet to pay the premium);
- **FCX declined G2/G3** (through-cycle 48.2% < 50%, inverted halves: train 8–19%);
- **NEM → WATCH LIST** (balanced halves, honest cluster 35–48% — under the 50% bar its 0.27 beta
  and 0.32 book corr impose, but it would clear a 30% gate easily; re-test end-Q1 2027: admits if
  new data reclassifies it uncorrelated or lifts the plan through 50%);
- **UAL declined G5** (variant A clears 50% outright, 56.2/51.9, but B collapses to 12.7% — the
  fragility floor — and the marginal book test fails: maxDD 29.2→30.8%, April-2025 stress
  −29.2→−30.8%, tested return flat. Neither out-earns nor de-risks).
The structural lesson: the model's premium engine needs volatility, and in this era volatility
itself is AI-correlated — LEN had the correlation profile but not the range, the other three had
the range but not the profile. Genuine 30%-gate candidates are scarce by construction; the bench
stays at GM/VLO/CF and the book at nine. Data in data_5min/ ({FCX,NEM,UAL,LEN}_5min.xlsx);
results in fresh_opt_cands.json.

### 3.14a AVGO: re-test scheduled for mid-September 2026 (after the ~4 Sep report)
User considered adding AVGO (acknowledged AI trade) under the new 09:00 rule; two rounds of
analysis (19 Aug):
- **Power-check correction to the June verdict**: AVGO's post-report pause was NOT contradicted
  by the train half — that half contained only 1 post-report fill (+1.45%) vs the test half's 9
  fills at −2.25% avg with 3 stops. The pause is reclassified adoptable-with-eyes-open (thin:
  9 fills, one half) and standalone it lifts AVGO 51.2→64.7% full, 53.7→83.0% test (2-session
  post-report no-buy; AVGO reports after the close).
- **But G5 is the binding gate and no pause fixes it**: with the 09:00 rule everywhere and the
  AVGO pause active, the 10-name book tests 114.0% vs the 9-name book's 118.4% (DD 24.8 vs 25.8)
  — minus 4.4pp tested-half for 1.0pp of drawdown. Without the pause it is −6.0pp. AVGO
  re-concentrates the AI factor at below-book-average margin. Fresh-fit fragility stands
  (A-variant test 21.7%).
**Agreed plan (user, 19 Aug): wait for the ~4 Sep 2026 report, then re-test** — it adds a tenth
post-report window to the thin 9-fill pause case. Re-test recipe: refresh AVGO 5-min + PM data
through ~mid-Sep, re-run the pause decomposition (earnings_pause + the per-half fill counts),
re-run the marginal book test (book_sim, 09:00 rule both sides, AVGO pause on); admit only if the
10-name book stops losing to the 9-name book. Data staged: data_5min/AVGO_5min.xlsx,
data_pm/AVGO_pm.xlsx (598 days); params = fresh_opt_cands.json AVGO reference vec.

### 3.19 Gap-exit correction: the sheet understates the live book by ~20pp/yr (execution fact)
User observation (19 Aug): the resting SELL is a limit order, so when a held position gaps up
overnight and the OPEN exceeds the target, the live fill is the open — the model books it at the
target. Engine/book_sim gained `gap_exit` (held-position target exits book at max(target, open);
same-day round trips unaffected; default False keeps the sheet convention — mirror re-verified
exact). Measured on deployed params, verified fills: **189 of 843 held exits (22%) gapped over
the target**, average uplift +0.7% to +2.4% per exit by name. Book pooled with the live config
(09:00/4% PM rule): full 87.3→106.0%, train 59.5→74.1%, TEST 118.4→141.8%, maxDD unchanged
(25.8→25.5). Per-name tested half: MU 148.5→194.7, MRVL 191.3→244.5, VRT 157.4→191.7. This is
an execution-accuracy correction, not an edge claim: every historical backtest number in this
file understates the live book accordingly, and all A-vs-B comparisons remain valid because both
sides were measured on the same (conservative) convention. The workbook Model sheets still book
target exits at the target — the blotter, which records actual fills, is the truth there.

### 3.15 Deep-bid exclusion (manual-intervention proxy): rejected — deep bids are good bids
User intuition: a bid 6–10% below the previous close "almost definitely won't fill", so exclude
that sleeve and pool its capital. The diagnostic kills the premise: deep bids fill ~1 day in 5
(20.1% at 6–8% depth, 18.6% at 8–12%, vs 49.5% at 0–2%) and their fills are the book's better
trades (median +2.7–2.9% vs +2.2% shallow). The mechanical rule (exclude sleeve when bid <
prevC×(1−thr), capital pools) tested on the pooled nine-name book: the train-picked threshold
(6%) LOSES the tested half (110.7%→105.3%); the 4% cell is train +5.6pp / test −0.9pp / maxDD
−2.4pp — return-neutral at best, not a both-halves win. Consistent with every stress-harvester
finding: the rare deep fill is the product. Note the tested rule cannot see pre-market
information; a judgement-based manual exclusion using live tape is neither validated nor refuted
by this, but the fill-rate numbers warn against the 'won't fill anyway' assumption. book_sim
gained `deep_excl`.

### 3.16 Pre-market exclusion: ADOPTED-QUALITY EVIDENCE — the first overlay to clear both halves
The user's manual-intervention rule, re-tested with the missing ingredient (user-supplied
pre-market 5-minute bars, 04:00–09:25, all nine names, data_pm/). Measured against the 09:25
pre-market price instead of yesterday's close, the §3.15 picture inverts: bids >4% below PM-last
fill only 13%/6.6%/4.1%/0% of days (4-6/6-8/8-12/>12% depth) and those fills average ~zero or
negative — adverse-information days, not harvestable dips. RULE: exclude a sleeve's order when
bid < PM_last×(1−4%); capital pools as normal. Pooled nine-name book: **train 45.4→53.3%, TEST
110.7→122.4%, maxDD 29.2→27.5%** — a both-halves win, robust across thresholds 3–12% (a plateau,
not a spike), gains spread over 7 of 9 names (exception RKLB, whose deep fills stay good; no
per-name exemptions taken — that would be selection). 23.9% of sleeve-days excluded. It survives
where ten overlays died because it ADDS information the model lacks rather than reshaping the
harvest. Scripts: `premarket_excl.py`; book_sim gained `excl_fn`. Live implementation: manual at
09:25 (skip orders with buy < PM×0.96) or an Allocation flag column like the DMA gate; Script 1
could automate with an IBKR pre-market snapshot. Cutoff sensitivity (user needs time for manual
updates): a 09:00 check keeps most of the edge — train 59.5% (best cell anywhere), TEST
110.7→118.4 (+7.7pp vs +11.7 at 09:25), full 87.3%, maxDD 25.8% (best) — the 09:00–09:25 window
carries ~4pp of tested-half edge; 08:30 decays to +/-0 (test 108.0). Adopted operating point:
09:00 cutoff, 4% threshold, upgrade to 09:25 if Script 1 automates the snapshot. Cutoff is NOT
monotone (09:15 tests below both 09:00 and 09:25) — cells inside the 09:00–09:25 band differ by
noise; all twelve cells 09:00+ beat baseline on both halves, 08:30 decays to ≈baseline.
ADJUST-instead-of-exclude variant (raise the bid to PM−clamp% when triggered, fill at the open
if the raised limit exceeds it): REJECTED — worse than baseline on both halves at every clamp
(4%→2%: test 110.7→102.7, DD 32.2%; universal PM−2% clamp: test 92.5%, DD 34.5%). Raising the
bid overrides the k·σ buffer on exactly the high-vol days it exists for: ~130 extra shallow
fills into falling names. The manual intervention may VETO an order, never AMEND one. book_sim
gained `bid_fn` (raised limits fill at the open when the open is lower).

### 3.17 Midday re-pool (13:00 second allocation session): rejected — afternoon top-ups feed faders
The natural extension of the pre-market rule: at 13:00, cancel unfilled orders deeper than y below
the tape, re-admit benched sleeves now within y, re-pool freed cash + provably-morning proceeds as
a top-up at unchanged model prices. Machinery: midday_sim.py (AM/PM segment index with pure
within-segment suffix maxima; validation with midday off reproduces book_sim to within 0.6pp).
The diagnostic confirms the dead capital is real — 35% of live order-days fill before 13:00, only
3.3% first-fill after, and the afternoon fill curve collapses fast (44.9% within 1% of the 13:00
tape, 12.5% at 1–2%, 3.6% at 2–3%, ~0 beyond) — but redeploying it fails: the train half picks
y=5%, which LOSES the frozen tested half (117.8→109.9); the cells with tested-half gains (y=1.5–2%,
125.7–127.9) lose the train half and blow the drawdown to 32–33% (vs 25.8). No cell wins both
halves; the re-arm variant is categorically bad (87.6% test). Mechanism: at 09:00 freed capital
spreads across the whole normal book, but at 13:00 the only orders still fillable belong to names
FALLING that afternoon — the top-up selectively concentrates capital into late-day faders that
close near their lows (adverse selection + intraday concentration, the April-2025 effect in daily
miniature). Dead capital earning interest until tomorrow's diversified morning allocation beats
funding this afternoon's faders. The morning session is where routing decisions belong.

### 3.18 Fill-probability-weighted allocation: rejected — equal weights stand (again)
The continuous version of the pre-market rule: weight surviving sleeves' morning allocations by
their fill probability given depth vs the 09:00 pre-market price. The train-half curve is strong
and monotone (>=PM: 96.6%, 0-1%: 80.6%, 1-2%: 50.1%, 2-3%: 30.8%, 3-4%: 24.3%) — yet every
weighting loses the train half (equal 59.5% vs p_fill 54.4%, sqrt 57.1%, p^2 49.9%); the mild
tested-half gains (+2.8 to +4.5pp) are the familiar unsanctioned-noise pattern. Why a real curve
doesn't help: the cost of equal-weighting a low-probability order is one day of idle cash at
interest (tiny), while weighting concentrates capital into near-the-money shallow-dip fills —
lower margin per fill, less diversification. The binary veto captures everything the curve has to
give. Consistent with the book-policy optimisation verdict. book_sim gained `weight_fn`.

### 3.20 Delayed entry (trade 2h after the open, open as the model signal): rejected — the morning IS the harvest
User proposal (26 Aug): place the order ~2 hours after the open, using the opening price as the
model signal. Decomposed and tested per name on verified fills, deployed params, both halves
(`delayed_entry.py`; engine gained `entry_low` / `entry_tape` — entry-touch restricted to a
post-cutoff window, marketable fill at the cutoff tape when it sits below the bid, target set off
the actual fill px; before/after snapshot EXACT MATCH on all nine names).
- **The diagnostic settles it before the backtest does**: 56–80% of ALL verified fills
  (book-wide ~72%) first-touch the bid before 10:30; only 6–21% after 13:00. The model is a
  morning-dip harvester — the first hour is the product.
- **Delay-only (2h)**: book average full 70.8→50.1%, train 40.1→23.9%, test 114.8→83.7%; buys
  −20–30% per name; test-better in 1/9 (VST, whose train collapses 53.4→1.3%). 1h and 3h no
  better — there is no good cutoff, the curve is bad everywhere.
- **Open-as-signal only** (OU anchored on today's open, Bayes fair nudged toward it,
  g∈{0.25,0.5,1.0}, no delay): every gain loses the book average on both halves (best cell
  g=0.25: test 92.7% vs 114.8%). The bid already caps at the open (min(fair−kW, O)) — the
  open's information is already in the order; letting it MOVE the bid re-prices the harvest
  with parameters co-adapted to the prev-close anchor (same failure as HAR σ, §3.10).
- **Combined (2h + signal)**: worst of all (45.4/19.2/78.5).
Mechanism is the midday-re-pool one in miniature (§3.17): what is still cheap at 11:30 is
disproportionately a name falling that afternoon — the delayed order forfeits the recovered
morning panics and keeps the adverse tail. Even with the marketable-limit benefit (the variants
fill at the better cutoff tape when it undercuts the bid) they lose. Rejection #11 for
harvest-reshaping overlays; resting from the open at the open-capped bid stands.

### 3.21 Holding-saturation halt (no new bids when the book wakes >=70-80% held): rejected — being held is not distress
User proposal (26 Aug): halt NEW entries for the day when the book is 70-80% holding (existing
positions and exits unchanged). Tested on the pooled nine-name book, live config (09:00/4% PM
rule both sides), strictly ex ante on yesterday's close state (`hold_halt_study.py`; book_sim
gained `hold_halt=(thr, basis)` with basis 'cap' = held MV/equity or 'sleeve' = held/18, plus an
always-on `frac_series` recording and `cost` in trade dicts; baseline reproduced 87.3/59.5/118.4
exactly).
- **Diagnostic 1 — saturation is the normal state, not an event**: the book wakes >=70% held
  (capital) on 43% of mornings (>=70% of sleeves: 22%). A 70% halt would switch off 200 of 587
  trading days.
- **Diagnostic 2 — the premise dies**: completed-trade returns by held fraction on the ENTRY
  morning are flat — avg 1.6-2.1%, median ~2.25% in every bucket, stop rates 2-5% with no
  gradient. Entries made on 85-100%-held mornings average +2.14%, among the best buckets. The
  held fraction carries no information about next-trade quality; a heavily-held book is the
  machine working, not the machine in trouble.
- **Intervention — every cell loses both halves**: user's cells cap>=70%: train 59.5→47.8, test
  118.4→103.5; cap>=80%: 53.2/113.6. Lower thresholds buy some drawdown (cap>=50%: DD 25.8→20.0)
  at −15pp train/−28pp test — expensive risk control the 200dma gate already provides ~free.
  sleeve>=90% is a 9-day no-op (±0.1pp).
Mechanism: in the pooled loop a saturated morning is usually mid-bull (dips filled, targets
pending), and the marginal cash entry on those mornings earns the same premium as any other. The
concentration hazard (all cash into the last free sleeve) is real in fast crashes but is not a
per-trade-return effect, and the halt pays a permanent bull toll to address it — same verdict
shape as the breaker (§3.13). Rejection #12; the pool stays always-on.

### 3.22 Intraday fast-crash stand-down: right breaker design, but entry vetoes cannot protect inventory — not adopted
The automation-only candidate from the 26 Aug idea round, built and tested (`fast_crash_sd.py`;
book_sim gained `intraday_sd=(trip, reset, R)` + per-day 5-min `bars`). Design fixes the daily
breaker's 2022 failure by construction: reference = max of the last R daily close equities (a
ROLLING peak that decays in a grind, so the rule re-arms instead of staying tripped for months);
trigger = first 5-min bar where morning cash + held book (marked at bar opens) <= ref×(1−trip);
action = cancel bids not yet touched (touch at/before the trigger bar still fills — pessimistic
for the rule); reset when a close recovers above ref×(1−reset). Strictly ex ante, veto-only.
Invariance: PM-rule baseline and the full §3.13 2022 matrix reproduce exactly.
- **The design goal is achieved**: stacked on the 200dma gate in 2022, SD 10%/R5 is IDENTICAL to
  the gate alone (−2.6%, 17.4% DD; SD 8% costs only 0.9pp) — no trace of the daily breaker's
  anti-synergy (gate+breaker −10.2%). The rolling reference is the right breaker architecture.
- **But it protects nothing**: April 2025 episode DD is unchanged at every trip level (25.8→
  25.8–26.1 alone; 32.2→31.5 on the gate — the concentration blind spot stands); 2022 alone
  −22.1/−22.3 vs −21.9 unprotected. Only SD 10%/R10 moves DD (25.8→23.1) and it pays −3.7pp
  train / −0.7pp test for it. No cell wins anything.
- **Mechanism — the negative result that settles the family**: a fast crash damages the book
  through held inventory marked down and overnight gaps, neither of which an ENTRY veto can
  touch. Cancelling crash-day bids saves only the marginal new entries, and §3.21's diagnostic
  already showed those are ordinary trades. Inventory is protected only by exits (price stops —
  rejected, §3.13) or sizing caps (15% sleeve cap — tested, costly, §3.13 addendum). April-class
  V-drops are the residual cost of holding the book; the samples say they are survivable and
  recover in weeks.
Verdict: nothing to adopt (no both-halves win, no drawdown product). SD 10%/R5 is ~free
(train −0.3pp, test −0.6pp, 3 trips/6 halt days in 2.4 years) and is the correct template if a
future regime ever argues for an automated kill-switch; the machinery stays in book_sim.
Rejection #13.

### 3.23 Breadth-conditional 200dma gate: RECOMMENDED UPGRADE — gate on the bear, not the name
User observation from live trading (26 Aug): VST sits below its 200dma, gated while recovering —
the per-name gate may be taxing recoverable single-name drawdowns. Proposal (user's): fire the
gate only when SEVERAL names breach at once. Rule tested (`breadth_gate.py`): a name below its
own 200dma is gated ONLY when >=K of the nine are below theirs that morning; K=1 = deployed gate.
- **Diagnostic confirms the intuition**: 2024-26 breach-days are mostly ISOLATED (193 days with
  1 name below, 171 with 2, vs 60 with >=5 — the April episode). The 384 forgone entries on
  isolated days (breadth<3) averaged **+2.35% (median +2.54%, only 21/384 losers)** — good
  trades the per-name gate throws away. VST alone: 195 gated days, 129 forgone entries.
- **2024-26 (pooled, PM rule both sides)**: per-name gate 87.5/59.4/119.0, maxDD 32.2 (April
  concentration). Breadth K>=4: 89.8/64.6/117.3, DD 25.8. K>=5 (=K>=6): **93.4/71.1/117.4, DD
  21.7** — the April episode goes 32.2 → 25.8 (K4) → 21.7 (K5): breadth-conditioning FIXES the
  gate's known concentration blind spot (it only gates during the acute broad phase, not the
  long single-name run-up/recovery tails that starved the pool).
- **2022 (the gate's reason to exist)**: K=2,3,4 IDENTICAL to per-name (−2.6%, DD 17.4 — the
  bear is a breadth event: 144 days with 6 names below). K=5 actually better (−0.4%, DD 16.1).
  **K=6 falls off the cliff (−12.6%, DD 23.2)** — 2022's plateau was exactly 6-below (the three
  diversifiers held), so K=6 forfeits the early-decline protection. The protection boundary is
  K<=5.
- **Recommendation: adopt breadth-conditional with K=4** (margin-of-safety choice: identical
  2022 protection with two names of headroom against a future bear where one more diversifier
  holds up; fixes April to 25.8; train +5.2pp vs per-name at test −1.7pp ≈ noise). K=5 is the
  performance choice (best everywhere in sample: train +11.7, DD 21.7, 2022 −0.4) but sits one
  step from the 2022 cliff. Live state at sample end (2026-08-03): breadth 3 (VRT, VST, RKLB
  below) — under either K, VST trades now, which is the user's live issue resolved.
- Test-half return is −1.1 to −1.7pp vs the alternatives everywhere in the grid — within noise;
  the gate is a PROTECTION overlay and the comparison that matters is drawdown dominance at
  ≈zero return cost, which K=4/5 deliver on both regimes.
Workbook wiring APPLIED (26 Aug, `wire_breadth_gate.py`, delivered as
TradingExcel_9stock_breadth.xlsx): AT M8 = K (4, label L8, explanation N8); Allocation G43 =
breadth count (sum of the nine Bayes-row breach flags; G25:G42 stay the RAW per-name flags);
F25:F42 = E*(1-D)*(1-G*($G$43>='Active Trading'!$M$8))*(1-H). Blank M8 fails CLOSED to the old
per-name gate. Notes gained an UPDATE — 26 AUGUST 2026 section. Cell-diff verified exact; no
script-read cells moved. Live state at delivery: breadth 2 (VST, RKLB below) — gate unarmed.

### 3.25 The complete earnings map: MU's pause is idiosyncratic, not a family — cross-name veto rejected
Two calendar studies (26 Aug, `earnings_map.py`; GM/VLO/CF report dates added to
`earnings_pause.EARNINGS`, gap-validated with the known pre-market-reporter caveat).
- **Part 1 — per-name pauses, the seven untested names** (TSM, VRT, VST, RKLB, GM, VLO, CF;
  P1/P2/P3 grids, both halves): **zero both-halves winners**. Near-earnings entries are as good
  as or better than away-entries in most names (VRT +2.4–2.5% all three report buckets vs +1.38%
  away, zero stops; RKLB likewise; TSM flat-positive). VLO and CF show weak 'week after' buckets
  (−0.3%, −1.0%) on tiny n (8, 3) and every pause intervention still loses both halves. TRAP
  NOTED: VST P2 shows train 53.4→99.9 with test 58.1→37.8 — textbook inverted halves, do not
  adopt. Standing state: **MU P3 remains the only earnings pause in the book** (its post-report
  drift is idiosyncratically adverse); AVGO pending its ~4 Sep report (§3.14a).
- **Part 2 — cross-name bellwether veto** (no new AI-six bids for 1–2 sessions after NVDA /
  NVDA+AVGO reports): the diagnostic kills it — AI-six entries in the two sessions after an NVDA
  report average **+2.10%** (vs +1.67% elsewhere) and after AVGO **+2.38% with zero stops**.
  Bellwether-night dips are premium harvest (the MRVL pattern generalises to the complex). The
  pooled intervention confirms: every cell loses the tested half (118.4→107.1–112.5), train flat
  to worse. Rejection #15.
Meta: calendar vetoes as a class now read 1 adopted / 10 rejected-or-unneeded — the adopted one
(MU) was found by following a name-specific adverse drift, not by pausing around events per se.
Event-adjacent volatility keeps being the product, not the hazard (§3.11, §3.20).

### 3.26 Pre-market breadth veto: premise dead at the diagnostic — broad panic mornings are the BEST mornings
Entry-side sweep item (26 Aug, `pm_breadth_diag.py`): should a BOOK-WIDE adverse pre-market
morning (many 09:00 prints down vs yesterday's close) veto the day's entries beyond the per-name
4% rule? Diagnostic on the pooled baseline's completed trades, bucketed by that morning's
adverse breadth (coverage >= 6 names, median 9):
- At >=2%-down breadth, per-trade returns rise MONOTONICALLY with breadth: 0 names down +1.72%
  (4% stops) → 6–9 names down **+2.46% with a 1% stop rate — the best bucket in the table**.
  At >=3%: breadth 3–9 gives +2.31% with 1 stop in 186 trades.
- The weakest bucket anywhere is 1–2 names down >=3% (+1.10%, 14 stops in 249): the
  IDIOSYNCRATIC single-name gap-down is the adverse-information case — and that is exactly what
  the per-name 4% rule already vetoes; these are its <=4% survivors.
Mechanism: a coordinated gap-down that still leaves a bid within 4% of the tape is a book-wide
panic that mean-reverts — the harvest (same shape as the regime gate §3.11 and the bellwether
veto §3.25, now on overnight information). Breadth is bear-armour information on the 200-DAY
horizon (§3.23) and harvest information on the OVERNIGHT horizon. No intervention run — a
breadth veto would delete the book's best conditional bucket. Rejection #16.

### 3.27 Premia at book level (pooled objective): diagnostic confirms CF is the pool's most expensive patience — intervention still fails, premia stand
User question (29 Aug): the per-name premia were fitted with captive capital; under pooling, the
opportunity cost of a held-day is the POOL's marginal return, which the isolation fit never saw —
should the slow diversifiers (CF 4.66/5.91% premia) exit earlier for the book's sake? This is a
NEW objective (never searched: book_policy_opt covered weights/ATH-eps/cap only), tested in
`premia_at_book.py` on the live config.
- **Diagnostic — yield per invested dollar-day (pooled baseline trades)**: CF is the book's
  lowest at **0.186%/dollar-day** (57 trades, median hold 12d, best per-trade margin +3.12%) vs
  book 0.306%, RKLB 0.476%, MU 0.431%; VLO 0.269%, GM 0.272%. The user's suspicion is factually
  right: CF's held capital earns ~40% less per dollar-day than the pool average.
- **Intervention — diversifier premium multipliers {0.5,0.65,0.8,1.0}³, both-directions
  book-policy protocol**: fit-train picks CF×0.8/VLO×0.5 (+0.6pp in sample) and LOSES the unseen
  half (116.7→115.2); fit-test picks the baseline outright (no cell beats 1.0 in sample).
  Directions disagree → no adoption. CF-only ladder, no picking: every reduction loses BOTH
  halves (×0.8: 59.6/116.1 vs 59.5/116.7; ×0.5: 58.1/115.7).
- **Mechanism**: the diagnostic's 0.306%/dd book average is the AVERAGE yield, not the marginal
  one. Freed CF capital does not create new trades — it thickens the pool's existing orders, so
  its redeployment earns the margin, not the average, while CF's forfeited premium (the book's
  best per-trade margin) is lost with certainty. Same shape as fill-prob weighting (§3.18) and
  the exit family (§3.24): the pool prices slow capital far more cheaply than intuition does,
  because next morning's diversified allocation is always waiting for it.
Verdict: the isolation-fitted premia are also the book-optimal premia within measurable
resolution; CF's patience is expensive per dollar-day and still worth it. Rejection #17. (Note:
windowed sims restart capital at the split, so this study's test-half baseline reads 116.7 vs
the full-path 118.4 — internally consistent A/B throughout.)

### 3.24 Week-end profit exit (sell in-profit open positions at the Friday close): rejected — the weekend hold is paid for
User proposal (26 Aug): a position that hasn't reached its target but stands in profit at the
Friday close sells at that close instead of carrying into next week. Tested per name and pooled
(`weekly_close.py`; engine + book_sim gained `week_end_exit='profit'` — sell at the week-end
close when close−comm > fill+comm, same-week and older holds alike; defaults reproduce
hold-to-target, book baseline invariance asserted in-run).
- **The diagnostic kills it**: 216 (position × Friday) observations open and in profit at a
  Friday close. Profit then: avg +1.34% (med +1.06%). The same position's final outcome: avg
  +2.97% (med +3.30%) — **the eventual exit beat the Friday close in 94% of cases, at a median
  5 further days**. The tail the rule insures against is small: only 6.0% eventually
  time-stopped (avg final −8.06%). Expected value of continuing to hold ≈ +1.5pp per position;
  the weekend gap risk is, on this sample, income (consistent with §3.19 — 22% of held exits
  GAP OVER their targets, and Friday sales pre-empt exactly those).
- **Intervention**: per name mixed and small (CF −15pp full — its slow high-premium trades are
  butchered; TSM/MRVL ±2); pooled book with the live config LOSES BOTH HALVES: full 87.3→79.3%,
  train 59.5→54.0%, test 118.4→107.2%, maxDD worse 25.8→27.3%, 213 week-end sales. Freed Monday
  capital does not come close to replacing the forfeited premium.
Mechanism: this is the vol-scaled-premium lesson (§3.12) mirrored — that one fattened targets
and lost to foregone turnover; this one truncates targets and loses the premium margin. The
fixed premium held to target IS the calibrated harvest; exits reshaped in either direction die.
Rejection #14. ADDENDUM (same day): restricted to the diversifiers only (user follow-up) it still
loses both halves — CF+VLO+GM-only 55.4/110.6 vs baseline 59.5/118.4 (DD worse); singly, CF-only
and GM-only lose both halves and VLO-only shows the familiar train-up/test-down noise pattern
(62.6/115.9). The freed Monday capital never replaces the forfeited premium, on any subset
(weekly_close_divers.json). ADDENDUM 2: holding to the FOLLOWING Friday instead ('profit_skip1' —
a position is spared its first week-end, only prior-week entries sell) also loses both halves
(train 59.5→55.4, test 118.4→115.5, DD 25.8→27.3, 63 forced sales; diversifier-scoped identical).
The age-split diagnostic explains why no Friday works: positions in profit at their SECOND-or-later
Friday go on to beat that close in 92% of cases (avg +3.57% final vs +1.58% then) — even more
in-the-money than first-Friday holds. There is no Friday at which the in-profit book is better
sold than held (weekly_close_skip1.json). ADDENDUM 3 — half-premium variants, both readings
(half_premium.json): (A) halving the TAKE-PROFIT TARGET itself (resting sell at bid + prem/2,
prem_mult hook / halved sleeve prem) is the family's worst cell — pooled full 87.3→69.4, train
59.5→44.2, test 118.4→97.5 despite 44% more fills (1363→1960; DD 25.8→21.7 is the one gain);
8 of 9 names lose full-sample. Doubling turnover at half margin does not clear the same
commissions/recycling bar — the FITTED premium level is load-bearing, not just its fixedness.
(B) The Friday sale gated on having captured >= half the premium (week_end_exit='half_prem')
still loses both halves (56.8/113.9, DD worse, 60 sales) — a subset of the §3.24 sales, all still
value-destroying. Exit family closed: no early-exit rule at any threshold or timing beats the
fixed premium held to target.

**Pooled-cost revision + April 2025 stress test (15 Aug).** The ~12pp/yr bull cost of the gate is
a held-construction number. In the POOLED loop (the one the book trades) the gate is free over
2024-26: 75.8%→75.9% full, 110.7%→110.8% test — pooling reallocates gated capital instead of
idling it. The real price is concentration in fast crashes: Feb–Mar 2025 put 8 of 9 names below
their 200dmas, the pool piled into RKLB, and the April 2025 episode deepened 29.2%→32.1% with
recovery pushed 16 Jun→9 Jul. A 15% per-sleeve cap fixes the episode (−25.5%) but costs ~10pp/yr
and damages the 2022 rotation (−2.6%→−6.7%) — tested, not adopted. Net: gate = grinding-bear
armour, ≈free on average, slightly negative in a V-crash; fast crashes remain the breaker's event.

### 3.28 COMPOSITION CHANGE (2 Sep 2026): RKLB out, AVGO in — user risk decision, wired

The user removed RKLB (SpaceX-linked performance since its IPO; binary Neutron launch risk; the
admission judged volatility/excitement-driven ahead of the SpaceX IPO) and put AVGO in its slot.
This was a **risk decision, not a model verdict** — do not re-litigate it against back-test
numbers. Wiring (`wire_avgo_swap.py` → `TradingExcel_9stock_avgo.xlsx`, cell-diff verified, 2,461
cells all in the intended set): Query N:Q = AVGO daily RTH OHLC from the verified research series
(exact date match, 587 days to 2026-08-03; **4–31 Aug cleared, backfill via `ops/backfill_query.py`
before AVGO trades** — until then AVGO's close/200dma/ATH read as of 3 Aug); `Model AVGO` params =
AVGO reference vector (λ=1, φ_L=0.28162, ψ=0.24815, k=0.21818, prem 2.912%, peak cap 5.993%,
OU W=113, buf 0.43090, OU prem 1.409%, OU cap 4.861% — captive verified 52.7/49.1/56.2, reference
51.2/49.2/53.7); labels (Dashboard A7, Alloc A31/A32, AT A1/A10, Feed note, Notes roster); Alloc
C14 ann-return 1.15→0.51; Performance hold refs AVGO 6.5 d (144 trades, 39% same-day), BOOK
5.9→6.5. Feed AVGO pulls from Query by INDEX so the chain self-updates. User had already renamed
Feed/Model sheets and rewired Dashboard row 7 / Alloc row 14 / order rows 25–26.
**New pooled baseline (AVGO in RKLB's slot, live config): full 72.4 / train 43.9 / test 104.9**
sheet-convention (was 87.3/59.5/118.4), **88.5 / 56.4 / 125.4 exec-accurate** (was 106.0/74.1/141.8,
reproduced exactly as the invariance check); maxDD improves 25.8→24.7; fills ~531/yr pooled
(~543 captive-sum), stops ~20/yr unchanged. **Documentation re-cast DONE (2 Sep):** ranking memo
§9 (new nine-name table: AVGO row full 53 / planning 51 / exec 60 via ×1.17 gap-exit uplift,
62 trades/yr, AI β 0.74, corr 0.31; averages 59/53/**66** exec, β 0.66, corr 0.30; §7 marked
superseded; watch-list text re-cast), evolution docs ×2 (roster, flowchart s9/s10, dated
composition paragraphs; plain edition explains the risk call), bear paper §10 composition note
(machinery slot-based and carries over; 2022 replay/April-2025 are RKLB-era measurements), ops manual v1.3 (planning basis 66%/yr, Performance-tab
66%, AVGO diary entry now in-book post-report check, watch bench = NEM only), one-pager
HIST_HOLD/roster. **Planned overall book return: ≈74%/yr** — construction SETTLED same day (user challenge:
"surely the plan should include any pooling uplift" — correct; gap exits and pooling are both
mechanical properties of the machine, and crediting one but not the other was inconsistent).
THREE-TIER PLAN NOMENCLATURE (the standing convention from here): (1) anchors — per-name captive,
sheet convention, OOS haircuts: 53%/yr; (2) × gap-exit execution uplift (per name, AVGO ×1.17):
66%/yr; (3) × pooling uplift at its WEAKER measured half: ×1.12 → **≈74%/yr = the plan**.
Pooling uplift measured captive-book vs pooled-book, identical frozen vectors, exec-accurate:
×1.233 full / ×1.485 train / ×1.121 test (swapped book; captive exec 71.8/38.0/111.8 vs pooled
88.5/56.4/125.4) — COUNTER-CYCLICAL: biggest in the weak half because that's when sleeves sit in
cash. The pooled full-sample measurement (88.5% exec / 72.4 sheet) is the upper reference, NOT the
target (carries fit lookahead). Old-book plans (79–80%) had no pooling tier — constructions are
not comparable across the 2-Sep boundary. Workbook plan wired: wire_plan_update.py (accepts C5
0.80 or the interim 0.66) sets C5=0.74 + generic chart title + Notes changelog
(TradingExcel_9stock_avgo_v3.xlsx delivered); pre-2-Sep performance is judged against the old
plan, after against 74%. Ranking memo §9 carries the tier definitions; ops manual v1.4.

**3.28c — Stop autopsy (3 Sep, user: "I don't like the number of stops — causal patterns?").**
`stop_autopsy.py`/`.json`. Pooled current-roster baseline (72.4, PM rule): 1,228 trades, 47 stops
(20.1/yr, 3.8% of trades), drag −$6.0m vs +$23.2m book P&L. DECOMPOSITION: (1) Feb–Mar 2025 fast
crash = 13 stops/−$2.4m across six names — the documented gate blind spot, breaker tested and
subtracts; not diagnosable at entry. (2) Report-adjacency = the ONE per-trade discriminator: 38%
of stops entered within 7d of that name's report vs 21% of other trades (~1.8×); 18 stops/−$2.8m
(8 overlap the crash). The LIVE MU pause (manual, not in baseline) catches ALL FOUR MU stops
(−$235k) → live expected ≈18.4/yr. Blanket own-report pauses DON'T follow: earnings map showed
report-adjacent entries are net GOOD for VRT/MRVL/TSM etc.; per-name pauses failed adoption
(#15, §3.28a AVGO single-episode). (3) Residual = 24 stops/−$2.0m (~10/yr, avg −$85k), spread
across all names/months, entry tape indistinguishable from winners (prior-5d +3.65% vs +3.78%,
vs-20d-high −1.7 vs −1.9, below-own-dma 17% vs 16%) — the flat tax of the buy-the-dip entry
style. AFTER the stop: 68% recover to entry and 55% to the original target within 50 further
sessions — trough-crystallising confirmed, but stop_days is fitted/frozen and the stop memo
showed the alternatives are worse. NO new rule proposed; nothing here clears the bar the earlier
tests didn't already fail.

**3.28b — 2022 bear replay of the CURRENT roster (2 Sep, user supplied AVGO Sep21–Jun23 5-min).**
`bear_replay_avgo.py` / `bear_avgo.json`; data_bear/AVGO_5min.xlsx (83 warm-up sessions before 2022
vs incumbents' ~90; AVGO OU W=113 live ~mid-Feb 2022). Earlier roster REPRODUCES published numbers
exactly (−21.9% unprotected 2022, DD 28.1; gate −2.6). AVGO per name 2022: B&H −15.7%, model
−3.6%/yr, DD 28.9, 7 stops / 56 buys (vs RKLB's −69% row). CURRENT book calendar 2022: unprotected
−13.8% (DD 23.7); per-name gate −1.5; **breadth K=4 (adopted) +1.7% (DD 15.7)**; gate+breaker −3.5
(breaker still subtracts). Full span Jan22–Jun23 totals: nothing +0.8, per-name gate +12.3,
**breadth +17.8**. NEW finding: on this roster breadth BEATS the per-name gate in the bear (was
merely save-preserving with RKLB) — recovering fourth slot trades through isolated breaches.
Papers updated: bear §10 results table + footer; evolution docs' 2022 claims re-cast to
current-roster numbers (−14% unprotected / gated +2%).

**3.28a — AVGO 2-day post-print pause, tested (2 Sep), NOT adoptable yet.** The 66% plan includes
gap exits by construction (exec-accurate = anchors × per-name gap-exit uplift; AVGO ×1.17) but
assumes AVGO trades through earnings — no AVGO pause exists (MU's P3 is the only pause). Measured
"no new AVGO bids for the 2 sessions after each report" (9 reports, 18 sessions): captive 52.7→65.5
sheet (61.4→75.3 exec), pooled swapped book 72.4→74.4 full / 43.9→43.8 train / 104.9→109.6 test.
Autopsy kills it: 10 blocked entries, 7 were winners (+1.4 to +3.4%); the ENTIRE gain is the
12 Dec 2025 double stop-out (both sleeves −14.17%, 52d) plus one −4.4% June-2026 stop. Halves:
train WORSENS 49.1→48.0, test +28pp (84.1) — one episode, one half; fails the both-halves bar
(the VST-P2 single-cell mirage pattern). Do not bake into the plan. The scheduled mid-Sep in-book
check adds a tenth report window — re-ask there with the ~4 Sep print in the data. Operationally
this week, keeping AVGO bids off through the print remains sensible (backfill + script swap are
pending anyway); it is an ops caution, not a plan input. Left alone by design:
historical RKLB blotter rows (P&L stays in the weekly log; per-stock funds row 10 now shows AVGO),
the OPEN discretionary RKLB position (manual book). Scripts 1/2: sheet layout and every address
unchanged — the only script edit is the ticker string RKLB→AVGO where they carry a ticker list;
if they read tickers from Query headers / order block, zero change. AVGO reports ~3–4 Sep 2026 and
its earnings map profile is the MU profile (week-of entries adverse) — bids off through the print
recommended; the 15 Sep AVGO re-test reminder now doubles as the post-print parameter sanity check.

### 3.28d Session block 4–10 Sep 2026 — disc-ticket thread, VRT episode, environment loss (READ FIRST in a new session)

**ENVIRONMENT — data loss and recovery (critical).** The remote container was recycled ~5–8 Sep:
ALL untracked data is GONE — `data_5min/`, `data_pm/` (incl. pm_last_cuts.pkl), `data_bear/`,
every delivered xlsx, and the old chat uploads. Consequences: NO engine/verified-fill/pooled-book
run is currently possible (book_sim.load_all, minute_index, PM rule all need those files); recent
studies fell back to DAILY data read from the user's attached workbook Query sheet
(`disc_structure.load_from_workbook(path)` — reusable loader). To restore full capability the user
must re-upload the 5-minute files (Box holds them: "TICKER 5min Apr2024-Aug2026.xlsx" etc. — Box
MCP can search/list but CANNOT download binaries). **[SUPERSEDED 8 Oct — see §3.34: Box CAN serve
these files, exactly, via get_file_content. Re-uploading by hand is no longer necessary.]** Also: `fresh_opt_cands.json` was gitignored
(early-era rule) AND lost locally — REBUILT 10 Sep from the live workbook's Model sheets + session
record (MRVL + AVGO reference vectors only, verified exact vs workbook cells), un-ignored, now
TRACKED. The original's candidate A/B variants and declined-name entries are still missing —
restore over the rebuilt file if a copy surfaces on the trading machine/Box. Other still-ignored
JSONs (params_all, fresh_opt_results, rank_book, weekly_12m, har_*, regime_gate) have the same
loss exposure — an audit of which are load-bearing was offered, not yet done.

**Discretionary "dislocation ticket" (user thread, 8–10 Sep).** User wants disc trades
semi-structured: human event-driven entries (his AVGO-on-MRVL/Google-news and MU-at-912 trades),
pre-defined exits, ~3%+/hold-week ambition, no stock-watching. Work done:
- `disc_structure.py`/`.json` — mechanical proxy (close ≥3% below 10dma + 5d TR ≥1.3× 60d median,
  buy next open) × bracket grid (target T × time-cap N), nine names daily (workbook Query data).
  Sweet spot T=5%/N=10 sessions: 67% hit, +1.86%/trade, median 6d hold; halves agree everywhere;
  worst single trade −37% (earnings crash inside window). Blended ≈2%/wk = the FLOOR; the user's
  live tickets (+10%/1d, +6%/3d) beat it — human filter is the alpha.
- `disc_loop.py`/`.json` — the ticket as a capital loop vs the book: best config ~30%/yr at ~28%
  occupancy vs book 72.4%/yr — LOSES decisively on occupancy (per-dollar-day yields comparable
  ~0.3%; dislocations are episodic, the book bids daily). Verdict: ticket = containment for disc
  trading at small carve-out (≤2 tickets, ≤8% each), never a pool alternative. Earnings-window
  exclusion COST return in the loop (30→19.5%) but stop-autopsy says report-adjacency is where
  disasters live — kept as cheap insurance, human may override when the print IS the thesis.
- TICKET DESIGN (agreed shape, not yet written into any doc): entry human but gated (one-sentence
  nameable cause; ≥3% below 10dma; vol ≥1.3× norm; not in own earnings window; ≤8% equity,
  ≤2 open); exit mechanical AT entry (GTC sell entry×1.05 + time-stop open of session 10, never
  revisited); quarterly review of disc yield/dollar-day vs the model book.

**VRT episode (9–10 Sep) — live case study.** VRT −8.17% on 9 Sep on NO company news (AI-infra
complex profit-taking; UtilityInnovation deal integration chatter; had been sliding since late
Jul). THE MODEL BOUGHT: Bayes @283.00 (target 289.14, prem 2.17%) and OU @278.10 (target 285.50,
prem 2.66%) — ~8–9% underwater at ~257.6, day ~1–2 of 50. VRT-specific recovery study (price-path,
daily data, dips ≥7% below 3-session high, 48-session window): band −7..−10% = 14/16 to pre-dip
level, 13/16 to +2.5% target, median 8 sessions; deeper than −10% = only 4/8 (crash regime).
Caveats: 2024–26 sample only; the two most recent dips (28 Jul, 18 Aug) are CENSORED and neither
had recovered yet — this is a multi-leg slide, closer in shape to the band's failures (Jun 2024,
May 2026) than to the clean snapbacks. Breadth was 2/9 pre-drop (VST, AVGO), VRT likely third —
gate unarmed under K=4. Discipline: note-and-wait; watch breadth, not VRT.

**`ops/dislocation_scan.py` — TESTED AND CORRECTED (10 Sep, see §3.29).** Pre-open scanner
formalising the VRT process: reads workbook Query, grades all nine names, prints per graded name
the dip metrics, the CLASS base rate (both halves), the NAME'S OWN banded base rates (48-session
recovery to pre-dip and +2.5%), breadth context with ≥4 caution, earnings proximity from AT
G7:G15 (blank = warn), the ready ticket where the grade earns one, and the explicit HUMAN news
test (company-specific = repricing ≠ ticket; sector/general = candidate). Also takes an optional
as-of date to replay a past session. Operating modes: (a) user uploads workbook here pre-open,
Claude runs scan + does the news layer via WebSearch (works today); (b) scheduled locally on the
trading machine post-Script-1, optionally piping flags through Claude CLI for the news pass. The
news layer stays human/Claude by design.

**Other state (4–10 Sep):** 9stock_performance.xlsx ABANDONED by user ("hard to manage" — Box
WOPI rewrote external links; rebuilt as static-snapshot + refresh script, but user will knit
metrics into the main excel later; builder/refresh stay in ops/). Watch-list: brief
(memo/watchlist_brief.pdf) + HANDOVER_WATCHLIST.md delivered for the colleague's Claude; colleague
got premarket_study.zip (tracked files; needs fresh_opt_cands.json separately — sent; and has NO
price data). NVDA question answered: 40% planning is captive/sheet/haircut by design; exec ×1.13
→ 45.4 vs restated bar ~56 — still fails G2; pooling enters only at G5. 3rd-party capital
discussion: AIFMD is the real regulation (not MiFID advice); sub-threshold registered AIFM route
sketched (~74-word summary in chat only, nothing in repo). MU pause window imminent (MU reports
late Sep; AT G11 still blank — chase). Plan remains 74%/yr; pooled refs 72.4/88.5; all five papers
consistent as of 3 Sep (no removal narrative, current-roster 2022 replay −13.8/+1.7 throughout).

### 3.29 The dislocation screen's flag rule, measured (10 Sep) — the week-of-range gate is load-bearing, and VRT does not earn a ticket

First run of `ops/dislocation_scan.py` against the live workbook (Query fresh through 2026-09-09,
613 sessions — the user has done the AVGO backfill). It ran clean and printed **no flags** — which
was itself the finding, because the script had been written to formalise the VRT episode and VRT
was the one thing it should have caught. Two separate causes, both in the flag rule, both now
measured on the harness that validated the original ticket study (`disc_vol_gate.py`, nine names,
daily workbook data, +5%/10-session bracket, halves split 2025-05-23; every signal scored
standalone so the populations nest — the non-overlap rule in `disc_structure.run` lets a loose
rule's early signal displace a tight rule's later one, which confounds exactly this comparison).

| cell | n | hit | avg | train | test |
|---|---|---|---|---|---|
| A tested proxy: 10dma ≤ −3%, week hot | 373 | 66% | +1.50% | +1.02% | +2.45% |
| B alternative: 3-session-high ≤ −5%, week hot | 322 | 71% | +1.85% | **+1.35%** | **+2.72%** |
| A OR B (the scanner as first written) | 445 | 66% | +1.48% | +0.99% | +2.33% |
| A AND B (both dip tests agree) → **STRONG** | 250 | 72% | +1.99% | +1.47% | +3.06% |
| B not A (dip off a running high) → **FLAG** | 72 | 68% | +1.38% | +0.78% | +1.95% |
| A not B (the grinding slide) → **SLIDE** | 123 | 53% | +0.52% | **+0.05%** | +1.32% |
| C violent day, calm week → **DAYVOL** | 154 | 70% | +1.86% | **−0.22%** | **+3.18%** |
| … of those, deep (3sh ≤ −8%) | 61 | 74% | +1.37% | −0.85% | +3.81% |
| D no vol gate at all: 3sh ≤ −5% | 769 | 69% | +1.41% | +0.66% | +2.09% |
| E no screen at all: every session | 4923 | 61% | +1.07% | +0.19% | +1.68% |

- **The dip test that pays is distance below the 3-SESSION HIGH, not below the 10-day mean.**
  B beats A on both halves (+0.33pp train, +0.27pp test, hit 71 vs 66%), and the signals only the
  10dma test finds — the grinding slide — earn **+0.05% on the train half against +0.19% for doing
  nothing at all** (row E). The 10dma branch was carrying the screen's dead weight. This is a
  specification change, not a threshold search: both dip tests were already written into the two
  scripts and no grid was run. Adopted, per §3.1's rule that structural changes survive.
- **The volatility gate must stay a WEEK of range** (5-day mean true range vs the 60-day median).
  Scoring the signal day's own range instead is the only way to flag VRT — and that population
  (row C) averages **−0.22% on the train half against +3.18% on the test half**, worse on train
  than doing nothing; the deep cut is more inverted still (−0.85% / +3.81%). That is the
  single-cell mirage pattern of VST-P2 (§3.25) and the AVGO pause (§3.28a). **Rejected.**
  Note also row D: dropping the vol gate entirely halves the train-half edge (+0.66% vs +1.35%).
  The gate earns its place.
- **So the scan's silence on VRT was correct, and is now explicit rather than accidental.** VRT
  on 9 Sep grades **DAYVOL**: −9.6% against its 3-session high, 2.37× its normal range on the day,
  but only 1.20× across the week — a violent session inside a calm one. The name's own 48-session
  band record is strong (27/31 back to pre-dip, 25/31 to +2.5%) and is printed, labelled as five
  times the ticket window and as context for the name rather than a ticket hit rate. The grade
  carries no ticket. Same discipline as §3.28d: note-and-wait, watch breadth.

Scanner changes: four grades (STRONG / FLAG / SLIDE / DAYVOL) each printing its own class base
rate and both halves, tickets only on STRONG and FLAG, a one-line table of all nine names every
run so no dislocation is ever invisible, the time-stop date derived from the workbook's own
session spacing instead of a ×1.5 calendar guess, an explicit up-front warning when AT G7:G15 is
empty, and an optional as-of argument that replays a past session (all four grade paths were
exercised that way: STRONG CF 2025-01-24, DAYVOL AVGO 2025-01-27, SLIDE AVGO 2025-01-30, FLAG VLO
2025-02-06). Baseline invariance: `disc_structure.py` on the fresh workbook reproduces the
published T=5%/N=10 cell exactly (127 trades, 67% hit, +1.86%, per-week 14.31).

**Live state on this run (data through 9 Sep):** breadth 2 of 9 below their 200dma (AVGO, VST) —
gate unarmed under K=4, so VRT trades. One grade in the book, VRT/DAYVOL, no ticket. **AT G7:G15
is entirely empty** — not just MU's G11; every earnings check the scanner and the ticket rule
depend on reads UNKNOWN. That is the chase, and MU reports late Sep.

**3.29a — the VRT episode was IDIOSYNCRATIC, not complex profit-taking (correction to §3.28d).**
The news layer could not be run (this session has no web search and the environment's egress
policy blocks the finance sites), so the tape half of the news test was done instead, from the
workbook's own Query data. It contradicts the characterisation recorded in §3.28d:
- **9 Sep was VRT alone.** VRT −9.6% close-to-close while MRVL **+4.3%**, MU **+2.8%**, CF +2.8%,
  VLO +1.6%; TSM −0.8%, VST −0.4%, AVGO −1.1%. Book median −0.4%. Exactly ONE name down ≥3%:
  VRT. The two most AI-levered names in the book both rose hard that session, so "AI-infra
  complex profit-taking" is not what the tape shows.
- **VRT was rallying into it, not sliding.** The three sessions before were +4.7%, +4.4%, +3.7% —
  up ~13% in three days, then −9.6% in one. The month-scale slide is real (−9.5% since 24 Jul
  against MRVL +21%, MU +11.6%, TSM +7.9%, VLO +28.6%) but the immediate setup was a round trip
  off a three-day run-up, not a continuation.
- **That puts the episode in §3.26's worst bucket.** The idiosyncratic single-name drop with the
  complex up is the adverse-information case that study isolated: 1–2 names down ≥3% earned
  +1.10% with 14 stops in 249 — the weakest bucket in the table, and precisely what the per-name
  4% pre-market rule exists to veto. Two independent screens now agree: the DAYVOL grade (train
  −0.22%) and the idiosyncratic-drop bucket.
- It also explains the DAYVOL shape mechanically: the WEEK's range was calm (1.20×) because the
  three preceding sessions were an orderly rally; only the 9 Sep session was violent (2.37×).
  "Violent day, calm week" IS the single-name gap-down shape.
- **What the tape cannot settle**, and the news test still must: whether VRT's own event was a
  company-specific repricing (guidance, a contract, a downgrade) or a VRT-specific flow (index/ETF,
  a block, a large holder). Note the asymmetry — under the ticket rules a company-specific cause
  is a repricing and disqualifies, and a single-name drop with the complex up already fails the
  sector-sympathy condition the ticket wants. The news test can only downgrade this one, never
  upgrade it. No ticket either way; the open question is about the held model position.
- **Number to reconcile:** §3.28d records −8.17% for 9 Sep; the workbook's Query has 290.83 →
  262.89, which is −9.61% close-to-close. The −8.17% was probably written intraday. The Query
  series is the reference.
- Not checked, for want of the data: whether the 09:00 pre-market rule would have vetoed either
  sleeve. Both bids (283.00, 278.10) sat ABOVE yesterday's close, so the 4%-below-PM veto looks
  unlikely to bind on this shape — but `data_pm/` was lost to the container recycle (§3.28d), so
  this is unverified and should not be quoted.

### 3.30 Frozen sleeves: the one-position-per-sleeve rule costs ~660 touched bids a year — DIAGNOSTIC PASSES, build it properly (3 Oct)

User proposal: when BOTH sleeves of a name are held, that name is frozen out of the book until
one sells. A violently-moving name can offer several round trips inside that window and the book
takes none of them. He has been taking them by hand in the discretionary log and reports strong
margin, and proposes a second "Today's orders" list permitting a second funding of a name.
Scripts: `disc_reentry_live.py`, `frozen_sleeve_diag.py`, `frozen_sleeve_reserve.py` (all read the
live workbook; the 5-minute archive is still lost so nothing here is verified-fill).

**The live log, corrected.** 20 discretionary trades to 2 Oct. SIX rows dated 2 Oct and labelled
VRT are in fact VST — logged at 135–140 when VRT traded 248.54–254.80 and VST 134.79–143.02
(`disc_reentry_live.py` now relabels any trade whose buy price sits outside the logged name's own
range that day and inside exactly one other name's, and prints the corrections). After the fix,
split by the sleeve occupancy reconstructed from the main blotter's own buy/sell dates:

| entry made when… | n | avg | worst | med hold | P&L |
|---|---|---|---|---|---|
| both sleeves frozen | 7 | +2.74% | +0.21% | 2 sess | +$63.3k |
| one sleeve held | 8 | +3.07% | +0.50% | 2 sess | +$85.3k |
| name wholly free | 5 | +1.47% | **−2.49%** | 16 sess | +$50.5k |

Fifteen entries into a name with capacity already committed, not one loser. The five into a wholly
free name hold the only losses and the only long holds (two AVGO tickets open since 19 Aug, both
under water). Small and hand-picked — the human filter is known to be the alpha (§3.28d) — but it
points the same way as everything below.

**It is a bookkeeping constraint, not a model one.** The Model sheets compute a bid every session
whether or not the sleeve can act on it. One position per sleeve is an artefact of the blotter's
one-row-per-tranche design, so relaxing it is a specification change, the category §3.1 says
survives, not a parameter search.

**Diagnostic — the prize is large** (`frozen_sleeve_diag.py`, nine Model sheets, 630 sessions,
deployed parameters, conservative fills: no position may exit before the day after entry):
- **28.7% of name-sessions have both sleeves occupied** — 74 per name-year. Per name 8.9% (VST) to
  46.7% (VLO); longest single spell 35 sessions.
- On those days the model's own bid is touched **1,619 times** (~660/yr, against the book's ~531
  actual pooled fills/yr). Those entries: avg +1.72%, **median +2.64%**, 101 stops (6.2%),
  **both halves positive (train +0.96%, test +2.18%)**. That is the quality of the trades the book
  already takes (§3.21: completed trades avg 1.6–2.1%, median ~2.25%).
- Not uniform: CF is the warning (118 entries, +0.91%, 42 stops, median hold 12d) and MRVL thin
  (+0.79%, worst −51.1%); TSM, MU, VLO, GM are the strong ones.

**But the pool is fully allocated, so this is a carve-out question, not free money.** On 2 Oct the
whole $2,574,895 of available cash went to six free ungated sleeves at $429,149 each, with nothing
over (Allocation B46 "OK"). A second list is funded only by taking from the first.

**Costed on the reserved capital** (`frozen_sleeve_reserve.py`; one pot, N concurrent slots, idle
cash at 3.14%, every idle day counted — the `dip_reserve.py` yardstick):

| | ann. return | occupancy | avg | aggregate %/dollar-day |
|---|---|---|---|---|
| shared pot, 3 slots, conservative fills | +56.7% | 80.1% | +1.85% | 0.231% |
| shared pot, 3 slots, **sheet convention** | **+77.3%** | 80.4% | +1.96% | 0.280% |
| the pooled book, sheet convention | 72.4% | — | — | 0.306% (§3.27) |

Like for like (sheet convention both sides) the carve-out earns **77.3% against the book's 72.4%**
— slightly ahead annually, slightly behind per dollar-day (0.280 vs 0.306), the difference being
occupancy: the re-entry pot is deployed 80% of the time. Halves agree (train +0.85%, test +2.03%
average per entry). **Slots barely matter** — 1 slot 64.0%, 3 slots 56.7%, 9 slots 55.8%
(conservative basis): the first slot captures most of it, which argues for a SMALL carve-out and
converges on the disc ticket's existing ≤2-open rule.

**The breadth gate does not conflict**, despite today's snapshot (3 of 9 frozen and all of them
gated, breadth 4). Over the sample the K=4 gate would block only **13%** of frozen-day touches, and
those are the weak ones (0.105%/dollar-day vs 0.248% for the rest). **73% of frozen-day touches are
on names ABOVE their own 200dma** — the freeze is normal operation, not distress, consistent with
§3.21. That also shrinks, without removing, the concentration worry.

**What is NOT established, and blocks adoption:**
1. **No drawdown number.** A third position in a name already double-held is triple exposure, which
   is precisely the April-2025 pooled blind spot (§3.13). Return is measured here; risk is not.
2. **Not the pooled marginal test.** Freeze windows come from the captive single-name sheets, and
   the carve-out is scored as an independent pot rather than inside book_sim's pooled loop where it
   would compete order-by-order with the first list and change its fills.
3. **No verified fills.** The 77.3% is sheet convention, which §3.5 shows reads high (RKLB 438 vs
   158); the conservative read is 56.7%. The truth sits between and usually nearer the floor.

**Recommendation at the time: build and test it, do not wire it yet.** It had the best prior of
anything proposed since the pre-market exclusion (§3.16). **It was tested the same day the archive
came back — see §3.30a, which rejects it.** Two things followed:
- **The funding mechanism already exists and is switched off.** Allocation E5 (flag 1/0) and E6
  (amount $) carve a discretionary fund out of cash BEFORE it is divided across the sleeves, and
  the disc log and weekly P&L are already wired to it. E5=0, E6=0 today. That is the second list,
  built, needing only a rule and a size.
- **Blocker for the real test:** `data_5min/` and `data_pm/` must be restored before book_sim can
  run the pooled marginal version with verified fills and a drawdown. Until then the ceiling on
  what can be claimed is what is in this entry.


### 3.30a The re-entry sleeve, tested in the pooled book: REJECTED — it redistributes capital, it does not create value

The 5-minute archive came back on 3 Oct (all nine names, Apr 2024 – 3 Aug 2026, with pre-market
bars), so §3.30's proposal could be run as the test that decides it rather than the diagnostic that
motivates it. `book_sim` gained `reentry` (default None, baseline byte-identical): a THIRD sleeve
per name, eligible only on mornings when both base sleeves are held, bidding the shallower of the
two live bids with that sleeve's premium, and claiming its allocation **from the same pool as every
other order** — so it is funded by thinning the rest, which is the only way to ask the question.
Live config throughout (09:00 / 4% PM rule, verified fills, deployed parameters).
Script: `frozen_reentry_book.py`.

| | full | train | test | maxDD | fills |
|---|---|---|---|---|---|
| baseline | 73.4 | 45.4 | 105.1 | 24.2 | 1234 |
| re-entry, 1 slot | 74.5 | **46.3** | **106.5** | 24.7 | 1337 |
| re-entry, 2 slots | 74.4 | **47.6** | 104.5 | 23.7 | 1421 |
| re-entry, 3 slots | 74.8 | 44.9 | 109.1 | 26.5 | 1460 |
| re-entry, uncapped | 75.3 | 46.0 | 108.7 | 26.6 | 1581 |
| 3 slots, bid ≤ −2% | 75.1 | 44.9 | 109.9 | 24.4 | 1357 |
| 3 slots, bid ≤ −4% | 73.8 | 45.6 | 105.7 | 24.8 | 1266 |

- **The protocol kills it.** Train-pick-then-freeze — the blade every adopted finding passed — picks
  **2 slots** on the train half (+2.1pp) and that cell then **loses the frozen test half by 0.6pp**.
  The only both-halves cell (1 slot, +0.8/+1.3) is picked with hindsight from a four-cell grid.
- **On the convention the book actually trades it is nothing.** Exec-accurate (gap exits both
  sides), 1 slot: **+0.4 full, +0.6 train, −0.0 test**, DD +0.5. The test-half edge disappears
  entirely once execution accuracy is on.
- **Robust to the one reconstruction risk.** data_pm/ was rebuilt from the 5-minute files and its
  cut convention is a reconstruction, so the comparison was re-run on both boundaries. Deltas are
  stable — full +0.4 to +1.1, train +0.6 to +1.6, test −0.0 to +1.3, DD +0.5 throughout. The
  verdict does not rest on the rebuilt cache.
- **Mechanism — the re-entry trades are ordinary book trades.** n=221 at 3 slots, avg +1.66%,
  median +2.21%, 8 stops (3.6%) against the book's own avg +1.73%, median +2.22%, 3.9%.
  Statistically the same trade. The P&L arithmetic shows what is really happening: re-entry adds
  **+$2.87m** while the base book falls from **$23.56m to $21.64m** because every allocation is
  thinner — net **+$0.95m on a $23.5m book, under 1%**. This is §3.27 restated: the pool does not
  have a capital-starvation problem that a new claimant fixes, because the marginal dollar was
  already earning the book's margin somewhere else.
- **The concentration fear was overstated** (my §3.30 caveat 1, withdrawn). Through the April 2025
  episode, 1 slot IMPROVES drawdown (24.0 → 23.1, −0.9pp) and the window return (+12.8 → +15.5).
  Only the uncapped variant hurts (+1.5pp DD). Triple exposure at small size is not the hazard §3.13
  made it look like.
- **Per name, 1 slot** (avg per trade): VLO +3.32, MRVL +3.53, MU +2.47, AVGO +2.07, VST +1.67,
  GM +1.48, TSM +1.27, **VRT −1.37**, **CF −1.24** (3 of the 4 stops are CF's). The name that
  motivated the proposal is the second-worst in the sleeve. Halves of the re-entry trades
  themselves: train n=36 avg +1.02%, test n=65 avg +2.00%.

**Rejection #18, and the first to be rejected after its diagnostic passed.** §3.30's diagnostic was
right that the forgone opportunity is large (660 touched bids/yr, median +2.64%); it was wrong to
read that as money on the table. Those bids are touchable but not *additional* — funding them costs
the same capital the book was already deploying at the same margin.

**What survives, and it matters.** The user's own hand-picked entries into occupied names (§3.30:
n=15, avg +2.74% / +3.07%, **no losers**) beat this mechanical rule's +1.66% decisively. That gap is
the §3.28d finding again — the human filter is the alpha, and the mechanical proxy is the floor. So
the conclusion is NOT that the observation was wrong; it is that **automating it earns the floor
while doing it by hand earns the filter**. Keep it in the discretionary carve-out (Allocation E5/E6,
still switched off), do not wire a second Today's orders list, and judge the carve-out on the
quarterly disc-yield review the ticket design already calls for.

### 3.30b Environment restored (3 Oct) — and what the rebuild cannot guarantee

The loss recorded in §3.28d is largely reversed. All nine 5-minute files are back in `data_5min/`
(Apr 2024 – 3 Aug 2026; MRVL to 13 Aug), and they carry **pre-market bars from 04:00**, which the
originals were separate files for — so `data_pm/` no longer needs its own extracts.
- `build_pm_cache.py` (new) rebuilds `pm_last.pkl` and `pm_last_cuts.pkl` (08:30/09:00/09:15/09:25)
  from `data_5min/` directly. Bars are start-stamped; a cut at T takes the last bar that FINISHED by
  T (stamp strictly before T), which is what a rule acting at T can see.
- `live5_load.py` repaired: it pointed at a dead upload path and still carried the pre-swap roster.
  It now discovers the workbook (`BAYES_WORKBOOK` env var, else `premarket_study/workbook.xlsx`,
  else the newest `TradingExcel*.xlsx` upload) and lists **AVGO, not RKLB**. Run anything that
  touches the book with `BAYES_WORKBOOK=<attachment>`.
- `baseline_check.py` (new) is the gate on all of it: engine vs the workbook's own Model sheets, then
  the pooled baseline against the published numbers.

**Mirror check: exact.** The engine reproduces all five Model sheets on annual return, buys and
stops to the digit (TSM 156.2%, VRT 243.9%, VST 257.7%, AVGO 91.2%, MU 174.2%).

**Pooled baseline: close but not exact, and the gap is the PM cache.** Live config gives
**73.4 / 45.4 / 105.1** against the published **72.4 / 43.9 / 104.9**; stops **47 exactly** and
530 fills/yr against ~531. The inclusive cut boundary gives 71.7 / 42.6 / 104.9 — so the published
figure sits BETWEEN the two reconstructions and neither is the original builder. **Consequence: new
LEVELS carry ±1pp of calibration uncertainty against anything published before 3 Oct; A/B DELTAS are
safe, because both arms share one cache** (the §3.19 convention). Quote deltas, and re-baseline
rather than mixing a post-3-Oct level with a pre-3-Oct one. If the original `data_pm/*_pm.xlsx`
extracts ever surface, rebuilding from them would close the last gap.


### 3.31 The discretionary carve-out made operable: tranche-driven exits, and a bracket placer (3 Oct)

User, on §3.30a's "keep it discretionary": the carve-out has two costs that make it too manual —
every trade is typed into IBKR by hand, and the badges of trade want a bracket with the exit fixed
at entry. Both are addressed; the second is written but UNTESTED against a broker.

**1. The log sets its own exit** (`premarket_study/wire_disc_targets.py` →
`TradingExcel_9stock_disctargets.xlsx`). Disc log col AA now derives the target from the Tranche
label in col V. The two conventions differ on purpose and must not be merged:

| V | target | why |
|---|---|---|
| `Bayes` | entry + prev close × that stock's Bayes π (E7:E15) | the sleeve's own resting sell — the main blotter's Sell @ is Buy @ + close × π |
| `OU` | entry + prev close × OU π (F7:F15) | same, OU side |
| anything else (`DISC`) | entry × (1 + AA40) = +5% | the tested dislocation ticket (§3.28d), multiplicative off the fill |

Previous close is the last Query session **strictly before** the buy date, via
`LOOKUP(2,1/(...))`. A `MATCH` on the buy date would fail at 09:00 (Script 1 pulls after the close)
and then silently change the recorded target next day — after the GTC was placed. "Last session
before" returns the same number either way, so a placed bracket and the log cannot drift apart.
Rows whose target was typed by hand (50, 51, 53, 56–59, 61) are **left as typed** — they record what
was actually placed. Cell-diff verified: 378 cells changed, all in the intended set, and every DISC
row re-derives to the value the sheet already cached. Python mirror of the new formula against the
hand-typed rows: r51 VRT/OU typed 258.64 vs formula 258.38; r50 AVGO/OU typed 360 vs formula 356.00
(AVGO's OU π is only 1.41%, so the round number was 1.1% rich).

**2. A ticker guard (col AH), which the mirror forced.** Running the formula over the live log
produced nonsense on rows 56–59: they are the §3.30 VST-typed-as-VRT rows, so the target was
computed from VRT's 246.12 close against a 139 entry. **Mislabelling used to cost only P&L
attribution; with the exit derived from the ticker it becomes a wrong order.** AH flags
`CHECK TICKER` when the entry sits outside that ticker's own high/low on the buy date, blank until
the buy date reaches Query. The placer refuses any ticket it flags.

**3. The bracket placer** (`ops/disc_bracket_place.py`, `ops/disc_bracket_place_test.py`).
Parent BUY LMT at the log's entry, child SELL LMT GTC at the log's target, transmitted together.
Design decisions worth keeping:
- **It never writes the workbook.** openpyxl blanks every cached value on save (§4), which on a
  live trading sheet means nothing displays until Excel reopens it. Placement state goes to a JSON
  journal keyed on (stock, date, price, shares), which is also what makes a re-run safe.
- Rails, all default-on: dry run unless `--live`; per-ticket and per-run notional caps; refuses a
  `CHECK TICKER` row, a target at or below the limit, or a limit >25% from the last close
  (decimal slips); `--live` against a live-account port additionally needs `--i-mean-it`.
- **The 10-session time stop is deliberately not automated** — IBKR has no "sell at the open after
  N sessions" order, so forcing it means a scheduled market sell, a second and riskier automation.
  `--due` reports which open tickets have passed it and leaves the selling to a human.
- 12/12 screening tests pass, including the openpyxl trap: a freshly-patched workbook whose
  formulas have no cached value reads target=None and the placer **refuses rather than guessing**.
  So the delivered workbook must be opened and saved in Excel once before the placer can read it.
- **Untested against a broker** (no gateway here, and ib_insync is assumed — the trading machine's
  Script 1 framework is unconfirmed). Paper account first, reconcile by hand, then live.

**Live finding from `--due`:** the two AVGO tickets bought 19 Aug are still open and are **six weeks
past their 10-session time stop** (due 2 Sep). They are also the only losers in the whole disc log
(§3.30: −1.94%, −2.49%). The discipline existed and was not applied; that is the carve-out's real
failure mode, not the typing.


### 3.32 CF's profile: the user is right, the profile is intrinsic, and it is the price of the zero beta (7 Oct)

User, on the live record: "I'm not happy with CF. With optimised parameters CF relies on a small
number of high-margin trades to meet its return. That is the wrong profile — it lacks
predictability. Fast turnover stocks are a better fit. But CF is a diversifier, so replacing it
probably needs another diversifier." Scripts: `live_record.py`, `cf_profile.py`,
`diversifier_profile.py`.

**The claim is confirmed, on two independent measures.** Pooled book, live config, verified fills:

| | /yr | avg | hold | stops | lose% | %/$-day | top 3rd of P&L |
|---|---|---|---|---|---|---|---|
| TSM | 91 | +1.00% | 1d | 4 | 2% | 0.222% | 68% |
| VRT | 74 | +1.70% | 1d | 5 | 3% | 0.395% | 73% |
| MU | 55 | +2.19% | 1d | 4 | 3% | 0.420% | 53% |
| GM | 60 | +1.45% | 1d | 4 | 3% | 0.260% | 79% |
| VLO | 35 | +2.87% | 5d | 7 | 7% | 0.258% | 64% |
| **CF** | **24** | **+3.12%** | **12d** | **8** | **14%** | **0.182%** | **102%** |

CF is last on every column that matters: fewest trades, longest hold, most stops, most losers,
lowest yield per invested dollar-day (3.27 found the same). **The decisive number is the top-third
share at 102% — CF's best third of trades carries more than all of its P&L, so the other two thirds
lose money net.** No other name is above 84%. CF uses **13.5% of the book's invested capital-days to
deliver 9.0% of its P&L**.

**But the profile is what the zero beta costs, not a defect.** Across the nine names, book
correlation and turnover correlate **+0.80** (AI beta vs trades/yr +0.59; vs yield per dollar-day
+0.64). CF has AI beta **−0.02**, the only true zero-beta name in the book, and is the slowest. That
is one relationship, not two separate facts, and it is 3.14's structural lesson restated from the
inside: the premium engine wants names that move, and in this era movement is AI-correlated.

**Neither lever changes it.**
- **Entry depth, never tested before** (CF bids k=2.04, the book's deepest). Sweeping CF's k down:
  trade count is FLAT — 57 (deployed), 58 (×0.75), 62 (×0.5), 61 (×0.35), 62 (×0.25) — and hold
  stays 11–14 days. The ×0.75 cell shows +3.1 train / +2.3 test, but it is one cell of five and it
  does not move the shape (top third 102 → 92%), so it addresses nothing the user raised.
- **Exit premium** was already tested and rejected (3.27; and 3.24 Addendum 3 found halving premia
  the exit family's worst cell). CF is slow because its fit asks for 4.66–5.91% and waits; that ask
  is load-bearing.

**What dropping CF is worth.** Pooled, live config: **+2.3pp full, −1.1 train, +6.8 test, maxDD
+2.2pp WORSE** (73.4/45.4/105.1 DD 24.2 → 75.7/44.3/112.0 DD 26.4). Stress windows get worse on
drawdown in all three and worse on return in two of three (Feb–Jun 2025 +12.8→+9.1; Jun–Jul 2026
+35.9→+30.2). CF is also by far the CHEAPEST diversifier to drop: without VLO the test half falls
**16.4pp**, without GM the train half falls **7.4pp**. The three are not interchangeable.

**GM is the existence proof that the quadrant is occupied** — AI beta 0.18, book correlation 0.25,
and yet 60 trades/yr on 1-day holds at 0.260%/dollar-day, on the LOWEST mean daily move in the book
(1.51%). So "uncorrelated ⇒ slow" is a tendency, not a law.

**Correction to 3.14's screening method.** That round screened candidates on daily RANGE and
declined LEN as "too quiet to pay the premium". Range is the weakest of four screens tested here
against realised turnover (corr with trades/yr: range +0.31, mean |move| +0.34, dip frequency +0.42,
dip-and-recovery +0.52). And even the best screen fails to separate CF from GM — 16.0% vs 17.5% of
sessions dipping and recovering, for 24 vs 60 trades/yr. The difference is what each name's FIT asks
for (CF 4.66/5.91%, GM 0.97/4.51%). **Turnover is a property of the fitted premium, not of the price
series, so a candidate cannot be pre-screened on price statistics; the fit has to be run and the
profile read off it.** Any future diversifier round should budget for that and should re-test LEN,
which may have been declined on the wrong measure.

**Recommendation: keep CF, and treat the swap as a priced risk decision rather than a model
verdict.** Dropping the book's only zero-beta name buys +2.3pp/yr and costs 2.2pp of drawdown — in a
sample that cannot price the insurance, because (§6) the only AI drawdown sits in the training
region of every walk-forward fold. That is the trade this book has declined repeatedly. The bar for
a replacement, stated numerically: **book correlation ≤0.3, ≥50 trades/yr, top-third share under
~80%** — GM's quadrant. If the user wants the search, it needs 5-minute data per candidate and a
full fit each, not a screen. **Live-record footnote:** the 63-day live sample has CF at 3 closed
trades, all winners (+1.31% avg) — too small to judge on, and its live complaint is absence rather
than loss.


### 3.33 LEN and NEM re-tested against CF's slot: both declined — turnover does not buy predictability in an uncorrelated name (7 Oct)

User supplied 5-minute data for LEN and NEM after §3.32, to test the two names the August round
(§3.14) left unresolved: LEN declined at G2, NEM put on the watch list for a re-test scheduled
end-Q1 2027 (done early here). Full §3.14 path — `fresh_opt_cands.py LEN NEM` (reference fitted
full-sample and flagged, then variants A and B on the train half), then the marginal book test in
`cf_swap_test.py`. Both files 596 sessions, Apr 2024 – Aug 2026.

**G1 reproduces the August round almost exactly**, which is also a check on the restored pipeline:
LEN beta 0.09 / book corr 0.15 (recorded 0.09 / 0.16), NEM beta 0.27 / 0.31 (recorded 0.27 / 0.32).
Classifications stand: LEN uncorrelated (30% gate), NEM AI-related (50% gate).

**The fits also reproduce.**

| | reference (full-sample, flagged) | A train/test | B train/test |
|---|---|---|---|
| LEN | 16.5% full, 46 buys | 19.2 / 19.9 (9 buys) | 12.5 / **−8.0** |
| NEM | 51.6% full, 87 buys | 47.2 / 35.0 (98 buys) | 48.0 / 39.8 (54 buys) |

LEN lands in §3.14's recorded "17–20%/yr"; NEM in its recorded "honest cluster 35–48%". **NEM passes
the fragility check that killed UAL** — A and B agree rather than one collapsing.

**LEN: declined again, now for two reasons.** Pooled swap CF→LEN is **−5.1 full / −4.0 train / −6.5
test**; B collapses to −8.0%; and the new reason — **LEN trades 19/yr, SLOWER than the 24/yr CF it
would replace.** It fails the user's own criterion as well as the return bar.

**NEM: passes every gate until the binding one.** Swap CF→NEM on the reference vector looks good —
**+1.0 full / −0.6 train / +3.0 test, maxDD −0.6**, 36 trades/yr against CF's 24, 8-day holds
against 12, and much better through the AI drawdown (Jan–Apr 2025 −6.6% → **+9.3%**; Feb–Jun 2025
+12.8 → +19.5). But that vector is a FULL-SAMPLE fit. On the honest train-half vectors the swap
**loses the tested half**:

| swap CF → NEM with… | full | train | test | maxDD | NEM/yr | top 3rd |
|---|---|---|---|---|---|---|
| reference (full-sample) | +1.0 | −0.6 | **+3.0** | −0.6 | 36 | 97% |
| variant A (train-half) | −1.5 | −0.0 | **−3.4** | −0.4 | 78 | **108%** |
| variant B (train-half) | −0.4 | +1.6 | **−3.1** | +0.1 | 45 | 92% |

Only the lookahead vector wins. **Declined at G5**, the gate §3.14a already identified as the
binding one.

**The symmetric test, run on request (`cf_vs_nem_honest.py`).** The comparison above set NEM-honest
against CF-DEPLOYED, and the deployed CF vector is itself a full-sample fit (§6), so CF's own A/B
vectors were refitted (they were lost with the original JSON) and each name run on its own honest
vector, variant against matching variant. **CF's refit reproduces §6 exactly** — reference full
46.9%, B test 42.4%, the published numbers to the decimal.

| captive, verified fills | reference full | A train/test | B train/test |
|---|---|---|---|
| CF | 46.9% | 43.4 / **52.9** | 44.4 / **42.4** |
| NEM | 51.6% | 47.2 / **35.0** | 48.0 / **39.8** |

NEM is better on the TRAIN half on both variants and worse on the TEST half on both — the
train-up/test-down shape this book has declined seventeen times. Pooled, symmetric:

| | full | train | test | maxDD |
|---|---|---|---|---|
| CF on its variant A | 72.4 | 44.6 | 103.9 | 24.1 |
| NEM on its variant A | 71.9 | 45.4 | 101.7 | 23.8 |
| **swap delta** | −0.4 | +0.9 | **−2.2** | −0.4 |
| CF on its variant B | 75.8 | 49.1 | 105.7 | 22.9 |
| NEM on its variant B | 73.0 | 47.0 | 102.0 | 24.3 |
| **swap delta** | −2.8 | −2.1 | **−3.7** | +1.4 |

**Removing the asymmetry strengthens the case against the swap rather than weakening it**: NEM loses
the tested half on both variants, by more than the earlier run suggested. One residual asymmetry
remains and it runs the other way (so it does not rescue NEM): a name with a reference vector is
fitted with ou_W frozen at deployed, so CF searched 8 and 6 dimensions against NEM's 9 and 7 —
the more conservative fit is CF's.

**Incidental, not an adoption case:** CF on its own honest B vector gives the book 75.8 / 49.1 /
105.7 at maxDD 22.9, against the deployed 73.4 / 45.4 / 105.1 at 24.2 — out of sample (the test
column, the only one the B vector did not see) that is +0.6pp, i.e. noise. Read it as reassurance
that CF's deployed vector is not leaving anything on the table, not as a reason to refit.

**The structural finding, and the real answer to the question.** Not one candidate clears §3.32's
profile bar (top third of trades under 80% of P&L): **CF 102%, NEM 97%, LEN 91%** — against MU 53%,
VLO 64%, TSM 68% among the AI names (on the honest vectors it is no better: CF-A 117%, CF-B 107%,
NEM-A 108%, NEM-B 92%). And NEM's variant A settles the mechanism directly: it trades
**78/yr, more than three times CF**, and its concentration is the **worst in the comparison at
108%**. *Turnover does not buy predictability in an uncorrelated name.* The §3.32 observation that
fast names are also even ones is a correlation across the book, not a lever that can be imported: a
name that does not move with the book earns when the book does not, which is by construction a
minority of the time. **The concentration IS the diversification.**

**Recommendation: keep CF.** Five candidates have now been tested against this slot (FCX, NEM, UAL,
LEN in §3.14, NEM and LEN re-tested here with better data and the corrected screen) and none
survives. The profile the user wants — uncorrelated AND even — does not exist in this sample. The
honest choice is therefore the one §3.32 framed: either accept that the diversifier slot is
inherently bursty and judge it on drawdown contribution rather than predictability, or drop the
slot entirely (eight names: +2.3pp/yr at +2.2pp of drawdown) as a priced risk decision. A genuinely
different return source — not a US equity in this regime — is the only thing that would change the
answer.


### 3.34 Box serves the 5-minute archive after all — the data-loss exposure is closed (8 Oct)

User asked whether he could give access to a Box folder of 5-minute data for a wider candidate
round. He already has: the Box MCP connection is live on his own account. **And §3.28d's note that
Box "can search/list but CANNOT download binaries" is wrong.** `get_file_content` returns the
sheet's extracted text, the harness writes it to disk when large, and the result is **exact**.

**Verification, on a file held both ways.** LEN pulled from Box against the hand-uploaded copy:
**53,643 of 53,643 bars identical, zero mismatches.** Round-tripped through the importer and read
back through the real pipeline: daily OHLC identical on all 596 sessions, and the verified-fill
checker agrees on 595 of 595. A Box-sourced file is indistinguishable from an uploaded one.

**Tooling: `ops/box_5min_import.py`.** The Box calls are the assistant's (search/list for the file
id, `get_file_content` to land the text on disk); the script converts that text to
`data_5min/<TICKER>_5min.xlsx` in the layout `minute_index` and `daily_from_5min` already read.
Datetime rendering VARIES BETWEEN FILES because the extraction reflects each sheet's display format
(LEN comes back "2024-04-01 7:35:00", SKHY "2026-07-13 04:00"), so the parser tries several.
Validation refuses to write on too-few bars, duplicate or out-of-order timestamps, or bars whose
high/low do not bracket open/close; `--check-against` compares to a reference file.

**Consequence for §3.28d.** The container-recycle exposure is largely closed: `data_5min/` and
`data_pm/` can both be rebuilt from Box without the user re-uploading anything (data_pm via
`build_pm_cache.py`, which derives from the 5-minute files). Cost is one `get_file_content` call
per ticker, so a session can comfortably restore or add ~10–20 names.

**What Box holds** (`Bayesian Capital / 00 Live Trading / data / minute data /`, 38 ticker folders,
plus `Pre market data/` and `2021 to 2023 bear market/`):
- *in the book*: TSM, VRT, VST, AVGO, MU, GM, VLO, CF, MRVL
- *already judged*: ALNY, RKLB, NVDA, PLTR, TSLA, SOFI, SPOT, FCX, NEM, UAL, LEN, MRNA, OXY, FSLR,
  DVN, COIN, AMD, SMCI, CEG
- *staged and never tested*: **ARM, DE, HOOD, MSTR, NOC, RBLX, RTX, SHOP, SKHY, STNG** — the folder
  ids of DE/NOC/RTX/STNG are adjacent to FCX/NEM/UAL/LEN's, so they were staged as the next
  candidate round. On the §3.32 reading the non-AI ones are the interesting set: **DE** (agriculture
  / industrial), **NOC** and **RTX** (defence), **STNG** (tankers). SKHY has only Jul–Aug 2026 and
  is too short to fit.


### 3.35 G1 on DE / NOC / RTX / STNG: three clean, and STNG is the best-shaped candidate yet screened (8 Oct)

First candidate round sourced entirely from Box (§3.34) rather than hand uploads. `g1_screen.py`
(new) runs the cheap gate — AI-factor beta, book correlation, and the price-behaviour columns —
with the incumbent diversifiers printed alongside for scale.

| | AI beta | corr AI | corr book | range% | \|move\|% | dip+rec | class |
|---|---|---|---|---|---|---|---|
| **NOC** | **−0.05** | −0.10 | **−0.07** | 2.05 | 1.10 | **8.2** | uncorrelated (30% gate) |
| **RTX** | 0.09 | 0.18 | 0.21 | 1.93 | 1.07 | **8.4** | uncorrelated (30% gate) |
| **STNG** | 0.13 | 0.17 | 0.21 | **3.23** | 1.77 | **23.5** | uncorrelated (30% gate) |
| [CF] | −0.02 | −0.02 | 0.14 | 2.89 | 1.67 | 16.0 | incumbent |
| [GM] | 0.18 | 0.24 | 0.35 | 2.61 | 1.51 | 17.5 | incumbent |
| [VLO] | 0.11 | 0.15 | 0.31 | 3.04 | 1.65 | 19.9 | incumbent |

**All three clear G1 as uncorrelated**, so all three face the 30% gate rather than 50%. But they
split sharply on shape:

- **NOC is the purest diversifier ever screened here** — book correlation −0.07, cleaner even than
  CF's 0.14. It is also **the quietest**: 8.2% of sessions dip-and-recover, barely half CF's 16.0%
  and well under LEN's 19.1%, and LEN went on to trade just 19/yr and was declined partly for being
  too quiet to pay the premium. **RTX is the same story** (0.21 correlation, 8.4% dip+rec). Both are
  defence primes — low-range trending names.
- **STNG is the find.** Correlation as clean as VLO's (0.21), and **more active than any incumbent
  diversifier or prior candidate**: range 3.23% (above VLO 3.04 and CF 2.89) and dip+rec **23.5%**,
  the highest yet recorded — above NEM 22.8, VLO 19.9, LEN 19.1, GM 17.5, CF 16.0. It is the first
  candidate to sit plainly in the quadrant §3.32 identified as occupied but unfilled: uncorrelated
  AND busy.

**Caveat carried forward from §3.33, and it is the binding one:** no price screen determines
turnover — that follows the FITTED PREMIUM, not the price series (dip+rec correlates only +0.52
with realised trades/yr, and it failed to separate CF from GM at all). So this table is a prior,
not a verdict. STNG has the best prior any candidate has had; NOC and RTX have the worst, but
"worst prior" is not a rejection and only a fit settles it.

**Next step: fit STNG** (full §3.14 path — reference, A, B — then the G5 marginal book test against
CF). NOC and RTX are lower priority on the shape evidence but remain untested.

**DE is blocked, not declined.** Its Box folder (409651804651) and file (2411461460426) both return
Internal Server Error on every call — `get_file_content`, `get_file_details` and
`list_folder_content_by_folder_id` alike — while every other folder and file in the same parent
responds normally. That is a Box-side problem with that item, not the integration. Re-uploading DE
to Box under a new item, or attaching the file to chat, would both route around it.


### 3.36 STNG declined twice over — the screen's best-ever prior produced the book's slowest fit, and the name cannot carry the size (8 Oct)

**The fit (§3.14 path, `fresh_opt_cands.py STNG`).**

| | train | test | buys (test) |
|---|---|---|---|
| reference (full-sample, flagged) | **−33.6%** | **+99.7%** | 51 |
| A | 24.3% | **13.4%** | 16 |
| B | 4.7% | **4.1%** | 15 |

The reference's halves are violently inverted (−33.6 / +99.7), and the honest vectors earn
**4–13% on the tested half against the 30% gate** STNG faces as an uncorrelated name. **Declined at
G2**, more decisively than LEN (17–20%). The honest fits also trade only ~13/yr, below LEN's 19 and
CF's 24.

**This is the sharpest confirmation yet of §3.33's rule, and it arrived prospectively.** STNG had
**the best price-behaviour prior any candidate has ever had** — dip-and-recover on 23.5% of
sessions, the highest ever screened, above every incumbent and every prior candidate — and the fit
turned it into **the slowest name in the comparison**. The screen was not merely imprecise; it was
anti-predictive. Turnover follows the fitted premium, not the price series. Treat every future
price screen as a way to order the queue, never as evidence.

### 3.37 A liquidity gate is missing from the protocol — and it independently kills STNG

User's question, prompted by STNG's thin tape: "if average volume is below 1m shares at $80, that is
under $80m traded a day, and I want to buy $0.5–1m. Will my activity move the price?"
Script: `liquidity_check.py`.

**ADV is the wrong denominator here.** The model does not work an order through the day — it rests a
LIMIT BUY below the market and is filled, if at all, by someone else's selling. What binds is the
dollar volume that trades AT OR BELOW the bid, which is far smaller than ADV. Measured from the
5-minute archive, regular hours, bid 2% below the previous close:

| | median px | ADV $m | $1m / ADV | $ at bid (median fill day) | of which first hour | **$1m / at-bid** | **$1m / at-bid, thin day** |
|---|---|---|---|---|---|---|---|
| **STNG** | **61** | **39.1** | **2.56%** | **16.9m** | **1.6m** | **5.9%** | **53.2%** |
| NOC | 522 | 309.1 | 0.32% | 95.5m | 13.2m | 1.0% | 7.3% |
| RTX | 139 | 484.4 | 0.21% | 203.2m | 6.5m | 0.5% | 3.2% |
| CF | 86 | 144.5 | 0.69% | 105.0m | 7.0m | 1.0% | 12.4% |
| GM | 53 | 422.8 | 0.24% | 245.4m | 22.9m | 0.4% | 3.0% |
| VLO | 154 | 336.5 | 0.30% | 189.3m | 10.9m | 0.5% | 7.0% |
| VST | 155 | 624.7 | 0.16% | 307.3m | 71.0m | 0.3% | 2.4% |
| TSM | 211 | 2641.1 | 0.04% | 1752.1m | 343.6m | 0.1% | 0.5% |
| MU | 123 | 2509.0 | 0.04% | 1711.2m | 393.5m | 0.1% | 0.5% |

- **The user's estimate was generous**: STNG's ADV is **$39m**, not $80m (median price $61, not $80).
- **At $1m, STNG is 5.9% of the at-bid volume on a median fill day and 53% on a thin one.** Only
  **$1.6m** trades at or below the bid in the first hour, where §3.20 showed 56–80% of fills occur.
  At that share the order is not participating in the price, it IS the price.
- **The book's incumbents are all fine.** The worst is CF at 1.0% / 12.4%; the AI names are
  negligible at 0.1%. **NOC and RTX are fine too** (1.0% / 7.3% and 0.5% / 3.2%) — liquidity is not
  what is wrong with them.
- **It also makes STNG's backtest unreliable in the flattering direction.** The engine assumes a
  FULL fill at the bid whenever the low touches it. Where an order is 5–50% of the volume available
  at that price, real fills would be partial, so the simulation overstates both fill count and
  return — for STNG and not for the book names.
- **Where impact actually lives**: entries and take-profits are resting limits (passive; the failure
  mode is a partial fill, not a worse price). The **50-day time stop sells AT THE OPEN** and is
  marketable — that is the one genuinely impactful order, on ~4% of trades.

**Proposed addition to the gates — G0b, liquidity, run before G2 because it is nearly free.** At the
book's current ~$5.4m equity a funded sleeve is ~$430k and both sleeves of a name ~$860k, so test
$1m. Admit only if **$1m ≤ ~1% of the median at-bid dollar volume AND ≤ ~10% on a thin (10th
percentile) fill day** — which is where every current book name sits and where STNG plainly does not.
Note the gate TIGHTENS as the book grows: at double the equity STNG's thin-day share would exceed
100%, and even CF's would pass 25%.


### 3.38 NOC declined; RTX is the first genuine contender — it fixes CF's concentration but G5 will not confirm it (8 Oct)

**NOC: declined at G2, decisively.** Reference (full-sample, flagged) 12.6% full / 2.2 train /
23.4 test; **variant A −1.9% on the tested half, variant B −7.2%** — both honest vectors NEGATIVE
out of sample, against a 30% gate. Pooled swap CF→NOC is −5.9 full / −7.1 train / −4.2 test. The
purest correlation ever screened here (book corr −0.07) and it earns nothing: §3.32's trade-off at
its most extreme. Its quiet tape (dip+rec 8.2%) did predict this, but only by luck — see STNG
(§3.36), where the same screen pointed the opposite way and was wrong.

**RTX: clears every gate up to the last one.**

| captive, verified fills | reference full | A train/test | B train/test |
|---|---|---|---|
| CF | 46.9% | 43.4 / 52.9 | 44.4 / 42.4 |
| **RTX** | **51.9%** | **36.7 / 47.2** (69 buys) | **34.3 / 49.7** (42 buys) |

**RTX is the first candidate whose two honest variants both clear its gate on both halves** (34–50%
against 30%). NEM's agreed but under a 50% gate it could not clear; LEN's and NOC's collapsed
negative. It also passes G0b comfortably (§3.37: $1m is 0.5% of at-bid volume on a median fill day,
3.2% on a thin one) and G1 cleanly (beta 0.09, book corr 0.21).

**And it fixes the thing the user actually complained about.** Top third of P&L: **RTX 66% on the
reference, 84% and 81% on A and B — against CF's 102%, 117% and 107%.** On every vector tested,
RTX's return is far more evenly spread than CF's. It is the first candidate to come in under
§3.32's 80% concentration bar at all, and the reference figure sits among the AI names (MU 53%,
VLO 64%, TSM 68%). Stress windows improve across the board (Jan–Apr 2025 −6.6% → **+1.5%**;
Feb–Jun 2025 +12.8 → +17.2; Jun–Jul 2026 +35.9 → **+49.6**).

**But G5 will not confirm it.** On the reference vector the swap is +1.7 full / +0.5 train / +3.1
test at maxDD +0.0 — a clean win. On the honest vectors, symmetric (each name on its own, variant
against matching variant):

| | full | train | test | maxDD | RTX /yr | top 3rd |
|---|---|---|---|---|---|---|
| swap on variant A | **+1.5** | **+1.0** | **+2.0** | −0.6 | 50 | 84% |
| swap on variant B | **−3.1** | **−4.9** | **−0.5** | +0.7 | 32 | 81% |

**A says swap, B says do not.** That is the §3.27 shape — directions disagree, so no adoption. The
disagreement is driven by CF's own B being an unusually strong configuration (75.8 / 49.1 / 105.7 at
maxDD 22.9), not by RTX being weak. RTX also only sometimes clears the ≥50/yr half of the bar
(50/yr on A, 32 on B, 24 on the reference) and holds 16 days on the reference, longer than CF's 12.

**Verdict and the shape of the decision.** Not adoptable on the protocol: the binding gate does not
agree with itself. But this is the first time the trade-off has been clean enough to put as a
choice rather than a verdict, because **the two objectives now separate**:
- On RETURN the evidence is a coin flip (+1.5 on A, −3.1 on B, +1.7 on the lookahead reference).
- On PREDICTABILITY — the user's actual objection — the evidence is **one-sided for RTX on every
  vector**, and drawdown is neutral-to-better throughout.

So the honest options are (a) keep CF and leave RTX on the watch list for a re-test when more data
accumulates, as NEM was; or (b) swap on the risk argument — trading roughly neutral expected return
for materially more evenly distributed P&L and slightly better drawdown — as a priced decision in
the shape of the RKLB→AVGO call (§3.28), explicitly NOT a model verdict. **Six candidates have now
been tested against this slot; RTX is the first that could be defended either way.**


### 3.39 DE declined at G2; the candidate programme closes at seven names, one contender

DE arrived by hand upload after its Box item kept erroring (§3.35). It clears the cheap gates
easily — liquidity $459m ADV, $1m = 0.5% of at-bid volume on a median fill day and 3.4% on a thin
one, better than CF; and G1 beta 0.14, between LEN's 0.09 and GM's 0.18, with a book correlation of
0.30 that matches incumbent VLO's 0.31. So: uncorrelated, 30% gate.

| DE | train | test | buys |
|---|---|---|---|
| reference (full-sample, flagged) | 31.2% | 37.6% | 88 (~37/yr) |
| A | 39.3% | **16.8%** | 27 |
| B | 38.7% | **22.7%** | 40 |

**Declined at G2.** The reference's halves are balanced and it trades 37/yr, which is the most
promising-looking reference of the round — but it is a full-sample fit, and both honest vectors
land at **16.8% and 22.7% against the 30% gate**. They at least agree with each other and decay in
the honest direction (train ~39 → test ~17–23) rather than inverting, so this is an ordinary
shortfall rather than a mirage. It is simply not enough.

**A correction made in passing.** `g1_screen.py` had classified DE as AI-related on a
book-correlation threshold of 0.30 that I introduced this session. §3.14 classified on AI BETA
(FCX 0.49, UAL 0.43, NEM 0.27 → AI-related; LEN 0.09 → uncorrelated), and a 0.30 correlation cut
would exclude incumbents GM (0.35) and VLO (0.31) from their own slot class. The script now keys on
beta, with book correlation as context, and flags anything between 0.09 and 0.27 as BORDERLINE
rather than deciding it. DE reads uncorrelated either way once the threshold is the documented one.

**The programme, settled.** Seven candidates have now been tested against CF's slot:

| | G1 | liquidity | G2 (honest test half) | G5 |
|---|---|---|---|---|
| FCX | AI-related | — | through-cycle 48.2% < 50% | declined (§3.14) |
| UAL | AI-related | — | A clears, B collapses to 12.7% | declined (§3.14) |
| NEM | AI-related | — | 35.0 / 39.8 vs 50% gate | **declined at G5**, both honest vectors (§3.33) |
| LEN | uncorrelated | pass | 19.9 / **−8.0** vs 30% | declined at G2 (§3.33) |
| STNG | uncorrelated | **FAIL** (53% of thin-day at-bid volume) | 13.4 / 4.1 vs 30% | declined twice (§3.36–37) |
| NOC | uncorrelated | pass | **−1.9 / −7.2** vs 30% | declined at G2 (§3.38) |
| DE | uncorrelated | pass | 16.8 / 22.7 vs 30% | declined at G2 (§3.39) |
| **RTX** | uncorrelated | pass | **47.2 / 49.7 vs 30%** | **ambiguous — A +1.5, B −3.1** (§3.38) |

Only RTX got past G2, and only RTX clears §3.32's concentration bar (top third 66% on the
reference against CF's 102%). It remains the single open question and the only one defensible
either way; everything else is closed. The structural reading of §3.32–3.33 stands unchallenged
after seven attempts: **in this era and this universe, a name that does not move with the book
earns in bursts, and no screen predicts which ones will earn at all.**


### 3.40 Is NEM really "AI-related"? The relationship is real, the threshold was not — and it changes nothing (8 Oct)

User challenge: NEM is a gold miner, 35.0/39.8 looks good, and it only failed at G5 — what is the
basis for the classification, and is it worth reconsidering? Scripts: `beta_stability.py`,
`nem_add_honest.py`.

**1. The basis is stronger than the §3.14 note's own aside ("even gold miners") suggests.**

| | beta | s.e. | 95% interval | R² | train | test | roll min/max | **ex-shock** |
|---|---|---|---|---|---|---|---|---|
| **NEM** | **0.27** | 0.034 | +0.20 to +0.34 | **0.097** | 0.19 | 0.39 | −0.22 / +0.59 | **0.30** |
| RTX | 0.09 | 0.021 | +0.05 to +0.13 | 0.031 | 0.12 | 0.05 | 0.00 / 0.28 | 0.05 |
| DE | 0.14 | 0.024 | +0.10 to +0.19 | 0.057 | 0.16 | 0.12 | −0.03 / 0.36 | 0.12 |
| LEN | 0.09 | 0.030 | +0.03 to +0.15 | 0.016 | 0.09 | 0.09 | −0.16 / 0.28 | 0.08 |
| [GM] | 0.18 | 0.029 | +0.12 to +0.23 | 0.059 | 0.21 | 0.13 | −0.02 / 0.37 | 0.17 |
| [VLO] | 0.11 | 0.030 | +0.05 to +0.17 | 0.021 | 0.21 | −0.04 | −0.22 / 0.54 | **−0.00** |
| [CF] | −0.02 | 0.031 | −0.08 to +0.04 | 0.000 | 0.08 | −0.15 | −0.36 / 0.19 | −0.10 |

NEM's beta is statistically solid (t ≈ 8), carries **the highest R² of any candidate or incumbent
diversifier**, and — the test that matters — **survives removal of the 5% largest factor-move days
at 0.30**, slightly higher than the full-sample estimate. So it is not risk-off co-movement, which
every equity shares; it is a persistent relationship. By contrast incumbent **VLO's apparent 0.11
beta vanishes ex-shock (−0.00) and flips sign between halves (0.21 → −0.04)** — VLO's factor link
is the artefact, not NEM's. The direction of the §3.14 call was right.

**2. But the threshold was never derived, and the number is not precise.** NEM's beta travels
0.19 → 0.39 across the halves and −0.22 to +0.59 across rolling windows, and 0.27 sits much nearer
GM's 0.18 (an incumbent) than UAL's 0.43, yet §3.14 grouped it with UAL. On the corrected
classifier (§3.39, which keys on beta and flags 0.09–0.27 as ambiguous) **NEM reads BORDERLINE, not
AI-related.** That is the same correction made for DE, and the user was right to ask for it.

**3. It changes nothing, because the gate only touches G2 and NEM failed G5.** On a 30% gate NEM's
35.0/39.8 passes G2 comfortably. G5 — the binding gate (§3.14a) — does not reference the
classification at all, and NEM fails it in both configurations on honest vectors:

| swap CF → NEM | full | train | test |   | add NEM as a tenth | full | train | test | maxDD |
|---|---|---|---|---|---|---|---|---|---|
| variant A | −1.5 | −0.0 | **−3.4** |   | variant A | −2.6 | +1.7 | **−8.1** | −2.3 |
| variant B | −0.4 | +1.6 | **−3.1** |   | variant B | −2.6 | +2.2 | **−8.7** | −1.9 |

The add-as-tenth case on honest vectors was the one gap left by §3.33 (it had been run on the
full-sample reference only, where it looked like −3.5 for −2.3pp of drawdown). Closed here: it is
**−8 to −9pp of tested-half return** for about 2pp of drawdown. Decisively bad.

**4. And it would not fix the original complaint.** NEM's top-third share is 97% on the reference,
117% on A, 93% on B — as concentrated as CF's 102%. RTX (66%) remains the only candidate that
addresses predictability.

**Verdict: NEM is reclassified BORDERLINE rather than AI-related, and still declined.** Its
standalone return is genuinely respectable; it simply does not survive contact with the book, in
either the swap or the add configuration, on either honest vector. The reclassification is worth
recording because it corrects the reasoning, not the outcome.


### 3.41 "Accept it is an AI strategy": two premises hold, the decisive one does not — and the diversifier to question is GM, not CF (8 Oct)

User's proposition: diversifier candidates keep failing; the AI names drive the live book's return;
if the AI trade takes a 25% hit the diversifiers will not save the book anyway; and in a bear we
will be watching daily regardless — so should this be run as an avowedly AI strategy?
Script: `bear_roster.py`, on the 2021–23 archive restored from Box (§3.34).

**Premise 1 — candidates keep failing: TRUE.** Seven tested, none admitted (§3.39).

**Premise 2 — the AI names drive the value: TRUE but milder than it sounds.** Live record to 6 Oct:
the AI six produced **80.4% of P&L from 67% of the slots**; the three diversifiers 19.6% from 33%.
Per slot the diversifiers run at **49% of an AI name's rate** — in a bull. That is what insurance
costs, not evidence it is not working.

**Premise 3 — "the diversifiers will not save the book anyway": CONTRADICTED.** Calendar 2022,
pooled, verified fills (nine-name rows reproduce §3.28b exactly, so the restored data is sound):

| roster | n | nothing | per-name gate | breadth gate |
|---|---|---|---|---|
| nine (current) | 9 | −13.8% DD 23.7 | −1.5% DD 16.8 | **+1.7% DD 15.7** |
| **AI six only** | 6 | **−25.1% DD 33.8** | −12.2% DD 26.5 | **−7.0% DD 22.1** |
| AI six + GM | 7 | **−26.2% DD 34.1** | −15.8% DD 28.3 | −15.8% DD 28.3 |
| AI six + VLO | 7 | −18.5% DD 28.6 | −5.3% DD 24.3 | −1.1% DD 20.9 |
| **AI six + CF** | 7 | −16.0% DD 24.9 | −3.3% DD 15.6 | **−0.3% DD 13.0** |

Full span Jan 2022 – Jun 2023: nine **+17.8%**, AI six **+14.6%**, AI six + CF **+19.3% at DD 13.0**
— the best cell in the table — and AI six + GM **+0.9%**.

- **The gate does not substitute for the diversifiers.** With the breadth gate on both sides,
  dropping them costs **8.7pp of 2022 return and 6.4pp of drawdown** (+1.7 → −7.0, DD 15.7 → 22.1).
  Unprotected the gap is **11.3pp** (−13.8 → −25.1). They were load-bearing in the one real bear.
- **It is the diversification, not the headcount.** ONE diversifier recovers most of it: AI six + CF
  (7 names) reaches −0.3% at DD **13.0**, a BETTER drawdown than the full nine.
- **CF is the best of the three in a bear — the name that was under review for removal.** On every
  protection setting and both windows, AI six + CF beats AI six + VLO beats AI six + GM.
- **GM is the one that failed.** Adding it to the AI six made 2022 *worse* (−26.2 vs −25.1) and cost
  **13.7pp over the full span** (+0.9 vs +14.6). A rate-sensitive automaker in a rate shock is not a
  diversifier. Note the opposite holds in 2024–26, where dropping GM costs 7.4pp of the train half
  (§3.32) — so this is regime-specific, and it is GM, not CF, whose diversifier credentials the
  evidence now questions.

**Premise 4 — "we will be watching daily anyway": the weakest link, and it is already tested.**
§3.22 established that a fast crash damages the book through **held inventory** marked down and
overnight gaps, *neither of which an entry veto can touch*; cancelling crash-day bids saves only
marginal new entries, and §3.21 showed those are ordinary trades. Every mechanical form of
"intervene in the downturn" has been tested and subtracted: the breaker (§3.13), gate+breaker
(−10.2% vs gate alone −2.6%), the price stop (§3.13), the holding halt (§3.21), the intraday
stand-down (§3.22). Watching tells you what is happening; the only instruments that protect
inventory are exits and sizing, and both have been measured as costly here.

**CAVEAT, and it is the real one.** 2022 was a rate-shock bear with a commodity bull to rotate into
— CF and VLO rose *because* of the energy and food shock. An AI-specific bust might offer no such
refuge, which §3.13 already flagged. So this says the diversifiers worked in the bear we have, not
that they will work in the bear the user is imagining. The nearest AI-specific episode in the sample
(Jan–Apr 2025, AI factor −45.9%) also favoured them on the held construction (§6: five names −37.3%
vs eight −21.6%), though today's pooled nine-vs-eight is more equivocal (§3.32: CF cost 3.6pp of
return in that window and saved 2.2pp of drawdown).

**Verdict.** The strategy IS AI-driven and saying so plainly is right — 80% of live P&L from the AI
six, and the honest planning basis should reflect it. But "therefore drop the diversifier slot" does
not follow from the evidence: in the only full bear on record the slot was worth 9–11pp of return
and 6–10pp of drawdown, and the gate did not replace it. The defensible version of the user's
instinct is narrower and better supported: **keep the slot, stop hunting for additions (seven
failures is enough), and question GM rather than CF.**


### 3.42 The AI-only case, properly tested: the diversifiers do not drag returns, and decisive stand-down is far worse than the gate (8 Oct)

User sharpened the §3.41 argument: a grinding bear is both what the diversifiers protect against AND
what a person watching daily can see starting; a sudden AI crash is unprotectable either way; so the
diversifiers insure a risk already covered more cheaply by judgement — run the AI book, take a
one-year view, review. **A correction first: my §3.41 reply cited §3.22 ("entry vetoes cannot
protect inventory"), but that finding is about FAST crashes. In a slow bear there is time to act,
and acting means SELLING. That is a different instrument and it had never been measured.**
`book_sim` gained `regime_exit` (default None, baseline invariant): on a signal, liquidate at the
open and place no orders until it clears. Scripts: `bear_standdown.py`, and the carrying-cost run.

**1. Decisive stand-down is much WORSE than the gate — on both rosters, both windows.**

| | nothing | gate (no new buys) | **STAND DOWN (sell all)** |
|---|---|---|---|
| nine, calendar 2022 | −13.8% DD 23.7 | **+1.7% DD 15.7** | **−15.1% DD 16.7** |
| AI six, calendar 2022 | −25.1% DD 33.8 | −7.0% DD 22.1 | −18.9% DD 21.1 |
| nine, full span | +0.8% | **+17.8%** | **−11.8%** |
| AI six, full span | −4.8% | +14.6% | −6.7% |

Selling into a grinding bear crystallises losses the model would otherwise have exited at target,
and then misses the recovery — the signal is on for **213 of 251 sessions in 2022**, so standing
down means being flat for most of the year including the turn. This is the exit family's verdict
again (§3.13 price stop, §3.24 week-end exit): **the gate — stop buying, hold to target — already
IS the optimal response to spotting a bear.** The user's instinct is right; the instrument that
expresses it is the one already deployed.

**2. The detection lag is the honest limit.** The breadth signal first fired **28 Jan 2022, 18
sessions in**, with the equal-weight index already **−12.4% from its peak** (nine) / −15.1%
(AI six) — **47% of the total fall was already done** before any stand-down could act. "We can spot
it" is true; "we can spot it early" is not, on a mechanical benchmark.

**3. The premise that the diversifiers drag returns is WRONG — and this is the decisive number.**
2024–26, live config, the regime most favourable to an AI-only book:

| roster | n | full | train | test | maxDD | fills |
|---|---|---|---|---|---|---|
| nine (current) | 9 | **73.4** | **45.4** | 105.1 | **24.2** | 1235 |
| **AI six only** | 6 | **66.1** | **32.7** | 105.7 | **35.2** | 949 |
| AI six + CF | 7 | 65.5 | 41.4 | 92.2 | 30.0 | 1008 |
| AI six + VLO | 7 | 72.6 | 34.3 | 119.2 | 31.1 | 1035 |
| AI six + GM | 7 | 72.3 | 49.8 | 97.0 | 29.0 | 1088 |

Dropping the three costs **−7.4pp full, −12.7pp train, +10.9pp of drawdown**, and fills fall 1235 →
949 (−23%). **There is no carry to harvest: the one-year view would give up return AND take more
drawdown.**

*Why the per-slot figure misled us both:* §3.41 measured the diversifiers at 49% of an AI name's
P&L rate per slot, which looked like drag. It ignored that they are also CAPACITY. The book is
constrained by sleeve occupancy, not by opportunity (§3.30): when the six AI names — which
correlate 0.61–0.85 with each other — are simultaneously held or gated, capital with nowhere to go
idles at 3.14%. Nine names give it somewhere to work. This is §3.28's counter-cyclical pooling
uplift seen from the other side. Note the comparison is already generous to the AI-only case:
giving the six the full capital rather than six-ninths would idle MORE of it, not less.

**Verdict.** Three of the four premises now fail: the diversifiers do not drag returns (they add
7.4pp and remove 10.9pp of drawdown even in an AI bull), spotting the bear is late (47% of the fall),
and acting decisively on the spot is far worse than the gate already deployed. What survives is
real and worth saying plainly: **this IS an AI-driven strategy** (80% of live P&L from the AI six),
**hunting for more diversifiers is finished** (seven failures), and **the three incumbents are not
interchangeable** — GM is the one the bear evidence questions (§3.41), CF the one it vindicates.


### 3.43 Capacity without leverage: the daily book is near its equal-weight liquidity ceiling, and every way of raising it concentrates the AI trade — which is the real case for a second cadence (8 Oct)

User wants to deploy more capital without leverage and proposes a different trading cadence —
weekly, larger premia, on names the daily book does not hold. Three things were established.

**1. The daily book is close to its ceiling, and CF sets it.** Applying §3.37's gate (an order
under ~1% of the median at-bid dollar volume and ~10% on a thin fill day) name by name:

| | median at-bid | thin day | max name order | binds on |
|---|---|---|---|---|
| AVGO | 2064.9m | 219.4m | **20.65m** | median |
| TSM | 1752.1m | 191.2m | **17.52m** | median |
| MU | 1711.2m | 185.1m | 17.11m | median |
| MRVL | 623.7m | 68.2m | 6.24m | median |
| VRT | 480.3m | 35.6m | 3.56m | thin day |
| VST | 307.3m | 41.3m | 3.07m | median |
| GM | 245.4m | 33.3m | 2.45m | median |
| VLO | 189.3m | 14.4m | 1.44m | thin day |
| **CF** | 105.0m | 8.1m | **0.81m** | thin day |

**Under equal weights the thinnest name binds the whole book: CF caps a name-order at $0.81m, so
the equity ceiling is ~$7.3m against today's ~$5.4m — about 1.3× headroom.** (Conservative: it
assumes every name funded at once, where a typical morning funds about six sleeves.)

**2. A per-name liquidity cap would raise the ceiling roughly 10×, to ~$73m — but it is not free.**
Letting each name take what it can absorb concentrates the book mechanically into the liquid AI
names (AVGO, TSM and MU alone absorb $55m of the $73m). That reintroduces exactly the
concentration §3.42 measured as costing **7.4pp of return and 10.9pp of drawdown**. Note this is a
different question from §3.18, which asked whether unequal weights EARN more at fixed capital (they
do not); this asks how much capital the book can CARRY, and there the answer differs. The cap is
worth testing on its own, but as a capacity instrument it buys room by taking AI beta.

**3. Which is the real argument for a second cadence — better than the one offered.** It is not
that the daily book cannot take more capital; it is that **every route to making it take more
concentrates it into the AI trade**, and that has just been measured as expensive. A weekly book on
names the daily model rejects is the only route that adds capacity without adding concentration.

**The weekly model's state, recovered.** It exists, is validated, and runs NVDA and AVGO live
(AVGO now also sits in the daily book — a conflict to resolve before any expansion). Two real
structural advantages over the daily model:
- **Only TWO parameters are fitted** (cap and premium), because the mean-reversion term is dormant
  — reconfirmed on a fresh name today: *"binding constraint: formula 0%, open 80%, athcap 20%"*.
  Against §3.1's record of fitting failures, a 2-parameter search is far more defensible than a
  10-parameter one.
- **It barely loses anything to fill verification.** Only Monday fills are same-day ambiguous;
  Tue–Fri exits are provable from daily bars. The daily model loses roughly half its sheet return
  to this (§3.5, RKLB 508% → 158%).

**Against it:** its own fragility record (implementation spec lists the weekly premium ranging
0.06–0.20 on one name, and weekly experiments pinning to a grid boundary, as overfitting tells;
§3.1 — weekly refitting beat frozen in 1 of 18 folds); its planning figures are LOWER than the
daily book's (NVDA 58%, AVGO 60% against the daily plan of 74%); and **its capital profile is
committed, not liquid** — today's smoke test ended with 3 of 3 tranches still holding, 100% of
terminal value in open positions, median hold 18 days but a 95th percentile of **562 days**, which
is what the 26-week cap exists to bound.

**Infrastructure repaired (it was dead).** `weekly_name.py` — "run any name through the full weekly
pipeline" — failed at import through three modules, all tracing to the 2025 upload path that died
with the container: `stop_sweep.load_book` (now discovers the workbook like `live5_load` and reads
its roster from the Query headers), `weekly_mr`'s NVDA-specific module globals (now tolerate a
roster without NVDA), and `five_min.make_checker` → `minute_index.make_checker` (different return
signature). It now runs end to end on any ticker with a 5-minute file.

**Proposed next step.** Candidates should be the HIGH-VOLATILITY names the daily model rejected,
since the weekly premia that fit are 6–20% and need names that move: TSLA and PLTR (which already
have weekly vectors in `weekly_params.json`), plus COIN, MSTR, SMCI, ARM, HOOD from Box. Run them
through `weekly_name.py`, judge on the NEIGHBOURHOOD MEDIAN rather than the fitted peak (the script
reports both by design), and apply the liquidity gate — it matters more here, since a weekly
position is held for weeks rather than days.


### 3.44 Weekly cadence, seven candidates: HOOD is the find, and it is the strongest candidate this book has produced (8 Oct)

First use of the repaired weekly pipeline (§3.43) as a candidate programme, on the high-volatility
names the daily model rejected. All seven pulled from Box (§3.34). Results:
`premarket_study/weekly_candidates.json` (tracked, per §3.28d's lesson about
gitignored result files being lost).

| stock | frozen (NVDA params) | optimised | **nbhd median** | 25th | WF | consensus |
|---|---|---|---|---|---|---|
| **HOOD** | 27.9% | 91.3% | **80.8%** | **76.5%** | **2/3 (+12.7pp)** | **2/3 (+16.0pp)** |
| PLTR | 29.5% | 123.9% | 94.4% | 81.5% | **1/3 (−7.4pp)** | 1/3 |
| TSLA | 18.7% | 47.1% | 19.4% | 13.3% | 2/3 | 1/3 |
| ARM | 1.4% | 38.3% | 19.1% | 10.9% | 1/3 | 1/3 |
| COIN | −22.3% | 1.8% | −10.3% | −15.0% | 2/3 | 2/3 |
| MSTR | −36.6% | −5.7% | −14.5% | −24.7% | 2/3 | 2/3 |
| SMCI | −18.3% | −5.0% | −8.0% | −13.1% | 2/3 | 2/3 |

**Rejected outright: COIN, MSTR, SMCI** — negative at frozen parameters AND negative neighbourhood
medians. The crypto proxies and SMCI trend rather than mean-revert on a weekly clock; the model has
nothing to harvest.

**Not worth a slot: TSLA, ARM.** Neighbourhood medians ~19%, far below the daily book's 74% plan,
and their optimised peaks are spikes (TSLA within-10pp 8/169, 25th percentile 13.3%).

**PLTR: high but it does not transfer.** A broad high plateau in sample (median 94.4%, 25th 81.5%)
and the best raw number of the seven — but the walk-forward is **1/3, mean −7.4pp**. The plateau is
an in-sample object; the walk-forward is the out-of-sample evidence, and it says refitting fails.
The trustworthy figure is the frozen 29.5%.

**HOOD is the find, and by this book's standards it is unusually clean:**
- **Neighbourhood median 80.8%, 25th percentile 76.5%, peak 91.6%** — the plateau is high AND
  broad (within-10pp of peak: **80 of 169 cells**, against TSLA's 8 and PLTR's 8). The premium
  profile climbs monotonically (18 → 48 → 56 → 72 → 73 → 78 → 90) rather than spiking.
- **The walk-forward is POSITIVE — 2/3, mean +12.7pp; the consensus vector 2/3, +16.0pp.** Set
  against §3.1, where weekly refitting beat frozen in **1 fold of 18** across six experiments, a
  2/3 with a double-digit mean is the first time refitting has transferred in this model.
- **Anchor-robust**: 91/96/85/122/92% across Mon–Fri, so it does not depend on the Monday anchor
  (§3.7's advantage is a bonus here, not a crutch).
- **Liquidity is ample**: $1.66bn ADV, $1m = 0.2% of median at-bid volume — twentyfold more
  headroom than CF, which binds the daily book.
- **Terminal-mark robust**: marking the open positions down 20% takes 91.3% → 73.7%.

**Planning figure by the §5 convention** (parameter-neighbourhood median) is **≈80%/yr** — above the
daily book's 74% plan, on capital the daily book cannot absorb (§3.43).

**Caveats, and they are not small.** The walk-forward is three folds, not eighteen — a 2/3 is
encouraging, not established. All of it is a 2024–26 bull. Every run ends 100% invested with a
95th-percentile hold of 113 days, so this is committed capital and the 26-week cap (§3.6) is
load-bearing. And HOOD is a retail-brokerage proxy whose correlation with the AI complex has not
been measured — G1 has NOT been run on it, which matters because §3.43's whole argument for a
second cadence is that it must add capacity WITHOUT adding AI concentration.

**Next steps, in order:** (1) G1 on HOOD — if it is just another AI-beta name the capacity argument
collapses; (2) a proper half-sample freeze rather than the 3-fold walk-forward; (3) resolve the AVGO
conflict (it runs the weekly model and now sits in the daily book); (4) only then a pooled weekly
book sim.

**Importer hardening, forced by the data.** SMCI's Box export is defective: the 19:00–19:55
after-hours block appears TWICE with DIFFERENT prices on 6 Nov in BOTH 2024 and 2025 — two series
spliced. The importer refused it, correctly. On inspection all 24 duplicates sit after 16:00 and the
regular-hours daily bars are clean, so `box_5min_import.py` now validates and writes only the window
the pipeline actually reads (04:00–16:00), reporting after-hours faults without failing on them.
All seven files were re-imported on that basis so the archive is uniform.


### 3.45 G1 on HOOD: it is an AI name, and my candidate set was AI-correlated by construction — but the low-correlation names rescue the idea, and RTX weekly is the best result in this book (8 Oct)

**HOOD fails, decisively.** AI beta **0.71** (s.e. 0.053, CI 0.60–0.81), book correlation 0.50,
**R² 0.234 — the highest of anything screened here**, against NEM's 0.097. Stable across halves
(0.78 / 0.60), rolling 0.45–1.16, never near zero, and **the relationship STRENGTHENS without crash
days (ex-shock 0.84)**. Robinhood is a retail risk-appetite proxy, and in this era the AI trade IS
the retail risk-appetite trade. §3.43's case for a second cadence was that it must add capacity
WITHOUT adding AI concentration; HOOD adds both. **Declined.**

**And the whole §3.44 set fails the same way**: PLTR 0.50, TSLA 0.60, MSTR 0.65, COIN 0.68,
ARM 0.97, SMCI 1.06. **My error**: I selected those names on HIGH VOLATILITY, and §3.14 had already
established that in this era volatility and AI correlation are the same axis. The candidate set was
AI-correlated by construction and I walked into a finding already in this file.

**Re-run on the LOW-CORRELATION names — which were sitting in `data_5min/` the whole time:**

| stock | AI beta | frozen | optimised | **nbhd median** | 25th | within 10pp | **WF** | consensus |
|---|---|---|---|---|---|---|---|---|
| **RTX** | **0.09** | 10.7% | 56.9% | **47.7%** | **45.9%** | 57/169 | **3/3 (+14.5pp)** | **3/3 (+14.5pp)** |
| **NEM** | 0.27 | 23.4% | 76.2% | **57.5%** | **50.9%** | 28/169 | 2/3 (+11.5pp) | 2/3 (+17.9pp) |
| DE | 0.14 | 22.4% | 35.2% | 27.7% | 23.0% | 81/169 | 2/3 (+1.6pp) | 3/3 (+4.2pp) |
| NOC | −0.05 | 2.5% | 22.1% | 17.5% | 7.0% | 81/169 | 1/3 | 1/3 |
| STNG | 0.13 | 8.5% | 25.4% | 16.2% | 13.9% | 53/169 | 2/3 | 2/3 |
| LEN | 0.09 | −19.5% | −12.2% | −14.3% | −16.7% | 169/169 | 1/3 | 1/3 |

**RTX on the weekly clock is the strongest single result this book has produced.**
- **Walk-forward 3/3, mean +14.5pp — and the consensus vector also 3/3.** Set against §3.1, where
  weekly refitting beat frozen in **1 fold of 18**, a clean 3/3 is unprecedented here.
- The plateau is nearly flat: median 47.7%, **25th percentile 45.9%**, peak 59.0%. The premium
  profile is a shelf (33/50/53/47/43/42/46/41), not a spike.
- **Anchor-invariant**: 57/54/51/51/53% Mon–Fri.
- **AI beta 0.09, book correlation 0.21** — genuinely uncorrelated, so it is capacity WITHOUT
  concentration, which is exactly what §3.43 required.
- Liquidity comfortable ($1m = 0.5% of median at-bid, 3.2% thin). Terminal mark −20% takes
  56.9% → 42.7%.
- Binding constraint **athcap 87%** — it is buying dips below the running high, not the open.

**The structural finding, and it reframes §3.38.** RTX was ambiguous in the DAILY book (G5
disagreed: A +1.5, B −3.1) and is unambiguous in the WEEKLY one. NEM was declined daily and is
strong weekly (57.5% median, consensus 2/3 +17.9pp). **The question was never "should RTX replace
CF" — it was "what cadence does RTX want".** A name that does not suit the daily clock can suit the
weekly one, and the daily programme's seven failures may partly have been a cadence mismatch rather
than seven bad names.

**Caveats.** Three folds is not eighteen. All of it is the 2024–26 bull. RTX's optimised run ends
100% invested with a 95th-percentile hold of 149 days, so the 26-week cap (§3.6) is load-bearing and
this is committed capital. And 47.7% is below the daily book's 74% plan — the case is that it earns
that on capital the daily book cannot absorb (§3.43), not that it is a better use of a marginal
dollar.

**Next:** a proper half-sample freeze on RTX and NEM rather than the 3-fold walk-forward; then a
pooled weekly book sim; then the AVGO conflict (it runs the weekly model and sits in the daily
book). Results in `premarket_study/weekly_candidates.json` (13 names, tracked).


### 3.46 The half-sample blade on RTX and NEM weekly: both pass, on five cuts each — and RTX is the one that fits the profile you asked for (9 Oct)

§3.45 rested on a three-fold walk-forward, which refits each fold and so can pass a name on the
strength of three vectors none of which you would have been holding. This is the blade that chose
the daily book instead (§5): **fit once on the first half, freeze, score the second with one vector
chosen blind.** Split 2025-05-23 → cut week 60 (2025-05-27); train 59 weeks, test 64.

| | NVDA params (no fit) | **FROZEN on test** | edge | frozen nbhd median | 25th | [lookahead] test optimum |
|---|---|---|---|---|---|---|
| **RTX** cap 0.050 prem 0.070 | 10.1% | **51.3%** | **+41.3pp** | **49.0%** | **46.0%** | 67.4% |
| **NEM** cap 0.065 prem 0.150 | 19.6% | **77.3%** | **+57.7pp** | 55.3% | 47.6% | 125.5% |

Both clear it, and clear it by a wide margin. The frozen vectors reached **76%** (RTX) and 62%
(NEM) of what a cheat with hindsight could have taken from the test half. Neither is in-sample
inflated — RTX scores *higher* on the half it never saw (train 46.2% → test 51.3%).

**Split-date sensitivity, because one cut is one number.** Refit and rescore at cuts 44/52/60/68/76
(`weekly_freeze_shift.py`). **Frozen beats the no-fit baseline on 5/5 cuts for both names.**

| cut | RTX frozen (edge) | RTX pick | NEM frozen (edge) | NEM pick |
|---|---|---|---|---|
| 44 (Feb-25) | 47.8% (+34.9) | 0.020/0.035 | 59.6% (+29.2) | 0.070/0.110 |
| 52 (Mar-25) | 62.4% (+49.9) | 0.030/0.070 | 59.8% (+30.7) | 0.070/0.110 |
| 60 (May-25) | 51.3% (+41.3) | 0.050/0.070 | 77.3% (+57.7) | 0.065/0.150 |
| 68 (Jul-25) | 50.2% (+39.2) | 0.030/0.070 | 34.0% (+11.8) | 0.070/0.110 |
| 76 (Sep-25) | 37.0% (+24.6) | 0.050/0.070 | 34.3% (+8.6) | 0.070/0.110 |

**A concern I raised and the sensitivity run retired.** At the base cut, NEM's train half picked
0.065/0.150 and its test half 0.020/0.080 — opposite corners, which is normally the tell that a
surface has moved rather than been measured. It is not: **the train-half pick is 0.070/0.110 at four
of the five cuts.** What moved was the *test* half's own argmax, and that is a lookahead quantity
with no standing. The fitted vector is stable; RTX's prem is 0.070 at three of five, cap drifts
0.020–0.050.

**The edge decays as the test half shortens** (RTX +49.9 → +24.6pp, NEM +57.7 → +8.6pp). Partly
fewer trades (RTX 50 → 12), partly that later cuts score only the 2026 stretch. **Plan on the
neighbourhood median across cuts — RTX ~49%, NEM ~50% — not on the base-cut headline**, and note
NEM's spread across cuts is far wider (29.9–55.3%) than RTX's (38.8–62.9% but 48.8/49.0/49.4 at
three of five).

**Why RTX is the pick, on your own criterion.** You rejected CF because "with optimised parameters
it relies on a small number of high margin trades… fast turnover stocks are a better fit." On the
full sample at their frozen vectors:

| | ann | trades/yr | per tranche | median hold | open at end | mark −20% | mark −40% |
|---|---|---|---|---|---|---|---|
| **RTX 0.050/0.070** | 52.9% | **17.9** | 6.0 | 26d | **0%** | **52.9%** | **52.9%** |
| NEM 0.070/0.110 | 73.0% | 15.8 | 5.3 | 14d | 100% | 57.3% | 39.2% |
| NEM 0.065/0.150 | 71.6% | 11.1 | 3.7 | 45d | 100% | 56.1% | 38.1% |

**RTX's frozen run ends entirely in cash.** Its 52.9% is realised, not marked — the only result in
this book with no terminal-mark exposure at all. NEM ends fully invested on all three tranches, so
a −20% mark takes 73.0% → 57.3% and −40% → 39.2%. NEM at the base-cut vector is also the CF profile
exactly: 11.1 trades/yr at a 15% premium with a 45-day median hold. **If NEM is run, run it at
0.070/0.110** — the vector the train half actually picks four times out of five, 15.8 trades/yr,
14-day median hold, and a higher full-sample return than the 0.150 cell.

**Status.** RTX weekly is confirmed: the blade, five cuts, AI beta 0.09, comfortable liquidity, and
a trade profile that matches what you said you want. NEM weekly passes too but is the weaker of the
two — wider cut-to-cut spread, full terminal-mark exposure, AI beta 0.27 — and its case rests on the
0.070/0.110 vector, not the one the base cut picked.

**Not yet done:** the pooled weekly book sim, and the AVGO conflict (it runs the weekly model and
now also sits in the daily book). Results in `premarket_study/weekly_freeze.json` and
`weekly_freeze_shift.json` (tracked).


### 3.47 The pooled weekly book: RTX+NEM carries $4–6m at ~59% tested, pooling adds almost nothing here (and why), and AVGO's weekly slot fails the blade (9 Oct)

Every weekly number before this one was a **captive** result — one name, three tranches, each
owning a third of that name's capital and compounding alone. `weekly_book_sim.py` runs the book the
way the daily book actually trades (§3.9): one pot of cash, and each Monday the free sleeves divide
whatever is not already committed.

**Validation first.** `mode='captive'` reproduces `Name.seg()` to **3.6e-15 on total return**, trade
counts identical, for both names. No pooled number was read before that passed. (One real bug it
caught: `Name.ann` measures from the first session of `w0` to the last of `w1`; annualising from
week-*end* to week-end silently inflated everything by 0.3–0.4pp.)

**The book, on frozen train-half vectors throughout — no lookahead anywhere below:**

| | ann | maxDD | trades/yr | open at end | mark −20% |
|---|---|---|---|---|---|
| **RTX+NEM pooled, full** | **66.2%** | **15.6%** | 33.6 | 48% | 59.3% |
| **RTX+NEM pooled, test half** | **58.8%** | **15.6%** | 32.3 | 48% | 46.5% |
| RTX alone, test | 58.7% | 16.3% | 17.8 | 0% | 58.7% |
| NEM alone, test | 62.9% | 28.5% | 14.5 | 100% | 36.0% |

Pairing them is worth it on risk, not return: **max drawdown 28.5% → 15.6%** against NEM alone, and
the terminal mark exposure halves. For scale, the daily book's tested maxDD is 24.7%.

**Pooling adds almost nothing on the weekly clock — +2.8pp full, +0.8pp on the test half — and I
had predicted the opposite.** The reason is structural and now measured, not guessed: across 246
name-weeks there are **zero** weeks with a zero-range predecessor, so a weekly sleeve is non-live
**only when it is holding** — and a holding sleeve has no cash to lend. The daily book's pooling
uplift comes from sleeves that are *in cash but blocked* (earnings pause, ATH guard); the weekly
model has no such block. Mean live sleeves 2.0 of 6. What uplift there is comes from recycling exit
proceeds, which in captive mode sit idle in the selling sleeve's own pot until that sleeve next
fills.

**AVGO and DE fail the same blade RTX and NEM passed** (`weekly_freeze.py`, same protocol as §3.46):

| | no fit | frozen on test | edge | train → test |
|---|---|---|---|---|
| AVGO | 33.0% | **30.9%** | **−2.0pp** | 106.1% → 30.9% |
| DE | 22.3% | **20.1%** | **−2.3pp** | 60.5% → 20.1% |

Both post a **negative** edge over not fitting at all, and AVGO's halves are inverted 3.4-fold —
the §5 tell. **AVGO is the incumbent weekly name and it does not survive the protocol that chose
the daily book.** That is evidence on the open AVGO conflict and it points one way: its weekly slot
is not earned. (I have not yet run the daily-side comparison, so this is one side of that question.)

Run anyway, as a measurement: adding them cuts the test half from 58.8% to **42.8%** (AVGO),
**45.7%** (DE), **36.9%** (both), while cutting maxDD 15.6% → 8.1%. That is drawdown insurance
bought at roughly 22pp of return — the same trade §3.42 priced and declined on the daily book.

**The 26-week cap (§3.6) is free here**: identical to no cap, so no position reaches it at these
vectors. A **13-week** cap is marginally better (66.8% vs 66.2%, maxDD 14.5% vs 15.6%, 100 trades
vs 79) — one sample, flagged, not adopted.

**Capacity, which is what §3.43 actually asked.** The liquidity gate (§3.37) binds on the single
order: $2.03m for RTX, $2.89m for NEM. Uncapped pooling lets one sleeve claim the whole pot, so the
*book* can be no bigger than one order. Capping a sleeve's share fixes that:

| max share of pool | implied book | ann | cost |
|---|---|---|---|
| uncapped | $2.0m | 66.2% | — |
| **0.50** | **$4.1m** | **66.2%** | **nil** |
| 0.33 | $6.1m | 65.0% | −1.2pp |
| 0.25 | $8.1m | 57.2% | −9.0pp |
| 0.17 | $12.2m | 48.9% | −17.3pp |

**$4m is free and $6m costs a point.** Beyond that the cap starts refusing capital at the moment
it is most wanted and the return falls away fast. So the weekly cadence adds roughly **$4–6m of
capacity at ~59% tested, uncorrelated with the AI trade** (RTX AI beta 0.09, NEM 0.27) — which is
precisely the thing §3.43 said the daily book could not do at any price.

**Caveats.** Two names and six sleeves is a thin book; the maxDD figures especially are one path.
All of it is the 2024–26 bull. And 48% of the test-half ending value sits in open positions, all of
it NEM's — a −20% mark takes 58.8% to 46.5%.

**Next:** correlate the weekly book's equity curve against the daily book's (the combined-book
question, which none of this answers), and close out the AVGO conflict with the daily side.
Results in `premarket_study/weekly_book_sim.json`; AVGO and DE merged into `weekly_freeze.json`.


### 3.48 The weekly "three tranches" are one position cut in three — they lock in week 4 and never separate again (9 Oct)

Asked to explain the six sleeves of §3.47's book, I measured them instead of describing the intent,
and the intent is not what happens.

**What a weekly sleeve is.** It is NOT the daily book's Bayes/OU pair — those are two different
models on one name. All three weekly sleeves of a name run the *same* model with the *same* fitted
(cap, prem). They differ only in start week: tranche 0 prices its first bid in week 2, tranche 1 in
week 3, tranche 2 in week 4, each with a third of the name's capital. Each holds at most one
position; when free it bids `min(week open, ATH×(1−cap))` and sells at `bid + prev week close ×
prem`.

**They synchronise immediately and permanently.**

| sleeve | first bid wk | weeks bidding | fills | exits | median hold | max hold |
|---|---|---|---|---|---|---|
| RTX t0 / t1 / t2 | 2 / 3 / 4 | 51 / 50 / 49 | 14 / 14 / 14 | 14 / 14 / 14 | 4w each | 20w each |
| NEM t0 / t1 / t2 | 2 / 3 / 4 | 33 / 33 / 32 | 14 / 13 / 13 | 13 / 12 / 12 | 2w each | 23w each |

Of RTX's 123 weeks, **49 have all three bidding, 72 have none, and exactly two have fewer than
three — weeks 2 and 3, before tranche 2 has started.** NEM is the same. From week 4 (2024-04-29)
the three never separate again, for 120 consecutive weeks. When two or more bid, the bids are
**identical in 49/50 weeks (RTX) and 32/32 (NEM)**.

**Why it is structural, not a quirk of these vectors.** Same parameters → same bid → they fill or
fail to fill together → same target → they exit together → they come free together. There is no
mechanism to desynchronise them. The initial stagger is the only source of difference and it is
consumed in the first three weeks. This holds for **every name in `weekly_candidates.json`**, since
`Name.seg` runs the identical construction.

**Collapsing the structure costs nothing** (RTX+NEM, full sample, pooled):

| structure | ann | maxDD | trades | open at end |
|---|---|---|---|---|
| 3 tranches, 1-week stagger | 66.2% | 15.6% | 79 | 48% |
| **1 sleeve per name** | **66.2%** | **15.6%** | **27** | **48%** |
| 3 tranches, 2-week stagger | 67.5% | 15.6% | 79 | 48% |
| 3 tranches, 4-week stagger | 68.1% | 15.6% | 78 | 48% |

Identical to the decimal, on a third of the trades. (Pooled mode is where this is exact: three
synchronised sleeves each taking a sixth of the pool is the same order as one sleeve taking a
third. Widening the stagger to 2 or 4 weeks buys 1–2pp by delaying the lock, which is a sample
artefact, not a design.)

**What this corrects in §3.45–3.47.**
1. **Every weekly trade count in this file is inflated threefold.** RTX's "17.9 trades/yr" is
   **6.0 distinct positions a year**, each entered in three identical pieces; NEM's 15.8 is 5.3.
   The relative ordering survives (RTX still turns over faster than NEM, and far faster than NEM
   at the base-cut 0.065/0.150 vector, which is 3.7), but **the absolute turnover is a third of
   what I reported, and my "fast turnover, the profile you asked for" claim for RTX was made on
   the inflated number.** Holding periods are unaffected: RTX 4 weeks median, NEM 2.
2. **§3.47's book is two positions, not six.** The 15.6% max drawdown is a two-position path. That
   is thinner than "six sleeves" sounds and the caveat should be read accordingly.
3. **It is a second, sharper reason pooling adds nothing** (§3.47 found a sleeve is non-live only
   when holding). The three sleeves of a name are not three claimants on the pool — they are one.

**What to do about it.** Collapse to one sleeve per name in any live weekly book: same return, same
drawdown, **a third of the commissions and a third of the manual IBKR entries**, which matters
given the carve-out friction raised earlier. If entry-timing diversification is genuinely wanted it
has to come from something that actually desynchronises — different premia per tranche, or a
staggered re-entry delay after an exit — neither of which has been tested.


### 3.49 The 2-day clock on RTX: it lengthens holds rather than shortening them, and the benchmark says turnover is a property of the NAME, not the bar (9 Oct)

The weekly model was declined on holding period, not return. The 2-day clock asks the other
question: keep the daily Bayes/OU architecture and slow only the bar. `two_day.py` does that —
the engine needed no change, since it already measures interest and the 50-day stop in **calendar**
days off the `dates` array rather than in rows, so bars stamped with each block's last session are
correct by construction. Two things did need building:

- **A block-aware fill verifier.** On a 2-session bar most same-bar ambiguity disappears: a bid
  touched in session 1 with the target high in session 2 is **provable from daily bars**. Only a
  round trip inside one session still needs the 5-minute checker. So the 2-day clock is verified
  at least as strictly as the daily book, not less.
- **Phase.** An n-session clock has n phases. Phase is a free parameter and fitting it is
  overfitting, so every phase is run.

RTX, n = 1 (the control, same harness), 2 and 3, all phases, scored on the half-sample blade:

| clock | no-fit test | **frozen test** | fills/yr | **median hold** | full fit | hold |
|---|---|---|---|---|---|---|
| n=1 ph0 | 41.9% | **43.1%** | 27.7 | **12d** | 51.5% | 15d |
| n=2 ph0 | 28.4% | **54.9%** | 18.1 | **28d** | 50.5% | 15d |
| n=2 ph1 | 30.9% | **36.6%** | 14.7 | **22d** | 48.9% | 25d |
| n=3 ph0 | 15.5% | 48.7% | 16.6 | 20d | 46.5% | 35d |
| n=3 ph1 | 16.9% | 44.9% | 17.2 | 24d | 47.8% | 24d |
| n=3 ph2 | 14.8% | 31.0% | 13.2 | 22d | 51.2% | 23d |

**1. It does the opposite of what was wanted. Median hold goes 12d → 22–28d.** The reason was
predicted and is confirmed: the clock does not set the holding period, the **premium** does, and
the fit raises the premium when the bar widens (daily 0.036/0.034 → 2-day 0.067/0.067). The 95th
percentile is 50–54d on *every* clock — that is the 50-calendar-day stop, i.e. the stop is doing
the exiting, not the target.

**2. The "edge" column is my own artefact and should be ignored.** The no-fit baseline is a daily
seed vector mechanically rescaled by √n, and it degrades as the bar widens (41.9% → ~30% → ~16%),
so n=2's "+26.5pp edge" is mostly the baseline falling, not the fit rising. Compare **levels**
instead: frozen test n=1 43.1%, n=2 average 45.8%, n=3 average 41.5%. **Flat.**

**3. Phase dependence sinks it anyway.** n=2 phase 0 gives 54.9% and phase 1 gives 36.6% — **18pp
on which session you start counting from.** By the rule written into the module before the run, a
result that depends on phase is not a result.

**4. The sample cost is severe.** Slowing the clock halves the bars. The n=2 train half is 144 bars
carrying 11–23 fills, fitted with **ten** parameters. Boundary hits across runs on `lam`, `k`,
`phi_L`, `ou_prem`, `ou_buf_k`, `ou_W`; seed-to-seed spread 1–4pp. Against §3.1's record this is
not a measurement.

**The benchmark that reframes the question** (`book_turnover.py`, live book at deployed parameters):

| | fills/yr | median | 75th | 95th | ≤5 days | |
|---|---|---|---|---|---|---|
| TSM / VRT / VST / AVGO / MU | 91.5 / 69.6 / 74.8 / 59.7 / 56.1 | **1d** | 3–6d | 22–40d | 70–81% | |
| **book, all trades** | **351.7** | **1d** | **5d** | 29d | **76%** | |
| GM (reference vector) | 60.3 | 1d | 5d | 35d | 76% | matches the book |
| VLO | 34.6 | 5d | 25d | 50d | 52% | |
| **CF** | **25.7** | **12d** | 28d | 50d | **35%** | |
| **RTX daily (frozen)** | **27.7** | **12d** | — | 50d | — | **CF's profile** |
| RTX 2-day (frozen) | 14.7–18.1 | 22–28d | — | 53d | — | |

**The live book turns over in a day.** Median hold 1 day, 76% of trades closed within 5 calendar
days, 352 fills a year across five names. That is the thing that is working, and it is very fast.

**CF's rejection is now quantified**: 25.7 fills/yr, median hold 12 days, only 35% inside 5 days
against the book's 76%. The intuition behind *"relies on a small number of high margin trades…
fast turnover stocks are a better fit"* was correct and is now a number.

**And RTX on the daily clock has exactly CF's profile** — 27.7 fills/yr, 12-day median. **RTX was
never going to be the complementary name wanted, on any clock.** The weekly result (§3.45–3.46) was
real, and it was real for a name whose turnover was always wrong for this purpose. Slowing the
clock only moved it further away.

**The conclusion that matters.** Turnover is a property of **the name and its fitted premium**, not
of the bar. A slow name cannot be made fast by changing the clock, and the clock change costs
sample, costs phase-robustness, and lengthens the hold. **The 2-day cadence is declined.**

**What to do instead — the screen has never had a speed gate.** Every candidate programme in this
file (§3.14, §3.38–3.45) judged names on return and on AI correlation. None judged them on fills
per year or holding period, which is why two of the three stored candidates (CF, VLO) are far
slower than the book and nobody noticed until now. Two concrete next steps:

1. **Add a turnover gate to the candidate screen** — something like ≥50 fills/yr, median hold ≤3
   days, ≥70% of trades inside 5 calendar days (the book's own profile; GM passes it, VLO and CF
   fail it) — and re-run selection on the low-AI-correlation names with that gate alongside G1.
2. **Or force the fast regime directly**: on the DAILY clock, constrain the premium and shorten
   `stop_days`, and measure the return available at each median holding period. That turns
   "what does the entity need" into a frontier you pick a point on, rather than a hope about the
   optimiser. The data above says the lever is the premium and the stop, both of which are already
   in the model.

Results in `premarket_study/two_day.json`; `two_day.py` and `book_turnover.py` are tracked.


### 3.50 The screen with a turnover gate (G4): only GM passes, the fast names are all AI names — and CF does not need replacing, it needs refitting (9 Oct)

**The gate.** Every candidate programme in this file judged names on return and AI correlation.
§3.33 used turnover once, as an aside, against the wrong yardstick — LEN was declined partly for
being "slower than the 24/yr CF it would replace" — and §3.49 showed CF is itself three times
slower than the book it sits in. **The bar is the book, not CF**: measured at deployed parameters,
the live five do 56–92 fills/yr, hold for a median of ONE day, and close 70–81% of positions inside
five calendar days.

**G4: ≥50 fills/yr, median hold ≤3 days, ≥70% closed within 5 days.** Measured on the unseen half
at the frozen train-half vector. Run over all 17 names in `data_5min/` outside the book
(`screen_speed.py`, harness = `two_day.Clock` at n=1, i.e. the daily model in §3.49's control).

| name | AI beta | class | no-fit | frozen | G2 | fills/yr | med | ≤5d | G4 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| **GM** | 0.18 | uncorrelated | 39.1% | 42.7% | Y | **53.5** | **1d** | **83%** | **Y** | **PASS** |
| VLO | 0.11 | uncorrelated | 106.3% | 47.6% | n | 25.1 | 4d | 60% | n | fails G2 |
| RTX | 0.09 | uncorrelated | 41.9% | 43.1% | Y | 26.9 | 8d | 39% | n | **fails G4 only** |
| CF | −0.02 | uncorrelated | 30.8% | 35.8% | Y | 42.6 | 5d | 59% | n | **fails G4 only** |
| DE | 0.14 | uncorrelated | 19.5% | 24.6% | Y | 18.8 | 17d | 30% | n | **fails G4 only** |
| LEN | 0.09 | uncorrelated | −3.9% | 16.5% | Y | 7.3 | 1d | 78% | n | **fails G4 only** |
| STNG | 0.13 | uncorrelated | 30.8% | 12.6% | n | 9.0 | 0d | 91% | n | fails G2 |
| NOC | −0.05 | uncorrelated | 21.5% | 7.0% | n | 15.5 | 1d | 74% | n | fails G2 |
| MRVL | 1.18 | AI-related | 85.1% | 88.9% | Y | **68.6** | **0d** | **93%** | **Y** | G1 |
| SMCI | 1.06 | AI-related | −27.8% | −1.1% | Y | **84.2** | **0d** | **93%** | **Y** | G1 |
| TSLA | 0.60 | AI-related | 13.3% | 26.6% | Y | **63.5** | **1d** | **79%** | **Y** | G1 |
| NEM 0.27 / ARM 0.97 / HOOD 0.71 / PLTR 0.50 / COIN 0.68 / MSTR 0.65 | | AI-related | | | | 14–33 | 2–7d | 32–72% | n | G1 |

G1 reproduces the record exactly (ARM 0.97, CF −0.02, LEN 0.09, NEM 0.27, RTX 0.09), which is also
a check on the restored factor.

**1. One name passes all three, and it is already in the book.** GM: 53.5 fills/yr, median 1 day,
83% within five days, AI beta 0.18, and it beats the no-fit baseline. **There is no undiscovered
fast uncorrelated name in this universe.**

**2. The fast names are the AI names.** MRVL, SMCI and TSLA are the only other G4 passes and all
three fail G1. This is the **third** appearance of one axis: §3.14 found volatility and AI
correlation are the same thing in this era, §3.45 found my candidate set was AI-correlated because
I had selected on volatility, and now turnover — which follows from volatility, since a name that
moves reaches both the bid and the target sooner — joins them. **Speed, volatility and AI
correlation are one axis.** That is why every diversifier round has produced slow names.

**Read G2 with caution.** The no-fit baseline is a single arbitrary seed vector (the median of the
stored reference vectors) and it is noisy — VLO's no-fit 106.3% beats its own fitted 47.6%. G4 is a
structural measurement and far more stable; the per-name G2 verdicts are not worth much weight.

**3. The finding that matters: four names fail ONLY on speed, and all four can be refit to pass**
(`screen_speed_fast.py` — G4 written into the objective the way the minimum-trade floor already is,
fitted on the train half, scored on the unseen half):

| | return-optimal (test) | **speed-constrained (test)** | cost | fills/yr | median | ≤5d |
|---|---|---|---|---|---|---|
| **CF** | 35.8% | **34.2%** | **−1.6pp** | **89.4** | **0d** | **79%** |
| DE | 24.6% | 16.9% | −7.7pp | 51.4 | 1d | 83% |
| RTX | 43.1% | 20.9% | −22.2pp | 65.2 | 0d | 81% |
| LEN | 16.5% | −0.5% | −17.0pp | 56.3 | 0d | 74% |

All four are feasible **out of sample** — the constraint was fitted on the train half and the test
half still clears it. The price differs enormously, and **CF is nearly free.**

**4. CF does not need replacing. It needs refitting.** The session opened with *"I'm not happy with
CF's performance… it relies on a small number of high margin trades… fast turnover stocks are a
better fit."* Everything since has looked for a replacement. The answer is that **CF's slowness was
a parameter choice, not the name**: at its deployed vector it does 25.7 fills/yr on a 12-day median,
at the return-optimal vector 42.6/yr on 5 days, and at the speed-constrained vector **89.4/yr on a
median of zero days with 79% inside five days — the fastest diversifier in the book, for 1.6pp.**

**Execution cost, because a 0.74% premium invites the question** (`screen_speed_slip.py`, nothing
refitted, cost raised on both sides):

| test half | 0.5c/share | 2c | 5c | 10c | 10c in bp |
|---|---|---|---|---|---|
| CF speed-constrained ($86) | 34.2% | 32.5% | 29.4% | 24.4% | 12bp |
| CF return-optimal | 35.8% | 35.0% | 33.4% | 30.9% | 12bp |
| DE speed-constrained ($474) | 16.9% | 16.7% | 16.2% | 15.6% | 2bp |
| RTX speed-constrained ($139) | 20.9% | 20.1% | 18.4% | 15.9% | 7bp |
| LEN speed-constrained ($122) | −0.5% | −1.4% | −3.2% | −6.0% | 8bp |

It survives. At 2c/share the cost of putting CF on the book's profile is **2.5pp**, not 1.6. At
10c — 12bp each way on an $86 stock, which would be poor execution — it is 6.5pp. **LEN is dead on
any basis.**

**A correction to §3.49.** I wrote there that "turnover is a property of the NAME, not the bar".
The first half stands, the phrasing does not: turnover follows **the fitted premium**, and the name
only sets the ceiling. `g1_screen.py`'s own docstring said this (§3.33, "no price screen predicts
turnover — that follows the fitted premium") and I restated it too strongly. CF moved 25.7 → 42.6 →
89.4 fills/yr without the name changing at all.

**Caveats.** G5 — the marginal book test — has NOT been run on any of this, and §3.14a established
G5 as the binding gate; every name declined since has died there, not at G2. The speed-constrained
vectors are one fit on one half each. CF's 0.74% Bayes premium is roughly fifteen times the
modelled commission, so it depends on getting the limit fill at the posted price, and its median
hold of zero days leans on the 5-minute verification being a good proxy for intraday ordering.

**Next:** run G5 on the speed-constrained CF against the deployed CF — a straight swap of the same
name's vector, which is a cleaner marginal test than any swap attempted so far, since nothing about
the book's composition changes. Results in `screen_speed.json`, `ssf_a.json`, `ssf_b.json`,
`screen_speed_slip.json`.


### 3.51 G5 on speed-constrained CF: declined — the extra turnover is paid for out of the rest of the book, and it destroys the stress behaviour CF is carried for (9 Oct)

The cleanest marginal test this book has run: **nothing changes except one name's parameter
vector.** No roster change, no new data, no correlation argument — CF's AI beta, capacity and slot
are held fixed by construction. Three arms, pooled nine-name book, live config with the PM rule.
Deltas are quoted against **return-optimal**, not against deployed, because the deployed vector is
a full-sample fit and §3.33 already made the mistake of setting an honest candidate against it.

| CF vector | full | train | test | maxDD | fills | Δ vs return-optimal |
|---|---|---|---|---|---|---|
| deployed *[lookahead]* | 73.4 | 45.4 | 105.1 | 24.2 | 1234 | −1.0 / −2.3 / +0.8 / +0.9 |
| **return-optimal** (train-half) | **74.4** | **47.7** | **104.4** | **23.4** | 1270 | — |
| **speed-constrained** (train-half) | **70.6** | **42.8** | **102.2** | **24.6** | 1347 | **−3.8 / −4.9 / −2.2 / +1.2** |
| drop CF (eight names) | 75.7 | 44.3 | 112.0 | 26.4 | 1171 | +1.3 / −3.4 / +7.6 / +3.0 |

**It loses on all three windows and gives up drawdown.** §3.14a's standard is that a candidate must
beat on BOTH halves without giving up drawdown; this does neither. **Declined at G5**, like every
other candidate since.

**1. The extra turnover is not free — it is paid for by the other eight names.** Captive, the speed
vector cost CF 1.6pp (§3.50). Pooled it costs the book 3.8pp. The mechanism is the pooling loop
itself: CF now fills on far more mornings, and every fill claims a share of the same pot the other
eight names bid from. At +0.71% a trade, CF's capital earns less than the book's average use of it.
**A name that trades more takes more capital from better names** — which is exactly the question
G5 exists to ask, and exactly what a captive backtest cannot see.

**2. It makes the original complaint worse, not better.** The §3.32 bar is two-legged — ≥50
trades/yr AND the top third of trades carrying <80% of P&L:

| CF vector | /yr | avg trade | hold | losers | **top third** | CF P&L | verdict |
|---|---|---|---|---|---|---|---|
| deployed | 24 | +3.12% | 12d | 14% | **102%** | $2.13m | fails the bar |
| return-optimal | 41 | +1.81% | 4d | 11% | **118%** | $1.93m | fails the bar |
| speed-constrained | **76** | +0.71% | **1d** | **4%** | **129%** | $1.59m | **fails the bar** |

It clears the turnover leg handsomely and **fails worse on the concentration leg.** The session
opened with *"CF relies on a small number of high margin trades"*; the fast vector gives **many tiny
wins and a few large stops** — 4% losers but 8 stops, so the bottom two thirds of trades are net
negative and the top third carries 129%. The dependence on a handful of trades did not go away; it
got worse, and the P&L fell by half a million dollars.

**3. The decisive one: it destroys the stress behaviour CF is carried for.**

| CF vector | Jan–Apr 2025 (the AI drawdown) | Feb–Jun 2025 | Jun–Jul 2026 |
|---|---|---|---|
| deployed | −6.6% (DD 24.2) | +12.8% | +35.9% |
| return-optimal | **−0.9%** (DD 23.4) | +14.6% | +36.2% |
| **speed-constrained** | **−10.1%** (DD 24.6) | +10.7% | +37.8% |
| drop CF (eight names) | −3.0% (DD 26.4) | +9.1% | +30.2% |

**The fast CF is worse through the AI drawdown than having no CF at all** (−10.1% against −3.0%).
CF is in the book as uncorrelated insurance (§6, §3.32); a vector that turns it into a loss-maker
precisely when the book needs it has defeated the purpose of the slot. Plausible mechanism: at a
0.71% premium with one-day holds it re-enters continuously into a falling tape and takes the stop,
instead of holding a position through to recovery.
*Caveat: Jan–Apr 2025 sits in the TRAIN half, so this window is in-sample for every train-fitted
vector here (§6 flagged the same limitation). It is in-sample and still bad, which is the point.*

**4. The methodological conclusion, which generalises beyond CF.** G4 is a good **screening
descriptor** and a bad **objective constraint**. Fitting to it buys turnover the only way the model
can — by cutting the premium — and a lower premium means thinner edge per trade, more capital
claimed from the pool, and no cushion when the tape goes against the position. §3.50's four
"rescues" should all be read this way until each has been through G5; CF was the cheapest of the
four by far (−1.6pp captive against RTX's −22.2pp) and it still fails here.

**5. And the premise deserved checking.** The nine-name book does **~537 fills a year**; CF
contributes 41 of them at the return-optimal vector, **under 8%**. Making CF three times faster
moves the book from ~537 to ~570 fills a year — **a 6% increase in trading activity for 3.8pp of
return and 1.2pp of drawdown.** The trading character of the entity rests on the book, which holds
for a median of one day and closes 76% of positions inside five days (§3.49); it was never going to
rest on its slowest 8%.

**Not a finding, but worth recording:** return-optimal CF and deployed CF are within ~1pp of each
other on the tested half (104.4 vs 105.1), so the honest train-half refit neither helps nor hurts.
There is no case here for changing the live CF vector.

**Status: CF stays as it is.** Results in `premarket_study/cf_speed_g5.json`.


### 3.52 Container recycle: the 5-minute archive restores in one command now, and the workbook no longer blocks imports (10 Oct)

The container recycled mid-session for the second time. `data_5min/`, `data_pm/` and the uploaded
workbook are all gone again — gitignored by design, so this is expected rather than a fault, but it
cost an hour the first time (§3.28d) and would cost it again every time.

**Two repairs, both so the next recycle is cheap.**

**1. `ops/box_5min_autoimport.sh`.** The §3.28d workflow was: call `get_file_content` on each Box
file, let the harness save the extraction to disk, then run `box_5min_import.py <path> <TICKER>`
once per name. The weak link was the TICKER argument — with several `get_file_content` calls in
flight at once the saved paths come back in a different order from the calls, and a mis-mapped
ticker is **silent data corruption, not an error**. Every extraction's first line carries its own
ticker (`VRT 5min`), so the importer now reads the name out of the file instead of being told it,
and imports every un-imported extraction in one pass. Restoring 25 names is now one command after
the Box calls.

**2. `live5_load.py` resolved the workbook at IMPORT time.** `UPLOAD = _find_workbook()` ran on
module load, so *every* module downstream — `fresh_opt`, `fresh_opt_cands`, `daily_from_5min`,
`two_day`, every candidate screen — failed to import at all when the workbook was absent, even
though almost none of them read it. A missing spreadsheet killed the whole pipeline. Now resolved
on first use via PEP 562 `__getattr__`, so `live5_load.UPLOAD` still works for the callers that
want the path and raises only when asked. `load()` resolves explicitly.
(First attempt at this was a `str` subclass with `__fspath__`; wrong, because openpyxl can take the
`str` value directly and would have opened a file called `<workbook unresolved>`.)

**Restore procedure, current:**
1. `python3 -m pip install numpy scipy openpyxl` — note `pip` on this image targets 3.13 while
   `python3` is 3.11, so plain `pip install` silently installs into the wrong interpreter.
2. Box: `minute data/<TICKER>/<TICKER> 5min Apr2024-Aug2026.xlsx` holds the book names and
   everything screened before; `data_5min/` (folder id 416953804140) holds ready-made
   `<TICKER>_5min.xlsx` extractions. `get_file_content` on each.
3. `ops/box_5min_autoimport.sh <tool-results dir>`.
4. `python3 premarket_study/build_pm_cache.py` if the pre-market caches are needed.

**Also recorded: the branch came back wrong.** The fresh checkout had
`claude/live-model-handover-wgnrl8` pointing at another session's tip (two "Trading status" commits
authored by Diarmuid Fewer). Nothing was lost — those commits live on
`origin/claude/personal-account-session-v75of4`, and this line was intact on the remote — but
**check `git log` against the remote before working after a recycle.**

**And a new universe is staged.** Box `data_5min/` holds 19 names that have never been through any
gate here: AAOI, ALNY, APLD, AXTI, CELH, CHTR, DLTR, EXPE, HUM, LULU, LUNR, NVTS, OKLO, PARR, QBTS,
RKT, SPOT, TEAM (+NEM, already screened). The composition is the part §3.50 said was missing —
consumer staples, managed care, media, telecom, travel, apparel, software, mortgage — alongside a
high-beta set that serves as a control. `screen_universe.py` runs G1 on them without the workbook,
and fits only the G1 survivors, because a fit costs five minutes and G1 costs nothing.


### 3.53 A universe that was never selected for volatility: PARR is the first name to clear G1+G2+G4 — and my G2 gate was wrong (10 Oct)

§3.50 closed with "no undiscovered fast uncorrelated name in this universe" and flagged that the
universe was 17 names picked for other reasons. Box held 19 that had never been through a gate.
`screen_universe.py` runs them, building the AI factor from its six constituents' own 5-minute
files so it needs no workbook.

**G1 — and the screen validates itself.** The high-beta names classify AI-related exactly as they
should (AAOI 1.46, APLD 1.21, OKLO 1.19, NVTS 1.08, QBTS 0.98, AXTI 0.97, LUNR 0.84), and NEM
reproduces at **0.27**, the recorded value to the decimal. **11 of 19 clear G1**, several at a beta
the old universe could not reach: HUM 0.01, CHTR −0.02, DLTR 0.07, ALNY 0.08, PARR 0.08, RKT 0.15,
CELH/LULU/TEAM 0.17, EXPE/SPOT 0.21. **§3.50 was right that its universe was the weak point — at
G1.**

**I had the G2 gate wrong, and it took this universe to show it.** `screen_speed.py` implemented G2
as "the frozen vector beats the no-fit baseline". **That is not §3.14's gate**, which is a RETURN
HURDLE: 30% for an uncorrelated name, 50% for an AI-related one. On this universe the proxy fails
in both directions — it passes TEAM at **−3.6%** because an arbitrary seed vector did worse, and
fails PARR at **+46.1%** because the same arbitrary vector happened to do well. §3.50 itself said
the baseline was noisy and "not worth much weight"; I should have replaced it then instead of
writing a caveat. Corrected in `screen_universe.py`; the baseline is now a printed diagnostic only.

**This changes three verdicts in §3.50** (the headline does not move — GM is still the only full
pass there):
- **VLO** 47.6% clears the 30% hurdle. It was recorded as "fails G2"; it fails **G4 only**.
- **DE** 24.6% and **LEN** 16.5% do **not** clear it. They were recorded as "fails G4 only".
- So §3.50's "four names fail only on speed" is **three** — RTX, CF, VLO. §3.51's note that the
  other three speed-rescues should be read like CF's applies only to RTX; **DE and LEN were never
  eligible**, which is a cleaner reason to drop them than the one given.

**The result on the new universe, with the correct hurdle:**

| name | AI beta | frozen test | hurdle | G2 | fills/yr | med | ≤5d | G4 | verdict |
|---|---|---|---|---|---|---|---|---|---|
| **PARR** | **0.08** | **46.1%** | 30% | **Y** | **109.6** | **0d** | **95%** | **Y** | **PASS** |
| EXPE | 0.21 | 23.2% | 30% | n | 17.6 | 5d | 54% | n | fails both |
| DLTR | 0.07 | 22.7% | 30% | n | 32.3 | 3d | 64% | n | fails both |
| HUM | 0.01 | 14.3% | 30% | n | 43.4 | 0d | 83% | n | fails both |
| TEAM | 0.17 | −3.6% | 30% | n | 65.4 | 0d | 90% | **Y** | fails G2 |
| ALNY 0.08 / CELH 0.17 / SPOT 0.21 / RKT 0.15 / LULU 0.17 / CHTR −0.02 | | −8% to −56% | 30% | n | 13–37 | 2–32d | 41–67% | n | fail both |

**PARR is the first name in this project to clear G1, G2 and G4 together.** Beta 0.08, 46.1% on the
half it never saw, and **109.6 fills a year on a median hold of zero days with 95% closed inside
five** — faster than anything in the book (TSM is 91.5/yr). On the §3.49 profile it is more
book-like than the book.

**Two reasons not to get ahead of this.**
1. **The no-fit baseline returned 114.5% on PARR** — the fitted vector *underperforms an arbitrary
   vector out of sample by 68pp*. Either the name is so favourable in this window that almost
   anything works (the 46.1% is then real but the fit is actively harmful and should be replaced by
   something simpler), or the train half misled the optimiser. **That has to be resolved before
   G5**, not after.
2. **PARR is a refiner and VLO is already in the book.** §6 recorded VLO–CF at 0.41. A low AI beta
   is not a low BOOK correlation, and this run could not report book correlation at all because
   GM, VLO and CF were not among the names restored from Box. PARR could be a second helping of an
   exposure the book already has.

**What this does and does not do to §3.50's structural claim.** It weakens it: a genuinely
different universe produced a candidate, so "the uncorrelated names are all slow and low-edge" was
partly an artefact of where we were looking. It does not overturn it: **10 of 11 genuinely
uncorrelated names still cannot clear a 30% hurdle with this model**, and seven of them lose money
outright. Across both universes that is 36 names screened and two live candidates (GM, PARR).

**Next, in order:** restore GM/VLO/CF and measure PARR's book correlation; explain the
fit-versus-no-fit gap; then G5. Results in `premarket_study/screen_universe.json`.


### 3.54 PARR: it is a second VLO, not a diversifier — and it is the first name whose train half ANTI-predicts its test half (10 Oct)

Both questions §3.53 left open are answered, and both change what PARR is for.

**A. PARR is a refiner and it trades like the refiner already in the book.**

| PARR vs | corr | | PARR vs | corr |
|---|---|---|---|---|
| **VLO** | **0.72** | | TSM / VRT / VST / AVGO / MRVL | 0.03–0.06 |
| CF | 0.35 | | MU | 0.13 |
| GM | 0.06 | | **book average** | **0.20** |

For scale: VLO–CF is 0.41 and the nine book names average **0.30** pairwise. **PARR–VLO at 0.72 is
more than twice the book's internal correlation.** PARR clears the §3.32 ≤0.30 book-correlation bar
only because the book is mostly AI names and PARR is uncorrelated with those (0.03–0.13); inside
the diversifier slot it is the same trade as VLO. §6 already called VLO and CF "one-and-a-bit
names"; adding PARR would make it one-and-a-bit-and-a-bit.

**So the question is not "add PARR". It is "replace VLO with PARR"** — same exposure, and on the
§3.49 profile a completely different animal: **PARR 109.6 fills/yr, median hold 0 days, 95% inside
five days against VLO's 25.1/yr, 4 days, 60%.** That is a like-for-like swap where the case is
entirely turnover, and it is a much cleaner test than anything the diversifier programme has run.

**B. On PARR the train half ANTI-predicts the test half. The fit is worse than useless.**

400 vectors drawn uniformly from the search bounds, each scored on both halves:

| | tradeable | test median | 25th | 75th | max | **train→test rank corr** | seed vector on test |
|---|---|---|---|---|---|---|---|
| **PARR** | 400/400 | **63.5%** | 44.7% | 86.8% | 149.6% | **−0.53** | 114.5% (94th pct) |
| GM (control) | 394/400 | 33.8% | 25.5% | 41.9% | 64.9% | **+0.33** | 39.1% (66th pct) |
| CF (control) | 392/400 | 27.0% | 19.3% | 33.6% | 64.4% | **+0.08** | 30.8% (65th pct) |

**−0.53 is not "fitting doesn't help", it is "fitting hurts".** A vector that wins the train half
is systematically a loser on the test half, which explains §3.53's anomaly exactly: the optimiser
picked a train-half winner and got 46.1% where the median *random* vector got 63.5%. **PARR's
fitted result sits below its own 25th percentile.**

The controls say this is PARR, not the model. GM at +0.33 is a name where fitting earns something;
CF at +0.08 is near-useless to fit, which independently reproduces §6's finding that CF's "fits
move a great deal between halves and the returns do not". Nothing in the record is as adverse
as −0.53.

**What follows for how PARR could ever be run.** It cannot be fitted — any deployed vector chosen
by optimising the train half is, on this evidence, a vector chosen to fail. A vector must therefore
come from somewhere that never saw PARR's history. The component-wise median of the stored
reference vectors is exactly that, and it returns **114.5%** on the unseen half — a legitimate
out-of-sample number, because that vector was never fitted to PARR in any way.

**The planning figure should nonetheless be the 25th percentile, 44.7%**, not 63.5% and certainly
not 114.5%. The argument: if we cannot fit, we cannot claim to land anywhere in particular in the
distribution, so we should plan on landing badly. That still clears §3.14's 30% hurdle for an
uncorrelated name.

**The large caveat.** A median of 63.5% across *arbitrary* parameter vectors is not evidence of a
63.5% edge; it says the test window was strongly favourable to long-only dip-buying in this one
refiner. The negative rank correlation is itself the warning that PARR's regime changes between
halves — and a name whose two halves disagree that violently is exactly the kind §3.1 warns about.
One refiner, one 1.2-year window.

**Blocked at G5, and the reason is worth fixing.** The marginal book test needs the pooled
nine-name book, and `book_sim.load_all` reads the five core names' **deployed parameters out of the
uploaded workbook**, which died with the container and cannot be restored from Box (the text
extraction serves data sheets, not a live formula workbook). **The live book's deployed vectors
exist in exactly one place, an upload that dies with every container.** `fresh_opt_cands.json`
carries AVGO's and nothing else. That should be a tracked file regardless of PARR.

**Next:** re-attach the workbook, then G5 as **VLO → PARR**, scored on the un-fitted reference
vector rather than a train-half fit, with the swap judged on both halves and on drawdown as §3.14a
requires. Results in `premarket_study/parr_check.json`.


### 3.55 Dip recovery time across the book: a genuinely new axis — but the veto it suggests is refuted by the data (14 Oct)

**The question.** The model buys at a discount, the name sometimes keeps falling, and with both
sleeves filled it is frozen (§3.30) until target or the 50-calendar-day stop. So: once we are 10%
down, how long are we stuck, and does it differ by name?

**It differs enormously.** Episodes built from the underwater curve (non-overlapping by
construction: open when the close drops below a running peak, close when it regains it), keeping
those reaching −10%:

| name | eps | /yr | med depth | −10%→recovery (sessions) med/75th/90th | med cal days | **P(rec ≤ 50 cal)** | unrec |
|---|---|---|---|---|---|---|---|
| MU | 10 | 4.3 | −18.4% | 14 / 22 / 303 | 21 | **80%** | 1 |
| VLO | 3 | 1.3 | −12.7% | 21 / 398 / 398 | 31 | **67%** | 0 |
| TSM | 7 | 3.0 | −18.4% | 34 / 62 / 105 | 49 | **57%** | 1 |
| VST | 7 | 3.0 | −20.2% | 22 / 76 / 105 | 32 | **57%** | 1 |
| AVGO | 8 | 3.4 | −19.6% | 21 / 88 / 112 | 29 | **50%** | 1 |
| MRVL | 5 | 2.1 | −28.3% | 94 / 302 / 302 | 137 | **40%** | 1 |
| CF | 6 | 2.6 | −22.6% | 88 / 104 / 171 | 127 | **33%** | 1 |
| VRT | 7 | 3.0 | −24.8% | 60 / 86 / 171 | 90 | **29%** | 1 |
| GM | 3 | 1.3 | −19.9% | 100 / 202 / 202 | 146 | **0%** | 0 |

The stop is 50 **calendar** days, so the last column is roughly the chance a 10%-underwater
position leaves at target rather than at the stop. **It ranges from 0% to 80%.**

**Stability.** Re-run at 5%, 7.5%, 10% and 15% thresholds: the name ordering is stable across
5–10% (rank correlation +0.60 to +0.97, and **7.5% vs 10% is +0.97**) and breaks down at 15%,
where episode counts fall to 1–5. So the measure is real within the range that has data.
**GM's 0% is the thin reading** — three episodes — and at shallower thresholds GM is unremarkable
(70% at 5%, n=10). The honest statement about GM is "dips rarely, but stays down when it does",
not "GM is a bad name".

**It is the first genuinely NEW axis this session has found.** §3.14 found volatility and AI
correlation are the same thing; §3.45 found my candidate set was AI-correlated by construction;
§3.50 found turnover joins them. Three strikes. This one does not:

| P(rec ≤ 50 cal) vs | rank corr |
|---|---|
| annualised volatility | **+0.23** |
| AI beta | **+0.05** |
| fills per year (§3.49) | **−0.14** |

MU is the most volatile name and the fastest to recover; GM is among the least volatile and the
slowest. Nothing already measured in this file predicts it.

**Now the strategy question — and the obvious rule does not survive contact with the data.**
The natural use is a veto: do not let the second sleeve fill when the name is already well below
its running peak. That only helps if forward returns are worse from down there. Every session of
all nine names, bucketed by distance below the running peak (4,841 observations, model-free):

| bucket | share | +10d med | +20d med | **+50d med** | +50d mean |
|---|---|---|---|---|---|
| at/near peak (0–2%) | 16% | 1.03% | 3.64% | **7.20%** | 9.07% |
| down 2–5% | 13% | 1.66% | 2.73% | **8.16%** | 9.66% |
| down 5–10% | 18% | 1.65% | 3.28% | **6.35%** | 9.13% |
| down 10–20% | 24% | 1.62% | 2.58% | **5.93%** | 9.16% |
| **down >20%** | 30% | 2.10% | 3.42% | **13.14%** | **20.75%** |

**Forward returns do not deteriorate with depth — they improve.** A drawdown veto would have
refused the best entries in the sample. Per name the picture is mixed in an interesting way: TSM
(3.6%→12.0% at +20d), VRT, AVGO and CF all improve with depth, while **MU (15.3%→1.5%) and MRVL
(16.5%→3.2%) get worse** — the two fastest-recovering names are the two where a deep drawdown is
genuinely bad news.

**The caveat that governs all of it:** 2024–26 is a bull sample. "Buy the dip" works mechanically
in a market that always came back, and the >20% bucket's +20.75% mean is largely post-drawdown
rebounds. §6 already records that the only AI drawdown in the sample sits inside the training
region. **This finding would be the first casualty of a real bear.**

**The stop idea is unresolved, not refuted.** Sweeping `stop_days` at fixed vectors ran on only
three names — TSM, VRT, VST and MU keep their deployed vectors in the workbook (§3.54, open item 7)
— and the one clean-looking result, VLO's 64.2% at 50 days against 44.7% at 80 and 33.3% at 30, is
a **single-cell spike**, the tell this file has used to reject parameters a dozen times. Three
names and a spike is not evidence.

**Where the metric does belong.** Not as an entry gate. As a **risk and capacity descriptor**: it
says how long capital stays committed when a name goes wrong, which is exactly what the
frozen-sleeve problem costs and what no other column in this file measures. And it has a portfolio
dimension — the **"10% under water" STATE correlates +0.20 pairwise across the nine**, against the
book's 0.30 return correlation, so recovery timing is partly diversifiable. But only partly:
**55% of sessions have five or more of the nine under water, and 11% have all nine.** When the book
freezes it largely freezes together.

**What I would test next, once the workbook is back:** whether a per-name stop set from each name's
own recovery distribution beats the uniform 50 days, across all nine rather than three — the one
use of this metric that the evidence neither supports nor rules out.

Results in `dip_recovery.json`, `dip_recovery_check.json`, `dip_stop_sweep.json`,
`dip_conditional.json`.


### 3.56 Workbook restored: PARR declined at G5, and dip recovery does not set the stop either (14 Oct)

Workbook re-attached, baseline reproduces exactly — 73.4 / 45.4 / 105.1, maxDD 24.2, stops 47,
530 fills/yr, identical to the earlier restored state this session. **Open item 7 is closed**: the
five core deployed vectors are now in `premarket_study/deployed_params.json`, so `book_sim` and G5
no longer die with the container.

**1. PARR: declined at G5.** The test is the swap, not the addition, because §3.54 measured
PARR–VLO at 0.72 against the book's own 0.30 average pairwise. PARR runs on the component-wise
median of the stored reference vectors — the neutral seed, chosen with no reference to PARR's
history — because §3.54 found its train half anti-predicts its test half at −0.53, so fitting it
selects a vector to fail.

| | full | train | test | maxDD | fills | Δ vs nine |
|---|---|---|---|---|---|---|
| **nine names (with VLO)** | **73.4** | **45.4** | **105.1** | **24.2** | 1234 | — |
| swap VLO → PARR | 65.9 | 34.7 | 102.2 | 25.2 | 1246 | **−7.6 / −10.7 / −2.9 / +1.0** |
| add PARR (ten names) | 69.3 | 32.4 | 114.1 | 23.9 | 1330 | −4.1 / −13.1 / +9.0 / −0.3 |
| drop VLO (eight names) | 69.6 | 51.6 | 88.8 | 26.0 | 1150 | −3.8 / +6.1 / −16.4 / +1.7 |

**The swap loses on all three windows and gives up drawdown** — §3.14a's standard, failed. Through
the Jan–Apr 2025 AI drawdown it returns **−14.4% against the nine-name book's −6.6%**. Adding PARR
as a tenth helps the tested half (+9.0) but costs the train half (−13.1), so it fails the
both-halves requirement too.

**And the attraction evaporates on an honest vector.** PARR's headline was **109.6 fills/yr on a
zero-day median** — but that was measured on the FITTED vector, the one §3.54 showed cannot be
used. On the un-fitted vector it does **39/yr**, against VLO's 35. The turnover case and the
can't-be-fitted finding are in direct conflict, and only one of them can be acted on.

Shape in the pooled book is the final word: **PARR's top third carries 119% of its P&L against
VLO's 64%.** VLO clears the §3.32 concentration leg and fails only on turnover; PARR fails
concentration outright — the same pattern that sank speed-constrained CF in §3.51.

**A side-result worth keeping: VLO is load-bearing.** Dropping it costs **16.4pp on the tested
half** and takes the AI-drawdown loss from −6.6% to **−18.5%**, worse than any other arm. VLO fails
the turnover bar at 35/yr and earns its slot anyway. That is the clearest statement yet that the
§3.32 shape bar measures something the book does not actually pay for.

**2. Dip recovery does not set the stop.** §3.55 left exactly one use open — a per-name stop drawn
from each name's own recovery profile — and it is now testable on all nine.

| name | P(rec ≤ 50 cal) | best stop | ann @50 | best ann | gain |
|---|---|---|---|---|---|
| MU | 80% | none | 58.6% | 63.4% | +4.8 |
| VLO | 67% | 50d | 64.2% | 64.2% | 0.0 |
| TSM | 57% | none | 48.9% | 62.5% | +13.7 |
| VST | 57% | 30d | 55.8% | 61.5% | +5.7 |
| AVGO | 50% | none | 51.2% | 60.7% | +9.5 |
| MRVL | 40% | 50d | 85.1% | 85.1% | 0.0 |
| CF | 33% | 20d | 46.9% | 58.3% | +11.4 |
| VRT | 29% | none | 56.3% | 78.1% | +21.8 |
| GM | 0% | 50d | 50.3% | 50.3% | 0.0 |

**Rank correlation between recovery probability and best stop length: −0.15.** The metric does not
predict the stop. GM, which never recovers inside 50 days, wants 50 days; MU, which recovers 80% of
the time, wants no stop at all. **The one remaining use of dip recovery is closed, and it is
closed negative.**

**What the sweep does show, with a large caveat.** The uniform 50 days is the best of six choices
for only **3 of 9** names, 4 prefer **no stop at all**, and the mean in-sample gain from a perfect
per-name choice is +7.4pp. That number is pure hindsight — it is the maximum over six options
picked with the answer in hand, and since recovery does not predict it (−0.15) there is no ex-ante
rule to capture it. It is also a **bull-sample artefact**: a stop costs return in a market that
always came back, and the stop exists for the bear that is not in this sample (§6). Nothing here
argues for lengthening or removing the stop.

**Where that leaves dip recovery.** It is real, it is stable, and it is genuinely orthogonal to
volatility, beta and turnover (§3.55) — but neither of the two ways to trade it survives testing:
the entry veto is refuted by forward returns improving with depth, and the stop rule is refuted
here. **It stays a risk and capacity descriptor**, which is what §3.55 concluded and what the
evidence now confirms twice over.

Results in `parr_g5.json`, `dip_stop_sweep.json`, `deployed_params.json`.


### 3.57 Live episode, 12–15 Oct 2026: the rates shock — measured, not acted on (15 Oct)

US inflation print pushed yields up; book down hard over three sessions with another 2–3%
indicated in Tuesday's pre-market. User asked how this compares with drops the book has recovered
from, scope narrowed to **this week only** — the months-old drawdowns (VRT 153 days past its peak,
VST 387, CF 42) are a separate condition and were excluded.

**The move, 9 Oct close → 14 Oct close, with −2.5% pre-market applied:**

| | TSM | VRT | VST | AVGO | MU | GM | VLO | CF | MRVL |
|---|---|---|---|---|---|---|---|---|---|
| week | −5.1% | −8.2% | −6.0% | −4.2% | −11.2% | +0.4% | **+6.0%** | **+7.1%** | −10.9% |
| +pre-mkt | −7.5% | −10.5% | −8.4% | −6.6% | −13.4% | −2.1% | **+3.4%** | **+4.4%** | −13.1% |

**Book −3.7% over three sessions, −6.1% including pre-market.** That is a 3% tail: 21 of 634
three-session windows since April 2024 were at least this bad.

**What followed those 21:**

| horizon | median | mean | 25th | % positive | worst | *unconditional median / % pos* |
|---|---|---|---|---|---|---|
| +5 sess | **+3.5%** | +1.5% | −2.7% | 67% | −15.7% | *+1.3% / 65%* |
| +10 sess | **+5.5%** | +3.0% | −0.4% | 71% | −11.9% | *+2.5% / 69%* |
| +20 sess | +2.0% | +5.4% | −3.1% | 62% | −14.1% | *+4.6% / 76%* |
| +50 sess | **+15.6%** | +13.8% | −6.7% | 71% | −28.5% | *+12.7% / 82%* |

Medians beat the unconditional at three of four horizons, consistent with §3.55's finding that
forward returns improve with depth. **But the hit rate is WORSE** at +20 (62% vs 76%) and +50 (71%
vs 82%), the 25th percentile at +50 is −6.7%, and the worst case is −28.5%. The distribution shifts
up and widens. Windows overlap, so these are not independent draws, and no attempt was made to
identify past episodes as rate shocks — 638 sessions is far too few to condition on a cause.

**CORRECTED 15 Oct — the diversifiers did NOT pay out, because the book is not in them.**
The original note read "the diversifiers paid out, in real time", citing VLO +6.0% and CF +7.1% on
the week against MU −11.2%, MRVL −10.9%, VRT −8.2%. Both price moves are real and **both are
irrelevant to this book**: VLO holds **zero shares** (both sleeves sat in CASH through the rally,
bids at 447.28/442.23 against a 459.78 close) and CF's open sleeve was bought at **130.16 on 18
Sep**, so a 7% bounce leaves it **−10.5%**. Measured on the actual open positions
(`position_pnl.py`, entries from the trade log): **diversifiers −6.6%, AI six −12.2%, whole held
book −11.2% = −$617,192 on $5,518,897.** The diversifiers cushioned in relative terms and lost
money in absolute ones. *A diversifier earns its place by what the book HOLDS of it, not by what
the ticker does — measuring the price series and calling it a hedge was the error.* The §6 thesis
is about the former — and note §3.56 had just confirmed VLO as load-bearing
(dropping it cost 16.4pp on the tested half). A rates/inflation shock is the one macro event where
the commodity names are a genuine hedge rather than a drag.

**The deployed gate (§3.23, K=4) is OFF: 3 of 9 below their 200dma** — VRT −18.9%, AVGO −8.3%,
VST −4.3%. **GM is +0.4% above its line**, so one ordinary day turns it on. TSM +6.4%, CF +2.2%,
MU +25.2%, MRVL +37.1%, VLO +65.3% — several names remain far above trend despite the fall.

**But the gate would protect nothing here, and that is the important finding.** Cash available is
**$6,034.78** and 13 of 18 sleeves are HOLDING; five names (TSM, VRT, AVGO, MU, GM) are frozen on
both sleeves. The gate suppresses NEW ENTRIES, and there is no money to enter with. **§3.22 already
established that an entry veto cannot protect a book whose damage is in held inventory** — this
episode is that case exactly.

**The selling is already scheduled.** The 50-calendar-day stop will act without anyone deciding:

| | held | targets vs close | stop fires |
|---|---|---|---|
| VRT Bayes + OU | 36d | 284.13 / 290.53 vs 222.83 (needs +27%/+30%) | **~28 Oct** |
| GM Bayes + OU, CF OU | 27d | 85.89 / 88.59 / 137.85 | **~6 Nov** |
| TSM ×2 | 8d | 480.00 / 477.34 vs 430 | ~26 Nov |
| VST OU, AVGO Bayes, MRVL OU | 7d | — | ~27 Nov |
| AVGO OU, MU ×2 | 3d | 1025.89 / 1004.77 vs 914.13 | ~1 Dec |

**Decision: no discretionary action.** The gate is off; it would be inert if on; the analogue
distribution favours holding; the diversifiers are doing their job; and the two positions least
likely to recover (VRT, needing +27% in a fortnight) are stopping out on their own in two weeks.
§3.42 measured decisive stand-down as far worse than the deployed gate.

**The limit of all of this, stated plainly.** Every number above comes from a 2024–26 sample with
no bear in it. §3.42's finding that stand-down is worse, §3.55's that depth predicts better forward
returns, and the 21 analogues here all rest on a market that always came back. **This analysis
cannot distinguish a dip from the first week of a regime change**, and if it is the latter, "hold"
is the wrong answer and the inventory is where the damage will be. The watch items are GM's 200dma
(0.4%) as the fourth breach, and whether the diversifiers keep holding up — in 2022 the plateau was
exactly six names below with the three diversifiers holding (§3.23), so the signal that this has
become a bear is the diversifiers joining the decline.

**WHY THE TWO APRILS CAME BACK — and why that is weaker comfort than it looks (15 Oct).**
The recoveries had completely different shapes, and only one of them is a precedent for today.

*April 2025 — the cause was withdrawn.* Day-by-day the book went 83.6, 85.9, 84.3, then **95.8**:
a **+13.7% single session on 9 Apr 2025**, with 53% of the whole 20-day recovery arriving in three
sessions and essentially all of it in that one day. On 8 Apr it was still falling. That is a policy
shock reversed by policy (the tariff pause). Delete that day and there is no April 2025 recovery.

*April 2024 — it ground back.* No single day above **+2.4%**, only 32% of the recovery in the first
three sessions, whole again in four sessions by a steady climb: 94.1, 95.3, 97.6, 98.9, 101.3. That
is a market absorbing a rate repricing (the hot CPI print of 10 Apr 2024 pushing back cut
expectations) and then being carried by a strong Q1 earnings season. *Macro attributions here are
recollection of 2024–25 market history, not derived from this dataset.*

**Today is the April 2024 type** — an inflation print moving the rate path, with no single
reversible trigger. So there is no +13.7% day to wait for, and the thing that resolved April 2024
was earnings delivering, which Q3 reporting is about to test on the same schedule.

**The asymmetry that cuts against the comfort.** April 2025 crashed into an ALREADY-CORRECTED
market: the book sat **−10% below its 200dma with 8 of 9 names below** on 1 Apr 2025. There was no
air underneath, which is exactly why the snapback was so violent. **Today the book is +12% ABOVE
its 200dma even after this fall** (it was +20% on 9 Oct), with only 3 of 9 below — MU +25%,
MRVL +37%, VLO +65%. There is considerably more room to fall before this is a washed-out market,
and the condition that made April 2025 rebound so fast is absent. (April 2024's extension is not
measurable: fewer than 200 sessions of history existed at that point.)

**CORRECTION (15 Oct) — April 2024 took 36 calendar days to recover, not 7.** The earlier "whole
again in four sessions / regained the pre-drop level in 7 days" measured from the level THREE
SESSIONS before the trough, not from the episode's peak. Traced properly (`april2024.py`,
peak searched 1–15 Apr, trough to 30 Apr, recovery to 31 May):

| | April 2024 | today |
|---|---|---|
| peak | 2024-04-03 *(row 2 — the true top may pre-date the data)* | 2026-10-07 |
| trough / now | 2024-04-19, **−10.7%** | 2026-10-14 +pm, **−11.2%** |
| **down** | **12 sessions / 16 cal days = −0.90%/session** | **5 sessions / 7 cal days = −2.24%/session** |
| up | 14 sessions / 20 cal days = +0.86%/session | — |
| **round trip peak-to-whole** | **26 sessions / 36 calendar days** | — |
| AI six | −12.8% | −13.1% |
| diversifiers | **−6.6%** (VLO −9.1, CF −4.5, GM −6.2) | **+2.5%** (VLO +5.7, CF +1.8, GM −0.0) |

**Same damage to the AI complex, at two and a half times the speed.** §3.22's distinction says the
fast kind is the one an entry veto cannot protect against, because the damage is in inventory —
today is the fast kind. Against that, April 2024 took the diversifiers down with it and today's
are up, so the fall is narrower (six of nine, peak-relative).

**And the recovery was not a straight line**: 89.3 at the trough (19 Apr) → 98.7 by 29 Apr → back
to **94.0 on 1 May** → whole on 9 May. An eight-session bounce retraced nearly half before the real
recovery, which matters to anyone planning to sell into strength.

**Net: "April recovered" is true and is weaker evidence than it sounds.** It does not change the
decision — no broad liquidation, VRT the one defensible early exit — but the recovery statistics
should be held with less confidence than their medians suggest.

**15 Oct, 30 minutes in — the tell did NOT trigger.** Actual prints: VRT −7.0%, TSM −4.5%,
MU −4.0%, MRVL −4.0%, AVGO −2.5%, VST −2.0%, but **GM +0.25%, CF 0.0%, VLO −1.5%**. Book −2.8%,
AI six −4.0%, **diversifiers −0.4%**. From the 7 Oct peak: book −8.1%, AI six −14.5%,
**diversifiers +4.7%**, six of nine below the peak. Three-session move −5.1%, rank 33 of 635.
Open positions −$642,440 (−11.6%).

**Breadth stayed at 3 of 9 below their 200dma, so the §3.23 gate did not fire** — GM needed −2.9%
to be the fourth breach and rose instead. (And the gate is a morning rule read off the PRIOR close,
so an intraday breach would have fed tomorrow's decision, not today's.) Against April 2025's
diversifiers −12.1% with 9/9 falling, this remains the April-2024 shape. **VRT is the one position
materially changed**: at ~207 it needs +37%/+40% to reach target, which is out of reach, with
earnings 20–21 Oct and the stop ~28 Oct.

Tooling: `drawdown_now.py` (current state vs each name's own dip history), `this_week.py`
(event window, conditional forward distribution, gate state). Results in `drawdown_now.json`,
`this_week.json`.


### 3.58 Capacity re-measured on the orders actually placed: headroom is ~$1.3m, not $2m — and CF/VLO are the binding constraint (15 Oct)

User plans to fund the daily book with NVDA proceeds and asked whether another **$2m** fits.
§3.43 answered with a static calculation — the thinnest name's gate (CF, $0.81m) divided across
equal weights, giving a ~$7.3m ceiling — and flagged its own assumption: *"it assumes every name
funded at once, where a typical morning funds about six sleeves."* That makes it conservative in
one direction and wrong in another, because the **pooled** book does the opposite of equal
weighting: when few sleeves are free, one name takes a much larger share.

`capacity_recheck.py` measures the real thing — run the pooled book at the proposed capital,
collect every fill, compare each name's ACTUAL order sizes against its own §3.37 gate.

**At today's mark (~$4.9m) the book already breaches its own gate.**

| | gate cap | binds | orders | median | 95th | max | over cap | worst |
|---|---|---|---|---|---|---|---|---|
| **CF** | **0.81m** | thin day | 57 | 0.64m | 2.14m | 2.64m | **16/57** | 3.27× |
| **VLO** | **1.44m** | thin day | 81 | 0.73m | 1.99m | 3.17m | **9/81** | 2.21× |
| GM | 2.45m | median | 139 | 0.47m | 1.51m | 4.45m | 2/139 | 1.81× |
| TSM / AVGO / MU / MRVL / VRT / VST | 3.07–20.65m | — | — | — | — | — | **0** | 0.07–0.86× |

**2.2% of all orders, and 28% of CF's.** The AI names have enormous headroom (MU 0.07×, TSM and
AVGO 0.13×). **The binding constraint is the diversifier sleeve, which is the part §3.56 showed is
load-bearing** — dropping VLO cost 16.4pp on the tested half.

**The sweep, and where it breaks:**

| capital | all orders over gate | CF | VLO | GM | **CF median vs its cap** |
|---|---|---|---|---|---|
| $4.0m | 1.6% | 21% | 7% | 1% | 0.65× |
| **$4.9m (today)** | **2.2%** | **28%** | **11%** | 1% | **0.80×** |
| $5.5m | 2.9% | 39% | 14% | 1% | 0.89× |
| **$6.0m (+$1.1m)** | 3.5% | 46% | 16% | 1% | **0.97×** |
| **$6.9m (+$2.0m)** | **4.6%** | **56%** | **23%** | 2% | **1.12×** |
| $8.0m | 5.8% | 67% | 30% | 5% | 1.30× |

**The median CF order crosses its own gate between $6.0m and $6.9m — call it $6.2m.** Past that it
is not the tail breaching, it is the typical order. **Headroom from today's mark is about $1.3m,
not $2m**, and §3.43's $7.3m was too generous because it assumed an allocation the pooled book does
not use.

**What a breach actually means.** §3.37's gate is an assumption about market impact: an order above
~1% of at-bid dollar volume may not fill at the posted price. A breach does not fail the trade, it
means **the backtest's fill was optimistic**. So the consequence of funding to $6.9m is that CF's
and VLO's modelled returns become progressively unachievable — in the sleeve that exists to protect
the book.

**Three ways to take the full $2m, all with a price:**
1. **Cap per-name orders.** The truncated capital flows to the liquid AI names, which is the
   concentration §3.42 priced at **7.4pp of return and 10.9pp of drawdown**.
2. **Accept the slippage.** Unquantified here; CF would breach on 56% of orders, up to 4.6×.
3. **Stage it.** ~$1.1m now, the rest when a more liquid diversifier exists.

**Two caveats that cut opposite ways.** The $4.9m is a **drawdown mark** — if the book recovers to
$5.5m the same $2m lands at $7.5m, worse than modelled here, so sizing off today's depressed mark
flatters the answer. Against that, the liquidity figures come from the 5-minute archive ending
**Aug 2026**; volumes in a selloff usually rise, which would help, but they are unmeasured.

**The structural point.** Capacity is not limited by the book's size but by its two thinnest names,
and those are diversifiers. Raising capacity therefore requires a **more liquid uncorrelated name**
— and the screens have produced exactly two candidates, GM (already held, $2.45m cap) and PARR
(declined at G5, §3.56). That is the same wall §3.43 hit, now located precisely.

Results in `capacity_recheck.json`, `capacity_sweep.json`.


### 3.59 The parallel book, screened on the new brief: six names at 20%+ with ≤2 AI does not exist — and the fittability test is why (15 Oct)

Brief: a second daily book, **≥6 names, ≤2 AI-related, ≥20% standalone, fills as the key metric**,
Bayes+OU as before. Thirteen names never screened here were restored from Box (AMD, CEG, DVN, FCX,
FSLR, MRNA, NVDA, OXY, RBLX, RKLB, SHOP, SOFI, UAL; SKHY skipped, only two months of data), taking
the screened universe to **49 names**.

**G1 on the thirteen: only 2 clear it** — DVN 0.15 and OXY 0.09, both energy. AMD 0.81, RKLB 0.82,
CEG 0.75, **NVDA 0.73**, SOFI 0.60, FCX 0.50, UAL 0.45, FSLR 0.45, SHOP 0.41, MRNA 0.35, RBLX 0.29
are all AI-related. *(NVDA at beta 0.73 / correlation 0.73 also settles, by measurement, the claim
made when advising on the NVDA sale that it is the same trade as the book.)*

**The decisive filter is not return, it is FITTABILITY** (§3.54's test: 300 random vectors scored on
both halves; rank correlation between train and test performance):

| name | test median | 25th | **rho** | reading | single-fit number |
|---|---|---|---|---|---|
| PARR | 63.7% | 44.8% | **−0.49** | fitting HURTS | 46.1% |
| AMD | 53.5% | 39.2% | **−0.59** | fitting HURTS | 53.2% |
| NVDA | 33.9% | 21.2% | **+0.41** | fitting works | 49.1% |
| RTX | 20.2% | 12.2% | **+0.36** | fitting works | 43.1% |
| DE | 13.1% | 9.9% | **+0.38** | fitting works | 24.6% |
| DVN | 18.8% | 12.0% | −0.47 | fitting HURTS | 15.6% |
| OXY | 16.4% | 7.3% | −0.33 | fitting HURTS | 11.3% |
| SOFI | 23.7% | 16.2% | +0.07 | useless | **70.9%** |
| DLTR | 7.3% | 1.9% | +0.20 | useless | **22.7%** |
| EXPE | 11.4% | 5.6% | +0.18 | useless | 23.2% |
| HUM | 0.8% | −3.7% | −0.39 | fitting HURTS | 14.3% |

**This demolishes four of the candidates that passed on a single fit.** SOFI's 70.9% sits against a
random-vector median of 23.7% with rho +0.07 — a lucky draw, not a fit. DLTR's 22.7% against a
median of **7.3%** and a 25th of 1.9% — the same. EXPE and HUM likewise. **A single train-half fit
reports a number for every name; the number only means something where rho is positive.**

**It also rehabilitates two.** AMD's fitted 53.2% looked like a fitting success; it is not — rho is
−0.59 — but its random-vector median is **53.5%** and its 25th **39.2%**, so AMD is a strong name
whose parameters barely matter. Same shape as PARR (median 63.7%, 25th 44.8%). For these the
planning figure is the 25th percentile, per §3.54.

**Honest standing of every candidate, best basis available:**

| | planning figure | fills/yr | class |
|---|---|---|---|
| **PARR** | 44.8% *(25th, unfittable)* | 109.6 fitted / 39 un-fitted | uncorrelated |
| **AMD** | 39.2% *(25th, unfittable)* | 55.2 | **AI 0.81** |
| **NVDA** | ~34–49% *(fittable)* | 49.3 | **AI 0.73** |
| **RTX** | ~20–43% *(fittable, median 20.2%)* | 26.9 | uncorrelated |
| DVN | 12.0% *(25th)* | 24.2 | uncorrelated |
| DE | ~13–25% *(fittable, median 13.1%)* | 18.8 | uncorrelated |
| OXY | 7.3% *(25th)* | 16.7 | uncorrelated |

**The brief cannot be met as written.** Only three names are genuinely strong — **PARR, AMD, NVDA**
— and **two of the three are AI**, which exhausts the AI budget and leaves one. Below them the
non-AI field falls to RTX (median 20.2%) and then to DVN/DE/OXY in the low teens. **There is no
set of four non-AI names at a credible 20%+.**

**What the fills constraint actually costs.** DVN, OXY and HUM have the best FILL profiles measured
anywhere in this project — median hold 0 days, **90%, 95% and 83%** of trades closed within five
days — and planning figures of 12.0%, 7.3% and −3.7%. The names that trade fastest in the non-AI
space are the ones that earn least. That is §3.50's axis finding again, now at 49 names.

**The one premise worth testing before giving up on the brief.** The brief assumes 20% standalone
becomes 30%+ pooled and gated. That uplift is real and large in the existing book — the nine-name
pooled result is 73.4% full / 105.1% test against constituents in the 35–50% range. **If pooling
reliably adds that much, the right move is to LOWER the floor to ~15% and buy fills**, which makes
PARR, RTX, DVN, OXY + DE a feasible non-AI five, plus one AI. That has not been tested and is the
obvious next run.

**Not yet done:** the pooled sim on any candidate set, and G5. §3.51's warning stands over all of
it — optimising for turnover by cutting the premium failed G5 decisively on CF.

Results: `fittability.json`, `fit_ai.json`, `su_dvn.json`, `su_new_g1.log`.


### 3.60 The 15%-floor parallel book, pooled and gated: the pooling premise is refuted, the gate works, and the book lands at a third of the nine-name result (15 Oct)

Six names at a 15% floor — **PARR, RTX, DVN, OXY, DE, AMD** (one AI) — run pooled on the live
config. Vectors chosen **per name by §3.59's fittability test**, which is the whole point: a fitted
vector is meaningful only where the train half predicts the test half, so RTX (+0.36) and DE (+0.38)
use their fitted vectors and PARR (−0.49), AMD (−0.59), DVN (−0.47) and OXY (−0.33) use the neutral
seed, never fitted to them at all.

| arm | full | train | test | maxDD | fills/yr |
|---|---|---|---|---|---|
| captive (standalone basis) | 19.8 | −2.2 | 45.3 | 18.0 | 174.3 |
| pooled | 17.0 | −7.8 | 46.9 | 24.3 | 174.3 |
| pooled + PM rule | 13.5 | −11.0 | 43.2 | 28.0 | 165.3 |
| **pooled + PM + breadth K≥2** | **22.3** | **+3.6** | 43.4 | **22.4** | 140.8 |
| pooled + PM + breadth K≥3 | 22.1 | +3.6 | 42.9 | 22.4 | 144.7 |
| pooled + PM + breadth K≥4 | 21.6 | +0.7 | 45.7 | 22.4 | 148.5 |

**1. The pooling premise is refuted for this set — but it is real for the nine-name book.** Measured
both ways on the same harness:

| | pooling uplift (captive → pooled) |
|---|---|
| **nine-name book** | **+6.8pp full, +6.7pp test, maxDD −1.5pp** |
| **the six candidates** | **−2.8pp full, +1.6pp test, maxDD +6.3pp** |

So the brief's assumption that a modest standalone number becomes much better pooled is **true of
the existing book and false of this set**. And even the book's +6.8pp on a 20% base gives 27%, not
30%+.

**The likely reason is composition, and it was self-inflicted: PARR, DVN and OXY are all
energy/commodity — three of six.** Pooling pays when the names want capital at different times; an
energy-heavy set dips together, so three sleeves compete for the pot on the same mornings and sit
idle together on the others. Consistent with §3.9's finding that the uplift is counter-cyclical.
*(Hypothesis, inferred from composition — the fill-day correlation was not measured.)*

**2. The GATE works, and that is the real find here.** Pooled+PM 13.5% → **22.3%** at K≥2, the
train half **−11.0% → +3.6%**, drawdown **28.0% → 22.4%**. Roughly **+9pp of return and −5.6pp of
drawdown** from breadth-gating alone. The brief's instinct that gating adds a lot is correct, even
though the pooling half of it is not.

**3. The pre-market rule does not transport.** It helps the nine-name book (64.8 → 73.4) and
**hurts this one** (17.0 → 13.5). §3.16 was calibrated on the book's names and should not be
assumed for new ones.

**4. Three of the six earn essentially nothing.** Standalone full-sample: PARR **40.4%**,
RTX **36.9%**, DE **34.0%**, then DVN 2.5%, OXY −3.4%, AMD −0.3%. The book is carried by three
names and diluted by three. Note also the violent half-asymmetry — the set makes almost nothing in
the train half (+3.6% at best) and 43% in the test half.

**Verdict: the parallel book as briefed does not work.** At its best configuration it returns
**22.3% full / 43.4% test with a 22.4% drawdown**, against the nine-name book's **73.4 / 105.1 at
24.2** — about **a third of the return for the same risk**. Nothing here justifies deploying
capital that could go to the existing book, which §3.58 says has ~$1.3m of headroom anyway.

**What survives.** PARR (25th percentile 44.8%, the strongest honest figure found in 49 names) and
RTX. Both already known; PARR failed G5 as a VLO swap (§3.56). The three-name set PARR+RTX+DE is
the only part of this worth any further work, and it is not six names and not a book.

Results in `parallel_book.json`, `nine_pooling_uplift.json`, `fittability.json`.

**Bug found and fixed:** `fittability.py` wrote to a fixed filename, so three successive runs
silently overwrote each other and the first parallel-book run fell back to neutral vectors for
every name. It now merges on write, as `weekly_freeze.py` does for the same reason (§3.28d's
lesson, learned twice).


### 3.61 PARR+RTX+DE works far better than the six — and "look for volatile names" is now measured as the wrong instruction (15 Oct)

**1. The three-name book.** Same harness, same per-name vector rule (PARR neutral at rho −0.49,
RTX and DE fitted at +0.36 and +0.38):

| arm | full | train | test | **maxDD** | fills/yr |
|---|---|---|---|---|---|
| captive | 36.6 | 20.8 | 53.2 | 8.6 | 91.8 |
| **pooled** | **38.4** | **18.5** | **59.8** | **7.9** | **91.8** |
| pooled + PM rule | 32.6 | 19.5 | 46.1 | 13.1 | 81.2 |
| pooled + PM + breadth K≥1 | 33.6 | 24.5 | 42.7 | 13.1 | 69.3 |

**38.4% full, 59.8% test, on a 7.9% drawdown.** Both halves positive, unlike the six-name set
(train −7.8%). Return over drawdown is **4.9** against the nine-name book's 73.4/24.2 = **3.0**.
Pooling uplift is **+1.7pp full / +6.6pp test** — positive here where it was negative across six.

**Dropping DVN, OXY and AMD did all of that.** They earned 2.5%, −3.4% and −0.3% standalone and
two of them were the energy names whose shared timing killed the pooling benefit (§3.60).

**The overlays both hurt.** The PM rule costs 5.8pp and nearly doubles drawdown (7.9 → 13.1); the
breadth gate adds nothing on top. Second time the PM rule has failed to transport off the
nine-name book (§3.60). With three names, suppressing entries costs more than it saves.

**2. The catch: PARR carries it, and PARR has two problems.**
- **Unfittable** (rho −0.49), so the honest planning figure is its 25th percentile **44.8%**, not
  the 114.8% test it posts standalone on the neutral vector.
- **Liquidity, and it is probably disqualifying at scale.** PARR's Box file has **no volume column
  at all** — the importer wrote zeros and `liquidity_check.py` divides by zero — so this had to be
  estimated externally: ADV ≈ **1.0m shares at ~$70–77 = ~$73m**. Applying the at-bid ratio of the
  comparable names (RTX and DE both run at-bid ≈ 42% of ADV) gives a median at-bid near **$29m**
  and a §3.37 cap near **$0.29m per order** — about a THIRD of CF's $0.81m, which §3.58 showed
  already binds the nine-name book at $6.2m. **That caps this book at roughly $0.6–0.9m, not $2m.**
  *Estimated, not measured: re-pull PARR with volume before relying on it.*

**3. "Should we look for other volatile names?" — No, and it is now measured rather than noticed.**
Across the 43 names with 5-minute data:

| | |
|---|---|
| rank correlation, annualised volatility vs AI beta | **+0.78** |
| linear correlation | +0.75 |

§3.14, §3.45 and §3.50 each noticed this locally. At 43 names it is simply the structure of this
market: **screening for volatility IS screening for AI exposure.**

**Only 3 of 43 names are above-median volatility AND uncorrelated** (median vol 57%):

| | vol | beta | and its screened return |
|---|---|---|---|
| CELH | 60% | 0.17 | **−8.5%** |
| TEAM | 59% | 0.17 | **−3.6%** |
| RKT | 58% | 0.15 | **−18.8%** |

**All three were already screened and all three lose money.** The volatile-uncorrelated corner of
this universe is three names wide and empty.

**And the inversion that matters: the non-AI names that WORK are the quiet ones.** RTX 25% vol,
DE 29%, OXY 33%, GM 35%, VLO 36%, DVN 36% — every one below the 57% median. The brief's instinct
was that volatility supplies fills and therefore return; in the uncorrelated half of the universe
the relationship runs the other way.

**Where this leaves the parallel book.** PARR+RTX+DE is a genuinely good risk-adjusted result and a
genuinely small one — capped near $0.6–0.9m by PARR's tape, on three names, with the best name
unfittable. It is not a home for $2m of NVDA proceeds. §3.58's ~$1.3m of headroom in the existing
book remains the better destination.

Results in `book3.json`, `vol_vs_beta.json`.


### 3.62 The twelve-name book: the risk trade works, the gates-off-the-three premise does not, and the liquidity threshold needs qualifying (15 Oct)

User's design: add PARR, RTX and DE to the nine, pool all twelve, withhold the overlays from the
three (since §3.61 found the PM rule costs them 5.8pp), accepting lower return for shock
protection. Capital $6.9m. Vectors: the nine as deployed; PARR neutral (rho −0.49), RTX and DE
fitted (+0.36, +0.38).

| arm | full | train | test | **maxDD** | fills/yr |
|---|---|---|---|---|---|
| NINE, live config (baseline) | 73.2 | 45.4 | 104.6 | 24.2 | 529 |
| TWELVE, no overlays | 58.2 | 31.3 | 88.8 | 20.2 | 638 |
| **TWELVE, PM on all 12** | **66.8** | **37.2** | **101.1** | **20.7** | 618 |
| TWELVE, PM on the NINE only | 64.1 | 37.0 | 94.9 | 19.9 | 624 |
| TWELVE, PM + breadth K≥4 on NINE | 63.6 | 36.1 | 94.9 | **18.0** | 592 |
| TWELVE captive | 51.9 | 28.9 | 77.6 | 22.6 | 624 |

**1. The risk trade is real and slightly favourable.** Twelve with PM on the nine gives up
**9.1pp of return** for **4.4pp less drawdown**. Risk-adjusted that is 64.1/19.9 = **3.22** against
the nine's 73.2/24.2 = **3.03**; adding the breadth gate takes it to 63.6/18.0 = **3.53**. Pooling
uplift inside the twelve is **+12.2pp full / +17.2pp test**, much larger than the nine's +6.8 —
more names with different fill timing is exactly where pooling pays (§3.60).

**2. The gates-off-the-three premise is WRONG in this context.** PM on ALL twelve beats PM on the
nine only by **+2.7pp full and +6.2pp test** at near-identical risk-adjusted return. §3.61's finding
that the PM rule hurts the three stands *for a three-name book* and does not transport: in a pooled
twelve, suppressing a poor PARR/RTX/DE entry frees capital for nine other names, where in a
three-name book there was nowhere else for it to go. **Apply the PM rule to all twelve.**

**3. Spreading over twelve does NOT fix PARR's order size.** Median PARR order **$0.59m**, 95th
$1.34m, max $1.65m — **104 of 105 orders above the $0.29m estimate**. The reason is §3.58's
mechanism: a pooled book CONCENTRATES, it does not spread. A free sleeve takes a full share of the
pot when the others are holding, regardless of how many names exist.

**4. A per-order cap fixes it and costs about half the book.**

| cap_frac | max order | full | test | maxDD | PARR median | over cap |
|---|---|---|---|---|---|---|
| none | — | 66.8 | 101.1 | 20.7 | $0.60m | 90/93 |
| 0.0417 (=1/24) | $0.29m | **35.5** | 50.0 | 11.7 | $0.28m | 43/93 |
| 0.0300 | $0.21m | **28.0** | 38.8 | 9.5 | $0.21m | **0/93** |
| 0.0200 | $0.14m | 20.8 | 28.1 | 7.0 | $0.14m | 0/93 |

Full compliance costs **39pp of return**. The cap binds on *every* name, not just PARR, which is
why it is so expensive.

**5. A QUALIFICATION THE RECORD NEEDS: §3.37's 1%/10% thresholds are not quantified.** Challenged
by the user on exactly this. What §3.37 established is solid — ADV is the wrong denominator, the
binding quantity is dollar volume at or below the bid, and the failure mode of a resting limit is a
**partial fill, not a worse price**. The *thresholds* were reverse-engineered from the incumbents:
in §3.37's own words, admit a name under those bounds *"which is where every current book name sits"*.
That is a don't-be-worse-than-today guard-rail, **not an impact model**, and the conclusions drawn
from it — PARR "undeployable", CF "binding the book" (§3.58) — are softer than they were stated.

**Two things that follow.** Only **3.8% of orders are marketable** (47 stops of 1,234 fills): the
50-day stop sells at the open. The other ~96% are resting limits that never cross the spread, so
the question is fill COMPLETION, not price impact. And the honest denominator is probably not the
daily figure but the **first hour**, where §3.20 found 56–80% of fills occur — on which RTX at a
$0.6m order is **9.2%** of at-bid volume rather than 0.3%. **That tightens the picture for names
already in the book, not just for PARR.**

**Open, and the right next measurement:** the realised participation distribution — every
historical fill as a share of that day's first-hour at-bid dollar volume — which replaces the
borrowed rule of thumb with measured data. PARR cannot be included until a volume source is found;
its Box file has no volume column (§3.61).

Results in `book12.json`, `book12_cap.json`.


---

## 4. Live workbook state and known issues

**Current file:** `TradingExcel_5stock_live.xlsx` (Notes, Allocation, Active Trading, Dashboard,
Query, 5× Feed, 5× Model). No Power Query connections — the Query sheet is written by the IBKR
script via the `IBKR_QueryAnchor` name. Feed runs 2024-04-01 to 2026-08-03, 587 sessions.

Named ranges the automation uses: `IBKR_AvailFunds` (`Allocation!B5`), `IBKR_Orders`
(`'Active Trading'!A18:J28`), `IBKR_LogAnchor`, `IBKR_QueryAnchor`, `IBKR_BuyFee`, `IBKR_SellFee`.

### Fixed this session
1. **Dashboard OU sigma** (delivered as `TradingExcel_5stock_live_fixed.xlsx`). Column P computed
   `STDEVP` of the last W closes — the level sigma — while the Model sheets used residual sigma and
   D3 had been re-scaled for it. The errors compounded: MU's OU tranche was bidding **636 against a
   close of 830**, 23% below market and unfillable. Backtests were never affected; only the morning
   order levels. Column P now mirrors `Model!AZ`.
2. **Free-sleeve allocation** (delivered as `TradingExcel_5stock_live_freesleeves.xlsx`).
   `Allocation!C25:C34` read `M11:N15` — a fixed tenth of capital each, regardless of holdings — so
   a sleeve that bought yesterday would be funded again. Now zeroes any sleeve whose blotter Status
   (`'Active Trading'!C19:C28`) reads `HOLDING` and divides `B5` across the rest, as a weight
   renormalisation. `'Active Trading'!D19:D28` and `H19:H28` now read the same block.
   - Found while doing this: `H19:H28` already held a copy of that logic capped with
     `MIN(..., $D19)`, but `D19:D28` sum to exactly `B5`, so the cap **always** bound and the
     redistribution could never fire.
3. **Weekly workbook ATH** — `MAXIFS` needs Excel 2019+, returned `#NAME?`, an `IFERROR` turned it
   blank and the ATH column carried the blank forward. Replaced with `SUMPRODUCT(MAX(...))` and made
   non-recursive so one bad cell cannot propagate.

### Outstanding, flagged not fixed
- **Split mode trap.** `Allocation!B9 = 2`, so the Bayes share comes from column `Q`, **not** `B6`.
  Both are 0.50 so behaviour is correct, but editing `B6` does nothing. To move the split, set
  `B9 = 1` *or* edit `Q11:Q15`, and mirror into `V2` on each Model sheet.
- **Stale prose.** `Notes!B4` and `Allocation!A2` still describe the retired 0.75 tilt.
- **`B5` must be cash on hand**, not total book value. With sleeves holding, the free ones take the
  whole of B5 between them. Relabelled "Cash available today ($)" in the fixed copy.

### Excel/openpyxl gotchas
- **openpyxl wipes all cached formula values on save** (`<v>…</v>` → `<v />`) but writes
  `fullCalcOnLoad="1"`, so Excel recalculates on open. **Consequence:** after any openpyxl write,
  reading the file back with `data_only=True` returns `None` until Excel has opened and saved it.
  A pipeline that writes prices with openpyxl and then reads computed order levels **cannot work**.
- **LibreOffice cannot open this workbook at all** — the unmodified original fails identically. So
  recalculation-based verification is unavailable; use the Python mirror pattern (re-derive each
  formula from cached values and compare cell by cell).
- `premarket_study/mirror.py` provides `assert_writable()` (refuses to write a master a human has
  open, checking both the `~$` lock file and open-for-append), `save_atomic()` and `publish()` for a
  read-only snapshot the user can open while Python writes the master. `publish_via_excel()` covers
  the COM case and is **untested** (no Excel on this box).

---

## 5. Methodology conventions

- **Half-sample split at 2025-05-23.** Fit on the first half only, freeze, score the second. This is
  the blade that decided the book (it eliminated PLTR: 365% first half, 3.1% tested).
- **Verified fills.** Same-day round trips kept only where 5-minute bars (1-minute for NVDA) prove
  the low preceded the high. Names without intraday coverage get the **at-open floor** — an exit
  allowed only where the bid is at or above the open — which is a hard lower bound, not an estimate.
- **Mark to market.** The engine's `annual_return` counts open positions at cost; use the
  Fund-column / equity-curve basis instead.
- **Planning figure** = parameter-neighbourhood median, or full-sample less the measured
  out-of-sample haircut. Never a raw fitted number.
- **Overfitting tells:** boundary-seeking parameters, wide fold spread, fitted ≫ tested.
- **Robust objective**: `0.5·base + 0.5·mean(±3% perturbations on the 6 policy parameters)`, with a
  minimum-trade floor. `differential_evolution(..., workers=1)` — `workers=-1` fails to pickle.
- **Nested folds are not independent evidence.** Fold agreement in an expanding walk-forward is not
  confirmation.

---

## 6. Diversifier work (most recent)

**Assessed:** GM, VLO, CF, ALNY (5-minute data, 587 sessions, 2024-04-01 to 2026-08-03).
**Recommended: add GM, VLO, CF at 35% each. Reject ALNY.** Not yet implemented in the workbook.

### The concentration being addressed
Four of five book names are one trade — TSM (semis), VRT (data-centre cooling), VST (data-centre
power), MU (HBM memory). **RKLB is not the exception it looks like**: beta 0.77 to the AI factor and
0.69 to TSM. It doesn't share the theme, it shares the risk appetite. The book is five-for-five
exposed.

Average pairwise correlation of share returns: four AI names **0.58**, current five **0.48**,
proposed nine **0.21**, the four candidates among themselves **0.11**.

Candidate betas to the AI factor: GM 0.19, VLO 0.11, **CF 0.00**, ALNY 0.12.
Caveat: **VLO and CF correlate 0.41** with each other (both energy/commodity) — one-and-a-bit names.

### Half-sample test (fit 1st half, freeze, score 2nd)
| | fit 1st | **tested** | full fit | buys/yr | tested DD | corr to book |
|---|---|---|---|---|---|---|
| GM | 68.3% | **37.1%** | 50.3% | 94 | 10.8% | 0.16 |
| VLO | 29.6% | **35.2%** | 64.2% | 20 | 4.3% | 0.30 |
| CF | 47.0% | **42.4%** | 46.9% | 28 | 15.0% | 0.01 |
| ALNY | 44.4% | **−8.0%** | 31.4% | 23 | 35.8% | 0.06 |

For contrast the previous shortlist (MRNA, OXY, FSLR, DVN, COIN) tested at −1.0, 4.1, 2.9, 15.1, 0.1%.

### Stress windows (held construction, full sample)
| | Jan–Apr 2025 (AI −45.9%) | Jun–Jul 2026 (−17.6%) | May–Aug 2024 (−27.3%) |
|---|---|---|---|
| five names | **−37.3%** | −9.2% | −4.5% |
| five + GM/VLO/CF | **−21.6%** | −2.9% | −2.8% |

In Jun–Jul 2026 VLO rose 30.9% and CF 17.9% *while* the theme fell.
Full sample: adding the three takes beta 0.58 → 0.41 and max drawdown 39.3% → 27.0%.
**Nuance:** R² to the factor stays at 0.37 for every book — adding these names scales total risk
down by ~⅓ rather than changing what the risk *is*. Beta and the stress windows are the honest
measures; R² is not.

### Walk-forward (3 expanding folds, all eight names refitted on train, no rebalancing)
| fold | test window | AI factor | five | eight | delta | DD five | DD eight |
|---|---|---|---|---|---|---|---|
| 1 | 2025-05-28 → 2025-10-13 | +61.2% | 120.0% | 79.1% | −41.0 | 4.6% | 2.8% |
| 2 | 2025-10-14 → 2026-03-04 | +31.1% | 69.2% | 56.7% | −12.5 | 11.4% | 8.3% |
| 3 | 2026-03-05 → 2026-07-23 | +42.5% | 49.8% | 61.6% | **+11.8** | 16.1% | 8.9% |

Lower drawdown 3/3 (mean −4.0pp), lower return 2/3 (mean −13.9pp).
**Fold 3 is the thesis in miniature** — RKLB fell 28.6% while VLO rose 50.6% and CF 20.2%.

> **What the walk-forward cannot show.** The AI factor **rose in every test window**. The only AI
> drawdown in the sample (Jan–Apr 2025) sits before the first fold boundary, so it is in the
> training half of all three folds. The walk-forward prices the premium and never tests the
> insurance. The halved stress loss remains evidence from **one episode inside the fitted region**.
> A reversed walk-forward (fit late, score the crash) was offered and the user was unconvinced.

### Planning returns and deployable parameters
From windows nothing had seen (3 folds + the half-sample test), median:
**GM 33%, VLO 35%, CF 41%** — plan on 35% each. Book goes ~79% → ~64%, about **15pp**.
Basis check: the five book names on the same unseen-window basis average 77.0% vs published 79.4%,
so the two can be quoted side by side.

| | GM | VLO | CF |
|---|---|---|---|
| λ | 0.704472 | 0.723393 | 0.736218 |
| φ_L | 0.750723 | 0.625222 | 0.106120 |
| ψ | 0.0805582 | 0.0200999 | 0.0694359 |
| k | 0.461711 | 0.543763 | 2.03552 |
| premium | 0.00969721 | 0.0303035 | 0.0465592 |
| peak cap | 0.0423717 | 0.0308569 | 0.0286416 |
| OU buffer | 1.06024 | 1.17841 | 0.841237 |
| OU premium | 0.0451112 | 0.0419514 | 0.0590932 |
| OU cap | 0.0417662 | 0.0370821 | 0.0831024 |
| OU W | 45 | 125 | 66 |

Full-sample fits, 61/35/27 buys per year. **The fits move a great deal between halves and the
returns do not** — GM's λ goes 0.20 → 0.70, CF's ψ fifteen-fold, yet out-of-sample returns from
both sets sit within a few points. The optimum is broad, not sharp: do not treat the vectors as
precise, and do not re-fit expecting improvement. Only the OU lookback holds still.

---

## 7. Key files

**Engine and harness**
- `engine.py` — validated Python replica of the Model sheet. `run_model(..., ou_sigma='level'|'resid'|'detrend', same_day_exit=True|callable|None)`. `'level'` preserves the old deployed path exactly.
- `five_min.py` / `minute_engine.py` — intraday fill verifiers (`make_checker`).
- `stop_sweep.load_book`, `daily_window_split`, `mu_rerun.from_workbook`, `newcands.load` — data loaders.
- `optimise_candidates.py` — `BOUNDS`, `POLICY`, `PERTURB`, `mp()`, `bvec()`; the shared optimiser contract.

**Studies**
- `planning_resid.py` — planning figures on the corrected sleeve.
- `workbook_basis.py` — reconciles sheet `Y5` with the planning basis.
- `weekly_*.py`, `max_hold_test.py`, `half_week_model.py` — the weekly model work.
- `ss_model.py`, `ss_sleeve.py`, `ss_experiment.py`, `ss_walkforward.py`, `tsla_ss.py` — Schwartz–Smith.
- `newdiv.py`, `newdiv_rebal.py`, `newdiv_params.py`, `ai_concentration.py`, `wf_eight.py`, `planning_new.py` — the diversifier work.
- `sleeve_corr.py`, `split_riskadj.py`, `xlsx_compat_check.py`, `mirror.py`.

**Workbook builders/patchers**
- `build_weekly_excel.py` (contains a Python `mirror()` that evaluates the sheet formulas and aborts the build on mismatch), `apply_ou_resid.py`, `fix_dashboard_sigma.py`, `alloc_free_sleeves.py`, `verify_free_sleeves.py`.

**Documents (`memo/`)**
- `seven_name_book_r5.tex` — book specification, current.
- `strategy_mathematics_r3.tex` — mathematical white paper, current.
- `live_workbook_spec.tex` — parameters, allocation and return expectation for the live workbook.
- `diversifiers_gm_vlo_cf.tex` — the diversifier assessment, current.

---

## 8. Open items

1. **Implement GM, VLO, CF in the workbook** — not started. Needs Feed/Model sheets, Allocation rows
   (8 names → 12.5% each, floor and cap both 0.125), Dashboard and blotter rows, `IBKR_Orders`
   widened from `A18:J28` to cover 16 sleeves.
2. **Merge the two workbook fixes** — `_fixed` (Dashboard sigma) and `_freesleeves` (allocation) were
   delivered from different uploads and have not been combined into one file.
3. **Reversed walk-forward** on the AI stress episode — offered, user unconvinced. Still the only way
   to get that episode out of sample with the data available.
4. **TSLA / Schwartz–Smith** — if pursued, the next step is reproducing the result in the real engine
   with verified fills rather than the simplified `ss_sleeve` replica.
5. **Website copy** — four revised summary points were delivered as text; a five-point variant
   splitting robustness and allocation was offered but not requested.
6. **Rotate the Massive API key.**
7. ~~Persist the five core names' DEPLOYED parameters to a tracked file.~~ **DONE (§3.56)** —
   `premarket_study/deployed_params.json`. Original note: They exist only in
   the uploaded workbook, which dies with every container, and `book_sim`/G5 cannot run without
   them (§3.54). `fresh_opt_cands.json` carries AVGO's and nothing else.

---

## 9. Corrections made during the session — do not re-derive

These were wrong and were fixed; a new session should not rediscover them as findings.

- Fold agreement in an expanding walk-forward is **not** independent evidence — the folds are nested.
- `g` is inert in the weekly model; `m` is the live switch. (An early claim that `g` carried the
  overfit was wrong.)
- Anchor mixing does **not** buy robustness — it lowers the neighbourhood median.
- A 12-week weekly cap is not free: it costs NVDA 12pp. 26 weeks is.
- The Bayes–OU correlation is **0.57** (engine), not 0.83 (a harness artefact); 0.90–0.97 when both
  sleeves hold.
- The first risk-adjusted split test was biased — `ou_buf_k` had been fitted at `bayes=0` on the full
  sample.
- The first diversifier marginal test used daily rebalancing and was wrong (see §3.4).
- **§3.37's 1%/10% liquidity thresholds are a guard-rail, NOT an impact model** (§3.62).
  They were reverse-engineered from the incumbents. The denominator finding (at-bid, not ADV)
  and the failure mode (partial fill, not worse price) ARE solid. ~96% of orders are resting
  limits that never cross the spread; only the 50-day stop is marketable, at 3.8% of fills.
- **Volatility and AI beta are the SAME AXIS: rank correlation +0.78 across 43 names**
  (§3.61). Screening for volatility is screening for AI exposure. Only 3 of 43 are
  above-median volatility and uncorrelated, and all three lose money. The non-AI names
  that work are the QUIET ones (RTX 25% vol, DE 29%, GM 35%).
- **Pooling is worth ~+6.8pp on the NINE-NAME book and ~0 on a new set** (§3.60). It pays
  only when names want capital at different times; an energy-heavy set dips together. Do not
  assume the uplift when sizing a new book. The PM rule likewise does not transport.
- **A single train-half fit means nothing where the train half does not predict the test
  half.** Run fittability.py (§3.59) BEFORE reading any fitted number: SOFI 70.9%, DLTR 22.7%
  and EXPE 23.2% all evaporate, while AMD and PARR are strong names whose fits are noise.
- **G2 is §3.14's RETURN HURDLE** (30% uncorrelated / 50% AI-related), NOT "beats the
  no-fit baseline" as screen_speed.py implemented it (§3.53). The proxy passes a name
  losing 3.6% and fails one making 46.1%. It changes three §3.50 verdicts.
- A turnover gate is a screening **descriptor**, not an objective **constraint** (§3.51):
  fitting to it cuts the premium, which in a pooled book takes capital from better names
  and removes the cushion in a drawdown.
- Turnover follows the **fitted premium**, not the name alone (§3.50): CF runs at
  25.7, 42.6 or 89.4 fills/yr on three different vectors. §3.49's "property of the name"
  was too strong.
- Weekly trade counts are **threefold inflated**: the three tranches of a name lock in
  week 4 and trade identically forever (§3.48), so RTX's "17.9/yr" is 6.0 distinct positions.
- GM trades **61** times a year on deployed parameters, not 94 (that was the tested-half figure on
  frozen first-half parameters).

### 3.63 The participation distribution: the liquidity question answered from the book's own record — the nine are fine, CF and VLO are not, and the binding constraint is the stop, not the bid (15 Oct)

User, after challenging §3.37's caps: *"what's the basis for the liquidity cap and is it quantified.
The key question for me is can we buy and sell efficiently?"* → *"run the participation distribution
across the nine plus RTX and DE"*. §3.62 conceded the 1%/10% thresholds were reverse-engineered from
what the incumbents happened to pass. `participation.py` replaces them with the measured record:
every historical fill sized against the liquidity a **resting limit actually reaches** — bars whose
low ≤ the bid (buy), whose high ≥ the target (passive sell) — first hour per §3.20. Capital $6.9m,
pooled, live config. PARR excluded (no volume column, §3.61).

**The nine, live config — 1,218 fills.** Order as a share of first-hour at-bid dollar volume:

| name | fills | median $ | max $ | %ADV | %at-bid | **%1st hr** | p95 1st hr | >5% | >10% |
|---|---|---|---|---|---|---|---|---|---|
| AVGO | 138 | 0.65m | 3.74m | 0.02 | 0.05 | **0.11** | 0.8 | 0% | 0% |
| MU | 127 | 0.86m | 1.78m | 0.01 | 0.04 | **0.05** | 1.3 | 0% | 0% |
| TSM | 211 | 0.82m | 3.17m | 0.03 | 0.06 | **0.16** | 1.0 | 0% | 0% |
| MRVL | 126 | 0.73m | 2.17m | 0.06 | 0.15 | **0.45** | 3.5 | 3% | 2% |
| VRT | 173 | 0.77m | 2.33m | 0.08 | 0.23 | **0.51** | 4.5 | 4% | 2% |
| VST | 166 | 0.78m | 3.71m | 0.10 | 0.27 | **0.79** | 6.7 | 7% | 2% |
| GM | 139 | 0.66m | 6.24m | 0.16 | 0.49 | **1.13** | 11.4 | 12% | 7% |
| **VLO** | 81 | 1.02m | 4.45m | 0.22 | 0.68 | **3.23** | 12.7 | **38%** | 6% |
| **CF** | 57 | 0.90m | 3.71m | 0.50 | 1.09 | **4.33** | **45.4** | **44%** | **22%** |
| BOOK | 1218 | 0.78m | 6.24m | 0.06 | 0.17 | **0.38** | 6.7 | 7% | 3% |

**1. ADV flatters the book by roughly 6×, and the first hour unflatters it by another 2×.** The
median order is **0.06% of ADV**, **0.17%** of whole-session at-bid volume and **0.38%** of
first-hour at-bid volume. §3.37's choice of denominator was right and the magnitude of the
correction is now measured: using ADV understates the demand the order actually makes by about
**six-fold**, and ignoring the first-hour concentration by about **two-fold** on top.

**2. Seven of the nine have no liquidity problem at all.** AVGO, MU, TSM, MRVL, VRT and VST sit at
**0.05–0.8%** of first-hour at-bid volume at the median with p95 under 7%. GM at 1.13% median is
comfortable. On these names the answer to *can we buy efficiently* is an unqualified yes, and the
$0.5–1m order is nowhere near the constraint.

**3. The two diversifiers are the problem, and CF is the acute one.** CF's median order is
**4.33%** of first-hour at-bid volume, its p95 **45.4%**, and **22% of its orders exceed 10%**.
VLO's median is 3.23% with 38% of orders above 5%. This independently confirms §3.58 on CF —
arrived at there from a reverse-engineered threshold, here from the book's own fills — and it is
now a **measurement, not a guard-rail**. Note what this means for §3.57: the diversifiers are not
only failing to pay (the user's correction), they are also the only two names whose orders are
demanding against available liquidity.

**4. Capacity, derived rather than assumed.** Participation is exactly linear in capital, so the
capital at which the 95th-percentile order reaches a given share of first-hour at-bid volume follows
directly:

| | CF | VLO | GM | VST | VRT | MRVL | MU | TSM | AVGO | **BOOK** |
|---|---|---|---|---|---|---|---|---|---|---|
| @5% | $1m | $3m | $3m | $5m | $8m | $10m | $26m | $34m | $41m | **$5m** |
| @10% | $2m | $5m | $6m | $10m | $15m | $20m | $51m | $68m | $82m | **$10m** |
| @20% | $3m | $11m | $12m | $20m | $31m | $39m | $102m | $135m | $165m | **$20m** |

CF and VLO are only 138 of 1,218 fills (11%) but they populate the tail, and removing them moves the
pooled 95th percentile from **7.2% to 4.1%** — book capacity **$5m / $10m / $19m → $8m / $17m /
$34m**, a **1.7× gain**. So the diversifiers cost roughly **four-tenths of the book's liquidity
capacity** on top of the return cost already recorded (§3.57) — material, but less than halving it.
Within the remaining seven the binding name is VST ($5m @5%, $10m @10%), and MU/TSM/AVGO are
effectively unconstrained at any capital this book will reach.

**5. The binding constraint is the STOP, not the bid.** ~96% of the loop is passive and cheap: the
passive sell (target hit) is a **median 0.15%** of at-or-above-target volume, p95 4.0%. But the
**47 of 1,218 exits (3.9%) that hit the 50-calendar-day stop sell AT THE OPEN**, and against the
opening 5-minute bar they are a **median 2.1%, p95 39.5%, max 73.8%**. Spread over the first 30
minutes the same orders are a median 0.6% and p95 7.1%. **This is the one actionable finding on the
execution side: working the stop over the first 30 minutes rather than dumping it into the opening
print cuts its p95 participation by a factor of 5.5.** It touches 4% of exits, so it will not show
up in backtest return — it is a real-money execution instruction, not a model change.

**6. A quarter of fills never reach the bid in the first hour.** 26% of the nine's fills (19% VRT →
42% VLO) had their bid untouched before 10:30 and rested into the session. Carrying those at the
whole-session denominator rather than dropping them moves the book p95 from 6.7% to **7.2%** — so
the first-hour figures are not flattered by survivorship, which was the obvious way this measurement
could have been wrong.

**7. Adding RTX and DE dilutes, mildly.** Eleven names at the same capital: book median first-hour
participation **0.38% → 0.34%**, p95 **6.7% → 5.6%**. RTX lands at 0.93% median / 9.1% p95 and DE at
1.26% / 9.3% — both between GM and VLO, i.e. tolerable but not free. Their own capacity lines are
**$4m @5% / $8m @10%**, which makes them, with CF and VLO, the names that would bind first as capital
grows. This also quantifies §3.62's point 3 from the other side: spreading over more names shrinks
the typical order only **~10%**, because a pooled book concentrates into whichever sleeves are free.

**What this does NOT measure.** Participation is how demanding the order is, not a slippage number
and not a fill probability. Being 10% of the volume that trades at or below your price does not mean
you capture 10% of it — queue position, order type and who else is resting there all matter, and none
of that is visible in 5-minute bars. The honest claim is a **demand distribution**: below ~1% the
order is invisible, above ~10% it is competing for a material share of the available flow, and the
severity in between is not resolvable from this data. PARR remains unmeasured.

Artifacts: `participation.py`, `participation.json`, `participation.log`. The JSON carries the raw
per-fill ratios under `"<arm> :: rows"`, so any later slice (drop a name, move a threshold) comes off
those rather than another full simulation. `book_sim.py`'s trade records now additionally carry `bid`
and `target` (purely additive; no behaviour change).

### 3.64 The twelve with PARR capped at $400k: the cap is free, and it also shows PARR is not earning its place (15 Oct)

User: *"I think we're going into too much detail here. CF has very few fills over the year anyway.
I've never had an issue with filling VLO in practice. Can you run the 12 stock model and cap PARR
at $400k"* — so §3.62's cap_frac sweep (which throttled every name to fix one) is set aside, and
§3.63's CF/VLO findings are noted but not acted on: CF is 57 fills over the period and the user's
live experience on VLO outranks a bar-derived ratio. `book_sim.simulate` gains `name_cap`
({name: max $/order}, remainder re-divided over the other free sleeves). The no-cap arm reproduces
`book12.json` to **0.000pp**, so the change is non-invasive.

| arm | full | train | test | maxDD | fills/yr | ret/DD |
|---|---|---|---|---|---|---|
| NINE, live config (baseline) | 73.2 | 45.4 | 104.6 | 24.2 | 529 | 3.02 |
| TWELVE, PM on all 12, no cap | 66.8 | 37.2 | 101.1 | 20.7 | 618 | 3.23 |
| **TWELVE, PM on all 12, PARR ≤ $400k** | **67.7** | **40.9** | **97.9** | **20.5** | 618 | **3.30** |
| TWELVE + breadth K≥4 on the nine, PARR ≤ $400k | 65.7 | 37.5 | 98.0 | **19.8** | 586 | **3.33** |
| **ELEVEN (no PARR), PM on all 11** | **70.4** | **47.3** | 95.7 | 21.0 | 577 | **3.36** |
| TWELVE captive, PARR ≤ $400k | 51.3 | 28.7 | 76.7 | 22.5 | 618 | 2.29 |

**1. The cap costs nothing.** Full **+0.8pp**, test −3.1pp, maxDD −0.2pp, **fill count identical**
(1,439). Capital denied to PARR re-divides into the other eleven, and those names use it at least as
well — RTX's median order goes $0.62m → $0.67m, DE's $0.54m → $0.59m. §3.62's conclusion that
capping PARR costs half the book was an artefact of `cap_frac`, which throttles **every** name; a
per-name cap costs nothing because only one name is over.

**2. The cap binds on every single PARR order.** Median = p95 = max = **exactly $0.40m** across all
93 orders (uncapped: median $0.60m, max $2.15m). PARR is therefore no longer participating in the
pool at all — it is a fixed-size sleeve. Per-**day** across both sleeves the total is median $400k,
max $800k, with **19 of 74 fill days at $800k** (both sleeves firing), which is the number the
at-bid volume actually has to absorb.

**3. And that makes PARR redundant.** The **eleven-name book without PARR beats the capped twelve**
on full (+2.7pp), train (+6.4pp) and ret/DD (3.36 vs 3.30), giving up 2.2pp of test return and
0.5pp of drawdown. PARR was always the weakest of the three additions — neutral vector, rho −0.49,
unfittable (§3.61) — and once it is pinned to a fixed $400k it contributes close to nothing.
**The honest reading: cap PARR and it is free but pointless; drop it and the book is simpler and
slightly better.** The case for keeping it rests entirely on the 2.2pp of test-half return and the
marginal drawdown, i.e. on diversification that has not yet proven itself out of sample.

**4. The risk trade the user bought is intact.** Capped twelve vs the nine: **−5.6pp return for
−3.7pp drawdown**, ret/DD 3.30 vs 3.02; with the breadth gate, 3.33 at an 19.8 maxDD. Eleven is the
same trade on better terms: −2.8pp return for −3.2pp drawdown, ret/DD 3.36.

Artifacts: `book12_parrcap.py`, `book12_parrcap.json`, `book12_parrcap.log`.
