"""
A maximum holding period on the weekly model.

The rule carries an unfilled target indefinitely. That is cheap on NVDA (median hold 4 days) but
the tails are long -- 95th percentiles of 224 days for NVDA, 77 for AVGO and 451 for MU -- and
capital immobilised for a year is a real cost the annualised figure does not show.

Tested: sell at the close of the Nth week if the target has not been reached, then re-enter the
following Monday. Parameters are held FIXED at each name's deployed values, so this is a
structural test rather than a refit -- the change is scored on the parameters that are actually
running, which is the only way to know what adopting it would cost.

Reported per N: annualised return marked to market, trades, the holding-period distribution, the
half-sample split, and how much of terminal value is still an open position.
"""
import datetime, statistics, sys
import weekly_anchor_test as WAT
from mu_rerun import from_workbook
import five_min

five_min.FILES.setdefault('MU', '/root/.claude/uploads/'
                          '2d71f10a-e19f-51b2-8457-2cd547c34dff/94f1080f-MU_5min_Apr2024Aug2026.xlsx')
WAT.data['MU'] = from_workbook()
five_min.FILES.setdefault('NVDA', '/root/.claude/uploads/'
    '2d71f10a-e19f-51b2-8457-2cd547c34dff/b0d1e498-Nvidia_Minute_Data__Day_Trading_Model_.xlsx')
import weekly_name as WN
WN.DATA['MU'] = WAT.data['MU']
from weekly_name import Name, pr

SPEC = {'NVDA': (0.0935, 0.0293), 'AVGO': (0.0800, 0.1000), 'MU': (0.0500, 0.1650)}
HOLDS = [1, 2, 3, 4, 6, 8, 12, 26, None]           # None = carry indefinitely, the current rule
CUT = datetime.date(2025, 5, 23)
COMM, INTEREST = 0.005, 0.0314


def run(nm, cap, prem, maxwk, w0=1, w1=None):
    """maxwk: sell at the close of the Nth week held if the target has not been reached."""
    DTS, O, H, L, C, WS = nm.DTS, nm.O, nm.L and nm.H, nm.L, nm.C, nm.WS
    H = nm.H
    N = nm.N
    if w1 is None: w1 = N - 1
    fund, shares, holding = 1.0, 0.0, False
    tgt = None; trades = 0; held_wk = 0; entry = None
    holds = []; forced = 0
    ath = max(H[i] for i in WS[w0]['idxs'])
    for wi in range(w0 + 1, min(w1, N - 1) + 1):
        prev, cwk = WS[wi-1], WS[wi]
        ath = max(ath, prev['h'])
        idxs = cwk['idxs']
        if not holding:
            fund += fund*INTEREST*(DTS[idxs[-1]] - DTS[prev['idxs'][-1]]).days/365.0
            buy = min(cwk['o'], ath*(1-cap)); tgt = buy + prev['c']*prem
            bd = next((k for k, i in enumerate(idxs) if L[i] <= buy), None)
            if bd is None: continue
            shares = fund/(buy + COMM); fund = 0.0; holding = True
            held_wk = 1; entry = DTS[idxs[bd]]
            sold = False
            for k in range(bd, len(idxs)):
                i = idxs[k]
                if H[i] >= tgt:
                    if k == bd and nm.check(i, buy, tgt) is False: continue
                    fund = shares*(tgt-COMM); shares = 0.0; holding = False
                    trades += 1; holds.append((DTS[i]-entry).days); sold = True; break
            if not sold and maxwk is not None and held_wk >= maxwk:
                px = C[idxs[-1]]
                fund = shares*(px-COMM); shares = 0.0; holding = False
                trades += 1; forced += 1; holds.append((DTS[idxs[-1]]-entry).days)
        else:
            held_wk += 1
            sold = False
            for i in idxs:
                if H[i] >= tgt:
                    fund = shares*(tgt-COMM); shares = 0.0; holding = False
                    trades += 1; holds.append((DTS[i]-entry).days); sold = True; break
            if not sold and maxwk is not None and held_wk >= maxwk:
                px = C[idxs[-1]]
                fund = shares*(px-COMM); shares = 0.0; holding = False
                trades += 1; forced += 1; holds.append((DTS[idxs[-1]]-entry).days)
    last = WS[min(w1, N-1)]['idxs'][-1]
    val = fund + (shares*C[last] if holding else 0.0)
    yrs = (DTS[last] - DTS[WS[w0]['idxs'][0]]).days/365.25
    holds.sort()
    return dict(ann=val**(1/yrs)-1, trades=trades, forced=forced, holds=holds,
                open_end=1 if holding else 0)


def _nvda_name():
    """NVDA's intraday file is minute bars in a different layout, so reuse the validated
    minute verifier rather than the 5-minute loader."""
    from weekly_mr import verify_same_day
    nm = Name.__new__(Name)
    nm.stock = 'NVDA'
    nm.S = WN.DATA['NVDA']
    nm.DTS, nm.O, nm.H, nm.L, nm.C = nm.S
    nm.check = verify_same_day
    nm.idx = {}
    from weekly_anchor_test import group_weeks, wstats
    nm.anchors = {a: [wstats(w, *nm.S[1:]) for w in group_weeks(nm.DTS, a)] for a in range(5)}
    nm.WS = nm.anchors[0]; nm.N = len(nm.WS)
    return nm


if __name__ == '__main__':
    names = [a for a in sys.argv[1:] if a in SPEC] or list(SPEC)
    from weekly_mr import verify_same_day
    for s in names:
        nm = Name(s) if s != 'NVDA' else _nvda_name()
        cap, prem = SPEC[s]
        kc = next(i for i, w in enumerate(nm.WS) if nm.DTS[w['idxs'][0]] >= CUT)
        print(f'\n{"="*88}\n{s}  (cap {cap:.4f}, prem {prem:.4f}, parameters fixed)', flush=True)
        print(f'{"max hold":>10s}{"annualised":>12s}{"trades":>8s}{"forced":>8s}'
              f'{"median":>8s}{"95th":>7s}{"max":>7s}{"1st half":>10s}{"tested":>10s}'
              f'{"open end":>10s}', flush=True)
        print('-'*88, flush=True)
        for mw in HOLDS:
            r = run(nm, cap, prem, mw)
            a = run(nm, cap, prem, mw, 1, kc-1)
            b = run(nm, cap, prem, mw, kc, nm.N-1)
            h = r['holds']
            lbl = 'none' if mw is None else f'{mw} wk'
            print(f'{lbl:>10s}{r["ann"]*100:>11.1f}%{r["trades"]:>8d}{r["forced"]:>8d}'
                  f'{h[len(h)//2]:>8d}{h[int(len(h)*0.95)]:>7d}{max(h):>7d}'
                  f'{a["ann"]*100:>9.1f}%{b["ann"]*100:>9.1f}%{r["open_end"]:>10d}', flush=True)
    print('\nDONE', flush=True)
