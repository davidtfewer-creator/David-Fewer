"""
Sub-period consistency check for the open-cap proxy finding.

Parameters are FROZEN (no fitting here), so this isn't a walk-forward over a fit — it
asks whether the live signal improvement (PM-VWAP vs prev-close as the O_t cap) is
consistent across time, or an artefact of one lucky stretch. We slice the continuous
equity curve into segments and compare segment return / Sharpe / maxDD per config.
"""
import csv, math
from datetime import date
from engine import Params, run_model
from experiment_nvda import load, prev_close_series


def seg_metrics(equity, lo, hi):
    seg = equity[lo:hi + 1]
    ret = seg[-1] / seg[0] - 1
    rets = [seg[i] / seg[i - 1] - 1 for i in range(1, len(seg)) if seg[i - 1] > 0]
    if len(rets) > 1:
        mu = sum(rets) / len(rets)
        sd = math.sqrt(sum((x - mu) ** 2 for x in rets) / (len(rets) - 1))
        sharpe = mu / sd * math.sqrt(252) if sd > 0 else 0.0
    else:
        sharpe = 0.0
    peak = -1e30; dd = 0.0
    for e in seg:
        peak = max(peak, e)
        dd = max(dd, (peak - e) / peak if peak > 0 else 0)
    return ret, sharpe, dd


if __name__ == '__main__':
    d = load('nvda_joined.csv')
    dates, O, H, L, C = d['dates'], d['O'], d['H'], d['L'], d['C']
    N = len(C)
    prevC = prev_close_series(C)
    pmV = d['pmV']
    p = Params()

    configs = {
        'oracle (true open)':        dict(),
        'live prev-close cap':       dict(open_cap=prevC),
        'PM-VWAP cap only (A)':      dict(open_cap=pmV),
        'PM-VWAP cap+anchor (A+B)':  dict(open_cap=pmV, ou_anchor=pmV),
    }
    eq = {name: run_model(dates, O, H, L, C, p, collect=True, **kw).frames['equity']
          for name, kw in configs.items()}

    # quarterly segments by calendar quarter
    segs = []
    start = 0
    for i in range(1, N):
        q  = (dates[i].year, (dates[i].month - 1) // 3)
        q0 = (dates[i - 1].year, (dates[i - 1].month - 1) // 3)
        if q != q0:
            segs.append((start, i - 1)); start = i
    segs.append((start, N - 1))

    print(f'NVDA sub-period check  ({N} days, {len(segs)} quarters)\n')
    hdr = f'{"quarter":10s}' + ''.join(f'{n.split(" (")[0][:16]:>18s}' for n in configs)
    print(hdr); print('-' * len(hdr))

    wins_A = 0; wins_AB = 0
    for lo, hi in segs:
        label = f'{dates[lo].year}Q{(dates[lo].month-1)//3+1}'
        rets = {}
        cells = []
        for name in configs:
            r, sh, dd = seg_metrics(eq[name], lo, hi)
            rets[name] = r
            cells.append(f'{r*100:>7.1f}%/{sh:>4.1f}')
        print(f'{label:10s}' + ''.join(f'{c:>18s}' for c in cells))
        if rets['PM-VWAP cap only (A)'] > rets['live prev-close cap']: wins_A += 1
        if rets['PM-VWAP cap+anchor (A+B)'] > rets['live prev-close cap']: wins_AB += 1

    print('\n(cells show segment return% / segment Sharpe)')
    print(f'\nAgainst the live prev-close baseline, per quarter:')
    print(f'  PM-VWAP cap only (A):     beats prev-close in {wins_A}/{len(segs)} quarters')
    print(f'  PM-VWAP cap+anchor (A+B): beats prev-close in {wins_AB}/{len(segs)} quarters')
