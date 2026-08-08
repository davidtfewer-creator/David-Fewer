"""
Planned return and trade frequency for every name in and around the book, on one basis.

NOMENCLATURE, fixed here and used consistently.

  FITTED return      scored on data the parameters were fitted on. Never a planning number.
  TESTED return      scored on a window the parameters have never seen.
  PLANNED return     the consolidation: the MEDIAN of a name's tested windows, annualised.
                     This is the repository's recorded convention -- handover section 5,
                     "planning figure = parameter-neighbourhood median, or full-sample less the
                     measured out-of-sample haircut, never a raw fitted number" -- and section 6
                     applied it as "from windows nothing had seen (3 folds + the half-sample
                     test), median", which is what produced GM 33%, VLO 35%, CF 41%.
  POTENTIAL return   full-sample fitted. Shown nowhere here; it is not evidence.

Four tested windows per name, from three fits:

  fit A   sessions 0..286      -> scores fold 1 [287..386]  AND  the half-sample tested half
                                  [287..586], which is the FROZEN arm over the whole unseen span
  fit B   sessions 0..386      -> scores fold 2 [387..486]
  fit C   sessions 0..486      -> scores fold 3 [487..586]

Fit A's train is the half-sample split (2025-05-23) to the session, so the blade and the first
walk-forward fold share one fit rather than duplicating it. Every score is annualised so a
100-session fold and a 300-session half are on the same footing.

Two headline numbers, per the user's ranking of what matters:

  PLANNED      median of the four tested windows, annualised.
  BUYS/YR      over the three DISJOINT folds only -- the half-sample window overlaps all three
               and would double-count.

The median is the point of the metric. One fold that annualises to +140% off a 100-session run
does not move it, and neither does one that annualises to -40%. Correlation is computed and
reported at the end but binds on nothing: which names follow the AI trade is a judgement call
about desired weighting, not a gate.

Verified fills and residual OU sigma throughout. Incumbents are REFITTED, not run on their
deployed parameters, so that every name is judged by what a fitter that had seen only the
training window would have produced.

Run:  python3 planned_return.py [nproc]
"""
import multiprocessing as mp_pool
import sys

import numpy as np

import admit_candidates as A
import nine_computed as NC
import ramp_premium as R
from engine import Params
from optimise_candidates import BOUNDS, NAMES

# ---------------------------------------------------------------------------------------------
# psi bound correction. The shipped cap of 0.1000 was excluding known-good configurations and
# pinning fitters at the boundary, which is on the house list of overfitting tells:
#   * RKLB's DEPLOYED psi is 0.1130 -- above the cap, so no refit could ever rediscover the
#     vector the book actually trades;
#   * VRT's fitter, given room, goes to 0.20-0.22 and its tested half improves from +40.1% to
#     +80.1%. Its published +48.2% planned return was understated by the bound alone.
# Patched on admit_candidates rather than at source: A.fit and A.robust both read that module's
# BOUNDS, and the Pool workers fork after this runs, so they inherit it. Nothing else in the
# repository changes behaviour.
# Widening psi is a correctness fix backed by both names above. No other bound is touched --
# the boundary-seeking report at the end of this script is what would evidence the next one.
# ---------------------------------------------------------------------------------------------
WIDE = list(BOUNDS)
WIDE[2] = (0.001, 0.25)
A.BOUNDS = WIDE

UP = '/root/.claude/uploads/822d405e-f99b-5b59-9c6b-87e725054402'
INCUMBENT = {
    'RKLB': f'{UP}/4d3fd234-RKLB_5min_Apr2024Aug2026.xlsx',
    'TSM':  f'{UP}/19b5b8d9-TSM_5min_Apr2024Aug2026.xlsx',
    'VST':  f'{UP}/f7870655-VST_5min_Apr2024Aug2026.xlsx',
    'VRT':  f'{UP}/72c19f40-VRT_5min_Apr2024Aug2026.xlsx',
    'MU':   f'{UP}/691cafca-MU_5min_Apr2024Aug2026.xlsx',
}
DIVERS = {k: NC.CAND5[k] for k in ('GM', 'VLO', 'CF')}
CANDID = {k: A.CAND[k] for k in ('AMD', 'HOOD', 'FSLR', 'ARM')}
PATHS = dict(INCUMBENT, **DIVERS, **CANDID)
GROUP = {**{n: 'incumbent' for n in INCUMBENT},
         **{n: 'diversifier' for n in DIVERS},
         **{n: 'candidate' for n in CANDID}}
ORDER = (['RKLB', 'TSM', 'VST', 'VRT', 'MU']
         + ['GM', 'VLO', 'CF']
         + ['AMD', 'HOOD', 'FSLR', 'ARM'])
CAPITAL = 1_000_000
SLICE = 100
FOLDS = 3


def one_name(name):
    """Three fits, four tested windows. Returns everything the tables need."""
    bars, dv, idx = A.five_min(PATHS[name])
    d, O, H, L, C = bars
    chk = R.make_checker(idx, d, O)
    n = len(d)
    t0 = Params(capital=CAPITAL, years=1.0)

    bounds = [(n - (FOLDS - k) * SLICE, n - (FOLDS - k - 1) * SLICE - 1)
              for k in range(FOLDS)]
    iS = bounds[0][0]                       # start of the unseen span == half-sample split

    folds, vec_a, vecs = [], None, []
    for k, (lo, hi) in enumerate(bounds):
        vec = A.fit(bars, chk, t0, 0, lo - 1, floor=8)
        vecs.append(vec)
        if k == 0:
            vec_a = vec
        ret, buys, dd, _ = A.score(bars, chk, vec, t0, lo, hi)
        folds.append(dict(k=k + 1, lo=d[lo], hi=d[hi], ret=ret, buys=buys, dd=dd))

    # frozen arm over the whole unseen span, from fit A -- the half-sample blade
    h_ret, h_buys, h_dd, _ = A.score(bars, chk, vec_a, t0, iS, n - 1)
    f_ret, _fb, _fd, _ = A.score(bars, chk, vec_a, t0, 0, iS - 1)     # fitted, for the spread

    tested = [f['ret'] for f in folds] + [h_ret]
    yrs = (d[n - 1] - d[iS]).days / 365.25
    for f in folds:
        f['yrs'] = (f['hi'] - f['lo']).days / 365.25
    # A.score returns buys PER YEAR, so recover the raw count before summing across folds
    tot_buys = sum(f['buys'] * f['yrs'] for f in folds)
    # and de-annualise each fold before compounding: (1+ann)**yrs, not ann*yrs
    raw = np.prod([(1 + f['ret']) ** f['yrs'] for f in folds])

    Cn = np.array(C, dtype=float)
    bh_tested = (Cn[n - 1] / Cn[iS]) ** (1 / yrs) - 1

    return dict(
        name=name, folds=folds, half=h_ret, fitted=f_ret,
        planned=float(np.median(tested)),
        stitched=float(raw ** (1 / sum(f['yrs'] for f in folds)) - 1),
        worst=float(min(tested)), npos=sum(1 for x in tested if x > 0),
        buys=tot_buys / yrs, dd=max([f['dd'] for f in folds] + [h_dd]),
        bh=bh_tested, closes=(d, Cn), sessions=n, vecs=vecs,
    )


def main():
    nproc = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    print(f'fitting {len(ORDER)} names x {FOLDS} fits on {nproc} processes...', flush=True)
    with mp_pool.Pool(nproc) as pool:
        res = {r['name']: r for r in pool.imap_unordered(one_name, ORDER)}
        for n in ORDER:
            r = res[n]
            print(f"  {n:5s} planned {100*r['planned']:+7.1f}%  "
                  f"{r['buys']:5.1f} buys/yr", flush=True)

    print('\n\n=== PLANNED RETURN -- median of four tested windows, annualised ===')
    print('    no window here was seen by the parameters that scored it\n')
    print(f"{'name':6s} {'group':12s} {'PLANNED':>9s} {'BUYS/YR':>8s} {'worst':>9s} "
          f"{'+/4':>4s} {'stitched':>9s} {'max DD':>7s} {'fitted':>9s} {'spread':>8s}")
    for grp in ('incumbent', 'diversifier', 'candidate'):
        for n in ORDER:
            if GROUP[n] != grp:
                continue
            r = res[n]
            print(f"{n:6s} {grp:12s} {100*r['planned']:+8.1f}% {r['buys']:8.1f} "
                  f"{100*r['worst']:+8.1f}% {r['npos']:>2d}/4 {100*r['stitched']:+8.1f}% "
                  f"{100*r['dd']:6.1f}% {100*r['fitted']:+8.1f}% "
                  f"{100*abs(r['half']-r['fitted']):7.1f}pp")
        print()

    print('=== the four tested windows behind each median ===\n')
    f0 = res[ORDER[0]]['folds']
    print(f"{'name':6s} " + ' '.join(f"{'f'+str(f['k'])+' '+str(f['lo'])[2:]:>16s}"
                                     for f in f0) + f"{'half-sample':>16s}")
    for n in ORDER:
        r = res[n]
        cells = ' '.join(f"{100*f['ret']:+11.1f}% {f['buys']:3.0f}" for f in r['folds'])
        print(f"{n:6s} {cells} {100*r['half']:+11.1f}%    ")
    print('  (annualised return, then buys/yr, per fold; last column is the frozen arm over')
    print('   the whole unseen span, which is the half-sample blade)\n')

    print('=== ranked on the two metrics that matter ===\n')
    by_p = sorted(ORDER, key=lambda n: -res[n]['planned'])
    by_b = sorted(ORDER, key=lambda n: -res[n]['buys'])
    print('  planned return: ' + ' > '.join(f'{n} {100*res[n]["planned"]:.0f}%' for n in by_p))
    print('\n  buys per year:  ' + ' > '.join(f'{n} {res[n]["buys"]:.0f}' for n in by_b))

    print('\n=== reference: buy-and-hold over the same unseen span ===\n')
    print(f"{'name':6s} {'planned':>9s} {'B&H p.a.':>10s} {'difference':>12s}")
    for n in by_p:
        r = res[n]
        print(f"{n:6s} {100*r['planned']:+8.1f}% {100*r['bh']:+9.1f}% "
              f"{100*(r['planned']-r['bh']):+11.1f}pp")
    print('\n  not exposure-matched: the model holds cash much of the time, so this overstates')
    print('  the gap in a rising window. It is here as context, not as a gate.')

    # ---- boundary-seeking: which bound to look at next -------------------------
    print('\n\n=== boundary-seeking parameters (within 2% of a bound) ===')
    print('    a fitter pinned at a bound is not choosing that value, it is being stopped at')
    print('    it. this is the evidence that would justify widening the next one.\n')
    hits = {}
    for n in ORDER:
        for vec in res[n]['vecs']:
            for i, x in enumerate(vec):
                lo, hi = WIDE[i]
                span = hi - lo
                if x <= lo + 0.02 * span:
                    hits[(NAMES[i], 'lo')] = hits.get((NAMES[i], 'lo'), 0) + 1
                elif x >= hi - 0.02 * span:
                    hits[(NAMES[i], 'hi')] = hits.get((NAMES[i], 'hi'), 0) + 1
    tot = len(ORDER) * FOLDS
    if hits:
        print(f"{'parameter':12s} {'edge':5s} {'fits pinned':>12s} {'of':>4s}  bound")
        for (nm, side), c in sorted(hits.items(), key=lambda kv: -kv[1]):
            i = NAMES.index(nm)
            print(f'{nm:12s} {side:5s} {c:12d} {tot:4d}  {WIDE[i]}')
    else:
        print('  none -- every fitted parameter sits in the interior of its range.')

    # ---- parameter stability across training windows ---------------------------
    print('\n\n=== parameter stability: how far the fit moves between training windows ===')
    print('    max/min of each policy parameter across the three fits. a name whose optimum')
    print('    swings wildly will score badly under refit no matter how good it is to trade.\n')
    POL = [3, 4, 5, 6, 7, 8]
    print(f"{'name':6s} " + ' '.join(f'{NAMES[i]:>10s}' for i in POL) + f"{'worst':>9s}")
    for n in ORDER:
        vs = res[n]['vecs']
        rat = []
        for i in POL:
            col = [v[i] for v in vs]
            rat.append(max(col) / max(min(col), 1e-9))
        print(f'{n:6s} ' + ' '.join(f'{r:9.1f}x' for r in rat) + f'{max(rat):8.1f}x')

    # ---- correlation, reported and non-binding --------------------------------
    print('\n\n=== correlation, for weighting judgement -- binds on nothing ===\n')
    common = sorted(set.intersection(*[set(res[n]['closes'][0]) for n in ORDER]))
    M = {}
    for n in ORDER:
        d, Cn = res[n]['closes']
        ix = {t: k for k, t in enumerate(d)}
        s = np.array([Cn[ix[t]] for t in common], dtype=float)
        M[n] = s[1:] / s[:-1] - 1
    AI = ('TSM', 'VRT', 'VST', 'MU')
    fac = np.mean([M[n] for n in AI], axis=0)
    print(f"{'name':6s} {'beta to AI':>11s} {'corr to AI':>11s}")
    for n in ORDER:
        beta = np.cov(M[n], fac)[0, 1] / np.var(fac)
        print(f'{n:6s} {beta:11.3f} {np.corrcoef(M[n], fac)[0, 1]:11.3f}')
    print('\n  how much AI beta the book carries is a weighting decision, not an admission test.')


if __name__ == '__main__':
    main()
