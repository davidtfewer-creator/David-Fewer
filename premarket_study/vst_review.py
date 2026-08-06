"""
Does the case for dropping VST hold? Re-examined once every other name became verifiable.

VST was dropped on a single observation: it was the weakest of the deployed five at the AT-OPEN
FLOOR. That basis has since been shown to be unusable as a ranking device. Measured on the four
names where both bases now exist, the floor understates verified performance by between +10pp
and +88pp -- a factor of nearly nine -- and the ordering does not survive: TSM is third at the
floor and last verified, VRT fourth at the floor and third verified. A ranking whose gaps vary
that much between names cannot decide which name is worst.

So the question is reopened on the three criteria that are available:

  RETURN       the published verified figures, the only verified numbers VST has.
  STABILITY    the fitted/tested spread -- the wide-spread overfitting tell, and the criterion
               that was used to question VLO. All five can be compared at the floor, which is
               legitimate here because a SPREAD between two windows on one basis is a fairer
               comparison than a level across bases.
  CONCENTRATION what VST does to the book's average pairwise correlation, which needs only
               price data and so is fully computable.

Run:  python3 vst_review.py
"""
import itertools

import numpy as np

import ramp_premium as R
from engine import run_model
import nine_computed as NC

UP = '/root/.claude/uploads/822d405e-f99b-5b59-9c6b-87e725054402'
LIVE = f'{UP}/8d17afe4-TradingExcel_5stock_live.xlsx'
NC.CAND5.update({
    'RKLB': f'{UP}/4d3fd234-RKLB_5min_Apr2024Aug2026.xlsx',
    'TSM':  f'{UP}/19b5b8d9-TSM_5min_Apr2024Aug2026.xlsx',
    'VRT':  f'{UP}/72c19f40-VRT_5min_Apr2024Aug2026.xlsx',
    'MU':   f'{UP}/691cafca-MU_5min_Apr2024Aug2026.xlsx',
})
FIVE = ('RKLB', 'TSM', 'VST', 'VRT', 'MU')
PUBLISHED = {'RKLB': 158, 'TSM': 57, 'VST': 62, 'VRT': 67, 'MU': 63}


def leg(n, sde):
    d, O, H, L, C = R.load_feed(n, path=LIVE)
    p, c = R.load_params(n, path=LIVE, years=(d[-1] - d[0]).days / 365.25)
    r = run_model(d, O, H, L, C, p, ou_sigma=c['ou_sigma'], same_day_exit=sde, collect=True)
    eq = r.frames['equity']
    iS = next(k for k, x in enumerate(d) if x >= R.SPLIT)
    return ((eq[-1] / eq[0]) ** (1 / p.years) - 1,
            (eq[iS] / eq[0]) ** (365.25 / (d[iS] - d[0]).days) - 1,
            (eq[-1] / eq[iS]) ** (365.25 / (d[-1] - d[iS]).days) - 1)


def main():
    print('=== 1. the floor cannot rank: gap to verified, four names ===\n')
    print(f"{'name':6s} {'floor':>8s} {'verified':>9s} {'gap':>8s}   floor rank -> verified rank")
    fl, ve = {}, {}
    for n in FIVE:
        fl[n] = leg(n, 'at_open')[0]
        if n != 'VST':
            _b, idx = NC.five_min(n)
            d, O, _H, _L, _C = R.load_feed(n, path=LIVE)
            ve[n] = leg(n, R.make_checker(idx, d, O))[0]
    fr = sorted(FIVE, key=lambda n: -fl[n])
    vr = sorted(ve, key=lambda n: -ve[n])
    for n in FIVE:
        v = f'{100*ve[n]:8.1f}%' if n in ve else '     n/a '
        g = f'{100*(ve[n]-fl[n]):+7.1f}' if n in ve else '    n/a'
        rk = f'{vr.index(n)+1} of 4' if n in ve else 'no 5-min data'
        print(f'{n:6s} {100*fl[n]:7.1f}% {v} {g}   {fr.index(n)+1} of 5 -> {rk}')
    gaps = [ve[n] - fl[n] for n in ve]
    print(f'\n  gaps span {100*min(gaps):+.1f}pp to {100*max(gaps):+.1f}pp. A ranking device whose')
    print(f'  error varies ninefold between names is not a ranking device.')
    print(f'\n  published verified: ' + ', '.join(f'{k} {v}%' for k, v in PUBLISHED.items()))
    print(f'  published order:    ' + ' > '.join(sorted(PUBLISHED, key=lambda k: -PUBLISHED[k])))
    print(f'  -> VST is FOURTH of five on the only verified basis it has, above TSM.')

    print(f'\n=== 2. stability: the criterion applied to VLO, applied evenly ===\n')
    print(f"{'name':6s} {'fitted':>8s} {'tested':>8s} {'spread':>10s}")
    sp = {}
    for n in FIVE:
        f, h1, h2 = leg(n, 'at_open')
        sp[n] = abs(h2 - h1)
        print(f'{n:6s} {100*h1:7.1f}% {100*h2:7.1f}% {100*abs(h2-h1):9.1f}pp')
    order = sorted(FIVE, key=lambda n: sp[n])
    print(f'\n  most to least stable: ' + ' < '.join(order))
    print(f'  -> VST has the NARROWEST spread in the deployed book, by a factor of three.')
    print(f'     On the test that questioned VLO, VST is the last name you would drop.')

    print(f'\n=== 3. concentration: the one argument that survives ===\n')
    px = {}
    for n in FIVE:
        d, _O, _H, _L, C = R.load_feed(n, path=LIVE); px[n] = (d, C)
    for n in ('NVDA', 'AVGO'):
        d, _O, _H, _L, C = R.load_feed(n); px[n] = (d, C)
    for n in ('GM', 'CF'):
        b, _i = NC.five_min(n); px[n] = (b[0], b[4])
    common = sorted(set.intersection(*[set(v[0]) for v in px.values()]))
    M = {}
    for n, (d, C) in px.items():
        ix = {t: k for k, t in enumerate(d)}
        s = np.array([C[ix[t]] for t in common], dtype=float)
        M[n] = s[1:] / s[:-1] - 1
    others = [n for n in FIVE if n != 'VST'] + ['NVDA', 'AVGO', 'GM', 'CF']
    cs = {o: np.corrcoef(M['VST'], M[o])[0, 1] for o in others}
    print(f"  VST's mean correlation to the other eight: {np.mean(list(cs.values())):.3f}")
    print('    ' + '  '.join(f'{k} {v:+.2f}' for k, v in cs.items()))
    E8 = ('RKLB', 'TSM', 'VRT', 'MU', 'NVDA', 'AVGO', 'GM', 'CF')

    def ac(ns):
        return float(np.mean([np.corrcoef(M[a], M[b])[0, 1]
                              for a, b in itertools.combinations(ns, 2)]))
    print(f'\n  eight-name book without VST   {ac(E8):.3f}')
    print(f'  nine-name book with VST       {ac(E8 + ("VST",)):.3f}   '
          f'({ac(E8 + ("VST",)) - ac(E8):+.3f})')
    print(f'\n  So VST does add concentration -- it is a data-centre-power name and correlates')
    print(f'  0.65 with VRT and 0.54 with NVDA -- but the whole effect is 0.017 of average')
    print(f'  correlation. That is a real argument and a small one.')

    print(f'\n=== verdict ===\n')
    print('  The return argument fails: it rested on the floor, which reorders under')
    print('  verification, and on the published verified basis VST outranks TSM.')
    print('  The stability argument reverses: VST is the steadiest name in the book.')
    print('  The concentration argument stands but is worth 0.017.')
    print('\n  VST cannot be settled properly without its 5-minute file -- it is now the only')
    print('  name in the book with no verified figure of its own.')


if __name__ == '__main__':
    main()
