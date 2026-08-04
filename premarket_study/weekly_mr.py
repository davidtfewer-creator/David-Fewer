"""
Python rebuild of the weekly 6-tranche mean-reversion model, verified against minute data.

Entry (mean-reversion tranche), all quantities from the PREVIOUS week except the open:
    L   = min( mean( m*(prevHigh+prevLow)/2 , prevClose*w ) + log10(prevRange)*g , thisOpen )
    buy = min( L , allTimeHigh*(1-cap) )
    target = buy + prevClose*prem

Exit, replicating the workbook's intra-week sequencing exactly:
  * carried position  -> sell if any day's high in the week reaches the target
  * bought this week  -> sell only on a day at or AFTER the buy day whose high reaches the target
The buy day is the first session in the week whose low reaches the buy price.

The residual ambiguity is a sell on the buy day itself: within one session we cannot know whether
the high came after the fill. Those cases -- and only those -- are checked against the NVDA
minute bars.
"""
import datetime, statistics, math
from stop_sweep import load_book
from minute_engine import build_index
import numpy as np

data, params, cached = load_book()
DTS, O, H, L, C = data['NVDA']
IDX = build_index()
COMM = 0.005
INTEREST = 0.0314

# workbook parameters
P = dict(w=1.0082, cap=0.0935, prem=0.0293, g=2.0374, m=1.1627)


def build_weeks():
    """[(dates, opens, highs, lows, closes)] per ISO week, in order."""
    wk, cur, key = [], [], None
    for i in range(len(C)):
        k = DTS[i].isocalendar()[:2]
        if key is None: key = k
        if k != key:
            wk.append(cur); cur = []; key = k
        cur.append(i)
    if cur: wk.append(cur)
    return [w for w in wk if len(w) >= 2]


WEEKS = build_weeks()


def wk_stats(idxs):
    return dict(o=O[idxs[0]], h=max(H[i] for i in idxs), l=min(L[i] for i in idxs),
                c=C[idxs[-1]], idxs=idxs)


WS = [wk_stats(w) for w in WEEKS]


def verify_same_day(i, buy, target):
    """True if, on session i, the target was reached at or after the fill (minute bars)."""
    e = IDX.get(DTS[i])
    if e is None:
        return None                      # no coverage -> caller decides
    lows, suf = e
    hit = lows <= buy + 1e-9
    if not hit.any(): return False
    j = int(np.argmax(hit))
    return bool(suf[j] >= target - 1e-9)


def run_tranche(start_w, p, mode='optimistic', capital=666_666.67):
    """mode: 'optimistic' | 'verified' | 'no_same_day'."""
    fund = capital; shares = 0.0; holding = False
    buy = tgt = None
    trades = 0; sd_total = 0; sd_killed = 0; uncovered = 0
    ath = max(H[i] for i in WS[start_w]['idxs'])
    for wi in range(start_w + 1, len(WS)):
        prev, cwk = WS[wi-1], WS[wi]
        ath = max(ath, prev['h'])
        # interest on idle cash for the week
        if not holding:
            days = (DTS[cwk['idxs'][-1]] - DTS[prev['idxs'][-1]]).days
            fund += fund * INTEREST * days / 365.0
        if prev['h'] - prev['l'] <= 0:
            continue
        rng = prev['h'] - prev['l']
        Lp = min(statistics.mean([p['m']*(prev['h']+prev['l'])/2, prev['c']*p['w']])
                 + math.log10(rng)*p['g'], cwk['o'])
        if not holding:
            buy = min(Lp, ath*(1 - p['cap']))
            tgt = buy + prev['c']*p['prem']
        idxs = cwk['idxs']
        if not holding:
            bd = None
            for k, i in enumerate(idxs):
                if L[i] <= buy: bd = k; break
            if bd is None:
                continue                              # no fill this week
            shares = fund/(buy + COMM); fund = 0.0; holding = True
            # sell on a day at or after the buy day
            sold = False
            for k in range(bd, len(idxs)):
                i = idxs[k]
                if H[i] >= tgt:
                    if k == bd:                        # same-session: ambiguous
                        sd_total += 1
                        if mode == 'no_same_day':
                            continue
                        if mode == 'verified':
                            v = verify_same_day(i, buy, tgt)
                            if v is None: uncovered += 1
                            elif not v:
                                sd_killed += 1; continue
                    fund = shares*(tgt - COMM); shares = 0.0
                    holding = False; sold = True; trades += 1; break
        else:
            for i in idxs:                             # carried: any day may sell
                if H[i] >= tgt:
                    fund = shares*(tgt - COMM); shares = 0.0
                    holding = False; trades += 1; break
    final = fund + (shares*C[-1] if holding else 0.0)
    return dict(final=final, trades=trades, sd_total=sd_total, sd_killed=sd_killed,
                uncovered=uncovered)


def run_book(p, mode='optimistic', n_tranches=3, stagger=1, start=1):
    tot = 0.0; tr = 0; sdt = sdk = unc = 0
    for t in range(n_tranches):
        r = run_tranche(start + t*stagger, p, mode)
        tot += r['final']; tr += r['trades']
        sdt += r['sd_total']; sdk += r['sd_killed']; unc += r['uncovered']
    cap = 666_666.67*n_tranches
    yrs = (DTS[-1] - DTS[WS[start]['idxs'][0]]).days/365.25
    return dict(final=tot, mult=tot/cap, ann=(tot/cap)**(1/yrs)-1, trades=tr,
                sd_total=sdt, sd_killed=sdk, uncovered=unc, yrs=yrs)


if __name__ == '__main__':
    print('=== WEEKLY MEAN-REVERSION, 3 staggered tranches on NVDA ===')
    print(f'sample {DTS[0]} -> {DTS[-1]}; minute coverage from {min(IDX)}\n')
    print(f'{"basis":18s}{"multiple":>10s}{"annualised":>12s}{"trades":>8s}'
          f'{"same-day":>10s}{"killed":>8s}')
    print('-'*66)
    for mode, lbl in (('optimistic', 'optimistic'), ('verified', 'MINUTE-VERIFIED'),
                      ('no_same_day', 'no same-day')):
        r = run_book(P, mode)
        print(f'{lbl:18s}{r["mult"]:>9.2f}x{r["ann"]*100:>11.0f}%{r["trades"]:>8d}'
              f'{r["sd_total"]:>10d}{r["sd_killed"]:>8d}')
    r = run_book(P, 'verified')
    print(f'\nsame-day exits not covered by minute data: {r["uncovered"]} '
          f'(treated as executed)')
    print(f'horizon {r["yrs"]:.2f}y')
