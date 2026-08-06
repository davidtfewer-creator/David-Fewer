"""
Every name computed on verified fills, on one basis, for the first time. VLO dropped.

With 5-minute bars now available for all nine names, nothing in this table is quoted. Each
name's daily OHLC comes from its validated workbook where one exists (the live book for RKLB,
TSM, VRT, MU; the original for NVDA, AVGO) and from the 5-minute bars themselves for GM and CF,
which have no workbook. The intraday files are used only to decide same-day round trips: first
bar whose low reaches the bid, then did a later bar's high reach the target. Opens agree
exactly between the two sources and closes to about 0.02%, so they are the same instrument.

Composition
    RKLB, TSM, VRT, MU     deployed rule and parameters (VST dropped)
    NVDA, AVGO             premium 4-6%, 200-day stop, residual sigma, buffer re-expressed
    GM, CF                 diversifier vectors as fitted
    VLO                    DROPPED -- fitted half 11.4% against a tested half of 137.9%, the
                           wide-fold-spread tell. Reported alongside so the cost is visible.

Potential is the full-sample verified figure. Planned applies each name's own measured
out-of-sample basis -- 2.1pp for the deployed names, the unseen-window figures for GM and CF --
and NVDA/AVGO are marked UNMEASURED because nothing establishes a haircut for them at this
setting. Those two are the softest numbers here.

Run:  python3 book_verified.py
"""
import itertools

import numpy as np

import ramp_premium as R
from engine import Params, run_model
import nine_computed as NC

UP = '/root/.claude/uploads/822d405e-f99b-5b59-9c6b-87e725054402'
LIVE = f'{UP}/8d17afe4-TradingExcel_5stock_live.xlsx'
NC.CAND5.update({
    'RKLB': f'{UP}/4d3fd234-RKLB_5min_Apr2024Aug2026.xlsx',
    'TSM':  f'{UP}/19b5b8d9-TSM_5min_Apr2024Aug2026.xlsx',
    'VRT':  f'{UP}/72c19f40-VRT_5min_Apr2024Aug2026.xlsx',
    'MU':   f'{UP}/691cafca-MU_5min_Apr2024Aug2026.xlsx',
})

DEPLOYED = ('RKLB', 'TSM', 'VRT', 'MU')
PAIR = ('NVDA', 'AVGO')
DIVERS = ('GM', 'VLO', 'CF')
HIGH = (0.040, 0.045, 0.050, 0.060)
HIGH_STOP = 200
BUF_BAND = (0.6, 0.8, 1.0, 1.25, 1.5)
HAIRCUT = 2.1
PLAN_DIV = {'GM': 33.0, 'VLO': 35.0, 'CF': 41.0}       # handover section 6, unseen windows
PUBLISHED_4 = {'RKLB': 158.0, 'TSM': 57.0, 'VRT': 67.0, 'MU': 63.0}


def legs():
    """name -> (dates, equity/capital, buys_per_year, verified)."""
    out = {}
    # deployed four: workbook bars and parameters, 5-minute verification
    for n in DEPLOYED:
        d, O, H, L, C = R.load_feed(n, path=LIVE)
        p, cached = R.load_params(n, path=LIVE, years=(d[-1] - d[0]).days / 365.25)
        _bars, idx = NC.five_min(n)
        chk = R.make_checker(idx, d, O)
        r = run_model(d, O, H, L, C, p, ou_sigma=cached['ou_sigma'],
                      same_day_exit=chk, collect=True)
        out[n] = (d, np.array(r.frames['equity']) / p.capital, r.total_buys / p.years)
    # NVDA / AVGO on the patient rule, band medians over premium and buffer
    for n in PAIR:
        d, O, H, L, C = R.load_feed(n)
        args = (d, O, H, L, C)
        p, _ = R.load_params(n, years=(d[-1] - d[0]).days / 365.25)
        chk = R.make_checker(R.build_index(n), d, O)
        mt = p.ou_buf_k / NC.sigma_ratio(args, p)
        cs, bs = [], []
        for m in BUF_BAND:
            for prem in HIGH:
                q = Params(**{**p.__dict__, 'ou_buf_k': mt * m, 'stop_days': HIGH_STOP,
                              'premium': prem, 'ou_prem': prem})
                r = run_model(*args, q, ou_sigma='resid', same_day_exit=chk, collect=True)
                cs.append(np.array(r.frames['equity']) / q.capital)
                bs.append(r.total_buys / q.years)
        out[n] = (d, np.median(cs, axis=0), float(np.median(bs)))
    # diversifiers: bars from the 5-minute files, handover vectors
    for n in DIVERS:
        bars, idx = NC.five_min(n)
        d = bars[0]
        p = NC.cand_params(n)
        p = Params(**{**p.__dict__, 'years': (d[-1] - d[0]).days / 365.25})
        r = run_model(*bars, p, ou_sigma='resid',
                      same_day_exit=R.make_checker(idx, d, bars[1]), collect=True)
        out[n] = (d, np.array(r.frames['equity']) / p.capital, r.total_buys / p.years)
    return out


def main():
    L = legs()
    common = sorted(set.intersection(*[set(v[0]) for v in L.values()]))
    yrs = (common[-1] - common[0]).days / 365.25
    iS = next(k for k, x in enumerate(common) if x >= R.SPLIT)

    curve = {}
    for n, (d, eq, _b) in L.items():
        ix = {t: k for k, t in enumerate(d)}
        c = np.array([eq[ix[t]] for t in common])
        curve[n] = c / c[0]

    def wins(c):
        return ((c[-1] / c[0]) ** (1 / yrs) - 1,
                (c[iS] / c[0]) ** (365.25 / (common[iS] - common[0]).days) - 1,
                (c[-1] / c[iS]) ** (365.25 / (common[-1] - common[iS]).days) - 1)

    def dd(c):
        peak, m = -1e30, 0.0
        for e in c:
            peak = max(peak, e)
            m = max(m, (peak - e) / peak)
        return m

    print(f'all names on VERIFIED fills, {len(common)} common sessions '
          f'{common[0]} .. {common[-1]}\n')
    print('=== per name ===\n')
    print(f"{'name':6s} {'rule':13s} {'potential':>10s} {'fitted':>8s} {'tested':>8s} "
          f"{'planned':>8s} {'buys/yr':>8s} {'maxDD':>7s}  basis")
    rows = {}
    for n in DEPLOYED + PAIR + DIVERS:
        f, h1, h2 = wins(curve[n])
        buys = L[n][2]
        if n in DEPLOYED:
            rule, plan, basis = 'deployed', 100 * f - HAIRCUT, f'2.1pp (published {PUBLISHED_4[n]:.0f}%)'
        elif n in PAIR:
            rule, plan, basis = '4-6% / 200d', 100 * f - HAIRCUT, '2.1pp, UNMEASURED'
        else:
            rule, plan, basis = 'deployed', PLAN_DIV[n], 'unseen windows'
        rows[n] = (100 * f, 100 * h1, 100 * h2, plan, buys, 100 * dd(curve[n]))
        tag = '  <-- dropped' if n == 'VLO' else ''
        print(f'{n:6s} {rule:13s} {100*f:9.1f}% {100*h1:7.1f}% {100*h2:7.1f}% {plan:7.1f}% '
              f'{buys:8.0f} {100*dd(curve[n]):6.1f}%  {basis}{tag}')

    print(f'\n  the deployed four against their published verified figures: ' +
          ', '.join(f'{n} {rows[n][0]:.0f} vs {PUBLISHED_4[n]:.0f}' for n in DEPLOYED))

    # ---- books ----------------------------------------------------------------------
    EIGHT = DEPLOYED + PAIR + ('GM', 'CF')
    NINE = DEPLOYED + PAIR + DIVERS
    books = (('NINE (with VLO)', NINE),
             ('EIGHT (VLO removed)', EIGHT),
             ('six AI-exposed only', DEPLOYED + PAIR),
             ('four deployed only', DEPLOYED))

    print(f'\n=== books, equal weight, held construction (no rebalancing) ===\n')
    print(f"{'book':24s} {'potential':>10s} {'fitted':>8s} {'tested':>8s} {'planned':>8s} "
          f"{'buys/yr':>8s} {'maxDD':>7s}")
    for label, names in books:
        w = 1.0 / len(names)
        eq = sum(w * curve[n] for n in names)
        f, h1, h2 = wins(eq)
        plan_mean = np.mean([rows[n][3] for n in names])
        buys = sum(rows[n][4] for n in names)
        print(f'{label:24s} {100*f:9.1f}% {100*h1:7.1f}% {100*h2:7.1f}% {plan_mean:7.1f}% '
              f'{buys:8.0f} {100*dd(eq):6.1f}%')

    # ---- correlation of the underlying shares ---------------------------------------
    px = {}
    for n in DEPLOYED:
        d, O, H, Lo, C = R.load_feed(n, path=LIVE); px[n] = (d, C)
    for n in PAIR:
        d, O, H, Lo, C = R.load_feed(n); px[n] = (d, C)
    for n in DIVERS:
        bars, _i = NC.five_min(n); px[n] = (bars[0], bars[4])
    M = {}
    for n, (d, C) in px.items():
        ix = {t: k for k, t in enumerate(d)}
        s = np.array([C[ix[t]] for t in common], dtype=float)
        M[n] = s[1:] / s[:-1] - 1

    def ac(names):
        return float(np.mean([np.corrcoef(M[a], M[b])[0, 1]
                              for a, b in itertools.combinations(names, 2)]))
    print(f'\n=== concentration ===\n')
    for label, names in books:
        print(f'  {label:24s} average pairwise correlation {ac(names):.3f}')
    print(f'\n  deployed five (with VST), for reference: 0.489')

    print(f'\n=== what dropping VLO costs and buys ===\n')
    for j, nm in ((0, 'potential'), (3, 'planned')):
        n9 = np.mean([rows[n][j] for n in NINE])
        n8 = np.mean([rows[n][j] for n in EIGHT])
        print(f'  {nm:10s} nine {n9:6.1f}%   eight {n8:6.1f}%   ({n8-n9:+.1f}pp)')
    e9 = sum(curve[n] for n in NINE) / len(NINE)
    e8 = sum(curve[n] for n in EIGHT) / len(EIGHT)
    print(f'  {"book curve":10s} nine {100*wins(e9)[0]:6.1f}%   eight {100*wins(e8)[0]:6.1f}%   '
          f'({100*(wins(e8)[0]-wins(e9)[0]):+.1f}pp)')
    print(f'  {"maxDD":10s} nine {100*dd(e9):6.1f}%   eight {100*dd(e8):6.1f}%')
    print(f'  {"corr":10s} nine {ac(NINE):6.3f}    eight {ac(EIGHT):6.3f}')
    print(f'  {"buys/yr":10s} nine {sum(rows[n][4] for n in NINE):6.0f}    '
          f'eight {sum(rows[n][4] for n in EIGHT):6.0f}')


if __name__ == '__main__':
    main()
