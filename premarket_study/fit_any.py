"""
Fit any name on the §3.50 harness, regardless of its G1 class.

screen_universe.py deliberately refuses to spend a five-minute fit on a name that
fails G1, which is right when AI correlation is disqualifying. It is wrong when
the book is allowed a bounded number of AI names, as in the parallel-book brief
(at most two of six). This fits whatever it is given and reports the same columns,
so an AI name can be ranked on fills alongside the uncorrelated ones.

It is the same protocol throughout: train-half fit, frozen, scored on the unseen
half, fills and holding period measured there too.

Usage:  OUT=x.json python3 fit_any.py TICKER [TICKER ...]
"""
import json
import os
import sys

from screen_speed import G4_FILLS_YR, G4_MED_D, G4_WITHIN5, turnover
from screen_universe import beta_on, build_factor, classify
from two_day import Clock, FILLS_PER_YEAR_FLOOR, x0_vector


def main():
    names = [a for a in sys.argv[1:] if not a.startswith('--')]
    cal, factor = build_factor()
    out = []
    print(f'{"name":6s}{"beta":>7s}{"class":>14s}{"no-fit":>9s}{"frozen":>9s}'
          f'{"fills/yr":>10s}{"med":>6s}{"<=5d":>7s}   20% floor?', flush=True)
    for nm in names:
        c = Clock(nm, 1, 0)
        b, rho, n = beta_on(nm, cal, factor)
        y_tr = (c.D[c.cut-1] - c.D[0]).days/365.25
        y_te = (c.D[c.N-1] - c.D[c.cut]).days/365.25
        rt0, _ = c.seg(x0_vector(1), c.cut, c.N-1)
        a_no = c.ann(rt0, c.cut, c.N-1)
        v = c.fit(0, c.cut-1, max(4, int(FILLS_PER_YEAR_FLOOR*y_tr)), seed=42)
        r_te, _ = c.seg(v, c.cut, c.N-1)
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
        cls = classify(b)
        out.append(dict(name=nm, beta=b, corr=rho, g1=cls, nofit_test=a_no,
                        frozen_test=a_te, fills_yr=fy, med=md, within5=w5,
                        vec=[float(x) for x in v], bound=c.on_bound(v)))
        print(f'{nm:6s}{b:>7.2f}{cls:>14s}{a_no:>8.1f}%{a_te:>8.1f}%{fy:>10.1f}'
              f'{md:>5d}d{w5:>6.0f}%   {"YES" if a_te >= 20 else "no"}', flush=True)
        with open(os.environ.get('OUT', 'fit_any.json'), 'w') as f:
            json.dump(out, f, indent=1)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
