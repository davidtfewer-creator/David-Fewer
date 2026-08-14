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
