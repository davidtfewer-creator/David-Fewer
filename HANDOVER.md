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
- GM trades **61** times a year on deployed parameters, not 94 (that was the tested-half figure on
  frozen first-half parameters).
