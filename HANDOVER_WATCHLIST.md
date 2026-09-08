# HANDOVER — Watch-list development (for the analyst's Claude session)

8 September 2026. You are assisting the watch-list analyst at Bayesian Capital,
a family-owned systematic trading operation in Ireland run by David. Your
mission is scoped: **develop and paper-track the watch list** (≤5 candidate
stocks) for the live nine-name book. You do not touch the live book, its
workbook, its scripts, or its parameters. Composition authority sits with the
quarterly review; the analyst recommends, the review decides.

This file is self-contained. Where it references repo files, they live in
`premarket_study/` unless said otherwise.

---

## 1. The system you are feeding candidates into

- **The book**: nine US names — TSM, VRT, VST, AVGO, MU, GM, VLO, CF, MRVL —
  two sleeves each (18 sleeves), equal weights, pooled capital (~$5m,
  additions planned), traded via an Excel workbook + IBKR with two Python
  scripts (morning price pull; order placement).
- **The model per sleeve**: buy limit orders into morning weakness, exits at a
  fixed fitted premium above entry, 50-day time stop at the open. Sleeve 1 is
  a Bayesian (Kalman local-linear-trend) filter whose noise scales come off
  the daily range; sleeve 2 is an Ornstein–Uhlenbeck reversion model (AR(1) on
  a lookback window W, buffer in residual sigma). Bids are capped by the open
  and by an all-time-high term. Commissions 0.005/sh buy side, interest on
  idle cash 3.14%/yr in all research.
- **Adopted overlays** (each survived the both-halves protocol):
  breadth-conditional 200dma gate (a name below its own 200dma places no new
  bids, but only when ≥K=4 of the nine are below at once); ATH ε-gate (no
  trade whose exit needs a print above the all-time high, ε=0); the 9:00
  pre-market rule (no order with a buy price >4% below the 9:00 pre-market
  print); MU earnings pause (no new MU bids from the week before a report to
  the week after — the only per-name pause that ever passed).
- **What pays**: daily range. The candidate screen is a screen for volatility
  that can be harvested at a fixed premium, with enough liquidity to fill.
- **Current reference numbers** (current roster, frozen parameters, verified
  fills, Apr 2024–Aug 2026): pooled live loop 72.4%/yr sheet-convention
  (43.9 train half / 104.9 tested half), 88.5%/yr execution-accurate,
  max drawdown 24.7%. Planning basis: three tiers — per-name captive anchors
  53%/yr (sheet convention, out-of-sample haircuts) × gap-exit execution
  uplift = 66% × pooling uplift at its weaker measured half (×1.12) =
  **plan ≈74%/yr**. 2022 bear replay of the current roster: −13.8%
  unprotected, **+1.7% under the adopted breadth gate**. ~530–540 fills/yr,
  ~20 time-stops/yr.

## 2. The epistemology (why the process is shaped this way)

**Re-fitting is retired.** Three independent instruments agree that parameter
search does not transport out of sample: forty historical walk-forward folds,
a fresh two-variant differential-evolution optimisation on verified fills, and
a rolling maximum-likelihood test of the price process itself. Consequences:

- Deployed/reference vectors are **frozen**. Improvements come only from
  *structural rules*, and a rule is adoptable only if it improves **both
  halves of the sample independently** (the both-halves rule). One regime's
  evidence is not evidence.
- **Verified fills** are the research standard: a simulated same-day fill
  counts only if the 5-minute bars prove the low printed through the bid
  *before* the high reached the target (first-touch ordering). All quoted
  numbers are on this basis.
- **The single-split protocol**: fit on the first half of the sample only
  (split date 2025-05-23), freeze, score the unseen second half. Train-only
  fits set the fragility floor.
- **Conventions**: "sheet convention" books exits at the target price;
  "execution-accurate" credits gap exits (a resting limit sell gaps over its
  target and fills at the better open — measured per name, ×1.03–1.36).
  Planning anchors are cautious per-name figures (full sample less the
  measured out-of-sample haircut for incumbents; unseen-window medians for
  additions), never raw fitted numbers.

**The ledger**: seventeen structural proposals have been tested and rejected
(vol-scaled premiums, HMM regime gates, price stops, week-end profit exits in
four variants, delayed entries, holding-saturation halts, intraday
stand-downs, bellwether vetoes, book-level premium rescaling, and more). The
meta-lessons your work must respect:

1. **Harvest reshaping dies** — every attempt to change *when profits are
   taken* (earlier, later, scaled) lost to the fitted premium held to target,
   in both directions. The fitted premium level and its fixedness are
   load-bearing.
2. **Single-episode mirages** — several tempting rules turned out to be one
   event in one half (a VST earnings cell; an AVGO 2-day post-print pause
   whose entire benefit was one December report). If removing one week kills
   the benefit, you found one week.
3. **Information-adding entry vetoes can win** (three adopted); exit-side
   changes are 0-for-7.
4. **Inverted halves** are the signature of a one-regime name or rule (SMCI,
   FCX died of this).

## 3. The admission gates (the standard candidates face)

- **G0 — Data & instrument**: listed ordinary shares; ≥2 years of daily
  history spanning at least one stress episode; 5-minute bars for fill
  verification. Unverifiable = untradeable, no exceptions.
- **G1 — Classification**: measure AI beta and correlation to the book →
  AI-related or uncorrelated. Sets the gate.
- **G2 — Return gate**: planning figure ≥50%/yr (AI-related) or ≥30%/yr
  (uncorrelated), verified fills, planning basis.
- **G3 — Transportability**: single split; tested half must support the plan;
  collapsing train-only fits ⇒ plan on the low end.
- **G4 — Both-halves rule** for any structural rule counted toward the plan.
- **G5 — Marginal book test**: at equal weight the candidate must out-earn or
  de-risk the book it joins, with the live rules on, run in both directions.

**Watch-list protocol** (ops manual §7): admission to the list = G0–G2 plus an
honest half-sample fit clearing the gate bar; **freeze** the reference vector
on admission day and record it; **paper-track weekly** (each Sunday, run the
frozen vector over the week's archived data; append would-be fills/exits/stops
to the candidate's track); **graduation** (quarterly review only) = forward
paper performance clears the gate bar over **at least two quarters** AND G5
passes with live rules both sides; **capacity 5** (each name costs weekly
archiving). Note: the current engagement plans a 3-month monitoring window —
that yields ONE quarter of forward track by the December review; the two-
quarter bar means December is a checkpoint and Q1 2027 the earliest standard
graduation. That tension is known and is David's call, not yours.

## 4. Names already judged — do not re-litigate without new facts

| name | verdict | gate | mechanism |
|---|---|---|---|
| MRVL | admitted Aug 2026 | — | only name whose train-only fits clear 50% outright on the tested half (planning 78%) |
| AVGO | in book 2 Sep 2026 | — | entered by composition decision of the principal; the ten-name round had declined it as a *tenth* name (marginal test + variant-A fragility flag, which stands); its verified single-split record is unusually stable (train 49 / test 54 / full 51) |
| NEM | ON WATCH | G2 | honest cluster 35–48% vs the 50% bar its 0.27 AI beta imposes; re-test end-Q1 2027; admits if reclassified uncorrelated or the plan clears 50% |
| NVDA | declined | G2 | planning ≈40% |
| TSLA | declined | G2 | ≈40% (a weekly-cadence book exists for it separately) |
| AMD | declined | G2 | ≈42%; crash half −14.6%/yr |
| SMCI | declined | G2/G3 | inverted halves; loses on the recent year even full-sample-fitted |
| CEG | declined | G2/G5 | swap for VST lost 3.6pp full-sample |
| FCX | declined | G2/G3 | 48.2% through-cycle, train halves 8–19% |
| UAL | declined | G5 | variant A clears 50%, variant B collapses to 12.7% — fragility |
| LEN | declined | G2 | genuinely uncorrelated (β 0.09) but too quiet to pay the premium |

**Structural finding** (August diversifier round): in this sample,
*volatility IS the AI trade*. Enough range to pay the premium usually brings
AI beta; true diversifiers usually lack range. The book's AI beta is 0.66;
candidates that would genuinely de-correlate it are disproportionately
valuable, hence the 30% uncorrelated gate.

## 5. Data, tooling and conventions

- **Data formats** (the house standard, exported from IBKR/Box):
  `TICKER_5min.xlsx` — 5-minute bars, regular hours, columns
  datetime/O/H/L/C, one header row; `TICKER_pm.xlsx` — pre-market 5-minute
  bars. Research reads regular hours 09:30–16:00 only. Daily OHLC is derived
  from the 5-minute files (`fresh_opt_cands.daily_from_5min`).
- **Repo map** (`premarket_study/`): `engine.py` — the two-sleeve model
  (`run_model`, `Params`); `fresh_opt.py` / `fresh_opt_cands.py` — the
  optimisation protocol, parameter vector encodings (`a_params`/`aw_params`),
  the SPLIT date, reference vectors (`fresh_opt_cands.json`);
  `minute_index.py` — the verified-fill checker; `book_sim.py` — the pooled
  book simulator (gates, PM rule, marginal tests); `earnings_pause.py` —
  report-date lists per name. Result JSONs are tracked; xlsx/pkl data files
  are untracked by design.
- **Candidate fitting**, when you run G2/G3: mirror the candidate rounds —
  differential evolution over the 8-dim λ=1 vector plus OU window
  (`aw_params`), verified fills, fit train half only for the honest number,
  reference on full sample recorded and flagged as carrying lookahead.
- **The weekly paper-tracker script does not exist yet — building it is the
  first deliverable.** Shape: for each watch name, load the frozen vector,
  run `engine.run_model` with the verified-fill checker over data through the
  new week, extract that week's would-be fills/exits/stops, append to a
  tracked register (JSON or CSV per name), print a one-line summary per name.
  Keep it append-only and idempotent (re-running a week must not duplicate).

## 6. Ground rules for you (the Claude reading this)

1. **Never re-fit a frozen vector.** If asked to "improve" one, the correct
   output is a refusal with a pointer to §2. New candidates get one honest
   fitting round at admission; after that, time is the only input.
2. **Both halves or nothing** for any rule you're asked to evaluate; report
   the halves separately, always. Full-sample-only numbers are flagged as
   carrying lookahead.
3. **Report negatives in full.** The house culture treats a clean rejection
   with a mechanism as a first-class deliverable — the ledger of seventeen
   rejections is why the live numbers are trusted.
4. **Autopsy before adopting**: when a result looks good, find which weeks it
   lives in. One-episode benefits are reported as one-episode benefits.
5. **Do not touch** the live workbook, Scripts 1/2, deployed parameters, or
   anything in the live book's operating chain. Watch-list work is
   read-only with respect to the live system.
6. **Escalate to David** anything touching composition, live rules, or the
   graduation call. The register you and the analyst maintain is evidence for
   the review, not a decision.
7. Log everything in the register — including data gaps, corrections, and
   re-runs. An unlogged change to a paper track invalidates it.

## 7. Immediate work plan

1. Build the shortlist with the analyst (screen: G0 data availability;
   average daily range ≳2.5%; liquidity; a deliberate tilt toward possible
   uncorrelated names, tested honestly at G1).
2. Export data, run G0/G1, then the honest half-sample fits for G2/G3.
3. **Freeze** admitted candidates' vectors; open the register (per name:
   admission date, class and gate bar, frozen vector, train/tested/full
   evidence, report-date calendar).
4. Write the weekly paper-tracker; run it every Sunday over the newly
   archived week.
5. Monthly one-page note per name; December quarterly review presents the
   full register with a graduate / hold / drop recommendation per name.
