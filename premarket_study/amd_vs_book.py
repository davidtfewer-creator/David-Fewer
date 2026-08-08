"""
AMD against the incumbents on one basis, end to end.

Why this cannot be answered from what is already computed. AMD's number comes from the
admission pipeline: daily bars aggregated from 5-minute data, parameters fitted on the FIRST
half only and frozen, scored on the second with verified fills and residual OU sigma. The
incumbents' published figures come from somewhere else entirely -- workbook daily bars,
workbook parameters that were chosen with the whole sample visible, and in the VST review, the
at-open floor. Setting 65.5% beside 158% would be comparing a frozen out-of-sample score
against an in-sample one on different bars. That comparison flatters the incumbents by exactly
the amount the blade is designed to remove.

So every name here is recomputed. Same 5-minute source, same daily aggregation, same split
(2025-05-23), same BOUNDS and robust objective, same verified-fill checker, same residual
sigma. The incumbents' deployed parameters are deliberately NOT used -- the point is what each
name is worth to a fitter that has seen only the first half, which is the only basis on which a
newcomer can be judged.

Four columns decide it, in the order the admission process weighs them:

  FITTED / TESTED   the blade. Tested is the number that admits or rejects; fitted is shown
                    only so the spread is visible, since a wide spread is the overfitting tell
                    that was used against VLO.
  BUYS/YR           how often the name actually works. A high return on 20 trades a year is a
                    thinner claim than the same return on 70.
  MAX DD            drawdown through the tested half.
  CORR              daily share-return correlation to the equal-weighted basket of the OTHER
                    names in the set. For an incumbent that is the other four; for AMD it is
                    all five. The asymmetry is unavoidable and is stated rather than hidden --
                    a member cannot be correlated with itself.

Buy-and-hold is carried alongside because on the deployed rule a name is only worth holding in
the book if the rule beats simply owning it over the same window.

Run:  python3 amd_vs_book.py
"""
import numpy as np

import admit_candidates as A
import nine_computed as NC
import ramp_premium as R
from engine import Params

UP = '/root/.claude/uploads/822d405e-f99b-5b59-9c6b-87e725054402'
FIVE = {
    'RKLB': f'{UP}/4d3fd234-RKLB_5min_Apr2024Aug2026.xlsx',
    'TSM':  f'{UP}/19b5b8d9-TSM_5min_Apr2024Aug2026.xlsx',
    'VST':  f'{UP}/f7870655-VST_5min_Apr2024Aug2026.xlsx',
    'VRT':  f'{UP}/72c19f40-VRT_5min_Apr2024Aug2026.xlsx',
    'MU':   f'{UP}/691cafca-MU_5min_Apr2024Aug2026.xlsx',
}
PATHS = dict(FIVE, AMD=A.CAND['AMD'])
ORDER = ('AMD', 'RKLB', 'TSM', 'VST', 'VRT', 'MU')
CAPITAL = 1_000_000

# Quoted, not recomputed: these came out of admit_candidates.py on this exact basis, so they
# are already like-for-like. Recomputing them would burn twenty minutes to reproduce them.
ACCEPTED = {'GM': 56.5, 'CF': 54.7, 'VLO': 137.9}


def main():
    print('loading 5-minute data...', flush=True)
    L = {}
    for n, p in PATHS.items():
        L[n] = A.five_min(p)
        print(f'  {n}: {len(L[n][0][0])} sessions '
              f'{L[n][0][0][0]} .. {L[n][0][0][-1]}', flush=True)

    t0 = Params(capital=CAPITAL, years=1.0)
    rows = {}
    for n in ORDER:
        bars, dv, idx = L[n]
        d, O, H, Lo, C = bars
        chk = R.make_checker(idx, d, O)
        iS = next(k for k, x in enumerate(d) if x >= R.SPLIT)
        scr = A.screen(n, bars, dv)

        vec = A.fit(bars, chk, t0, 0, iS - 1, floor=8)
        f_ret, f_buys, f_dd, _ = A.score(bars, chk, vec, t0, 0, iS - 1)
        t_ret, t_buys, t_dd, _ = A.score(bars, chk, vec, t0, iS, len(d) - 1)

        Cn = np.array(C, dtype=float)
        yrs_t = (d[-1] - d[iS]).days / 365.25
        bh_t = (Cn[-1] / Cn[iS]) ** (1 / yrs_t) - 1

        rows[n] = dict(vec=vec, fit=f_ret, test=t_ret, buys=t_buys, dd=t_dd,
                       bh=bh_t, scr=scr)
        print(f'  {n:5s} fitted {100*f_ret:+7.1f}%  tested {100*t_ret:+7.1f}%  '
              f'{t_buys:5.0f} buys/yr  DD {100*t_dd:5.1f}%', flush=True)

    # ---- correlation to the rest of the set -----------------------------------
    common = sorted(set.intersection(*[set(L[n][0][0]) for n in ORDER]))
    M = {}
    for n in ORDER:
        d, _O, _H, _L, C = L[n][0]
        ix = {t: k for k, t in enumerate(d)}
        s = np.array([C[ix[t]] for t in common], dtype=float)
        M[n] = s[1:] / s[:-1] - 1
    corr = {}
    for n in ORDER:
        rest = [m for m in ORDER if m != n and m != 'AMD'] if n != 'AMD' else list(FIVE)
        basket = np.mean([M[m] for m in rest], axis=0)
        corr[n] = float(np.corrcoef(M[n], basket)[0, 1])

    # ---- output ---------------------------------------------------------------
    print('\n\n=== screen, identical window and bars ===\n')
    print(f"{'name':6s} {'B&H total':>10s} {'B&H p.a.':>9s} {'avg range':>10s} "
          f"{'worst day':>10s} {'median $vol':>13s}")
    for n in ORDER:
        s = rows[n]['scr']
        print(f"{n:6s} {100*s['drift']:9.1f}% {100*s['ann']:8.1f}% {100*s['rng']:9.2f}% "
              f"{100*s['worst']:9.1f}% {s['dv']/1e6:12.0f}m")

    print('\n\n=== the blade: fit first half, freeze, score the tested half ===')
    print(f'    split {R.SPLIT}; verified fills; residual OU sigma; '
          f'incumbents refitted, NOT deployed parameters\n')
    print(f"{'name':6s} {'fitted':>9s} {'tested':>9s} {'spread':>9s} {'buys/yr':>9s} "
          f"{'max DD':>8s} {'B&H tested':>11s} {'vs B&H':>9s} {'corr rest':>10s}")
    for n in ORDER:
        r = rows[n]
        mark = '  <-- candidate' if n == 'AMD' else ''
        print(f"{n:6s} {100*r['fit']:+8.1f}% {100*r['test']:+8.1f}% "
              f"{100*abs(r['test']-r['fit']):8.1f}pp {r['buys']:9.0f} "
              f"{100*r['dd']:7.1f}% {100*r['bh']:10.1f}% "
              f"{100*(r['test']-r['bh']):+8.1f}pp {corr[n]:10.3f}{mark}")
    print('\n  quoted from the same pipeline (admit_candidates.py), not recomputed here:')
    print('    ' + '  |  '.join(f'{k} tested {v}%' for k, v in ACCEPTED.items()))

    # ---- ranks ----------------------------------------------------------------
    print('\n\n=== where AMD sits ===\n')
    for lab, key, rev in (('tested return', 'test', True),
                          ('edge over buy-and-hold', None, True),
                          ('trade frequency', 'buys', True),
                          ('fitted/tested spread (narrow is better)', None, False),
                          ('max drawdown (small is better)', 'dd', False),
                          ('correlation to the rest (low is better)', None, False)):
        if lab.startswith('edge'):
            val = {n: rows[n]['test'] - rows[n]['bh'] for n in ORDER}
        elif lab.startswith('fitted/'):
            val = {n: abs(rows[n]['test'] - rows[n]['fit']) for n in ORDER}
        elif lab.startswith('correlation'):
            val = corr
        else:
            val = {n: rows[n][key] for n in ORDER}
        rank = sorted(ORDER, key=lambda n: -val[n] if rev else val[n])
        print(f'  {lab:40s} {rank.index("AMD")+1} of 6   '
              + ' > '.join(rank))

    print('\n\n=== deployable vectors, first-half fit ===\n')
    print(f"{'name':6s} " + ' '.join(f'{x:>7s}' for x in
                                     ('lam', 'phiL', 'psi', 'k', 'prem', 'cap',
                                      'oubuf', 'ouprem', 'oucap', 'ouW')))
    for n in ORDER:
        print(f'{n:6s} ' + ' '.join(f'{v:7.3f}' for v in rows[n]['vec']))


if __name__ == '__main__':
    main()
