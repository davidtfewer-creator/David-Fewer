"""
Read rolling_mle.csv and answer the drift question with numbers.

For each name and window length, and each of (lam, phi_L, psi):

  CHI2/DOF   on NON-OVERLAPPING windows only (every ceil(W/step)-th window), against
             the full-sample MLE: mean of ((theta_w - theta_full)/SE_w)^2. Under
             stationarity this is ~1 (the synthetic calibration in test_rolling_mle
             gives median |z| ~ 1.0). Values well above 1 mean real movement.
  SPREAD     IQR of the window estimates, natural units, for scale.
  REGIME     Spearman correlation of the trajectory (all windows) with the AI factor
             drawdown at the window end, and with the factor's 63-day return. With
             ~9 independent looks, |rho| below ~0.5 is noise; report it, don't lean
             on it.

Same treatment for the OU rolling AR(1) and residual sigma (no SEs there; spread and
regime correlation only).

Output: console tables + mle_drift.png (trajectories with +/-1SE bands over the AI
factor drawdown).
"""
import csv
import math
from collections import defaultdict
from datetime import date

import numpy as np
from scipy import stats

STEP = 21
PARAMS = ['lam', 'phi_L', 'psi']


def load(path='rolling_mle.csv'):
    rows = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            for k in r:
                if k not in ('name', 'window', 'end_date'):
                    r[k] = float(r[k]) if r[k] not in ('', 'nan') else float('nan')
            r['end_date'] = date.fromisoformat(r['end_date'])
            rows.append(r)
    return rows


def main():
    rows = load()
    names = sorted({r['name'] for r in rows})
    full = {r['name']: r for r in rows if r['window'] == 'full'}
    byNW = defaultdict(list)
    for r in rows:
        if r['window'] != 'full':
            byNW[(r['name'], int(float(r['window'])))].append(r)
    for v in byNW.values():
        v.sort(key=lambda r: r['end_date'])

    print('=' * 100)
    print('DRIFT TEST — chi2/dof of non-overlapping windows vs the full-sample MLE '
          '(stationary ~ 1), IQR across all windows, Spearman rho vs AI drawdown')
    print('=' * 100)
    hdr = f'{"name":6s}{"W":>5s}' + ''.join(
        f'{p+" x2/dof":>12s}{p+" IQR":>10s}{p+" rho":>9s}' for p in PARAMS)
    print(hdr)
    summary = {}
    for (name, W), rs in sorted(byNW.items()):
        stride = math.ceil(W / STEP)
        indep = rs[::stride]
        line = f'{name:6s}{W:>5d}'
        for p in PARAMS:
            th_f = full[name][p]
            zs = [((r[p] - th_f) / r[p + '_se']) ** 2 for r in indep
                  if np.isfinite(r[p + '_se']) and r[p + '_se'] > 0]
            chi2 = float(np.mean(zs)) if zs else float('nan')
            vals = [r[p] for r in rs]
            iqr = float(np.percentile(vals, 75) - np.percentile(vals, 25))
            dd = [r['ai_dd'] for r in rs]
            ok = [i for i in range(len(rs)) if np.isfinite(dd[i])]
            rho = stats.spearmanr([vals[i] for i in ok], [dd[i] for i in ok]).statistic \
                if len(ok) > 4 else float('nan')
            summary[(name, W, p)] = dict(chi2=chi2, iqr=iqr, rho=rho, n_indep=len(indep))
            line += f'{chi2:>12.2f}{iqr:>10.4f}{rho:>9.2f}'
        print(line)

    print()
    print('OU rolling stats (deployed W lookback), spread and regime correlation:')
    print(f'{"name":6s}{"W":>5s}{"AR med":>9s}{"AR IQR":>9s}{"AR rho":>9s}'
          f'{"sig med":>10s}{"sig IQR":>10s}{"sig rho":>10s}')
    for (name, W), rs in sorted(byNW.items()):
        if W != 126:
            continue
        ars = [r['ou_ar'] for r in rs if np.isfinite(r['ou_ar'])]
        sigs = [r['ou_sig'] for r in rs if np.isfinite(r['ou_sig'])]
        dd = [r['ai_dd'] for r in rs]
        ok = [i for i in range(len(rs)) if np.isfinite(dd[i]) and np.isfinite(rs[i]['ou_ar'])]
        rho_a = stats.spearmanr([rs[i]['ou_ar'] for i in ok], [dd[i] for i in ok]).statistic
        rho_s = stats.spearmanr([rs[i]['ou_sig'] for i in ok], [dd[i] for i in ok]).statistic
        print(f'{name:6s}{W:>5d}{np.median(ars):>9.3f}'
              f'{np.percentile(ars,75)-np.percentile(ars,25):>9.3f}{rho_a:>9.2f}'
              f'{np.median(sigs)*100:>9.2f}%{(np.percentile(sigs,75)-np.percentile(sigs,25))*100:>9.2f}%'
              f'{rho_s:>10.2f}')

    # ---------------- plot ----------------
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    W = 126
    fig, axes = plt.subplots(len(names), 4, figsize=(19, 3.0 * len(names)),
                             sharex=True, squeeze=False)
    for i, name in enumerate(names):
        rs = byNW[(name, W)]
        ds = [r['end_date'] for r in rs]
        for j, p in enumerate(PARAMS):
            ax = axes[i][j]
            v = np.array([r[p] for r in rs])
            se = np.array([r[p + '_se'] for r in rs])
            ax.plot(ds, v, '-o', ms=2.5, lw=1.2, color='#1f6f8b')
            m = np.isfinite(se)
            ax.fill_between(np.array(ds)[m], (v - se)[m], (v + se)[m],
                            alpha=0.25, color='#1f6f8b', lw=0)
            ax.axhline(full[name][p], color='#c44536', lw=1.0, ls='--')
            s = summary[(name, W, p)]
            ax.set_title(f'{name} {p}   x2/dof {s["chi2"]:.1f}  rho {s["rho"]:.2f}',
                         fontsize=9)
            ax.tick_params(labelsize=7)
        ax = axes[i][3]
        dd = [r['ai_dd'] for r in rs]
        ax.fill_between(ds, [d * 100 for d in dd], 0, color='#888', alpha=0.5)
        ax2 = ax.twinx()
        ax2.plot(ds, [r['ou_sig'] * 100 for r in rs], color='#7a5195', lw=1.2)
        ax2.tick_params(labelsize=7, colors='#7a5195')
        ax.set_title(f'{name}: AI drawdown %  |  OU resid sigma % (purple)', fontsize=9)
        ax.tick_params(labelsize=7)
    fig.suptitle(f'Rolling {W}-day MLE, stepped {STEP}d — dashed red = full-sample MLE',
                 fontsize=11)
    fig.autofmt_xdate()
    fig.tight_layout(rect=[0, 0, 1, 0.98])
    fig.savefig('mle_drift.png', dpi=110)
    print('\nwrote mle_drift.png')


if __name__ == '__main__':
    main()
