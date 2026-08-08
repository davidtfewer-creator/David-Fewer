"""
Where exactly is the cliff in RKLB's take-profit premium, and where is it safe to sit?

The full-sample constrained fit produced a premium of 2.258% that returns 217.3% over the
unseen span. Nudging it up ten percent -- to 2.484%, a change of 23 basis points -- collapses
that to 79.3%, while nudging it down ten percent holds at 172.3%. Five of the six policy
parameters are flat under the same test; this one is not. A three-point check locates a cliff
but cannot say how wide it is, how far the flat ground extends, or whether the fitted value is
sitting on a genuine plateau or on a spike that happens to be tall.

So the premium is swept finely with every other parameter held at the fitted vector. Nothing is
re-fitted: each point is one evaluation of the same model, so differences are attributable to
the premium alone.

Three things are read off it:

  MECHANISM   trades and stop-outs at each premium. If the collapse is a threshold effect --
              targets that used to clear now failing, positions running to the 50-day stop --
              then stops should rise sharply exactly where return falls. If stops are flat
              through the cliff, the explanation is something else and the scan is the wrong
              diagnostic.
  WIDTH       how much premium either side of a candidate value keeps the return within a
              modest band. A value is only deployable if the ground around it is flat, because
              the live stock will not reproduce the backtest exactly.
  HONESTY     the unseen span is scored, not the full sample, because the full sample is
              in-sample for this vector and its curve would flatter every point equally.

The cap constraint is preserved at every step: peak_cap is lifted to meet the premium wherever
the swept value would exceed it, so no point in the scan is quietly buying back the
all-time-high breach that motivated the whole exercise. Where that lift happens is reported.

Run:  python3 rklb_premium_scan.py
"""
import numpy as np

import admit_candidates as A
import pair_planned as PP
import planned_return as P
import ramp_premium as R
from engine import Params, run_model
from optimise_candidates import mp

NAME = 'RKLB'
CAPITAL = 1_000_000
SLICE, FOLDS = 100, 3

# Full-sample constrained fit, from rklb_deploy.py (deterministic, seed=42).
PROPOSED = [0.66172, 0.20087, 0.17327, 0.30975, 0.02258, 0.03375,
            0.46156, 0.03335, 0.08122, 117.25389]
LO, HI, STEP = 0.014, 0.032, 0.0005


def evaluate(bars, chk, vec, t, lo, hi):
    d, O, H, L, C = bars
    r = run_model(d, O, H, L, C, mp(vec, t), ou_sigma='resid', same_day_exit=chk, collect=True)
    eq = r.frames['equity']
    yrs = (d[hi] - d[lo]).days / 365.25
    ret = (eq[hi] / eq[lo]) ** (1 / yrs) - 1 if eq[lo] > 0 else float('nan')
    br, n = PP.breach_share(bars, chk, vec, t, lo, hi)
    # Result.stop_loss_exits counts the whole sample; the scan needs the scored window only,
    # so it is recounted from the frames on the same test the engine uses: a sale booked
    # below the target is a stop.
    stops = 0
    for s in ('t1', 't2'):
        f = r.frames[s]
        stops += sum(1 for i in range(lo, hi + 1)
                     if f['AD'][i] == 1 and f['AC'][i] is not None
                     and f['AB'][i] is not None and f['AC'][i] < f['AB'][i])
    peak, dd = -1e30, 0.0
    for e in eq[lo:hi + 1]:
        peak = max(peak, e)
        dd = max(dd, (peak - e) / peak) if peak > 0 else dd
    return ret, n, stops, dd, br


def main():
    A.BOUNDS = PP.STD
    bars, _dv, idx = A.five_min(P.PATHS[NAME])
    d, O, H, L, C = bars
    chk = R.make_checker(idx, d, O)
    n = len(d)
    iS = n - FOLDS * SLICE
    t0 = Params(capital=CAPITAL, years=1.0)

    grid = np.arange(LO, HI + 1e-9, STEP)
    print(f'sweeping premium {100*LO:.2f}% to {100*HI:.2f}% in {100*STEP:.2f}% steps, '
          f'{len(grid)} points, everything else held\n', flush=True)

    print(f"{'premium':>8s} {'cap used':>9s} {'UNSEEN ret':>11s} {'trades':>7s} "
          f"{'stops':>6s} {'maxDD':>7s} {'breach':>7s}   profile")
    rows = []
    best = None
    for x in grid:
        v = PP.repair([*PROPOSED[:4], float(x), *PROPOSED[5:]])
        ret, tr, st, dd, br = evaluate(bars, chk, v, t0, iS, n - 1)
        rows.append(dict(prem=float(x), cap=v[5], ret=ret, tr=tr, st=st, dd=dd, br=br))
        best = max(best or ret, ret)
    for r in rows:
        bar = '#' * int(max(0, min(40, 40 * r['ret'] / max(best, 1e-9))))
        mark = '  <- fitted' if abs(r['prem'] - PROPOSED[4]) < STEP / 2 else ''
        print(f"{100*r['prem']:7.2f}% {100*r['cap']:8.2f}% {100*r['ret']:10.1f}% "
              f"{r['tr']:7d} {r['st']:6d} {100*r['dd']:6.1f}% {100*r['br']:6.1f}%   "
              f"{bar}{mark}")

    # ---- plateau search --------------------------------------------------------
    print('\n\n=== where is the flat ground? ===')
    print('    for each candidate, the worst return within +/-15% of it (about +/-35bp)\n')
    print(f"{'premium':>8s} {'return':>10s} {'worst nearby':>13s} {'give-up':>9s} "
          f"{'window':>18s}")
    scored = []
    for i, r in enumerate(rows):
        lo_p, hi_p = r['prem'] * 0.85, r['prem'] * 1.15
        near = [q for q in rows if lo_p - 1e-9 <= q['prem'] <= hi_p + 1e-9]
        if len(near) < 3:
            continue
        worst = min(q['ret'] for q in near)
        scored.append((worst, r, near))
        print(f"{100*r['prem']:7.2f}% {100*r['ret']:9.1f}% {100*worst:12.1f}% "
              f"{100*(r['ret']-worst):8.1f}pp "
              f"{100*near[0]['prem']:7.2f}-{100*near[-1]['prem']:.2f}%")

    scored.sort(key=lambda t: -t[0])
    worst, pick, near = scored[0]
    fitted = next(r for r in rows if abs(r['prem'] - PROPOSED[4]) < STEP / 2)
    fw = min(q['ret'] for q in rows
             if PROPOSED[4] * 0.85 - 1e-9 <= q['prem'] <= PROPOSED[4] * 1.15 + 1e-9)

    print('\n\n=== recommendation ===\n')
    print(f"  fitted premium      {100*PROPOSED[4]:.3f}%   return {100*fitted['ret']:.1f}%   "
          f"worst nearby {100*fw:.1f}%   give-up {100*(fitted['ret']-fw):.1f}pp")
    print(f"  most robust premium {100*pick['prem']:.3f}%   return {100*pick['ret']:.1f}%   "
          f"worst nearby {100*worst:.1f}%   give-up {100*(pick['ret']-worst):.1f}pp")
    print(f"\n  choosing the robust value costs "
          f"{100*(fitted['ret']-pick['ret']):+.1f}pp of backtested return and buys "
          f"{100*(worst-fw):+.1f}pp\n  of protection against being slightly wrong about "
          f"the premium.")
    print(f"\n  trades {fitted['tr']} -> {pick['tr']}, stops {fitted['st']} -> {pick['st']}, "
          f"drawdown {100*fitted['dd']:.1f}% -> {100*pick['dd']:.1f}%, "
          f"breach {100*pick['br']:.1f}%")


if __name__ == '__main__':
    main()
