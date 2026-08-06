"""
Does the SHAPE of the ramp do anything, once you control for the fact that it cuts the
average premium?

A ramp does two things at once: it lowers the premium on average, and it makes the premium
depend on how long the position has been held. Only the second is a new idea -- the first is
available for free by simply setting a lower fixed premium.

So: for every ramp, measure the average premium multiplier it actually collects, then compare
it against a FLAT premium at that same multiplier, interpolated off a dense flat sweep. If the
ramps land on the flat curve, the ramp is a premium cut wearing a costume.

Two further guards against reading noise as signal:
  * every schedule is also scored as a NEIGHBOURHOOD MEDIAN -- the median return over premium
    scalings of +/-10% -- which is the study's standing defence against a lucky point estimate;
  * everything is reported on the fitted half and the tested half separately. A real structural
    effect should show up on both. The OU-sigma correction did. A fitted one shows up on one.

Run:  python3 ramp_shape_test.py
"""
import sys

import numpy as np

import ramp_premium as R
from ramp_oos import window_return

STOCK = sys.argv[1] if len(sys.argv) > 1 else 'NVDA'
MODE = 'verified'

SHAPES = [
    ('fixed',                    None),
    ('0.75 / 1.0',               (0.75, 1.0)),
    ('0.50 / 1.0',               (0.50, 1.0)),
    ('0.50 / 0.75 / 1.0',        (0.50, 0.75, 1.00)),
    ('0.60 / 0.80 / 1.0',        (0.60, 0.80, 1.00)),
    ('0.40 / 0.70 / 1.0',        (0.40, 0.70, 1.00)),
    ('0.25 / 0.50 / 0.75 / 1.0', (0.25, 0.50, 0.75, 1.00)),
    ('0.50 / 0.65 / 0.80 / 1.0', (0.50, 0.65, 0.80, 1.00)),
    ('0.30 / 1.0',               (0.30, 1.0)),
    ('0.65 / 0.85 / 1.0',        (0.65, 0.85, 1.00)),
    ('0.55 / 0.70 / 0.85 / 1.0', (0.55, 0.70, 0.85, 1.00)),
    ('0.80 / 0.90 / 1.0',        (0.80, 0.90, 1.00)),
    ('0.70 / 1.0 (2-step)',      (0.70, 1.00)),
    ('rising 1.0/1.1/1.2',       (1.00, 1.10, 1.20)),   # the OPPOSITE ramp, as a null
    ('rising 1.0/1.25/1.5',      (1.00, 1.25, 1.50)),
]

PERTURB = (0.90, 0.95, 1.00, 1.05, 1.10)


def mean_mult(res, ramp):
    if ramp is None:
        return 1.0
    ms = []
    for tr in (res.frames['t1'], res.frames['t2']):
        for _e, _x, sess, _s, _q in R.trades_of(tr):
            ms.append(ramp[min(sess - 1, len(ramp) - 1)])
    return float(np.mean(ms)) if ms else 1.0


def main():
    d, O, H, L, C = R.load_feed(STOCK)
    yrs = (d[-1] - d[0]).days / 365.25
    p, _ = R.load_params(STOCK, years=yrs)
    idx = R.build_index(STOCK)
    data = (d, O, H, L, C)

    # ---- dense flat reference curve -------------------------------------------------
    grid = np.arange(0.30, 1.301, 0.02)
    flat_full, flat_h1, flat_h2 = [], [], []
    for sc in grid:
        r = R.run(STOCK, ramp=None, mode=MODE, p=p, data=data, idx=idx, prem_scale=float(sc))
        flat_full.append(r.annual_return)
        flat_h1.append(window_return(r, d, d[0], R.SPLIT))
        flat_h2.append(window_return(r, d, R.SPLIT))
    flat_full = np.array(flat_full); flat_h1 = np.array(flat_h1); flat_h2 = np.array(flat_h2)

    def interp(curve, x):
        return float(np.interp(x, grid, curve))

    print(f'=== ramps vs a flat premium at the SAME average multiplier ({MODE} fills) ===\n')
    print(f"{'schedule':28s} {'x̄mult':>6s} | {'full':>7s} {'flat':>7s} {'Δ':>6s} | "
          f"{'1st half':>8s} {'flat':>7s} {'Δ':>6s} | {'tested':>7s} {'flat':>7s} {'Δ':>6s}")
    rows = []
    for label, ramp in SHAPES:
        r = R.run(STOCK, ramp=ramp, mode=MODE, p=p, data=data, idx=idx)
        mm = mean_mult(r, ramp)
        f, h1, h2 = r.annual_return, window_return(r, d, d[0], R.SPLIT), window_return(r, d, R.SPLIT)
        ff, f1, f2 = interp(flat_full, mm), interp(flat_h1, mm), interp(flat_h2, mm)
        rows.append((label, mm, f - ff, h1 - f1, h2 - f2))
        print(f"{label:28s} {mm:6.3f} | {100*f:6.2f}% {100*ff:6.2f}% {100*(f-ff):+5.2f} | "
              f"{100*h1:7.2f}% {100*f1:6.2f}% {100*(h1-f1):+5.2f} | "
              f"{100*h2:6.2f}% {100*f2:6.2f}% {100*(h2-f2):+5.2f}")

    adv = [r for r in rows if r[0] != 'fixed']
    for j, nm in ((2, 'full sample'), (3, 'fitted half'), (4, 'tested half')):
        v = np.array([a[j] for a in adv])
        print(f"\n  shape advantage over matched flat, {nm}: median {100*np.median(v):+.2f}pp, "
              f"mean {100*v.mean():+.2f}pp, {sum(1 for x in v if x > 0)}/{len(v)} positive")

    # ---- neighbourhood medians ------------------------------------------------------
    print(f'\n=== neighbourhood medians (median over premium scalings {PERTURB}) ===\n')
    print(f"{'schedule':28s} {'full':>8s} {'1st half':>9s} {'tested':>8s}")
    base = None
    for label, ramp in SHAPES:
        fs, h1s, h2s = [], [], []
        for sc in PERTURB:
            r = R.run(STOCK, ramp=ramp, mode=MODE, p=p, data=data, idx=idx, prem_scale=sc)
            fs.append(r.annual_return)
            h1s.append(window_return(r, d, d[0], R.SPLIT))
            h2s.append(window_return(r, d, R.SPLIT))
        f, h1, h2 = np.median(fs), np.median(h1s), np.median(h2s)
        if base is None:
            base = (f, h1, h2)
        print(f"{label:28s} {100*f:7.2f}% {100*h1:8.2f}% {100*h2:7.2f}%"
              f"   ({100*(f-base[0]):+5.2f} / {100*(h1-base[1]):+5.2f} / {100*(h2-base[2]):+5.2f})")


if __name__ == '__main__':
    main()
