# Pre-market VWAP as a signal — NVDA study

Investigates open item #3 from the project handoff: can **pre-market VWAP (04:00–09:30 ET)**
replace **previous close** as the live "current price" signal in the Bayesian + OU model?
NVDA only, as a first step. No Excel writing — pure Python off a validated engine.

## Files

| File | What it does |
|---|---|
| `engine.py` | Faithful Python replica of the `Model NVDA` sheet (Kalman local-linear-trend Bayes tranche + AR(1) OU tranche, stop-loss, monthly interest, compounding). Signal-injection hooks: `open_cap`, `ou_anchor`, `bayes_signal`. |
| `validate_nvda.py` | Proves the engine reproduces the workbook **to the dollar**. |
| `experiment_nvda.py` | Baseline vs PM-VWAP for each injection point (A: open cap, B: OU anchor, A+B). |
| `period_check_nvda.py` | Per-quarter consistency check (params frozen). |

Data CSVs (`nvda_ohlc.csv`, `nvda_joined.csv`) are derived from the user's workbooks and
are **git-ignored**; regenerate with the extraction snippets in the project notes.

## Engine validation

Reproduces `Model NVDA` cached results exactly: terminal fund **$7,520,461.83**,
annual return **150.20%**, **186** buys (138 Bayes / 48 OU), **0** stop-loss exits.
(The only non-obvious detail: the OU tranche starts accruing idle-cash interest one row
later than the Bayes tranche — `AF`/`AR` initialise on row 9, not row 8.)

## Where "previous close" enters as a signal

- **(A) Open cap `Oₜ`** — both bids are `MIN(fair−buffer, Oₜ, peak)`. The backtest uses the
  *true* open (unknowable pre-open); live it must be proxied. **Live-fidelity question.**
- **(B) OU forecast anchor** — `forecast = mean + φ·(anchor − mean)`, anchor = prev close.
  **Genuine alpha question.**
- **(C) Bayes fair value** — could feed PM VWAP as an extra same-morning Kalman observation.
  Not yet tested (a design change, not a swap).

## Finding (NVDA, full history, frozen params)

| Config | Ann return | Sharpe | maxDD |
|---|---|---|---|
| Oracle (true open — unattainable live) | 150.2% | 4.53 | 12.5% |
| Live: prev-close cap | 113.1% | 3.15 | 14.7% |
| **Live: PM-VWAP cap only (A)** | **118.4%** | **3.49** | **11.6%** |
| Live: PM-VWAP cap + anchor (A+B) | 108.6% | 3.25 | 12.8% |

- **(A) PM-VWAP as the open cap is a clear win** — higher return, higher Sharpe, *lower*
  drawdown than prev-close, and beats prev-close in **7/10 quarters**. Economic story: on
  gap-up mornings prev-close caps the bid too low and misses fills; PM-VWAP tracks the real
  open (MAE $0.61 vs $1.86) and recovers them.
- **(B) PM-VWAP as the OU anchor hurts** (−9pp return) — beats prev-close in only 4/10
  quarters. Keep the OU anchor on previous close.
- **Best live design: PM-VWAP for the open cap, previous close for the OU anchor.**

## Should we re-optimize the parameters for the VWAP variant? — No (`optimize_nvda.py`)

The frozen params were tuned for the close-cap model, so it's fair to ask whether the
VWAP-cap variant wants its own tuning. Ran a walk-forward re-optimization (differential
evolution, robustness term, min-trade floor) — optimize on train, judge on the unseen
test slice — comparing frozen-VWAP vs reopt-VWAP:

| Fold | Test slice | frozen+close | frozen+VWAP | reopt+VWAP | winner |
|---|---|---|---|---|---|
| 1 | [291:387] | 23.1% | 23.8% | 34.4% | reopt |
| 2 | [388:483] | 49.1% | 47.6% | 12.1% | frozen |
| 3 | [484:581] | 32.5% | 33.0% | 14.2% | frozen |
| **avg OOS** | | **34.9%** | **34.8%** | **20.2%** | **frozen** |

Re-optimizing beats frozen out-of-sample in only **1/3 folds**, and when it loses it
*collapses* (fold 2: 12% vs 48%). Average OOS return drops from **34.8% → 20.2%**. The
re-optimized params swing wildly fold-to-fold (ψ −74%, φ_L +67%, λ −29% in the last
fold) — no stable optimum, exactly the "parameter CV ≈ 0.4–0.6" result from §2.

**Conclusion: keep the frozen (close-optimized) params even under the VWAP cap.** The
close-optimized params generalize better than any VWAP-specific re-tune — reinforcing
that the edge is structural. The PM-VWAP open cap is a clean *signal* improvement to layer
**on top of** the frozen params, not a reason to re-fit them.

## Does the open-cap win generalize? — Yes, all ten names (`multi_stock.py`)

Engine validated against **all ten** workbooks' cached results (annual return, buys, stops)
exactly. Then, frozen params throughout, compared the live open-cap proxy prev-close vs
PM-VWAP (both traded against actual OHLC). The workbook's headline returns are *oracle*
numbers that assume perfect knowledge of the open — unattainable live.

| | avg annual return | avg Sharpe | avg maxDD |
|---|---|---|---|
| Oracle (true open — sim only) | ~221% | — | — |
| Live: prev-close cap (current) | 111.5% | 1.90 | 32.8% |
| **Live: PM-VWAP cap (proposed)** | **164.4%** | **2.94** | **23.6%** |

- **PM-VWAP beats prev-close on annual return in 10/10 stocks**, and in **68/100
  stock-quarters** — consistent across names and across time.
- Return +52.9pp on average, Sharpe 1.90→2.94, and max drawdown *falls* 32.8%→23.6%.
- The biggest gains are on the high-gap names (VST +91pp, RKLB +155pp, SOFI +93pp) —
  exactly where a stale prev-close proxy misfires most.
- **Interpretation:** the workbook's returns are simulation-with-oracle-open. Live, the
  prev-close proxy realises only ~half of that. **PM-VWAP recovers ~half of the remaining
  sim-to-live gap, with lower drawdown** — a pure live-fidelity gain, no parameter fitting,
  no lookahead (PM VWAP is known pre-open; fills use the actual day's range).

## Caveats (per the project's recurring principle)

This is **one stock, full history**. Change (A) is a live-fidelity improvement with
*frozen* parameters (not a fit), which is the robust kind — but before trusting it live:
extend to the other names, and ideally run a warm-started walk-forward per name.

## Pre-market VWAP / actual open as the SIGNAL (not the cap) — hurts

Distinct from the open-cap work: this tests the user's actual question — is a *less-noisy*
(PM-VWAP) or *fresher* (actual open) **signal** for setting the bid better? Execution held
fixed at correct limit mechanics; frozen params; both injection points (OU forecast anchor,
Bayes fair-value nudge). All ten names:

| Signal change | avg Δ annual | beats baseline |
|---|---|---|
| OU anchor = PM-VWAP | −8.4pp | 2/10 |
| OU anchor = actual open | −10.0pp | 2/10 |
| Bayes fair → open (gain 0.5) | −14.6pp | 0/10 |

Fills mostly *decrease*, not increase. **Mechanism:** the edge is a *stable, smoothed*
reference that rests a patient discounted bid below the market, which daily volatility comes
down to and fills. A fresher/less-noisy signal makes the bid *chase* the current price — it
moves away from where dips form — so it fills less and earns less. The smoothing is the
feature, not noise to remove. (Consistent with the frequency case study: more fills ≠ better.)

## Fair-fight: re-optimise NVDA params for the actual-open SIGNAL (`optimize_open_signal_nvda.py`)

The frozen params were tuned for the close signal, so we gave the open-signal its own tuning
(OU anchor = open; Bayes fair nudged toward open with free gain; all 11 params optimised for
profit + trade floor), judged out-of-sample.

- **In-sample (full history):** ann 150.2% → **200.6%**, buys 186 → **268**, gain 0.87 — a big
  apparent win in *both* profit and trades. (The mirage — an in-sample re-fit always wins.)
- **Walk-forward OOS (reopt-open vs frozen-close):** fold1 34.3 vs 26.5 (reopt), fold2 30.9 vs
  51.2 (frozen, −20pp collapse), fold3 51.3 vs 40.6 (reopt). **2/3 folds to reopt, but average
  essentially tied (38.8% vs 39.4%, −0.6pp)** with a fat-tail losing fold.

**Read:** unlike the other rejected ideas, this is *borderline* — the open-signal, properly
tuned, is roughly competitive OOS, not clearly worse. But the +50pp in-sample gain does **not**
survive, the average OOS edge is nil, and the loss fold shows the overfitting asymmetry (small
wins, big losses). Caveat: the frozen baseline was full-history-tuned (mildly optimistic on the
test slices), so a cleaner tiebreaker re-tunes *both* signals per fold. On this evidence it
doesn't justify displacing the validated close-signal model, but it's the closest call so far.

## Clean tiebreaker: open vs close signal, both re-optimised per fold (`optimize_tiebreaker.py`)

Removes the incumbent's full-history peeking: both signals re-optimised on each training
fold, judged OOS. Two comparisons, answering different questions:

**(i) Same-policy, no-peek — reopt-open vs reopt-close:** open wins **6/9 folds**; overall
OOS open **33.5%** vs close **24.9%**. *But* re-optimising the close signal is self-defeating
(reopt-close 24.9% vs the frozen close incumbent's 40.9% — the §2 lesson again), so this is
partly beating a strawman.

**(ii) Decision-relevant — reopt-open vs the FROZEN close incumbent (what's deployed):**

| name | frozen-close (incumbent) | reopt-open | open beats |
|---|---|---|---|
| NVDA | 39.4% | 39.5% | 2/3 (tie on avg) |
| AVGO | 33.6% | 41.2% | 2/3 (+7.6pp) |
| SPOT | 49.6% | 19.8% | 1/3 (−29.8pp, collapse fold) |
| **overall** | **40.9%** | **33.5%** | — |

**Verdict:** against the actual deployed model, the re-tuned open signal does **not** win
overall (33.5% vs 40.9%) — it ties NVDA, wins AVGO, loses badly on SPOT (with a −20pp fold).
So there is **no robust, general edge**, and it would reintroduce ongoing re-optimisation (this
project's nemesis) plus tail risk. Keep the frozen close-signal model.

**But the instinct wasn't baseless:** under a same-policy comparison the open signal is
*more robust to re-optimisation* than close (holds ~39% on NVDA where reopt-close collapses to
26%), hinting the fresh open info has real predictive content. Not enough to switch on 3 names,
but the honest "something" — worth a larger (all-10, more-fold, robustified) test before final
burial if ever revisited.

## All-ten clean tiebreaker — the definitive test (`optimize_tiebreaker_all.py`)

Same tiebreaker across all ten names, three OOS numbers per fold on the same unseen slice:
frozen-close (deployed incumbent) | reopt-close | reopt-open. 30 folds total.

| Model | avg OOS return |
|---|---|
| **Frozen close (incumbent)** | **52.9%** |
| reopt-open | 44.9% |
| reopt-close | 32.8% |

- **reopt-open beats the frozen incumbent in only 15/30 folds and 5/10 names** — a coin-flip
  by count, and the incumbent wins the aggregate by **+8pp (52.9% vs 44.9%)**.
- **Why the incumbent wins the aggregate:** the open signal wins *small* on mid-range names
  (TSM +13, VRT +13, AVGO +8, TSLA +2) but loses *big* on the highest-return names — RKLB
  (107→72), SPOT (50→20), SOFI (74→50), PLTR (31→9), where the frozen params capture the big
  trends and re-tuning-to-open gives them up.
- reopt-close (32.8%) is worst of all — re-optimising the close signal overfits (§2 again).

**Definitive verdict:** no robust, general edge from the actual-open (or PM-VWAP) signal. A
~50% fold/name hit-rate with the incumbent winning the magnitude battle is what *no edge* looks
like. **Keep the frozen close-signal model** — best aggregate, simplest, no re-optimisation,
no tail blow-ups. The open signal's competitiveness on some mid-caps is real but not bankable.

## Laddered scale-in entries — tested, rejected (`ladder_engine.py`, `test_ladder_nvda.py`)

Idea: replace each tranche's single bid with R rungs at increasing σ-depths to deploy the
idle ~75% cash on bigger dips. Sanity: 1-rung ladder reproduces baseline (151% vs 150%, 186
trades, corr −0.01). NVDA sweep, both sleeves laddered, 3 equal rungs, blended TP:

| Config | Ann | Sharpe | maxDD | Trades | Bayes–OU corr |
|---|---|---|---|---|---|
| Baseline (1-rung) | 150% | 4.53 | 12.5% | 186 | −0.01 |
| span [.6,1,1.4]×σ | 128% | 3.69 | 16.0% | 504 | +0.40 |
| deep [1,1.5,2]×σ | 79% | 3.60 | 11.5% | 350 | +0.01 |
| wide [.5,1,1.8]×σ | 101% | 3.04 | 15.9% | 445 | +0.49 |
| shallow [.4,.7,1]×σ | 89% | 2.14 | 22.6% | 498 | +0.66 |
| span, Bayes-only | 133% | 4.28 | 11.1% | 425 | +0.03 |

**Every config hurts, in-sample (the optimistic case), so no walk-forward needed.** Two
mechanisms: (1) laddering forces reserve-holding, which starves the frequent normal dips that
are the profit engine → lower return; (2) laddering *both* sleeves drives Bayes–OU correlation
from −0.01 to +0.40…+0.66, collapsing the decorrelation hedge (~0.7 Sharpe). Volume rose (186→
350–500) but profit fell — "more trades ≠ more profit" again. **The idle cash is the inherent
cost of patience + decorrelation, not recoverable dry powder.** Remaining structural lever that
doesn't fight either edge: breadth (more independent names).

## Laddering, part 2 — first-rung take-profit + rung weighting (user's idea)

The blended TP made the shallow rung break even, wasting the deep rungs. User's fix: exit the
whole stack at the *shallowest* rung's target (anchor + premium) so deep rungs book full margin.

- **first-rung TP rescued the "deep" ladder** (rung1 at k, deeper below): 79% → **113%** (+34pp).
  But it *hurts* shallow-rung1 geometries (span/wide → 77%/68%): a shallow rung1 sets too high an
  exit → holds too long → 50-day stop-outs → drawdown to 22%.
- **Weighting toward rung1=k** (`ladder_engine.py` now takes per-rung weights) climbs monotonically
  toward baseline: w=[.6,.25,.15]→130%, [.7,.2,.1]→135%, [.8,.15,.05]→141%; Bayes-only
  [.8,.15,.05]→**144%** (Sharpe 4.54, maxDD 11.3%, 302 trades).

**Definitive:** no ladder config beats the 150% baseline on return; it approaches from below and
maxes at baseline (= all weight at k = no laddering). Every dollar moved from depth-k to deeper
rungs is net drag — normal dips at k are the profit engine, deep dips too rare to compensate even
with the enhanced margin. Best case is ≈baseline return with slightly lower drawdown + more trades
(a marginally more conservative profile), not a profit gain. The only way deep-dip buying could
*add* return is extra capital (leverage/pooling), not reallocating a fixed pot — a different lever.

## Bayes-only ladder as a trade-volume option — all-ten (in-sample)

Config: ladder the Bayes sleeve only (OU single-bid), depths [k,1.5k,2k], weights [0.8,0.15,0.05],
first-rung TP. Motivation: more backtest trades → more statistical confidence in the edge.

| avg across 10 | Return | Sharpe | maxDD | Trades |
|---|---|---|---|---|
| Baseline | 222% | 4.20 | 17% | 258 |
| Bayes-only ladder | 208% | **4.46** | 16% | **388 (+50%)** |

Total trades 2,581 → 3,878 (+50%). **Unlike frequency-max (Sharpe 4.3→2.1), this raises trades
AND Sharpe** — the extra trades are the deep rungs bought cheaper and booked at the first-rung
target, so they're "good" volume. Cost is ~14pp absolute return (reserve-holding dilutes the
biggest winners); risk-adjusted it's neutral-to-better.

**Caveat:** Bayes–OU correlation rises on ~half the names (AVGO +0.44, PLTR/VRT/TSLA/SOFI +0.27..0.35;
NVDA/TSM stay <0) — laddering Bayes deeper makes it fire on big down-days when OU also fires, eroding
the hedge on those names. In-sample only; needs walk-forward before adoption. First genuinely
adoptable tweak (besides the uncapped-bid execution fix) *if* trade-count/robustness is valued
over absolute return.

## Bayes-only ladder — walk-forward (sub-period consistency, 30 slices)

Frozen params (nothing fit), so the test is consistency across 10 names × 3 time-thirds.
Three configs vs baseline single-bid (all Bayes-only, first-rung TP):

| Config | avg Δret/slice | avg ΔSharpe | trades× | Sharpe≥base | trades↑ | worst slice | avg corr |
|---|---|---|---|---|---|---|---|
| A [.80,.15,.05] d[k,1.5,2] | −4.8pp | +0.06 | 1.53× | 18/30 | 30/30 | −22.9pp | 0.19 |
| B [.85,.12,.03] d[k,1.5,2] | −3.4pp | +0.06 | 1.53× | 17/30 | 30/30 | −19.5pp | 0.19 |
| C [.80,.15,.05] d[k,1.3,1.7] | −2.9pp | +0.06 | 1.65× | 17/30 | 30/30 | −21.6pp | 0.19 |

**Survives OOS:** trade increase in 30/30 slices (+53–65%); Sharpe neutral (avg +0.06, ≥base
~57% of slices) — confirms it is NOT the frequency-max trap (more trades, no risk-adjusted
degradation). Return cost modest (−3 to −5pp/slice); **C (gentler depths) dominates** — most
trades, least cost. Costs: tail ~−20pp worst slice (B mildest); OU hedge softens to corr ~0.19
under any geometry (deep rungs fire on big down-days when OU also fires). **Adoptable if
trade-count/robustness is valued over peak absolute return; recommended config C.**
