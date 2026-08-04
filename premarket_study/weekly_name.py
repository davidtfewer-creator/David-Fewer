"""
Run any name through the full weekly-model pipeline, on the basis settled for NVDA and AVGO.

Usage:  python3 weekly_name.py TSLA PLTR SOFI SPOT

What was learned on the first two names is built in here rather than re-derived:

  * the mean-reversion formula is dormant at the workbook parameters -- the entry is the anchor
    day's open, or the all-time-high cap when the name is near its high -- so only cap and prem
    are fitted. Stage 0 checks that this holds for each new name instead of assuming it.
  * the grid runs to prem = 0.20 from the start. AVGO's first pass put the optimum on the
    boundary of a narrower grid, which is not an optimum but a statement about where the search
    stopped.
  * a single-cell peak is reported as a spike, not as the result. What matters is the level of
    the surrounding region, since that is what you live on if the ridge moves.
  * the model carries no stop loss and ends fully invested, so holding period and the terminal
    mark are reported alongside the headline.

Same-day exits are verified against each name's 5-minute bars; sessions outside that coverage
fall back to the provable at-open case only.
"""
import statistics, math, sys
from stop_sweep import load_book
from weekly_anchor_test import group_weeks, wstats, tranche, DAY
from weekly_mr import P
from five_min import make_checker

DATA, _P, _C = load_book()
CAPS = [round(0.02 + 0.005*i, 4) for i in range(37)]       # 0.020 .. 0.200
PREMS = [round(0.02 + 0.005*i, 5) for i in range(37)]      # 0.020 .. 0.200
PERT = (0.97, 1.03)
COMM, INTEREST = 0.005, 0.0314


def pr(cap, prem, **kw):
    d = dict(P); d['cap'] = cap; d['prem'] = prem; d.update(kw); return d


class Name:
    def __init__(self, stock):
        self.stock = stock
        self.S = DATA[stock]
        self.DTS, self.O, self.H, self.L, self.C = self.S
        self.check, self.idx = make_checker(stock, self.DTS, self.O)
        self.anchors = {a: [wstats(w, *self.S[1:]) for w in group_weeks(self.DTS, a)]
                        for a in range(5)}
        self.WS = self.anchors[0]
        self.N = len(self.WS)

    def seg(self, p, w0, w1, ws=None, n=3, stag=1):
        ws = ws if ws is not None else self.WS
        tot = 0.0; tr = 0
        for t in range(n):
            f, k = tranche(ws, self.S, w0 + t*stag, w1, p=p, capital=1.0/n, verify=self.check)
            tot += f; tr += k
        return tot - 1.0, tr

    def ann(self, r, w0, w1, ws=None):
        ws = ws if ws is not None else self.WS
        yrs = (self.DTS[ws[min(w1, len(ws)-1)]['idxs'][-1]]
               - self.DTS[ws[w0]['idxs'][0]]).days/365.25
        return (1+r)**(1/yrs) - 1

    def robust(self, cap, prem, w0, w1, floor):
        def one(c, q):
            c = min(max(c, CAPS[0]), CAPS[-1]); q = min(max(q, PREMS[0]), PREMS[-1])
            r, t = self.seg(pr(c, q), w0, w1)
            return -5.0 + t*1e-3 if t < floor else r
        base = one(cap, prem)
        sm = [one(cap*f, prem) for f in PERT] + [one(cap, prem*f) for f in PERT]
        return 0.5*base + 0.5*sum(sm)/len(sm)

    def grid(self, w0, w1, floor):
        best = None
        for c in CAPS:
            for q in PREMS:
                s = self.robust(c, q, w0, w1, floor)
                if best is None or s > best[0]: best = (s, c, q)
        return best[1], best[2]

    def walk(self, p):
        """Replay the tranches: ending cash, ending position value, hold lengths."""
        cash = pos = 0.0; hd = []; still = 0
        H, L, C, DTS, WS, N = self.H, self.L, self.C, self.DTS, self.WS, self.N
        for t0 in range(3):
            fund, shares, holding = 1/3, 0.0, False
            buy = tgt = None; entry = None
            ath = max(H[i] for i in WS[1 + t0]['idxs'])
            for wi in range(2 + t0, N):
                prev, cwk = WS[wi-1], WS[wi]
                ath = max(ath, prev['h'])
                if prev['h'] - prev['l'] <= 0: continue
                if not holding:
                    fund += fund*INTEREST*(DTS[cwk['idxs'][-1]]
                                           - DTS[prev['idxs'][-1]]).days/365.0
                    buy = min(cwk['o'], ath*(1 - p['cap'])); tgt = buy + prev['c']*p['prem']
                idxs = cwk['idxs']
                if not holding:
                    bd = next((k for k, i in enumerate(idxs) if L[i] <= buy), None)
                    if bd is None: continue
                    shares = fund/(buy + COMM); fund = 0.0; holding = True
                    entry = DTS[idxs[bd]]
                    for k in range(bd, len(idxs)):
                        i = idxs[k]
                        if H[i] >= tgt:
                            if k == bd and self.check(i, buy, tgt) is False: continue
                            fund = shares*(tgt - COMM); shares = 0.0; holding = False
                            hd.append((DTS[i] - entry).days); break
                else:
                    for i in idxs:
                        if H[i] >= tgt:
                            fund = shares*(tgt - COMM); shares = 0.0; holding = False
                            hd.append((DTS[i] - entry).days); break
            last = WS[N-1]['idxs'][-1]
            cash += fund; pos += shares*C[last]; still += holding
        return cash, pos, hd, still


def report(stock):
    nm = Name(stock)
    N = nm.N
    rw, tw = nm.seg(P, 1, N-1)
    base = nm.ann(rw, 1, N-1)*100
    floor = max(8, int(0.4*tw))
    print(f'\n{"="*78}\n{stock}: {N} weeks, 5-min coverage {len(nm.idx)} days', flush=True)
    print(f'at the NVDA parameters (Monday anchor): {base:.1f}% ann, {tw} trades; '
          f'trade floor {floor}', flush=True)

    # 0 -- structure
    nb = {'formula': 0, 'open': 0, 'athcap': 0}
    for wi in range(1, N):
        prev, cwk = nm.WS[wi-1], nm.WS[wi]
        rng = prev['h'] - prev['l']
        if rng <= 0: continue
        ath = max(max(nm.H[i] for i in w['idxs']) for w in nm.WS[:wi])
        raw = statistics.mean([P['m']*(prev['h']+prev['l'])/2, prev['c']*P['w']]) \
            + math.log10(rng)*P['g']
        nb[min({'formula': raw, 'open': cwk['o'], 'athcap': ath*(1-P['cap'])}.items(),
               key=lambda kv: kv[1])[0]] += 1
    t = sum(nb.values())
    print(f'  binding constraint: ' + ', '.join(f'{k} {v/t*100:.0f}%' for k, v in nb.items()),
          flush=True)

    # 1 -- anchors at the NVDA parameters
    row = []
    for a in range(5):
        ws = nm.anchors[a]
        r, _ = nm.seg(P, 1, len(ws)-1, ws=ws)
        row.append(nm.ann(r, 1, len(ws)-1, ws)*100)
    print('  anchors @ NVDA params: ' + '  '.join(f'{DAY[a]} {row[a]:.0f}%' for a in range(5))
          + f'   best {DAY[max(range(5), key=lambda i: row[i])]}', flush=True)

    # 2 -- full-sample grid
    bc, bq = nm.grid(1, N-1, floor)
    ro, to = nm.seg(pr(bc, bq), 1, N-1)
    print(f'  OPTIMISED: cap {bc:.3f} prem {bq:.3f} -> {nm.ann(ro,1,N-1)*100:.1f}% ann, '
          f'{to} trades   (from {base:.1f}%)', flush=True)

    # premium profile through the optimum
    prof = []
    for q in (0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20):
        r2, t2 = nm.seg(pr(bc, q), 1, N-1)
        prof.append(f'{q:.2f}:{nm.ann(r2,1,N-1)*100:.0f}%')
    print('  prem profile at that cap: ' + '  '.join(prof), flush=True)

    # 3 -- neighbourhood
    caps = [round(bc*(0.80 + 0.0333*i), 5) for i in range(13)]
    prems = [round(bq*(0.80 + 0.0333*i), 6) for i in range(13)]
    vals = []
    for c in caps:
        for q in prems:
            r2, _ = nm.seg(pr(c, q), 1, N-1)
            vals.append(nm.ann(r2, 1, N-1)*100)
    vals.sort(); pk = vals[-1]
    print(f'  neighbourhood: median {statistics.median(vals):.1f}%  25th {vals[len(vals)//4]:.1f}%'
          f'  peak {pk:.1f}%  within 10pp {sum(1 for v in vals if v > pk-10)}/169', flush=True)

    # 4 -- walk-forward
    cuts = [int(N*f) for f in (0.5, 0.667, 0.833, 1.0)]
    picks = []; wins = 0; d = []
    for k in range(3):
        trhi = cuts[k]; telo, tehi = cuts[k], cuts[k+1]-1
        _, ttr = nm.seg(P, 1, trhi-1)
        c, q = nm.grid(1, trhi-1, max(4, int(0.4*ttr)))
        picks.append((c, q))
        a_, _ = nm.seg(pr(c, q), telo, tehi); b_, _ = nm.seg(P, telo, tehi)
        wins += (a_ > b_); d.append((a_-b_)*100)
    cc = statistics.median(p[0] for p in picks); cq = statistics.median(p[1] for p in picks)
    w2 = 0; d2 = []
    for k in range(3):
        telo, tehi = cuts[k], cuts[k+1]-1
        a_, _ = nm.seg(pr(cc, cq), telo, tehi); b_, _ = nm.seg(P, telo, tehi)
        w2 += (a_ > b_); d2.append((a_-b_)*100)
    print(f'  walk-forward: fitted beats NVDA params {wins}/3 (mean {statistics.mean(d):+.1f}pp); '
          f'consensus cap {cc:.3f} prem {cq:.3f} {w2}/3 (mean {statistics.mean(d2):+.1f}pp)',
          flush=True)
    print(f'  fold picks: ' + '  '.join(f'{c:.3f}/{q:.3f}' for c, q in picks), flush=True)

    # 5 -- anchors at the optimised parameters
    po = pr(bc, bq)
    row2 = []
    for a in range(5):
        ws = nm.anchors[a]
        r2, _ = nm.seg(po, 1, len(ws)-1, ws=ws)
        row2.append(nm.ann(r2, 1, len(ws)-1, ws)*100)
    print('  anchors @ optimised:   ' + '  '.join(f'{DAY[a]} {row2[a]:.0f}%' for a in range(5))
          + f'   best {DAY[max(range(5), key=lambda i: row2[i])]}', flush=True)

    # 6 -- holding period and terminal mark
    for lbl, p in (('NVDA params', P), ('optimised', po)):
        cash, pos, hd, still = nm.walk(p)
        tot = cash + pos
        if not hd:
            print(f'  {lbl:12s} no completed trades', flush=True); continue
        hd.sort()
        print(f'  {lbl:12s} {nm.ann(tot-1,1,N-1)*100:5.1f}% ann  n={len(hd):3d}  '
              f'median hold {hd[len(hd)//2]:3d}d  95th {hd[int(len(hd)*0.95)]:4d}d  '
              f'open position {pos/tot*100:3.0f}% of ending value ({still}/3 holding)  '
              f'mark -20% -> {nm.ann(cash+pos*0.8-1,1,N-1)*100:5.1f}%', flush=True)
    return dict(stock=stock, base=base, opt=nm.ann(ro, 1, N-1)*100, cap=bc, prem=bq,
                nbhd=statistics.median(vals), q25=vals[len(vals)//4], wf=wins, cons=w2)


if __name__ == '__main__':
    names = sys.argv[1:] or ['TSLA', 'PLTR', 'SOFI', 'SPOT']
    out = [report(s) for s in names]
    print(f'\n{"="*78}\nSUMMARY', flush=True)
    print(f'{"stock":7s}{"NVDA params":>13s}{"optimised":>11s}{"cap":>7s}{"prem":>7s}'
          f'{"nbhd median":>13s}{"25th":>7s}{"WF":>5s}{"cons":>6s}', flush=True)
    for r in out:
        print(f'{r["stock"]:7s}{r["base"]:>12.1f}%{r["opt"]:>10.1f}%{r["cap"]:>7.3f}'
              f'{r["prem"]:>7.3f}{r["nbhd"]:>12.1f}%{r["q25"]:>6.1f}%{r["wf"]:>4d}/3'
              f'{r["cons"]:>5d}/3', flush=True)
    print('DONE', flush=True)
