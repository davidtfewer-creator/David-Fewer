"""
Calibrate the bias from using 5-minute instead of 1-minute bars.

Within a single bar we cannot order the low and the high, so a trade whose fill AND target fall
in the same bar is counted as a real same-day exit. A coarser bar widens that benefit-of-the-
doubt window, so 5-minute data should OVERSTATE the true fill rate.

Measure it: downsample NVDA's 1-minute bars to 5-minute, re-run the verification with both, and
compare fill rates and resulting returns. The gap is the discount to apply to 5-minute results
for other names.
"""
import numpy as np
from stop_sweep import load_book
from engine import run_model
from minute_engine import build_index

data, params, cached = load_book()
dts, O, H, L, C = data['NVDA']
P0 = params['NVDA']


def coarsen(idx1, k):
    """Rebuild the (lows, suffix_max_high) index at k-minute resolution."""
    out = {}
    for d, (lows, suffix) in idx1.items():
        # coarse low  = min of the fine lows in the bucket
        # coarse suffix-max-high = suffix[first minute of bucket], since suffix[i]=max(highs[i:])
        # already equals the max over everything from that minute onward.
        n = len(lows)
        m = (n + k - 1) // k
        lo_c = np.array([lows[i*k:(i+1)*k].min() for i in range(m)])
        # suffix max of highs at coarse resolution = suffix of the first minute in each bucket
        su_c = np.array([suffix[i*k] for i in range(m)])
        out[d] = (lo_c, su_c)
    return out


def make_check(idx):
    def check(i, bid, target):
        ent = idx.get(dts[i])
        if ent is None:
            return bid >= O[i] - 1e-9
        lows, suffix = ent
        hit = lows <= bid + 1e-9
        if not hit.any():
            return False
        j = int(np.argmax(hit))
        return bool(suffix[j] >= target - 1e-9)
    return check


if __name__ == '__main__':
    idx1 = build_index()
    print(f'1-minute index: {len(idx1)} sessions')
    results = {}
    for k, label in ((1, '1-minute (truth)'), (5, '5-minute'), (15, '15-minute')):
        idx = idx1 if k == 1 else coarsen(idx1, k)
        r = run_model(dts, O, H, L, C, P0, same_day_exit=make_check(idx))
        results[k] = r
        print(f'{label:20s} ann {r.annual_return*100:5.0f}%  buys {r.total_buys:3d}  '
              f'Sharpe {r.sharpe:.2f}  maxDD {r.max_drawdown*100:.0f}%')
    a1 = results[1].annual_return; a5 = results[5].annual_return
    print(f'\n5-minute overstates annual return by {(a5-a1)*100:+.1f}pp '
          f'({(1+a5)/(1+a1)-1:+.1%} on a growth basis)')
