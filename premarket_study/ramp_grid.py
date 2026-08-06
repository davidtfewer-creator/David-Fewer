"""
NVDA: ramped take-profit vs the fixed premium, with flat-premium controls.

Run:  python3 ramp_nvda.py
"""
import sys

import numpy as np

import ramp_premium as R

STOCK = sys.argv[1] if len(sys.argv) > 1 else 'NVDA'

RAMPS = [
    ('fixed (baseline)',      None),
    ('0.75 / 1.0',            (0.75, 1.0)),
    ('0.50 / 1.0',            (0.50, 1.0)),
    ('0.50 / 0.75 / 1.0',     (0.50, 0.75, 1.00)),   # the proposal
    ('0.60 / 0.80 / 1.0',     (0.60, 0.80, 1.00)),
    ('0.40 / 0.70 / 1.0',     (0.40, 0.70, 1.00)),
    ('0.25 / 0.50 / 0.75 / 1.0', (0.25, 0.50, 0.75, 1.00)),
    ('0.50 / 0.65 / 0.80 / 1.0', (0.50, 0.65, 0.80, 1.00)),
    ('0.30 / 1.0',            (0.30, 1.0)),
]

FLATS = [1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.6, 0.5]


def mean_mult(res, ramp):
    """Average premium multiplier actually collected at exit."""
    if ramp is None:
        return 1.0
    ms = []
    for tr in (res.frames['t1'], res.frames['t2']):
        for _e, _x, sess, _s, _p in R.trades_of(tr):
            ms.append(ramp[min(sess - 1, len(ramp) - 1)])
    return float(np.mean(ms)) if ms else float('nan')


def main():
    d, O, H, L, C = R.load_feed(STOCK)
    yrs = (d[-1] - d[0]).days / 365.25
    p, cached = R.load_params(STOCK, years=yrs)
    idx = R.build_index(STOCK)
    data = (d, O, H, L, C)
    n = len(d)

    for mode in ('verified', 'sheet', 'none'):
        print(f'\n=== {STOCK}  fill rule: {mode}   ({n} sessions, {yrs:.2f}y, '
              f'premium {p.premium:.4%} Bayes / {p.ou_prem:.4%} OU) ===')
        print(f"{'schedule':28s} {'profit $':>13s} {'annual':>8s} {'Δpp':>7s} "
              f"{'trips':>6s} {'1-day':>6s} {'medhold':>8s} {'cash%':>6s} {'x̄mult':>6s}")
        base = None
        for label, ramp in RAMPS:
            r = R.run(STOCK, ramp=ramp, mode=mode, p=p, data=data, idx=idx)
            s = R.stats(r, p, n)
            if base is None:
                base = r.annual_return
            print(f"{label:28s} {r.profit:13,.0f} {100*r.annual_return:7.2f}% "
                  f"{100*(r.annual_return-base):+6.2f} {s['trips']:6d} {s['same_day']:6d} "
                  f"{s['med_hold']:8.0f} {s['cash_pct']:5.1f}% {mean_mult(r, ramp):6.3f}")

        print(f"  -- control: FLAT premium scaled (no ramp) --")
        for sc in FLATS:
            r = R.run(STOCK, ramp=None, mode=mode, p=p, data=data, idx=idx, prem_scale=sc)
            s = R.stats(r, p, n)
            print(f"{'flat x'+format(sc,'.2f'):28s} {r.profit:13,.0f} {100*r.annual_return:7.2f}% "
                  f"{100*(r.annual_return-base):+6.2f} {s['trips']:6d} {s['same_day']:6d} "
                  f"{s['med_hold']:8.0f} {s['cash_pct']:5.1f}% {sc:6.3f}")


if __name__ == '__main__':
    main()
