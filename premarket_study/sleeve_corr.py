"""
Why 0.83 and not 0.09? Decomposing the Bayes-OU correlation discrepancy.

The white paper reports a Bayes-OU return correlation of 0.09 -- the basis of the claim that the
OU sleeve is a genuine hedge. Measured on the live book with the corrected sleeve I get 0.83 to
0.87. Both cannot be describing the same thing.

Three candidate explanations, all testable:

  1. CONFIGURATION. The 0.09 was measured on NVDA alone at W=120, k=0.5, with the superseded
     sigma. The deployed names run W=77-122 with different buffers.
  2. THE SIGMA CORRECTION. Residual sigma is a third of the old scale, so the OU bid sits much
     closer to the market and fills far more often. Two sleeves that are both long more of the
     time must correlate more, whatever their signals say.
  3. CASH DAYS. A sleeve in cash returns ~0. If a sleeve is rarely invested, its return series is
     mostly zeros and correlates with nothing -- which flatters the hedge without any economic
     independence behind it.

Measured per name: the correlation on all days, the correlation on days when BOTH sleeves are
actually holding stock, and how often each state occurs. If (3) is the story, the all-days
correlation will be low and the both-invested correlation high.
"""
import copy, statistics
import numpy as np
from engine import run_model
from ss_sleeve import DATA, PARAMS, BOOK, BUF_RESID, chk


def tranche_equity(fr, key, C):
    t = fr[key]
    eq = np.array([t['AA'][i]*C[i] if t['AE'][i] == 1 else t['Y'][i] for i in range(len(C))],
                  dtype=float)
    hold = np.array([1 if t['AE'][i] == 1 else 0 for i in range(len(C))])
    return eq, hold


def measure(s, mode, W=None, buf=None):
    dts, O, H, L, C = DATA[s]
    p = copy.copy(PARAMS[s]); p.bayes_pct = 0.5
    if W is not None: p.ou_W = W
    p.ou_buf_k = buf if buf is not None else (BUF_RESID.get(s, p.ou_buf_k) if mode == 'resid'
                                              else p.ou_buf_k)
    fr = run_model(dts, O, H, L, C, p, ou_sigma=mode, collect=True,
                   same_day_exit=chk(s)).frames
    e1, h1 = tranche_equity(fr, 't1', C)
    e2, h2 = tranche_equity(fr, 't2', C)
    r1 = e1[1:]/e1[:-1]-1; r2 = e2[1:]/e2[:-1]-1
    ok = np.isfinite(r1) & np.isfinite(r2)
    both = ok & (h1[1:] == 1) & (h2[1:] == 1)
    c_all = float(np.corrcoef(r1[ok], r2[ok])[0, 1]) if ok.sum() > 3 else float('nan')
    c_both = float(np.corrcoef(r1[both], r2[both])[0, 1]) if both.sum() > 3 else float('nan')
    return dict(all=c_all, both=c_both, n_both=int(both.sum()), n=int(ok.sum()),
                inv1=float((h1 == 1).mean()), inv2=float((h2 == 1).mean()),
                overlap=float(both.sum()/ok.sum()))


if __name__ == '__main__':
    print('=== 1. THE DEPLOYED BOOK, superseded vs corrected sigma ===')
    print(f'{"stock":7s}{"sigma":9s}{"corr all":>10s}{"corr both":>11s}'
          f'{"Bayes inv":>11s}{"OU inv":>9s}{"both inv":>10s}')
    agg = {}
    for s in BOOK:
        for mode in ('level', 'resid'):
            m = measure(s, mode)
            agg.setdefault(mode, []).append(m)
            print(f'{s:7s}{mode:9s}{m["all"]:>10.2f}{m["both"]:>11.2f}'
                  f'{m["inv1"]*100:>10.0f}%{m["inv2"]*100:>8.0f}%{m["overlap"]*100:>9.0f}%')
    for mode in ('level', 'resid'):
        a = agg[mode]
        print(f'{"MEAN":7s}{mode:9s}{statistics.mean(x["all"] for x in a):>10.2f}'
              f'{statistics.mean(x["both"] for x in a):>11.2f}'
              f'{statistics.mean(x["inv1"] for x in a)*100:>10.0f}%'
              f'{statistics.mean(x["inv2"] for x in a)*100:>8.0f}%'
              f'{statistics.mean(x["overlap"] for x in a)*100:>9.0f}%')

    print('\n=== 2. THE WHITE PAPER CONFIGURATION: NVDA, W=120, k=0.5, superseded sigma ===')
    for W, k in ((120, 0.5), (120, 0.907), (12, 0.0)):
        m = measure('NVDA', 'level', W=W, buf=k)
        print(f'  W={W:3d} k={k:5.3f}   corr(all) {m["all"]:5.2f}   corr(both) {m["both"]:5.2f}'
              f'   OU invested {m["inv2"]*100:3.0f}%   both {m["overlap"]*100:3.0f}%')
    print('\n=== 3. WHAT DRIVES IT: correlation against overlap, across every case above ===')
    rows = []
    for s in BOOK:
        for mode in ('level', 'resid'):
            m = measure(s, mode); rows.append((m['overlap'], m['all']))
    for W, k in ((120, 0.5), (120, 0.907), (12, 0.0)):
        m = measure('NVDA', 'level', W=W, buf=k); rows.append((m['overlap'], m['all']))
    x = np.array([r[0] for r in rows]); y = np.array([r[1] for r in rows])
    print(f'  correlation between "% days both invested" and "measured sleeve correlation": '
          f'{np.corrcoef(x, y)[0,1]:+.2f}  (n={len(rows)})')
    print('DONE')
