"""
Is old data actually irrelevant? Test the premise instead of assuming it.

The objection to walk-forward is that these names trade a theme moving through step changes, so
what happened 24 months ago says little about today. That is an empirical claim and it can be
checked rather than argued: measure the strategy's edge quarter by quarter and see whether it
is stable.

The edge measured here is EXPOSURE-MATCHED -- the model's return in the quarter minus what the
same time-in-market would have earned holding the stock, with idle cash at the IBKR rate:

    edge = r_model - [ exposure * r_buyhold + (1 - exposure) * 0.0314 ]

That subtraction is what makes the test regime-robust. A raw return series confounds the rules
with the market and will of course look unstable when the market changes -- which would
"confirm" the objection without evidence. The exposure-matched edge asks only whether the entry
and exit rules beat a coin flip with the same market participation, and that question has the
same meaning in every regime.

If the edge is roughly stationary across quarters, older data is informative about the rules
even though it is uninformative about the level of returns, and the half-sample blade keeps its
force. If the edge trends or flips sign, the objection is right and only recent data should
count -- at the cost of having far less of it.

Run:  python3 edge_stability.py
"""
import numpy as np

import ramp_premium as R
from engine import Params

ALL_NAMES = ('NVDA', 'AVGO', 'TSM', 'RKLB', 'VST', 'VRT', 'TSLA', 'PLTR', 'SOFI', 'SPOT')
HIGH = (0.040, 0.045, 0.050, 0.060)
RF = 0.0314


def quarters(dates):
    out, cur, key = [], [], None
    for i, d in enumerate(dates):
        k = (d.year, (d.month - 1) // 3)
        if key is None:
            key = k
        if k != key:
            out.append((key, cur))
            cur, key = [], k
        cur.append(i)
    out.append((key, cur))
    return [(k, v) for k, v in out if len(v) >= 20]


def main():
    per_q = {}
    for stock in ALL_NAMES:
        d, O, H, L, C = R.load_feed(stock)
        args = (d, O, H, L, C)
        p, _ = R.load_params(stock, years=(d[-1] - d[0]).days / 365.25)
        for label, band, stop in (('deployed', None, 50), ('4-6%/200d', HIGH, 200)):
            prems = [None] if band is None else list(band)
            acc = {}
            for prem in prems:
                q = Params(**{**p.__dict__, 'stop_days': stop}) if prem is None else \
                    Params(**{**p.__dict__, 'premium': prem, 'ou_prem': prem, 'stop_days': stop})
                r = R.run(stock, ramp=None, mode='at_open', p=q, data=args, idx=None)
                eq = r.frames['equity']
                t1, t2 = r.frames['t1'], r.frames['t2']
                for key, ix in quarters(d):
                    i0, i1 = ix[0], ix[-1]
                    if eq[i0] <= 0 or C[i0] <= 0:
                        continue
                    rm = eq[i1] / eq[i0] - 1
                    rb = C[i1] / C[i0] - 1
                    ex = sum(t1['AE'][i] + t2['AE'][i] for i in ix) / (2 * len(ix))
                    yrs = (d[i1] - d[i0]).days / 365.25
                    bench = ex * rb + (1 - ex) * RF * yrs
                    acc.setdefault(key, []).append(rm - bench)
            for key, v in acc.items():
                per_q.setdefault((label, key), {})[stock] = float(np.median(v))

    for label in ('deployed', '4-6%/200d'):
        keys = sorted({k for (lb, k) in per_q if lb == label})
        print(f'\n=== quarterly exposure-matched edge, pooled across ten names: {label} ===\n')
        print(f"{'quarter':9s} {'median':>8s} {'mean':>8s} {'names >0':>9s}   {'per-name spread':>18s}")
        meds = []
        for k in keys:
            v = np.array(list(per_q[(label, k)].values()))
            meds.append(float(np.median(v)))
            print(f"{k[0]}Q{k[1]+1:<5d} {100*np.median(v):+7.2f}% {100*v.mean():+7.2f}% "
                  f"{sum(1 for x in v if x > 0):5d}/10   "
                  f"{100*v.min():+7.1f} .. {100*v.max():+7.1f}")
        m = np.array(meds)
        t = np.arange(len(m))
        slope = np.polyfit(t, m, 1)[0] if len(m) > 2 else float('nan')
        print(f"\n  quarters with a positive median edge: {sum(1 for x in m if x > 0)}/{len(m)}")
        print(f"  median across quarters: {100*np.median(m):+.2f}%, "
              f"sd {100*m.std():.2f}pp")
        print(f"  trend in the median edge: {100*slope:+.2f}pp per quarter "
              f"({'decaying' if slope < 0 else 'improving'})")
        first, second = m[:len(m)//2], m[len(m)//2:]
        print(f"  first half of quarters {100*np.median(first):+.2f}%  vs  "
              f"second half {100*np.median(second):+.2f}%")


if __name__ == '__main__':
    main()
