"""
What the corrected OU sigma does to NVDA and AVGO on the DAILY model.

Both are on the weekly model, chosen because their daily returns were the weakest in the book --
NVDA 36% and AVGO 31% at the 50/50 split, against a 50% floor. That comparison was made against
an OU sleeve whose sigma measured the trend rather than the residual, and these two are the most
persistently trending names in the book, so they are exactly where the mis-specification should
have bitten hardest.

If the corrected daily model now clears what the weekly model delivers, the decision to move them
should be revisited. If it does not, the weekly choice stands on better evidence than before.

Verified fills (1-minute NVDA, 5-minute AVGO), marked to market, true span, same half-sample
boundary, and a walk-forward of the sigma choice with ou_buf_k fitted on the training window only.
"""
import copy, datetime, statistics
from engine import run_model
from stop_sweep import load_book
from five_min import make_checker as fm
from minute_engine import make_checker as nv

DATA, PARAMS, _ = load_book()
NAMES = ['NVDA', 'AVGO']
MODES = ['level', 'resid', 'detrend']
CUT = datetime.date(2025, 5, 23)
BUFS = [round(0.05 + 0.05*i, 3) for i in range(50)]
WEEKLY = {'NVDA': dict(verified=82.0, plan=58, h1=44.2, h2=81.8),
          'AVGO': dict(verified=90.7, plan=60, h1=72.2, h2=96.4)}
CHK = {}


def chk(s):
    if s not in CHK:
        d = DATA[s]
        CHK[s] = nv(d[0], d[1])[0] if s == 'NVDA' else fm(s, d[0], d[1])[0]
    return CHK[s]


def run(s, mode, bayes, buf=None):
    dts, O, H, L, C = DATA[s]
    p = copy.copy(PARAMS[s]); p.bayes_pct = bayes
    if buf is not None: p.ou_buf_k = buf
    p.years = (dts[-1]-dts[0]).days/365.25
    r = run_model(dts, O, H, L, C, p, ou_sigma=mode, collect=True, same_day_exit=chk(s))
    return dts, r.frames['equity'], r


def ann(eq, dts, lo, hi):
    d = (dts[hi]-dts[lo]).days
    return ((eq[hi]/eq[lo])**(365.25/d)-1)*100 if eq[lo] > 0 and d else float('nan')


def score(s, mode, bayes, buf=None, lo=None, hi=None):
    dts, eq, r = run(s, mode, bayes, buf)
    lo = 0 if lo is None else lo; hi = len(dts)-1 if hi is None else hi
    return ann(eq, dts, lo, hi), r


if __name__ == '__main__':
    print('=== 1. OU SLEEVE ALONE (bayes 0), buffer frozen then re-fitted ===')
    print(f'{"stock":7s}{"":4s}' + ''.join(f'{m:>14s}' for m in MODES))
    best = {}
    for s in NAMES:
        froz = [score(s, m, 0.0)[0] for m in MODES]
        print(f'{s:7s}{"froz":4s}' + ''.join(f'{v:>13.0f}%' for v in froz))
        cells = []
        for m in MODES:
            b = max((score(s, m, 0.0, buf=k)[0], k) for k in BUFS)
            best[(s, m)] = b[1]; cells.append(f'{b[0]:5.0f}% (k={b[1]:.2f})')
        print(f'{"":7s}{"fit":4s}' + ''.join(f'{c:>14s}' for c in cells))

    print('\n=== 2. FULL DAILY MODEL at 75% Bayes ===')
    print(f'{"stock":7s}{"level":>10s}{"resid":>10s}{"resid+k":>10s}'
          f'{"weekly (deployed)":>20s}')
    for s in NAMES:
        a = score(s, 'level', 0.75)[0]
        b = score(s, 'resid', 0.75)[0]
        c = score(s, 'resid', 0.75, buf=best[(s, 'resid')])[0]
        print(f'{s:7s}{a:>9.0f}%{b:>9.0f}%{c:>9.0f}%{WEEKLY[s]["verified"]:>19.0f}%')

    print('\n=== 3. HALF-SAMPLE, daily at 75% Bayes with corrected sigma + fitted k ===')
    print(f'{"stock":7s}{"daily 1st":>11s}{"daily tested":>14s}{"weekly 1st":>12s}'
          f'{"weekly tested":>15s}')
    for s in NAMES:
        dts = DATA[s][0]
        k = next(i for i, d in enumerate(dts) if d >= CUT)
        _, eq, _ = run(s, 'resid', 0.75, best[(s, 'resid')])
        print(f'{s:7s}{ann(eq,dts,0,k):>10.0f}%{ann(eq,dts,k,len(dts)-1):>13.0f}%'
              f'{WEEKLY[s]["h1"]:>11.0f}%{WEEKLY[s]["h2"]:>14.0f}%')

    print('\n=== 4. WALK-FORWARD on the sigma choice (k fitted on train only) ===')
    CUTS = (0.5, 0.667, 0.833, 1.0)
    for m in ('resid', 'detrend'):
        wins = tot = 0; d = []
        for s in NAMES:
            dts = DATA[s][0]; N = len(dts); cuts = [int(N*f) for f in CUTS]
            for j in range(3):
                trhi = cuts[j]; telo, tehi = cuts[j], cuts[j+1]-1
                kb = max((score(s, m, 0.0, buf=k, lo=0, hi=trhi-1)[0], k) for k in BUFS)[1]
                kl = max((score(s, 'level', 0.0, buf=k, lo=0, hi=trhi-1)[0], k) for k in BUFS)[1]
                a = score(s, m, 0.0, buf=kb, lo=telo, hi=tehi)[0]
                b = score(s, 'level', 0.0, buf=kl, lo=telo, hi=tehi)[0]
                wins += (a > b); tot += 1; d.append(a-b)
        print(f'  {m:8s} beats level in {wins}/{tot} folds; mean {statistics.mean(d):+.1f}pp')

    print('\n=== 5. TRADE COUNTS (per year, 75% Bayes) ===')
    print(f'{"stock":7s}{"level":>9s}{"resid+k":>10s}{"weekly":>9s}')
    for s in NAMES:
        dts = DATA[s][0]; yrs = (dts[-1]-dts[0]).days/365.25
        _, _, ra = run(s, 'level', 0.75)
        _, _, rb = run(s, 'resid', 0.75, best[(s, 'resid')])
        wk = 20 if s == 'NVDA' else 6.5
        print(f'{s:7s}{ra.total_buys/yrs:>9.0f}{rb.total_buys/yrs:>10.0f}{wk:>9.1f}')
    print('DONE')
