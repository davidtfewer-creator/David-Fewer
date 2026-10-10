"""
The screen, run on a universe that was never selected for volatility.

§3.50 ended with "there is no undiscovered fast uncorrelated name in this
universe" and flagged exactly why that might be wrong: the 17 names were chosen
for other reasons -- the §3.44 weekly set was picked on high volatility, the
rest were diversifier candidates -- so the screen was run over a sample already
tilted toward the AI complex. Box holds 19 names that have never been through
any gate here, and their composition is the part that was missing: consumer
staples (DLTR), managed care (HUM), media and telecom (CHTR, SPOT), travel
(EXPE), apparel (LULU), software (TEAM), mortgage (RKT), beverages (CELH),
refining (PARR), biotech (ALNY) -- alongside a high-beta set (AAOI, APLD, AXTI,
NVTS, OKLO, QBTS, LUNR) that serves as a control: if the screen works, those
should classify AI-related and the consumer names should not.

Gates, cheapest first, same definitions as §3.50:
  G1  AI beta  (<0.20 uncorrelated, >=0.27 AI-related, between = borderline)
  G2  frozen train-half vector beats the no-fit baseline on the unseen half
  G4  the book's own profile: >=50 fills/yr, median hold <=3d, >=70% within 5d

Only names that clear G1 are fitted, because a fit costs ~5 minutes and G1 costs
nothing -- which is the whole point of running it first.

Differences from screen_speed.py, both forced and both recorded:
  * The AI factor is built from the six constituents' own 5-minute files rather
    than through the workbook, so this runs without the live workbook present.
    The factor definition is unchanged (TSM, VRT, VST, AVGO, MU, MRVL).
  * BOOK CORRELATION IS NOT REPORTED -- it would need GM, VLO and CF restored
    too. §3.14 classified on AI BETA alone and g1_screen.py says so explicitly,
    so the verdict is unaffected, but the context column is missing.

Usage:  python3 screen_universe.py [--g1-only] [TICKER ...]
"""
import json
import math
import os
import sys

import numpy as np

from fresh_opt_cands import daily_from_5min
from screen_speed import G4_FILLS_YR, G4_MED_D, G4_WITHIN5, turnover
from two_day import Clock, FILLS_PER_YEAR_FLOOR, x0_vector

AI = ('TSM', 'VRT', 'VST', 'AVGO', 'MU', 'MRVL')
NEW = ['AAOI', 'ALNY', 'APLD', 'AXTI', 'CELH', 'CHTR', 'DLTR', 'EXPE', 'HUM',
       'LULU', 'LUNR', 'NEM', 'NVTS', 'OKLO', 'PARR', 'QBTS', 'RKT', 'SPOT', 'TEAM']


def closes(nm):
    dts, O, H, L, C = daily_from_5min(nm)
    return {d: c for d, c in zip(dts, C)}


def build_factor():
    """Equal-weight mean daily return of the six AI constituents, on their
    common calendar. Same definition as g1_screen, different plumbing."""
    cl = {n: closes(n) for n in AI}
    cal = sorted(set.intersection(*(set(c) for c in cl.values())))
    rets = {}
    for n in AI:
        c = cl[n]
        rets[n] = np.array([np.nan] + [c[cal[i]]/c[cal[i-1]] - 1 for i in range(1, len(cal))])
    return cal, np.nanmean(np.vstack([rets[n] for n in AI]), axis=0)


def beta_on(nm, cal, factor):
    c = closes(nm)
    r = np.array([np.nan] + [
        (c[cal[i]]/c[cal[i-1]] - 1) if (cal[i] in c and cal[i-1] in c) else np.nan
        for i in range(1, len(cal))])
    m = ~(np.isnan(factor) | np.isnan(r))
    if m.sum() < 60:
        return None, None, 0
    b = float(np.polyfit(factor[m], r[m], 1)[0])
    rho = float(np.corrcoef(factor[m], r[m])[0, 1])
    return b, rho, int(m.sum())


def classify(b):
    return 'uncorrelated' if b < 0.20 else 'AI-related' if b >= 0.27 else 'BORDERLINE'


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    names = args or NEW
    cal, factor = build_factor()
    print(f'AI factor: {len(cal)} sessions {cal[0]} .. {cal[-1]}, '
          f'constituents {", ".join(AI)}\n', flush=True)
    print(f'G1 (no fitting)\n{"name":6s}{"AI beta":>9s}{"corr":>8s}{"n":>7s}'
          f'{"sessions":>10s}   class', flush=True)
    rows = []
    for nm in names:
        if not os.path.exists(os.path.join('data_5min', f'{nm}_5min.xlsx')):
            print(f'{nm:6s}  G0 FAIL — no 5-minute file', flush=True)
            continue
        b, rho, n = beta_on(nm, cal, factor)
        if b is None:
            print(f'{nm:6s}  G0 FAIL — only {n} overlapping sessions', flush=True)
            continue
        dts, *_ = daily_from_5min(nm)
        cls = classify(b)
        rows.append(dict(name=nm, beta=b, corr=rho, n=n, sessions=len(dts), g1=cls))
        print(f'{nm:6s}{b:>9.2f}{rho:>8.2f}{n:>7d}{len(dts):>10d}   {cls}', flush=True)
    with open('screen_universe.json', 'w') as f:
        json.dump(rows, f, indent=1)
    passers = [r for r in rows if r['g1'] != 'AI-related']
    print(f'\n  {len(passers)} of {len(rows)} clear G1: '
          f'{", ".join(r["name"] for r in passers) or "none"}', flush=True)
    if '--g1-only' in sys.argv:
        print('DONE', flush=True)
        return

    print(f'\nG2 / G4 on the G1 survivors (one train-half fit each)\n', flush=True)
    for r in passers:
        nm = r['name']
        c = Clock(nm, 1, 0)
        y_tr = (c.D[c.cut-1] - c.D[0]).days/365.25
        y_te = (c.D[c.N-1] - c.D[c.cut]).days/365.25
        f_tr = max(4, int(FILLS_PER_YEAR_FLOOR*y_tr))
        rt0, _ = c.seg(x0_vector(1), c.cut, c.N-1)
        a_no = c.ann(rt0, c.cut, c.N-1)
        v = c.fit(0, c.cut-1, f_tr, seed=42)
        r_te, b_te = c.seg(v, c.cut, c.N-1)
        a_te = c.ann(r_te, c.cut, c.N-1)
        fr = c.run(v).frames
        hd = []
        for key in ('t1', 't2'):
            t = fr[key]
            e = None
            for i in range(c.N):
                if t['Z'][i] == 1:
                    e = i
                if t['AD'][i] == 1 and e is not None:
                    if e >= c.cut:
                        hd.append((c.D[i] - c.D[e]).days)
                    e = None
        fy, md, w5 = turnover(hd, y_te)
        g2 = a_te > a_no
        g4 = fy >= G4_FILLS_YR and md is not None and md <= G4_MED_D and w5 >= G4_WITHIN5
        r.update(nofit_test=a_no, frozen_test=a_te, g2=bool(g2), fills_yr=fy,
                 med=md, within5=w5, g4=bool(g4), vec=[float(x) for x in v],
                 bound=c.on_bound(v))
        print(f'{nm:6s} beta {r["beta"]:+.2f} | G2 {"pass" if g2 else "FAIL"} '
              f'({a_te:6.1f}% vs {a_no:6.1f}% no-fit) | G4 {"pass" if g4 else "FAIL"} '
              f'({fy:5.1f}/yr, med {md}d, {w5:3.0f}% <=5d)'
              f'{"   PASS ALL" if (g2 and g4) else ""}', flush=True)
        with open('screen_universe.json', 'w') as f:
            json.dump(rows, f, indent=1)
    print('\nDONE', flush=True)


if __name__ == '__main__':
    main()
