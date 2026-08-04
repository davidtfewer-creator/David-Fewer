"""
AVGO through the full weekly-model pipeline, on the same basis as NVDA.

Everything that was established for NVDA is re-derived here rather than assumed, because the two
names differ in the one place that matters most: at the workbook parameters the entry is the
week's open in 78% of NVDA weeks and the all-time-high cap in 22%, whereas for AVGO the split is
52/48. AVGO therefore leans much harder on the cap, and the cap is one of the two live parameters.

Same-day exits are verified against AVGO's 5-minute bars (earlier calibration showed 5-minute
reproduces the 1-minute answer exactly). Dates outside the 5-minute coverage fall back to the
provable at-open case only, so the figures are conservative rather than optimistic.

  0  which constraint binds, and are w, m, g inert for AVGO too
  1  anchor sweep at the NVDA workbook parameters -- the honest starting point
  2  exhaustive grid on the two live parameters
  3  walk-forward: grid on train weeks, scored on unseen weeks
  4  the parameter neighbourhood around AVGO's own optimum -- ridge or plateau
  5  anchor sweep again at AVGO's optimised parameters
  6  does switching the mean-reversion formula on (via m) help AVGO
"""
import statistics, math
from weekly_anchor_test import group_weeks, wstats, tranche, data, DAY
from weekly_mr import P
from five_min import make_checker

STOCK = 'AVGO'
S = data[STOCK]
DTS, O, H, L, C = S
CHECK, _IDX = make_checker(STOCK, DTS, O)
WS = [wstats(w, O, H, L, C) for w in group_weeks(DTS, 0)]
N = len(WS)

CAPS = [round(0.02 + 0.005*i, 4) for i in range(47)]
PREMS = [round(0.005 + 0.0025*i, 5) for i in range(39)]
PERT = (0.97, 1.03)


def pr(cap, prem, **kw):
    d = dict(P); d['cap'] = cap; d['prem'] = prem; d.update(kw); return d


def seg(p, w0, w1, ws=None, n=3, stag=1):
    ws = ws if ws is not None else WS
    tot = 0.0; tr = 0
    for t in range(n):
        f, k = tranche(ws, S, w0 + t*stag, w1, p=p, capital=1.0/n, verify=CHECK)
        tot += f; tr += k
    return tot - 1.0, tr


def ann(r, w0, w1, ws=None):
    ws = ws if ws is not None else WS
    yrs = (DTS[ws[min(w1, len(ws)-1)]['idxs'][-1]] - DTS[ws[w0]['idxs'][0]]).days/365.25
    return (1+r)**(1/yrs) - 1


def robust(cap, prem, w0, w1, floor):
    def one(c, q):
        c = min(max(c, CAPS[0]), CAPS[-1]); q = min(max(q, PREMS[0]), PREMS[-1])
        r, t = seg(pr(c, q), w0, w1)
        return -5.0 + t*1e-3 if t < floor else r
    base = one(cap, prem)
    sm = [one(cap*f, prem) for f in PERT] + [one(cap, prem*f) for f in PERT]
    return 0.5*base + 0.5*sum(sm)/len(sm)


def grid(w0, w1, floor, objective='robust'):
    best = None
    for c in CAPS:
        for q in PREMS:
            if objective == 'raw':
                s, t = seg(pr(c, q), w0, w1)
                if t < floor: continue
            else:
                s = robust(c, q, w0, w1, floor)
            if best is None or s > best[0]: best = (s, c, q)
    return best[1], best[2]


if __name__ == '__main__':
    rw, tw = seg(P, 1, N-1)
    floor = max(10, int(0.4*tw))
    print(f'{STOCK}: weeks {N}; at NVDA workbook parameters {ann(rw,1,N-1)*100:.1f}% ann, '
          f'{tw} trades; trade floor {floor}\n', flush=True)

    print('=== 0. WHICH CONSTRAINT BINDS, AND ARE w/m/g INERT? ===', flush=True)
    nb = {'formula': 0, 'open': 0, 'athcap': 0}
    for wi in range(1, N):
        prev, cwk = WS[wi-1], WS[wi]
        rng = prev['h'] - prev['l']
        if rng <= 0: continue
        ath = max(max(H[i] for i in w['idxs']) for w in WS[:wi])
        raw = statistics.mean([P['m']*(prev['h']+prev['l'])/2, prev['c']*P['w']]) \
            + math.log10(rng)*P['g']
        cands = {'formula': raw, 'open': cwk['o'], 'athcap': ath*(1-P['cap'])}
        nb[min(cands, key=cands.get)] += 1
    tot = sum(nb.values())
    print('  binding constraint: ' + ', '.join(f'{k} {v} ({v/tot*100:.0f}%)' for k, v in nb.items()),
          flush=True)
    for lbl, mods in (('workbook', {}), ('g x 5', {'g': P['g']*5}), ('g / 5', {'g': P['g']/5}),
                      ('w = 1.10', {'w': 1.10}), ('m = 0.90', {'m': 0.90})):
        d = dict(P); d.update(mods)
        r, t = seg(d, 1, N-1)
        print(f'  {lbl:12s}{ann(r,1,N-1)*100:6.1f}% ann, {t} trades', flush=True)

    print('\n=== 1. ANCHOR SWEEP at the NVDA workbook parameters ===', flush=True)
    print(f'{"anchor":8s}{"annualised":>12s}{"trades":>9s}{"weeks":>8s}', flush=True)
    anchors = {}
    for a in range(5):
        ws = [wstats(w, O, H, L, C) for w in group_weeks(DTS, a)]
        anchors[a] = ws
        r, t = seg(P, 1, len(ws)-1, ws=ws)
        print(f'{DAY[a]:8s}{ann(r,1,len(ws)-1,ws)*100:>11.1f}%{t:>9d}{len(ws):>8d}', flush=True)

    print('\n=== 2. FULL-SAMPLE GRID on cap and prem (Monday anchor) ===', flush=True)
    c_raw, q_raw = grid(1, N-1, floor, 'raw')
    r1, t1 = seg(pr(c_raw, q_raw), 1, N-1)
    print(f'  NVDA workbook   cap {P["cap"]:.4f}  prem {P["prem"]:.4f} -> '
          f'{ann(rw,1,N-1)*100:5.1f}% ann, {tw} trades', flush=True)
    print(f'  best (raw)      cap {c_raw:.4f}  prem {q_raw:.4f} -> '
          f'{ann(r1,1,N-1)*100:5.1f}% ann, {t1} trades', flush=True)
    c_rb, q_rb = grid(1, N-1, floor, 'robust')
    r2, t2 = seg(pr(c_rb, q_rb), 1, N-1)
    print(f'  best (robust)   cap {c_rb:.4f}  prem {q_rb:.4f} -> '
          f'{ann(r2,1,N-1)*100:5.1f}% ann, {t2} trades', flush=True)

    print('\n=== 3. WALK-FORWARD (grid on train, scored on unseen weeks) ===', flush=True)
    cuts = [int(N*f) for f in (0.5, 0.667, 0.833, 1.0)]
    print(f'{"fold":5s}{"train":>10s}{"test":>10s}{"fitted cap/prem":>20s}{"fitted OOS":>12s}'
          f'{"NVDA params OOS":>17s}{"winner":>10s}', flush=True)
    print('-'*84, flush=True)
    wins = 0; d = []; picks = []
    for k in range(3):
        trhi = cuts[k]; telo, tehi = cuts[k], cuts[k+1]-1
        _, t_tr = seg(P, 1, trhi-1)
        c, q = grid(1, trhi-1, max(4, int(0.4*t_tr)), 'robust')
        picks.append((c, q))
        a, _ = seg(pr(c, q), telo, tehi); b, _ = seg(P, telo, tehi)
        wins += (a > b); d.append((a-b)*100)
        print(f'{k+1:<5d}{f"1-{trhi-1}":>10s}{f"{telo}-{tehi}":>10s}'
              f'{f"{c:.3f} / {q:.4f}":>20s}{a*100:>11.1f}%{b*100:>16.1f}%'
              f'{("fitted" if a > b else "NVDA params"):>10s}', flush=True)
    print('-'*84, flush=True)
    print(f'fitted beats the NVDA parameters OOS in {wins}/3 folds; '
          f'mean {statistics.mean(d):+.1f}pp', flush=True)
    print(f'  cap  across folds {min(p[0] for p in picks):.3f} - {max(p[0] for p in picks):.3f}   '
          f'prem {min(p[1] for p in picks):.4f} - {max(p[1] for p in picks):.4f}', flush=True)
    cc = statistics.median(p[0] for p in picks); cq = statistics.median(p[1] for p in picks)
    cwn = 0; cdd = []
    for k in range(3):
        telo, tehi = cuts[k], cuts[k+1]-1
        a, _ = seg(pr(cc, cq), telo, tehi); b, _ = seg(P, telo, tehi)
        cwn += (a > b); cdd.append((a-b)*100)
    print(f'  consensus cap {cc:.4f} prem {cq:.4f}: beats in {cwn}/3, '
          f'mean {statistics.mean(cdd):+.1f}pp', flush=True)

    print('\n=== 4. PARAMETER NEIGHBOURHOOD around AVGO\'s own optimum ===', flush=True)
    for lbl, (bc, bq) in (('AVGO optimum', (c_rb, q_rb)), ('NVDA workbook', (P['cap'], P['prem']))):
        caps = [round(bc*(0.80 + 0.0333*i), 5) for i in range(13)]
        prems = [round(bq*(0.80 + 0.0333*i), 6) for i in range(13)]
        vals = []
        for c in caps:
            for q in prems:
                r, _ = seg(pr(c, q), 1, N-1)
                vals.append(ann(r, 1, N-1)*100)
        vals.sort(); pk = vals[-1]
        at, _ = seg(pr(bc, bq), 1, N-1)
        print(f'  {lbl:15s} at point {ann(at,1,N-1)*100:5.1f}%   nbhd median '
              f'{statistics.median(vals):5.1f}%   25th {vals[len(vals)//4]:5.1f}%   '
              f'peak {pk:5.1f}%   within 10pp {sum(1 for v in vals if v > pk-10)}/169', flush=True)

    print('\n=== 5. ANCHOR SWEEP at AVGO\'s optimised parameters ===', flush=True)
    po = pr(c_rb, q_rb)
    print(f'{"anchor":8s}{"annualised":>12s}{"trades":>9s}', flush=True)
    for a in range(5):
        ws = anchors[a]
        r, t = seg(po, 1, len(ws)-1, ws=ws)
        print(f'{DAY[a]:8s}{ann(r,1,len(ws)-1,ws)*100:>11.1f}%{t:>9d}', flush=True)

    print('\n=== 6. DOES SWITCHING THE FORMULA ON HELP? (coarse m sweep, cap/prem refit) ===',
          flush=True)
    print(f'{"m":>8s}{"cap":>8s}{"prem":>9s}{"annualised":>13s}{"trades":>8s}', flush=True)
    for mv in (0.85, 0.95, 1.05, P['m']):
        best = None
        for c in CAPS[::3]:
            for q in PREMS[::3]:
                d = pr(c, q, m=mv)
                r, t = seg(d, 1, N-1)
                if t < floor: continue
                if best is None or r > best[0]: best = (r, c, q, t)
        if best is None:
            print(f'{mv:>8.3f}{"-":>8s}{"-":>9s}{"no config clears the trade floor":>13s}',
                  flush=True); continue
        r, c, q, t = best
        print(f'{mv:>8.3f}{c:>8.3f}{q:>9.4f}{ann(r,1,N-1)*100:>12.1f}%{t:>8d}', flush=True)
    print('DONE', flush=True)
