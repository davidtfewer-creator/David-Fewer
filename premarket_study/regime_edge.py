"""
Regime-conditional edge: does the strategy's skill depend on the state of the AI theme?

This is the constructive version of the objection that a walk-forward is meaningless when the
underlying theme is moving through step changes. Rather than assume stationarity or abandon
history, condition on the regime and report the edge inside each one. You then supply the
forward view -- "I expect continued step-ups in adoption and spending" -- and read off the cell
that matches it, instead of relying on a single blended number that averages over regimes you
do not expect to see again.

What is measured
----------------
A daily EXPOSURE-MATCHED edge, per name:

    edge_t = r_model_t - [ e_t * r_stock_t + (1 - e_t) * rf_daily ]

where e_t is the fraction of the name's two sleeves already invested going into session t. The
subtraction is the whole point: raw returns confound the rules with the market, so a rising
theme would make the strategy look skilful in exactly the regime the theme rose. The edge asks
only whether the entry and exit rules beat holding the same amount of stock for the same time.
Both are reported side by side, because the gap between them IS the finding.

Regimes (all strictly trailing, known at the previous close -- no lookahead)
---------------------------------------------------------------------------
An AI factor is built as the equal-weight daily return of TSM, VRT and VST, following the
convention already used in ai_concentration.py (which also had MU, absent from this workbook).
When one of those three is the name under test it is dropped from the factor, so a name is
never bucketed by a variable it helps determine.

    DRIFT      60-session trailing return of the factor -- is the theme stepping up or not
    VOL        60-session realised volatility of the factor
    DRAWDOWN   the factor's distance below its trailing 252-session peak

Terciles are cut on the pooled distribution so each bucket carries a third of the sessions.

Run:  python3 regime_edge.py
"""
import numpy as np

import ramp_premium as R
from engine import Params

ALL_NAMES = ('NVDA', 'AVGO', 'TSM', 'RKLB', 'VST', 'VRT', 'TSLA', 'PLTR', 'SOFI', 'SPOT')
FACTOR_NAMES = ('TSM', 'VRT', 'VST')
HIGH = (0.040, 0.045, 0.050, 0.060)
CONFIGS = (('deployed', None, 50), ('4-6% / 200d', HIGH, 200))
RF_D = 0.0314 / 252
LOOK_DRIFT, LOOK_VOL, LOOK_PEAK = 60, 60, 252


def load_all():
    data = {}
    for n in ALL_NAMES:
        d, O, H, L, C = R.load_feed(n)
        data[n] = (d, O, H, L, C)
    ref = data[ALL_NAMES[0]][0]
    for n in ALL_NAMES:
        assert data[n][0] == ref, f'{n} dates not aligned'
    return data, ref


def factor_returns(data, exclude=None):
    names = [n for n in FACTOR_NAMES if n != exclude]
    N = len(data[names[0]][0])
    out = np.zeros(N)
    for n in names:
        C = np.array(data[n][4])
        r = np.zeros(N)
        r[1:] = C[1:] / C[:-1] - 1
        out += r
    return out / len(names)


def regimes(fr):
    """Trailing regime variables, aligned so index t uses information through t-1."""
    N = len(fr)
    lvl = np.cumprod(1 + fr)
    drift = np.full(N, np.nan)
    vol = np.full(N, np.nan)
    ddn = np.full(N, np.nan)
    for t in range(1, N):
        if t - 1 >= LOOK_DRIFT:
            drift[t] = lvl[t - 1] / lvl[t - 1 - LOOK_DRIFT] - 1
        if t - 1 >= LOOK_VOL:
            vol[t] = fr[t - LOOK_VOL:t].std() * np.sqrt(252)
        if t - 1 >= 20:
            peak = lvl[max(0, t - LOOK_PEAK):t].max()
            ddn[t] = lvl[t - 1] / peak - 1
    return dict(drift=drift, vol=vol, drawdown=ddn)


def edge_series(name, args, p, band, stop):
    """Daily exposure-matched edge and raw model return, median over the premium band."""
    d, O, H, L, C = args
    N = len(d)
    Cn = np.array(C)
    rstock = np.zeros(N)
    rstock[1:] = Cn[1:] / Cn[:-1] - 1
    prems = [None] if band is None else list(band)
    E, M, X = [], [], []
    for prem in prems:
        q = Params(**{**p.__dict__, 'stop_days': stop}) if prem is None else \
            Params(**{**p.__dict__, 'premium': prem, 'ou_prem': prem, 'stop_days': stop})
        r = R.run(name, ramp=None, mode='at_open', p=q, data=args, idx=None)
        eq = np.array(r.frames['equity'])
        t1, t2 = r.frames['t1'], r.frames['t2']
        rm = np.zeros(N)
        ok = eq[:-1] > 0
        rm[1:][ok] = eq[1:][ok] / eq[:-1][ok] - 1
        expo = np.zeros(N)
        for t in range(1, N):
            expo[t] = (t1['AE'][t - 1] + t2['AE'][t - 1]) / 2.0
        bench = expo * rstock + (1 - expo) * RF_D
        E.append(rm - bench)
        M.append(rm)
        X.append(expo)
    return np.median(E, axis=0), np.median(M, axis=0), np.median(X, axis=0)


def main():
    data, dates = load_all()
    N = len(dates)

    series = {}
    for label, band, stop in CONFIGS:
        for n in ALL_NAMES:
            d, O, H, L, C = data[n]
            p, _ = R.load_params(n, years=(d[-1] - d[0]).days / 365.25)
            series[(label, n)] = edge_series(n, data[n], p, band, stop)
    regs = {n: regimes(factor_returns(data, exclude=n if n in FACTOR_NAMES else None))
            for n in ALL_NAMES}
    # regime for reporting "where are we now" uses the full factor
    now = regimes(factor_returns(data))

    for var, pretty in (('drift', f'AI factor {LOOK_DRIFT}-session trailing return'),
                        ('vol', f'AI factor {LOOK_VOL}-session realised volatility'),
                        ('drawdown', f'AI factor drawdown from its {LOOK_PEAK}-session peak')):
        pooled = np.concatenate([regs[n][var][~np.isnan(regs[n][var])] for n in ALL_NAMES])
        q1, q2 = np.percentile(pooled, [33.333, 66.667])
        buckets = (('low', -np.inf, q1), ('mid', q1, q2), ('high', q2, np.inf))
        print(f'\n{"="*104}')
        print(f'REGIME: {pretty}')
        print(f'  tercile cuts at {q1:+.4f} and {q2:+.4f}   |   '
              f'latest reading {now[var][-1]:+.4f} -> '
              f'{[b[0] for b in buckets if b[1] <= now[var][-1] < b[2]][0].upper()}')
        print(f'{"="*104}')
        for label, _b, _s in CONFIGS:
            print(f'\n  -- {label} --')
            print(f"    {'bucket':8s} {'sessions':>9s} {'model ret':>11s} {'stock ret':>11s} "
                  f"{'exposure':>9s} {'EDGE':>9s} {'names >0':>9s} {'t':>6s}")
            for bname, lo, hi in buckets:
                ed_all, mo_all, st_all, ex_all = [], [], [], []
                per_name = []
                nsess = 0
                for n in ALL_NAMES:
                    rv = regs[n][var]
                    m = (rv >= lo) & (rv < hi) & ~np.isnan(rv)
                    if m.sum() == 0:
                        continue
                    e, mo, ex = series[(label, n)]
                    Cn = np.array(data[n][4])
                    rs = np.zeros(N)
                    rs[1:] = Cn[1:] / Cn[:-1] - 1
                    ed_all.append(e[m]); mo_all.append(mo[m])
                    st_all.append(rs[m]); ex_all.append(ex[m])
                    per_name.append(e[m].mean())
                    nsess += int(m.sum())
                ed = np.concatenate(ed_all)
                se = ed.std(ddof=1) / np.sqrt(len(ed)) if len(ed) > 1 else np.nan
                t = ed.mean() / se if se and se > 0 else np.nan
                print(f"    {bname:8s} {nsess:9d} "
                      f"{100*252*np.concatenate(mo_all).mean():10.1f}% "
                      f"{100*252*np.concatenate(st_all).mean():10.1f}% "
                      f"{100*np.concatenate(ex_all).mean():8.0f}% "
                      f"{100*252*ed.mean():+8.1f}% "
                      f"{sum(1 for x in per_name if x > 0):5d}/10 {t:6.1f}")
        print()

    # ---- how much independent evidence is really behind those buckets? --------------
    print(f'\n{"="*104}')
    print('HOW MUCH EVIDENCE IS ACTUALLY THERE')
    print(f'{"="*104}\n')
    print('  The session counts above are NAME-sessions. The ten names share one set of dates and')
    print('  correlate 0.48-0.58, so ~1750 name-sessions is at most ~175 calendar sessions, and')
    print('  those are not independent either: a regime persists, so the real unit is the EPISODE.')
    print()
    print(f"  {'regime':10s} {'calendar sessions':>18s} {'episodes low/mid/high':>24s} "
          f"{'median episode':>16s}")
    for var in ('drift', 'vol', 'drawdown'):
        rv = now[var]
        ok = ~np.isnan(rv)
        q1, q2 = np.percentile(rv[ok], [33.333, 66.667])
        lab = np.full(len(rv), -1)
        lab[ok & (rv < q1)] = 0
        lab[ok & (rv >= q1) & (rv < q2)] = 1
        lab[ok & (rv >= q2)] = 2
        runs, prev, start = [], -1, None
        for i, x in enumerate(lab):
            if x != prev:
                if prev in (0, 1, 2) and start is not None:
                    runs.append((prev, i - start))
                prev, start = x, i
        if prev in (0, 1, 2) and start is not None:
            runs.append((prev, len(lab) - start))
        cnt = {0: 0, 1: 0, 2: 0}
        for b, _ln in runs:
            cnt[b] += 1
        print(f"  {var:10s} {int(ok.sum()/3):18d} "
              f"{f'{cnt[0]} / {cnt[1]} / {cnt[2]}':>24s} "
              f"{int(np.median([l for _b, l in runs])):13d} d")
    print()
    print('  A dozen episodes per bucket, most of them short, is enough to form a hypothesis and')
    print('  not enough to price one. Treat the cross-name agreement (the "names >0" column) as the')
    print('  informative statistic and the t column as decorative -- it assumes an independence')
    print('  the data does not have.')
    print()
    print('  Returns are annualised as mean daily x 252 (a difference series does not compound'
          ' meaningfully).')


if __name__ == '__main__':
    main()
