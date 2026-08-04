"""
Re-run the Bayes/OU capital split with the OU sleeve's sigma corrected.

The 75% Bayes tilt was chosen against an OU sleeve whose bid buffer inflated on trending names,
because its sigma measured the price level's dispersion rather than the AR(1) residual. If part
of the tilt was compensating for that, the efficient split should move back toward OU now the
sleeve is specified properly -- and that would be worth more than the 3pp the correction itself
adds at the book level.

Two sigma modes are run side by side:
    level   the deployed definition, with ou_buf_k at its deployed value
    resid   the corrected definition, with ou_buf_k re-fitted per name (one parameter, disclosed)

and, to separate the correction from the re-fit, resid is also run at the DEPLOYED ou_buf_k.

The split is then walk-forwarded exactly as before: the share is chosen on the training window
only and scored on unseen sessions against the deployed 75%.
"""
import copy, datetime, statistics
from engine import run_model
from daily_window_split import data, params
from five_min import make_checker as fm
from mu_rerun import from_workbook

data['MU'] = from_workbook()
NAMES = ['RKLB', 'TSM', 'VST', 'VRT', 'MU']
SHARES = sorted(set([round(0.1*i, 2) for i in range(11)] + [0.75]))
BUF_RESID = {'RKLB': 0.25, 'TSM': 0.20, 'VST': 0.65, 'VRT': 0.40, 'MU': 0.75}
CUTS = (0.5, 0.667, 0.833, 1.0)
DEPLOYED = 0.75
CHK = {}


def chk(s):
    if s not in CHK: CHK[s] = fm(s, data[s][0], data[s][1])[0]
    return CHK[s]


def eq_of(s, mode, bayes, buf):
    dts, O, H, L, C = data[s]
    p = copy.copy(params[s]); p.bayes_pct = bayes
    if buf is not None: p.ou_buf_k = buf
    p.years = (dts[-1]-dts[0]).days/365.25
    r = run_model(dts, O, H, L, C, p, ou_sigma=mode, collect=True, same_day_exit=chk(s))
    return dts, r.frames['equity'], r


def ann(eq, dts, lo, hi):
    d = (dts[hi]-dts[lo]).days
    return ((eq[hi]/eq[lo])**(365.25/d)-1)*100 if eq[lo] > 0 and d else float('nan')


CONFIGS = [('level  (deployed k)', 'level', None),
           ('resid  (deployed k)', 'resid', None),
           ('resid  (refit k)', 'resid', 'fit')]


def buf_for(s, spec):
    return BUF_RESID[s] if spec == 'fit' else None


if __name__ == '__main__':
    print('=== 1. RETURN BY BAYES SHARE (verified, marked to market) ===')
    curves = {}
    for lbl, mode, spec in CONFIGS:
        print(f'\n{lbl}')
        print(f'{"stock":7s}' + ''.join(f'{int(b*100):>6d}%' for b in SHARES) + f'{"best":>8s}')
        book = []
        for s in NAMES:
            row = []
            for b in SHARES:
                dts, eq, _ = eq_of(s, mode, b, buf_for(s, spec))
                row.append(ann(eq, dts, 0, len(dts)-1))
            curves[(lbl, s)] = row
            book.append(row)
            bi = max(range(len(SHARES)), key=lambda i: row[i])
            print(f'{s:7s}' + ''.join(f'{v:>6.0f} ' for v in row) + f'{SHARES[bi]:>7.0%}')
        mean = [statistics.mean(r[i] for r in book) for i in range(len(SHARES))]
        bi = max(range(len(SHARES)), key=lambda i: mean[i])
        print(f'{"MEAN":7s}' + ''.join(f'{v:>6.0f} ' for v in mean)
              + f'{SHARES[bi]:>7.0%}   (deployed 75% -> {mean[SHARES.index(0.75)]:.0f}%)')

    print('\n=== 2. WALK-FORWARD ON THE SPLIT (share chosen on train, scored on unseen) ===')
    for lbl, mode, spec in CONFIGS:
        wins = 0; tot = 0; d = []; picks = []
        for s in NAMES:
            dts = data[s][0]; N = len(dts); cuts = [int(N*f) for f in CUTS]
            eqs = {b: eq_of(s, mode, b, buf_for(s, spec))[1] for b in SHARES}
            for j in range(3):
                trhi = cuts[j]; telo, tehi = cuts[j], cuts[j+1]-1
                bb = max(SHARES, key=lambda b: eqs[b][trhi-1]/eqs[b][0])
                picks.append(bb)
                a = eqs[bb][tehi]/eqs[bb][telo]-1
                c = eqs[DEPLOYED][tehi]/eqs[DEPLOYED][telo]-1
                wins += (a > c); tot += 1; d.append((a-c)*100)
        print(f'  {lbl:22s} chosen beats 75% in {wins:2d}/{tot} folds; '
              f'mean {statistics.mean(d):+5.1f}pp; median share chosen '
              f'{statistics.median(picks):.0%}')

    print('\n=== 3. DEPLOYED vs CORRECTED, like for like at 75% Bayes ===')
    print(f'{"stock":7s}{"level":>10s}{"resid dep k":>13s}{"resid fit k":>13s}{"gain":>8s}')
    tot = {0: [], 1: [], 2: []}
    for s in NAMES:
        vals = []
        for i, (lbl, mode, spec) in enumerate(CONFIGS):
            dts, eq, _ = eq_of(s, mode, DEPLOYED, buf_for(s, spec))
            v = ann(eq, dts, 0, len(dts)-1); vals.append(v); tot[i].append(v)
        print(f'{s:7s}{vals[0]:>9.0f}%{vals[1]:>12.0f}%{vals[2]:>12.0f}%'
              f'{vals[2]-vals[0]:>+7.0f}pp')
    print(f'{"mean":7s}' + ''.join(f'{statistics.mean(tot[i]):>9.0f}%' if i == 0
                                   else f'{statistics.mean(tot[i]):>12.0f}%' for i in range(3)))
    print('DONE')
