"""
Does spreading tranches across weekday anchors beat betting all of them on Monday?

Established so far: the entry is the anchor day's open (the mean-reversion formula never binds at
the workbook parameters), weekend gaps are genuinely the largest repricing of the week, Monday
scores best on NVDA in every sub-period -- but Monday's cross-sectional edge over nine other names
is worth a couple of points, not thirty, and the 80% sits on a narrow parameter ridge whose
neighbourhood median is 57%.

So the question is not only "which mix returns most" but "which mix is least dependent on having
guessed right". Four things are therefore measured for each mix:

  1 return at the workbook parameters
  2 the median over the 169-cell parameter neighbourhood -- if diversifying anchors flattens the
    ridge, that median rises even where the peak falls, and the median is what you should expect
    to live on
  3 sub-period stability
  4 whether it survives on nine other names, and whether the mix CHOICE survives walk-forward

Tranches with different anchors are offset by weekday rather than by week, so a Mon/Tue/Wed mix
buys three different opens in the same calendar week.
"""
import statistics
from weekly_anchor_test import group_weeks, wstats, tranche, data, NAMES, DAY
from weekly_mr import P, verify_same_day

COMMON = data['NVDA']
CAPS = [round(0.075 + 0.0025*i, 5) for i in range(13)]
PREMS = [round(0.023 + 0.001*i, 5) for i in range(13)]

MIXES = [
    ('Mon x3 (baseline)', [0, 0, 0]),
    ('Mon/Tue/Wed',       [0, 1, 2]),
    ('Mon/Wed/Fri',       [0, 2, 4]),
    ('Mon/Mon/Tue',       [0, 0, 1]),
    ('Mon/Mon/Wed',       [0, 0, 2]),
    ('Mon/Tue/Thu',       [0, 1, 3]),
    ('all five days',     [0, 1, 2, 3, 4]),
]

_WS = {}


def weeks(name, anchor):
    k = (name, anchor)
    if k not in _WS:
        s = data[name]
        _WS[k] = [wstats(w, *s[1:]) for w in group_weeks(s[0], anchor)]
    return _WS[k]


def run_mix(name, anchors, p=P, f0=0.0, f1=1.0, verify=None, stagger_same=True):
    """Equal capital per tranche. Repeated anchors are staggered a week apart."""
    s = data[name]; dts = s[0]
    n = len(anchors); tot = 0.0; tr = 0
    seen = {}
    for a in anchors:
        WS = weeks(name, a)
        off = seen.get(a, 0); seen[a] = off + 1
        lo = max(1, int(f0*len(WS))) + (off if stagger_same else 0)
        hi = max(lo, int(f1*len(WS)) - 1)
        f, k = tranche(WS, s, lo, hi, p=p, capital=1.0/n, verify=verify)
        tot += f; tr += k
    W0 = weeks(name, 0)
    lo0 = max(1, int(f0*len(W0))); hi0 = max(lo0, int(f1*len(W0)) - 1)
    yrs = (dts[W0[hi0]['idxs'][-1]] - dts[W0[lo0]['idxs'][0]]).days/365.25
    return tot**(1/yrs) - 1, tr


def pr(cap, prem):
    d = dict(P); d['cap'] = cap; d['prem'] = prem; return d


if __name__ == '__main__':
    print('=== 1. NVDA, workbook parameters, minute-verified ===', flush=True)
    print(f'{"mix":22s}{"annualised":>12s}{"trades":>9s}', flush=True)
    base = None
    for lbl, an in MIXES:
        r, t = run_mix('NVDA', an, verify=verify_same_day)
        if base is None: base = r
        print(f'{lbl:22s}{r*100:>11.1f}%{t:>9d}', flush=True)

    print('\n=== 2. PARAMETER-NEIGHBOURHOOD ROBUSTNESS (169 cells around the workbook) ===',
          flush=True)
    print('does diversifying the anchor flatten the ridge?', flush=True)
    print(f'{"mix":22s}{"at workbook":>13s}{"nbhd median":>13s}{"nbhd 25th":>11s}'
          f'{"peak":>8s}{"within 10pp":>13s}', flush=True)
    for lbl, an in MIXES:
        vals = []
        for c in CAPS:
            for q in PREMS:
                r, _ = run_mix('NVDA', an, p=pr(c, q), verify=verify_same_day)
                vals.append(r*100)
        w, _ = run_mix('NVDA', an, verify=verify_same_day)
        vals.sort(); pk = vals[-1]
        print(f'{lbl:22s}{w*100:>12.1f}%{statistics.median(vals):>12.1f}%'
              f'{vals[len(vals)//4]:>10.1f}%{pk:>7.1f}%'
              f'{sum(1 for v in vals if v > pk-10):>9d}/169', flush=True)

    print('\n=== 3. SUB-PERIODS (NVDA, minute-verified) ===', flush=True)
    print(f'{"mix":22s}{"first third":>13s}{"middle":>10s}{"last third":>13s}{"worst":>9s}',
          flush=True)
    for lbl, an in MIXES:
        rs = []
        for (a, b) in ((0.0, 1/3), (1/3, 2/3), (2/3, 1.0)):
            r, _ = run_mix('NVDA', an, f0=a, f1=b, verify=verify_same_day)
            rs.append(r*100)
        print(f'{lbl:22s}{rs[0]:>12.1f}%{rs[1]:>9.1f}%{rs[2]:>12.1f}%{min(rs):>8.1f}%', flush=True)

    print('\n=== 4. NINE OTHER NAMES (same-day exits disallowed, workbook parameters) ===',
          flush=True)
    hdr = ['Mon x3', 'Mon/Tue/Wed', 'Mon/Wed/Fri', 'all five']
    sel = [[0, 0, 0], [0, 1, 2], [0, 2, 4], [0, 1, 2, 3, 4]]
    print(f'{"stock":8s}' + ''.join(f'{h:>14s}' for h in hdr) + f'{"best":>14s}', flush=True)
    print('-'*72, flush=True)
    tally = {h: 0 for h in hdr}; sums = {h: [] for h in hdr}
    for nm in NAMES:
        rs = [run_mix(nm, a)[0]*100 for a in sel]
        b = hdr[max(range(len(rs)), key=lambda i: rs[i])]
        tally[b] += 1
        for h, v in zip(hdr, rs): sums[h].append(v)
        print(f'{nm:8s}' + ''.join(f'{v:>13.0f}%' for v in rs) + f'{b:>14s}', flush=True)
    print('-'*72, flush=True)
    print(f'{"mean":8s}' + ''.join(f'{statistics.mean(sums[h]):>13.0f}%' for h in hdr), flush=True)
    print(f'{"median":8s}' + ''.join(f'{statistics.median(sums[h]):>13.0f}%' for h in hdr),
          flush=True)
    print('wins: ' + ', '.join(f'{h} {tally[h]}' for h in hdr), flush=True)

    print('\n=== 5. WALK-FORWARD ON THE MIX CHOICE (NVDA, minute-verified) ===', flush=True)
    print(f'{"fold":5s}{"train":>12s}{"chosen":>22s}{"chosen OOS":>12s}{"Mon x3 OOS":>13s}'
          f'{"winner":>10s}', flush=True)
    print('-'*76, flush=True)
    cuts = [0.0, 0.5, 0.667, 0.833, 1.0]
    wins = 0; d = []
    for k in range(3):
        trhi = cuts[k+1]; telo, tehi = cuts[k+1], cuts[k+2]
        best = None
        for lbl, an in MIXES:
            r, _ = run_mix('NVDA', an, f0=0.0, f1=trhi, verify=verify_same_day)
            if best is None or r > best[0]: best = (r, lbl, an)
        _, lbl, an = best
        a_, _ = run_mix('NVDA', an, f0=telo, f1=tehi, verify=verify_same_day)
        b_, _ = run_mix('NVDA', [0, 0, 0], f0=telo, f1=tehi, verify=verify_same_day)
        wins += (a_ > b_); d.append((a_-b_)*100)
        print(f'{k+1:<5d}{f"0-{trhi:.2f}":>12s}{lbl:>22s}{a_*100:>11.1f}%{b_*100:>12.1f}%'
              f'{("chosen" if a_ > b_ else "Mon x3"):>10s}', flush=True)
    print('-'*76, flush=True)
    print(f'chosen mix beats Mon x3 in {wins}/3 folds; mean {statistics.mean(d):+.1f}pp', flush=True)
    print('DONE', flush=True)
