"""
Does the ramp survive the half-sample blade, and is its edge bigger than the noise?

Two checks the headline table cannot answer:

1. NOISE. Profit as a function of the premium is not smooth -- a round trip either clears the
   target or it does not, so small premium changes reshuffle which trades happen at all. A
   dense flat-premium sweep measures how big that jitter is. Any ramp effect smaller than the
   jitter is not an effect.

2. OUT OF SAMPLE. Returns are read off the equity curve (held construction, mark to market)
   over the tested half only -- 2025-05-23 onward -- with the first half serving purely as
   warm-up. Nothing is fitted on the tested half.

Run:  python3 ramp_nvda_oos.py
"""
import sys

import numpy as np

import ramp_premium as R
from ramp_grid import RAMPS

STOCK = sys.argv[1] if len(sys.argv) > 1 else 'NVDA'


def window_return(res, dates, start, end=None):
    """Annualised return off the equity curve between two dates (held construction)."""
    eq = res.frames['equity']
    i0 = next(i for i, d in enumerate(dates) if d >= start)
    i1 = (len(dates) - 1) if end is None else max(i for i, d in enumerate(dates) if d <= end)
    yrs = (dates[i1] - dates[i0]).days / 365.25
    if eq[i0] <= 0 or yrs <= 0:
        return float('nan')
    return (eq[i1] / eq[i0]) ** (1 / yrs) - 1


def main():
    d, O, H, L, C = R.load_feed(STOCK)
    yrs = (d[-1] - d[0]).days / 365.25
    p, _ = R.load_params(STOCK, years=yrs)
    idx = R.build_index(STOCK)
    data = (d, O, H, L, C)
    mode = 'verified'

    print(f'=== 1. how noisy is the premium dimension? (flat scales, {mode} fills) ===')
    print('   full sample, then the two halves, annualised off the equity curve\n')
    print(f"{'scale':>7s} {'full':>8s} {'1st half':>9s} {'tested':>8s} {'trips':>6s}")
    fulls, tests = [], []
    for sc in np.arange(0.50, 1.201, 0.025):
        r = R.run(STOCK, ramp=None, mode=mode, p=p, data=data, idx=idx, prem_scale=float(sc))
        f = r.annual_return
        h1 = window_return(r, d, d[0], R.SPLIT)
        h2 = window_return(r, d, R.SPLIT)
        fulls.append(f); tests.append(h2)
        s = R.stats(r, p, len(d))
        print(f"{sc:7.3f} {100*f:7.2f}% {100*h1:8.2f}% {100*h2:7.2f}% {s['trips']:6d}")
    fulls = np.array(fulls); tests = np.array(tests)
    print(f"\n  full-sample spread over the scale grid: "
          f"{100*fulls.min():.1f}% .. {100*fulls.max():.1f}%  (sd {100*fulls.std():.2f}pp)")
    print(f"  tested-half spread over the scale grid: "
          f"{100*tests.min():.1f}% .. {100*tests.max():.1f}%  (sd {100*tests.std():.2f}pp)")
    print(f"  step-to-step |change| in tested half: median "
          f"{100*np.median(np.abs(np.diff(tests))):.2f}pp, max {100*np.abs(np.diff(tests)).max():.2f}pp")

    print(f'\n=== 2. ramps vs flat controls, scored on the tested half only ===')
    print(f'    (warm-up 2024-04-01 .. {R.SPLIT}; scored {R.SPLIT} .. {d[-1]})\n')
    for mode in ('verified', 'none'):
        print(f'-- fill rule: {mode} --')
        print(f"{'schedule':28s} {'1st half':>9s} {'tested':>8s} {'Δpp vs base':>12s} {'x̄mult':>7s}")
        base_t = None
        rows = []
        for label, ramp in RAMPS:
            r = R.run(STOCK, ramp=ramp, mode=mode, p=p, data=data, idx=idx)
            h1 = window_return(r, d, d[0], R.SPLIT)
            h2 = window_return(r, d, R.SPLIT)
            if base_t is None:
                base_t = h2
            ms = []
            if ramp is not None:
                for tr in (r.frames['t1'], r.frames['t2']):
                    for _e, _x, sess, _s, _q in R.trades_of(tr):
                        ms.append(ramp[min(sess - 1, len(ramp) - 1)])
            mm = float(np.mean(ms)) if ms else 1.0
            rows.append((label, h1, h2, h2 - base_t, mm))
        for sc in (0.9, 0.85, 0.8, 0.75, 0.7, 0.6):
            r = R.run(STOCK, ramp=None, mode=mode, p=p, data=data, idx=idx, prem_scale=sc)
            rows.append((f'flat x{sc:.2f}', window_return(r, d, d[0], R.SPLIT),
                         window_return(r, d, R.SPLIT),
                         window_return(r, d, R.SPLIT) - base_t, sc))
        for label, h1, h2, dl, mm in rows:
            print(f"{label:28s} {100*h1:8.2f}% {100*h2:7.2f}% {100*dl:+11.2f} {mm:7.3f}")
        print()


if __name__ == '__main__':
    main()
