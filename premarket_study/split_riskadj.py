"""
The sleeve split on a risk-adjusted objective.

The split was chosen on return, and on return 50/50 and 75/25 are a coin flip. But the OU sleeve's
justification was never return -- it was meant to be a hedge, and the hedging evidence turns out
to be weaker than the white paper claims: the sleeves correlate 0.59 rather than 0.09, and
blending saves about 4pp of drawdown rather than halving it.

So the split should be tested on what the sleeve is actually for. Three objectives are swept
across the Bayes share:

    return    annualised, marked to market
    Sharpe    annualised, on daily book-equity returns
    Calmar    annualised return divided by maximum drawdown

Measured per name and, more importantly, at BOOK level on the equal-weighted equity curve, since
that is where risk actually lands. Then walk-forwarded: the share is chosen on the training
window by each objective and scored on unseen sessions against the deployed 50/50.

Everything runs the corrected OU sleeve, which is what is deployed.
"""
import copy, datetime, statistics
import numpy as np
from engine import run_model
from ss_sleeve import DATA, PARAMS, BOOK, BUF_RESID, chk

SHARES = [round(0.1*i, 2) for i in range(11)]
CUTS = (0.5, 0.667, 0.833, 1.0)
_EQ = {}


def eq_of(s, b):
    if (s, b) not in _EQ:
        p = copy.copy(PARAMS[s]); p.bayes_pct = b; p.ou_buf_k = BUF_RESID[s]
        p.years = (DATA[s][0][-1]-DATA[s][0][0]).days/365.25
        r = run_model(*DATA[s], p, ou_sigma='resid', collect=True, same_day_exit=chk(s))
        _EQ[(s, b)] = np.array(r.frames['equity'], dtype=float)
    return _EQ[(s, b)]


def metrics(e, dts, lo=None, hi=None):
    lo = 0 if lo is None else lo; hi = len(e)-1 if hi is None else hi
    seg = e[lo:hi+1]
    if seg[0] <= 0 or len(seg) < 5: return dict(ret=np.nan, sharpe=np.nan, dd=np.nan, cal=np.nan)
    d = (dts[hi]-dts[lo]).days
    ret = ((seg[-1]/seg[0])**(365.25/max(d, 1))-1)*100
    r = seg[1:]/seg[:-1]-1
    r = r[np.isfinite(r)]
    sh = float(r.mean()/r.std()*np.sqrt(252)) if len(r) > 2 and r.std() > 0 else np.nan
    peak = np.maximum.accumulate(seg)
    dd = float((1-seg/peak).max()*100)
    return dict(ret=ret, sharpe=sh, dd=dd, cal=ret/dd if dd > 0 else np.nan)


def book_eq(b, lo=None, hi=None):
    """Equal-weighted book equity across the five daily names."""
    curves = [eq_of(s, b) for s in BOOK]
    n = min(len(c) for c in curves)
    return np.vstack([c[:n]/c[0] for c in curves]).mean(axis=0)


if __name__ == '__main__':
    dts = DATA['RKLB'][0]
    print('=== 1. BOOK LEVEL: each objective across the Bayes share ===')
    print(f'{"Bayes":>7s}{"return":>10s}{"Sharpe":>9s}{"max DD":>9s}{"Calmar":>9s}')
    rows = {}
    for b in SHARES:
        m = metrics(book_eq(b), dts)
        rows[b] = m
        star = '  <-- deployed' if b == 0.5 else ''
        print(f'{b:>7.0%}{m["ret"]:>9.0f}%{m["sharpe"]:>9.2f}{m["dd"]:>8.0f}%{m["cal"]:>9.2f}{star}')
    for key, lbl in (('ret', 'return'), ('sharpe', 'Sharpe'), ('cal', 'Calmar')):
        best = max(SHARES, key=lambda b: rows[b][key])
        print(f'  best on {lbl:7s}: {best:.0%}')

    print('\n=== 2. PER NAME: the share that maximises each objective ===')
    print(f'{"stock":7s}{"best return":>13s}{"best Sharpe":>13s}{"best Calmar":>13s}'
          f'{"Sharpe @50":>12s}{"Sharpe @best":>14s}')
    for s in BOOK:
        ms = {b: metrics(eq_of(s, b), DATA[s][0]) for b in SHARES}
        br = max(SHARES, key=lambda b: ms[b]['ret'])
        bs = max(SHARES, key=lambda b: ms[b]['sharpe'])
        bc = max(SHARES, key=lambda b: ms[b]['cal'])
        print(f'{s:7s}{br:>12.0%}{bs:>13.0%}{bc:>13.0%}'
              f'{ms[0.5]["sharpe"]:>12.2f}{ms[bs]["sharpe"]:>14.2f}')

    print('\n=== 3. WALK-FORWARD: share chosen on train by each objective, scored unseen ===')
    n = len(dts); cuts = [int(n*f) for f in CUTS]
    for key, lbl in (('ret', 'return'), ('sharpe', 'Sharpe'), ('cal', 'Calmar')):
        wins = 0; d = []; picks = []
        for j in range(3):
            trhi = cuts[j]; telo, tehi = cuts[j], cuts[j+1]-1
            pick = max(SHARES, key=lambda b: metrics(book_eq(b), dts, 0, trhi-1)[key])
            picks.append(pick)
            a = metrics(book_eq(pick), dts, telo, tehi)[key]
            c = metrics(book_eq(0.5), dts, telo, tehi)[key]
            wins += (a > c); d.append(a-c)
        print(f'  {lbl:7s} chosen beats 50/50 in {wins}/3; mean diff {statistics.mean(d):+.2f}'
              f'   shares chosen {[f"{p:.0%}" for p in picks]}')

    print('\n=== 4. FIXED SPLITS HEAD TO HEAD, out of sample (Sharpe) ===')
    print(f'{"share":>7s}{"fold1":>9s}{"fold2":>9s}{"fold3":>9s}{"mean":>9s}')
    for b in (0.0, 0.25, 0.5, 0.75, 1.0):
        vals = []
        for j in range(3):
            telo, tehi = cuts[j], cuts[j+1]-1
            vals.append(metrics(book_eq(b), dts, telo, tehi)['sharpe'])
        star = '  <-- deployed' if b == 0.5 else ''
        print(f'{b:>7.0%}' + ''.join(f'{v:>9.2f}' for v in vals)
              + f'{statistics.mean(vals):>9.2f}{star}')
    print('DONE')
