"""
The OU sleeve's sigma is measuring the trend, not the noise.

Deployed, OUsig is STDEVP of the last W closes about the window mean -- the dispersion of the
price LEVEL. On a name that ran 90 to 236 over the sample, most of that dispersion is the trend
itself, so the bid buffer ou_buf_k * sigma inflates exactly when the stock is trending, pushing
the bid far below the market and killing fills.

Two corrections, both cheap:
    resid     sigma from the fitted AR(1) residuals -- what the reversion model cannot explain
    detrend   sigma about a linear trend through the window, with the mean re-anchored to the
              fitted value at the window end instead of the arithmetic average

Because sigma changes scale (the residual is about a third of the level dispersion), a
frozen-parameter comparison would be unfair -- ou_buf_k was fitted against the inflated sigma. So
both are reported: frozen, and with ou_buf_k alone re-fitted, which is the one parameter that
pairs with sigma. Everything else is held.

Scored on verified fills, marked to market, over each series' true span, with the same
2025-05-23 half-sample split and a walk-forward of the choice.
"""
import copy, datetime, statistics
from engine import run_model
from daily_window_split import data, params
from five_min import make_checker as fm
from mu_rerun import from_workbook

data['MU'] = from_workbook()
NAMES = ['RKLB', 'TSM', 'VST', 'VRT', 'MU']
MODES = ['level', 'resid', 'detrend']
CUT = datetime.date(2025, 5, 23)
BUFS = [round(0.05 + 0.05*i, 3) for i in range(50)]        # 0.05 .. 2.50
CHK = {}


def chk(s):
    if s not in CHK:
        CHK[s] = fm(s, data[s][0], data[s][1])[0]
    return CHK[s]


def run(s, mode, bayes, buf=None):
    dts, O, H, L, C = data[s]
    p = copy.copy(params[s]); p.bayes_pct = bayes
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
    print('=== 1. OU SLEEVE ALONE (bayes_pct = 0), parameters FROZEN ===')
    print(f'{"stock":7s}' + ''.join(f'{m:>12s}' for m in MODES) + f'{"buys level/resid":>20s}')
    for s in NAMES:
        row = []; buys = []
        for m in MODES:
            a, r = score(s, m, 0.0); row.append(a); buys.append(r.ou_buys)
        print(f'{s:7s}' + ''.join(f'{v:>11.0f}%' for v in row)
              + f'{f"{buys[0]}/{buys[1]}":>20s}')

    print('\n=== 2. OU SLEEVE with ou_buf_k re-fitted (1 parameter, the one paired with sigma) ===')
    best = {}
    print(f'{"stock":7s}' + ''.join(f'{m+" (k)":>18s}' for m in MODES))
    for s in NAMES:
        cells = []
        for m in MODES:
            b = max((score(s, m, 0.0, buf=k)[0], k) for k in BUFS)
            best[(s, m)] = b[1]; cells.append(f'{b[0]:6.0f}% (k={b[1]:.2f})')
        print(f'{s:7s}' + ''.join(f'{c:>18s}' for c in cells))

    print('\n=== 3. HALF-SAMPLE, OU sleeve at its own best k ===')
    print(f'{"stock":7s}' + ''.join(f'{m:>24s}' for m in MODES))
    print(f'{"":7s}' + ''.join(f'{"1st / tested":>24s}' for m in MODES))
    for s in NAMES:
        dts = data[s][0]
        k = next(i for i, d in enumerate(dts) if d >= CUT)
        cells = []
        for m in MODES:
            _, eq, _ = run(s, m, 0.0, best[(s, m)])
            cells.append(f'{ann(eq,dts,0,k):7.0f}% /{ann(eq,dts,k,len(dts)-1):7.0f}%')
        print(f'{s:7s}' + ''.join(f'{c:>24s}' for c in cells))

    print('\n=== 4. WALK-FORWARD: k fitted on train, scored on unseen, level vs best mode ===')
    CUTS = (0.5, 0.667, 0.833, 1.0)
    for m in ('resid', 'detrend'):
        wins = 0; tot = 0; diffs = []
        for s in NAMES:
            dts = data[s][0]; N = len(dts); cuts = [int(N*f) for f in CUTS]
            for j in range(3):
                trhi = cuts[j]; telo, tehi = cuts[j], cuts[j+1]-1
                kb = max((score(s, m, 0.0, buf=k, lo=0, hi=trhi-1)[0], k) for k in BUFS)[1]
                kl = max((score(s, 'level', 0.0, buf=k, lo=0, hi=trhi-1)[0], k) for k in BUFS)[1]
                a = score(s, m, 0.0, buf=kb, lo=telo, hi=tehi)[0]
                b = score(s, 'level', 0.0, buf=kl, lo=telo, hi=tehi)[0]
                wins += (a > b); tot += 1; diffs.append(a-b)
        print(f'  {m:8s} beats level in {wins}/{tot} folds; mean {statistics.mean(diffs):+.1f}pp')

    print('\n=== 5. FULL BOOK at 75% Bayes, parameters frozen except ou_buf_k ===')
    print(f'{"stock":7s}' + ''.join(f'{m:>12s}' for m in MODES))
    means = {m: [] for m in MODES}
    for s in NAMES:
        row = []
        for m in MODES:
            a, _ = score(s, m, 0.75, buf=best[(s, m)]); row.append(a); means[m].append(a)
        print(f'{s:7s}' + ''.join(f'{v:>11.0f}%' for v in row))
    print(f'{"mean":7s}' + ''.join(f'{statistics.mean(means[m]):>11.0f}%' for m in MODES))
    print('DONE')
