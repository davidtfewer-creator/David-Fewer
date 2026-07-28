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

## Caveats (per the project's recurring principle)

This is **one stock, in-sample, full history**. Change (A) is a live-fidelity improvement
with *frozen* parameters (not a fit), which is the robust kind — but before trusting it:
extend to the other names, and ideally run a true warm-started walk-forward.
