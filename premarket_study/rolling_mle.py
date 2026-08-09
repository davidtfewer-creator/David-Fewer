"""
Rolling-MLE drift study: is the price process non-stationary on monthly timescales?

The claim under test (user's hypothesis, 9 Aug 2026): stock behaviour shifts with the
AI-trade market view on ~monthly timescales, so parameters fitted to a 2.2-year window
are a stale average and a periodically refitted model would do better.

The cheap, sharp test: the Kalman local-linear-trend filter's noise scales (lam, phi_L,
psi) have an exact Gaussian likelihood on PRICES — one-step innovations nu_i with
variance S_i, loglik = -0.5*sum(log 2pi + log S_i + nu_i^2/S_i). Days are the sample
(63-126 per window), not trades (6-25), so a 3-6 month window actually identifies them.
Fit by MLE on rolling windows stepped monthly and look at the trajectories:

  - drift coherent with the AI factor's regime  -> non-stationarity confirmed; we learn
    WHICH parameters move and how much, and can size an adaptation mechanism.
  - wander inside the error bars                -> the process is stationary enough; a
    generic vector loses little, and periodic P&L refits would track noise.

Also recorded per window, no fitting needed: the OU sleeve's rolling AR(1) coefficient
and residual sigma (as a fraction of price) at the deployed lookback W — the engine
already computes these each session; here they are summarised per window.

The AI factor follows ai_concentration.py: equal-weight daily close-to-close return of
TSM, VRT, VST, MU; regime = drawdown state of its cumulative index.

Everything here is estimation on prices. No P&L, no fills, no optimiser over backtests.
"""
import csv
import math
import os
import sys

import numpy as np
from scipy.optimize import minimize

# --- deployed configuration (HANDOVER.md section 2) --------------------------------
DEPLOYED = {
    'TSM':  dict(lam=0.462001, phi_L=0.254287, psi=0.065039, ou_W=77),
    'VRT':  dict(lam=0.420699, phi_L=0.425851, psi=0.081656, ou_W=80),
    'VST':  dict(lam=0.373520, phi_L=0.264322, psi=0.096187, ou_W=122),
    'RKLB': dict(lam=0.352847, phi_L=0.237406, psi=0.113048, ou_W=85),
    'MU':   dict(lam=0.600000, phi_L=0.263600, psi=0.010000, ou_W=91),
}
AI_NAMES = ['TSM', 'VRT', 'VST', 'MU']          # ai_concentration.py factor basis
HALF_SPLIT = None   # set to a datetime.date to also report half-sample MLEs

# log-space bounds: wide, generous — the point is to let the data speak
LOG_BOUNDS = [(math.log(0.02), math.log(5.0)),   # lam
              (math.log(0.005), math.log(5.0)),  # phi_L
              (math.log(1e-4), math.log(1.0))]   # psi
BURN = 10           # filter rows at window start excluded from the likelihood


def loglik(C, F, lam, phi_L, psi, burn=BURN):
    """Exact Gaussian log-likelihood of the engine.py LLT recursion on one window.

    Same recursion and same initialisation as engine.run_model (Lvl0=C0, P11=P22=r0,
    P12=0); the first `burn` innovations are excluded so the init convention doesn't
    contaminate the fit.
    """
    n = len(C)
    qL = (phi_L * F) ** 2
    qb = (psi * F) ** 2
    r = (lam * F) ** 2
    lvl, slp = C[0], 0.0
    p11, p12, p22 = r[0], 0.0, r[0]
    ll = 0.0
    for i in range(1, n):
        pred = lvl + slp
        p11m = p11 + 2 * p12 + p22 + qL[i]
        p12m = p12 + p22
        p22m = p22 + qb[i]
        S = p11m + r[i]
        nu = C[i] - pred
        if i > burn:
            ll -= 0.5 * (math.log(2 * math.pi) + math.log(S) + nu * nu / S)
        kL = p11m / S
        kb = p12m / S
        lvl = pred + kL * nu
        slp = slp + kb * nu
        p11 = (1 - kL) * p11m
        p12 = (1 - kL) * p12m
        p22 = p22m - p12m ** 2 / S
    return ll


def fit_window(C, F, x0s):
    """MLE of (lam, phi_L, psi) on one window; multi-start Nelder-Mead in log space.

    Returns (params, standard errors, loglik). SEs from the numerical Hessian of the
    log-space negative loglik, delta-method back to natural scale.
    """
    C = np.asarray(C, float)
    F = np.asarray(F, float)
    neg = lambda z: -loglik(C, F, *np.exp(z))
    lo_b = [b[0] for b in LOG_BOUNDS]
    hi_b = [b[1] for b in LOG_BOUNDS]
    best = None
    for x0 in x0s:
        z0 = np.clip(np.log(x0), lo_b, hi_b)
        res = minimize(neg, z0, method='Nelder-Mead',
                       options=dict(xatol=1e-5, fatol=1e-7, maxiter=2000))
        if best is None or res.fun < best.fun:
            best = res
    z = np.clip(best.x, lo_b, hi_b)
    theta = np.exp(z)
    # numerical Hessian in log space
    h = 1e-3
    H = np.zeros((3, 3))
    f0 = neg(z)
    for a in range(3):
        for b in range(a, 3):
            za = z.copy(); za[a] += h; zb = z.copy(); zb[b] += h
            zab = z.copy(); zab[a] += h; zab[b] += h
            H[a, b] = H[b, a] = (neg(zab) - neg(za) - neg(zb) + f0) / (h * h)
    se = np.full(3, np.nan)
    try:
        cov = np.linalg.inv(H)
        d = np.diag(cov)
        if np.all(d > 0):
            se = np.sqrt(d) * theta          # delta method: se(exp z) = exp(z)*se(z)
    except np.linalg.LinAlgError:
        pass
    return theta, se, -best.fun


def ou_window_stats(C, W, lo, hi):
    """Median rolling AR(1) slope and residual sigma / price over rows [lo, hi].

    Same definitions as engine.py ou_sigma='resid': slope clamped to [0, 0.99],
    residual sigma of the fitted AR(1) about the window mean.
    """
    ars, sigs = [], []
    for i in range(max(lo, W), hi + 1):
        win = C[i - W:i]
        mean_w = sum(win) / W
        y = win[1:]; x = win[:-1]
        n = len(x)
        mx = sum(x) / n; my = sum(y) / n
        num = sum((x[j] - mx) * (y[j] - my) for j in range(n))
        den = sum((x[j] - mx) ** 2 for j in range(n))
        a = min(max(num / den if den else 0.0, 0.0), 0.99)
        e = [win[j] - (mean_w + a * (win[j - 1] - mean_w)) for j in range(1, W)]
        me = sum(e) / len(e)
        sig = math.sqrt(sum((v - me) ** 2 for v in e) / len(e))
        ars.append(a)
        sigs.append(sig / C[i - 1])
    if not ars:
        return float('nan'), float('nan')
    ars.sort(); sigs.sort()
    m = len(ars) // 2
    return ars[m], sigs[m]


def ai_factor(data):
    """Equal-weight daily return of AI_NAMES on their common dates -> (dates, index, dd)."""
    common = None
    for s in AI_NAMES:
        ds = set(data[s][0])
        common = ds if common is None else (common & ds)
    dates = sorted(common)
    idx_of = {s: {d: i for i, d in enumerate(data[s][0])} for s in AI_NAMES}
    rets = []
    for j in range(1, len(dates)):
        r = 0.0
        for s in AI_NAMES:
            C = data[s][4]
            i0, i1 = idx_of[s][dates[j - 1]], idx_of[s][dates[j]]
            r += C[i1] / C[i0] - 1
        rets.append(r / len(AI_NAMES))
    index = [1.0]
    for r in rets:
        index.append(index[-1] * (1 + r))
    peak, dd = 0.0, []
    for v in index:
        peak = max(peak, v)
        dd.append(v / peak - 1)
    return dates, index, dd


def run_study(data, windows=(63, 126), step=21, out_csv='rolling_mle.csv'):
    """data: {name: (dates, O, H, L, C)}. Writes trajectories to out_csv, returns rows."""
    fdates, findex, fdd = ai_factor(data)
    fdd_of = dict(zip(fdates, fdd))
    fix_of = dict(zip(fdates, findex))

    rows = []
    for name, (dts, O, H, L, C) in data.items():
        F = [H[i] - L[i] for i in range(len(C))]
        dep = DEPLOYED.get(name, dict(lam=0.5, phi_L=0.3, psi=0.05, ou_W=80))
        x0s = [np.array([dep['lam'], dep['phi_L'], dep['psi']]),
               np.array([0.8, 0.15, 0.02]),
               np.array([0.3, 0.6, 0.15])]
        N = len(C)

        # full-sample MLE reference
        th_full, se_full, ll_full = fit_window(C, F, x0s)
        print(f'{name}: full-sample MLE  lam {th_full[0]:.3f}±{se_full[0]:.3f}  '
              f'phi_L {th_full[1]:.3f}±{se_full[1]:.3f}  psi {th_full[2]:.4f}±{se_full[2]:.4f}'
              f'   (deployed {dep["lam"]:.3f}/{dep["phi_L"]:.3f}/{dep["psi"]:.4f})', flush=True)
        rows.append(dict(name=name, window='full', end_date=dts[-1], n=N,
                         lam=th_full[0], lam_se=se_full[0], phi_L=th_full[1],
                         phi_L_se=se_full[1], psi=th_full[2], psi_se=se_full[2],
                         ou_ar=float('nan'), ou_sig=float('nan'),
                         ai_dd=float('nan'), ai_index=float('nan'), loglik=ll_full))

        for Wn in windows:
            ends = list(range(Wn, N, step))
            if ends and ends[-1] != N - 1:
                ends.append(N - 1)
            for hi in ends:
                lo = hi - Wn + 1
                th, se, ll = fit_window(C[lo:hi + 1], F[lo:hi + 1], x0s + [th_full])
                oar, osig = ou_window_stats(C, dep['ou_W'], lo, hi)
                d = dts[hi]
                rows.append(dict(name=name, window=Wn, end_date=d, n=Wn,
                                 lam=th[0], lam_se=se[0], phi_L=th[1], phi_L_se=se[1],
                                 psi=th[2], psi_se=se[2], ou_ar=oar, ou_sig=osig,
                                 ai_dd=fdd_of.get(d, float('nan')),
                                 ai_index=fix_of.get(d, float('nan')), loglik=ll))
            print(f'  {name} W={Wn}: {len(ends)} windows done', flush=True)

    with open(out_csv, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f'wrote {out_csv} ({len(rows)} rows)', flush=True)
    return rows


if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else None
    if src is None or not os.path.exists(src):
        sys.exit('usage: rolling_mle.py <workbook.xlsx | csv_dir>  (data not in repo)')
    if src.endswith('.xlsx'):
        from mle_load import load_workbook_ohlc
        data = load_workbook_ohlc(src)
    else:
        from mle_load import load_csv_dir
        data = load_csv_dir(src)
    run_study(data)
