"""
Walk-forward on the weekly MR model's TWO live parameters.

The clamp test showed the mean-reversion formula never binds -- its level sits a median +9.4%
above the week's open and was the binding constraint in 0 of 120 NVDA weeks. So w, m and g change
nothing, and the earlier 0/6 walk-forward verdict was reached while three of the five fitted
dimensions were inert. That is worth redoing honestly:

    buy    = min( thisWeekOpen , allTimeHigh*(1-cap) )
    target = buy + prevClose*prem

Two parameters, so an exhaustive grid replaces differential evolution -- no seeds, no convergence
question, the reported optimum IS the optimum on that grid.

  Stage 0  confirm the inert parameters really are inert
  Stage 1  full-sample grid, raw and robust
  Stage 2  walk-forward: grid on train weeks, score unseen weeks against the workbook
  Stage 3  consensus pair (median of the fold picks) on every test window
  Stage 4  the objective surface, to see whether the workbook sits on a plateau or a cliff
"""
import statistics
from weekly_anchor_test import group_weeks, wstats, tranche, data, P
from weekly_mr import verify_same_day

SERIES = data['NVDA']
DTS = SERIES[0]
WS = [wstats(w, *SERIES[1:]) for w in group_weeks(DTS, 0)]
N = len(WS)

CAPS = [round(0.02 + 0.005*i, 4) for i in range(47)]        # 0.020 .. 0.250
PREMS = [round(0.005 + 0.0025*i, 5) for i in range(39)]     # 0.0050 .. 0.1000
PERT = (0.97, 1.03)


def pr(cap, prem):
    d = dict(P); d['cap'] = cap; d['prem'] = prem; return d


def seg(p, w0, w1, n=3, stag=1):
    tot = 0.0; tr = 0
    for t in range(n):
        f, k = tranche(WS, SERIES, w0 + t*stag, w1, p=p, capital=1.0/n, verify=verify_same_day)
        tot += f; tr += k
    return tot - 1.0, tr


def ann(r, w0, w1):
    yrs = (DTS[WS[min(w1, N-1)]['idxs'][-1]] - DTS[WS[w0]['idxs'][0]]).days/365.25
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
            s = robust(c, q, w0, w1, floor) if objective == 'robust' else seg(pr(c, q), w0, w1)[0]
            if objective == 'raw':
                _, t = seg(pr(c, q), w0, w1)
                if t < floor: continue
            if best is None or s > best[0]: best = (s, c, q)
    return best[1], best[2]


if __name__ == '__main__':
    rw, tw = seg(P, 1, N-1)
    floor = max(10, int(0.4*tw))
    print(f'weeks {N}; workbook {ann(rw,1,N-1)*100:.1f}% ann, {tw} trades; trade floor {floor}',
          flush=True)
    print(f'grid {len(CAPS)}x{len(PREMS)} = {len(CAPS)*len(PREMS)} points\n', flush=True)

    print('=== STAGE 0: are w, m, g really inert? ===', flush=True)
    for lbl, mods in (('workbook', {}), ('g x 5', {'g': P['g']*5}), ('g / 5', {'g': P['g']/5}),
                      ('m = 0.90', {'m': 0.90}), ('w = 1.10', {'w': 1.10}),
                      ('all three moved', {'g': 0.4, 'm': 0.95, 'w': 1.03})):
        d = dict(P); d.update(mods)
        r, t = seg(d, 1, N-1)
        print(f'  {lbl:18s}{ann(r,1,N-1)*100:6.1f}% ann, {t} trades', flush=True)

    print('\n=== STAGE 1: full-sample grid ===', flush=True)
    c_raw, q_raw = grid(1, N-1, floor, 'raw')
    r1, t1 = seg(pr(c_raw, q_raw), 1, N-1)
    print(f'  workbook      cap {P["cap"]:.4f}  prem {P["prem"]:.4f} -> '
          f'{ann(rw,1,N-1)*100:5.1f}% ann, {tw} trades', flush=True)
    print(f'  best (raw)    cap {c_raw:.4f}  prem {q_raw:.4f} -> '
          f'{ann(r1,1,N-1)*100:5.1f}% ann, {t1} trades', flush=True)
    c_rb, q_rb = grid(1, N-1, floor, 'robust')
    r2, t2 = seg(pr(c_rb, q_rb), 1, N-1)
    print(f'  best (robust) cap {c_rb:.4f}  prem {q_rb:.4f} -> '
          f'{ann(r2,1,N-1)*100:5.1f}% ann, {t2} trades', flush=True)

    print('\n=== STAGE 2: walk-forward (grid on train, scored on unseen weeks) ===', flush=True)
    cuts = [int(N*f) for f in (0.5, 0.667, 0.833, 1.0)]
    print(f'{"fold":5s}{"train":>10s}{"test":>10s}{"fitted cap/prem":>20s}'
          f'{"fitted OOS":>12s}{"workbook OOS":>14s}{"winner":>10s}', flush=True)
    print('-'*81, flush=True)
    wins = 0; d = []; picks = []
    for k in range(3):
        trhi = cuts[k]; telo, tehi = cuts[k], cuts[k+1]-1
        _, t_tr = seg(P, 1, trhi-1)
        c, q = grid(1, trhi-1, max(4, int(0.4*t_tr)), 'robust')
        picks.append((c, q))
        a, _ = seg(pr(c, q), telo, tehi)
        b, _ = seg(P, telo, tehi)
        wins += (a > b); d.append((a-b)*100)
        print(f'{k+1:<5d}{f"1-{trhi-1}":>10s}{f"{telo}-{tehi}":>10s}'
              f'{f"{c:.3f} / {q:.4f}":>20s}{a*100:>11.1f}%{b*100:>13.1f}%'
              f'{("fitted" if a > b else "workbook"):>10s}', flush=True)
    print('-'*81, flush=True)
    print(f'fitted beats workbook OOS in {wins}/3 folds; mean {statistics.mean(d):+.1f}pp',
          flush=True)
    print(f'  cap  across folds: {min(p[0] for p in picks):.3f} - {max(p[0] for p in picks):.3f}'
          f'   (workbook {P["cap"]:.3f})', flush=True)
    print(f'  prem across folds: {min(p[1] for p in picks):.4f} - {max(p[1] for p in picks):.4f}'
          f'  (workbook {P["prem"]:.4f})', flush=True)

    print('\n=== STAGE 3: consensus pair on each test window ===', flush=True)
    cc = statistics.median(p[0] for p in picks); cq = statistics.median(p[1] for p in picks)
    print(f'  consensus cap {cc:.4f}  prem {cq:.4f}', flush=True)
    cw = 0; cd = []
    for k in range(3):
        telo, tehi = cuts[k], cuts[k+1]-1
        a, _ = seg(pr(cc, cq), telo, tehi); b, _ = seg(P, telo, tehi)
        cw += (a > b); cd.append((a-b)*100)
        print(f'  fold {k+1}: consensus {a*100:6.1f}%   workbook {b*100:6.1f}%   '
              f'{"consensus" if a > b else "workbook"}', flush=True)
    print(f'  consensus beats workbook in {cw}/3; mean {statistics.mean(cd):+.1f}pp', flush=True)
    rc, tc = seg(pr(cc, cq), 1, N-1)
    print(f'  full sample: {ann(rc,1,N-1)*100:5.1f}% ann, {tc} trades', flush=True)

    print('\n=== STAGE 4: full-sample surface (annualised %, trades in brackets) ===', flush=True)
    cs = [0.04, 0.06, 0.0935, 0.12, 0.15, 0.18, 0.22]
    qs = [0.010, 0.020, 0.0293, 0.040, 0.055, 0.070, 0.090]
    hdr = 'cap \\ prem'
    print(f'{hdr:>10s}' + ''.join(f'{q:>13.4f}' for q in qs), flush=True)
    for c in cs:
        row = []
        for q in qs:
            r, t = seg(pr(c, q), 1, N-1)
            row.append(f'{ann(r,1,N-1)*100:4.0f}% ({t:3d})')
        mark = ' <- workbook cap' if abs(c - P['cap']) < 1e-6 else ''
        print(f'{c:>10.4f}' + ''.join(f'{x:>13s}' for x in row) + mark, flush=True)
    print('DONE', flush=True)
