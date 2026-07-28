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
