"""
Is "look for more volatile names" a strategy, or a tautology for "more AI"?

§3.14 found volatility and AI correlation were the same axis; §3.45 found a
candidate set that was AI-correlated because it had been selected on volatility;
§3.50 found turnover joins them. Each was a local observation. With 49 names now
carrying a measured AI beta there is enough to test the relationship directly
instead of re-noticing it.

If the rank correlation between annualised volatility and AI beta is high, then
screening for volatile names IS screening for AI names and the brief's cap of two
AI names is self-defeating. If it is moderate, the interesting question becomes
which names sit OFF the line -- high volatility, low beta -- because those are
the only places a volatile non-AI book could come from.

Volatility and beta are both computed on the common calendar of whatever names
have 5-minute files, so the figures are comparable across the whole set.

Usage:  python3 vol_vs_beta.py
"""
import json
import math
import os
import statistics

import numpy as np

from fresh_opt_cands import daily_from_5min
from screen_universe import AI, build_factor


def main():
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_5min')
    names = sorted(f[:-10] for f in os.listdir(here) if f.endswith('_5min.xlsx'))
    cal, factor = build_factor()
    rows = []
    for nm in names:
        try:
            dts, O, H, L, C = daily_from_5min(nm)
        except Exception:
            continue
        px = dict(zip(dts, C))
        # leading NaN so this aligns with build_factor's series (it does the same)
        r = np.array([np.nan] + [(px[cal[i]]/px[cal[i-1]] - 1)
                                 if (cal[i] in px and cal[i-1] in px) else np.nan
                                 for i in range(1, len(cal))])
        m = ~(np.isnan(factor) | np.isnan(r))
        if m.sum() < 200:
            continue
        beta = float(np.polyfit(factor[m], r[m], 1)[0])
        vol = float(np.nanstd(r))*math.sqrt(252)*100
        rows.append(dict(name=nm, beta=beta, vol=vol, ai=nm in AI))
    def rank(v):
        o = sorted(range(len(v)), key=lambda i: v[i]); q=[0.0]*len(v)
        for p,i in enumerate(o): q[i]=p
        return q
    vb = [r['beta'] for r in rows]; vv = [r['vol'] for r in rows]
    rho = float(np.corrcoef(rank(vv), rank(vb))[0, 1])
    pear = float(np.corrcoef(vv, vb)[0, 1])
    print(f'{len(rows)} names with 5-minute data\n')
    print(f'  rank correlation, annualised volatility vs AI beta : {rho:+.2f}')
    print(f'  linear correlation                                  : {pear:+.2f}\n')
    rows.sort(key=lambda r: -r['vol'])
    print(f'{"name":6s}{"ann vol":>9s}{"AI beta":>9s}   class')
    for r in rows:
        cls = 'uncorrelated' if r['beta'] < 0.20 else ('AI-related' if r['beta'] >= 0.27 else 'BORDERLINE')
        print(f'{r["name"]:6s}{r["vol"]:>8.0f}%{r["beta"]:>9.2f}   {cls}'
              + ('   [factor constituent]' if r['ai'] else ''))
    # the exceptions: above-median volatility AND uncorrelated
    med = statistics.median(vv)
    exc = [r for r in rows if r['vol'] > med and r['beta'] < 0.20]
    print(f'\n  median volatility {med:.0f}%')
    print(f'  ABOVE-MEDIAN VOLATILITY *AND* UNCORRELATED (beta<0.20): '
          f'{len(exc)} of {len(rows)}')
    for r in exc:
        print(f'    {r["name"]:6s}{r["vol"]:>8.0f}%{r["beta"]:>9.2f}')
    json.dump(dict(rho=rho, pearson=pear, rows=rows,
                   exceptions=[r['name'] for r in exc]),
              open('vol_vs_beta.json', 'w'), indent=1)
    print('\nDONE', flush=True)


if __name__ == '__main__':
    main()
