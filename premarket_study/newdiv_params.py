"""
Recover the deployable parameter sets for GM, VLO and CF.

newdiv.py fitted each name twice -- once on the first half, to be frozen and scored on the tested
half, and once on the whole sample -- but only printed the first-half vector. The full-sample fit
is what the book deploys for its own names, so it is what the memo has to carry.

Same optimiser, same seed, same bounds and floor as newdiv.py, so this reproduces those runs
rather than producing new ones: the returns printed here should match the 'full fit' column
already reported (GM 50.3%, VLO 64.2%, CF 46.9%). If they do not, something has drifted and the
numbers in the memo cannot be trusted.

Both vectors are printed. The full-sample fit is the deployment candidate; the first-half fit is
what the out-of-sample evidence was actually built on, and is kept beside it so the two can be
compared -- a large gap between them is itself a warning about how much the fit is moving.
"""
import copy
import datetime
import statistics

from optimise_candidates import NAMES
from newdiv import CAND, CUT, SEED, ann, daily_from_5min, optimise, seg
import five_min

ADD = ['GM', 'VLO', 'CF']
FIRST_HALF = {
    'GM':  [0.2011, 0.2907, 0.04228, 0.3827, 0.005803, 0.03368, 0.6041, 0.009885, 0.09131, 41.42],
    'VLO': [1.441, 0.7016, 0.02011, 0.945, 0.02321, 0.05922, 1.799, 0.02552, 0.08021, 116.7],
    'CF':  [0.8737, 0.4777, 0.004598, 1.838, 0.02545, 0.06327, 0.8036, 0.05159, 0.09228, 65.56],
}
EXPECT = {'GM': 50.3, 'VLO': 64.2, 'CF': 46.9}


if __name__ == '__main__':
    out = {}
    for t in ADD:
        dts, O, H, L, C = daily_from_5min(t)
        N = len(C)
        tmpl = copy.copy(SEED)
        tmpl.years = (dts[-1]-dts[0]).days/365.25
        d = dict(dts=dts, O=O, H=H, L=L, C=C)
        chk = five_min.make_checker(t, dts, O)[0]
        th = optimise(d, tmpl, 0, N-1, max(8, int(0.03*N)), chk)
        r, b = seg(d, th, tmpl, 0, N-1, chk)
        a = ann(r, dts, 0, N-1)*100
        yrs = (dts[-1]-dts[0]).days/365.25
        out[t] = (th, a, b/yrs)
        flag = 'matches' if abs(a - EXPECT[t]) < 0.6 else f'DRIFT vs {EXPECT[t]}%'
        print(f'{t:5s} full-sample {a:6.1f}%  ({flag})  buys/yr {b/yrs:.0f}', flush=True)

    print('\n=== deployable parameters, full-sample fit ===', flush=True)
    for t in ADD:
        th = out[t][0]
        print(f'\n{t}', flush=True)
        for n, v in zip(NAMES, th):
            print(f'    {n:10s} {v:.6g}', flush=True)

    print('\n=== how far the fit moved between the two halves ===', flush=True)
    print(f'{"param":10s}' + ''.join(f'{t + " 1st":>13s}{t + " full":>13s}' for t in ADD),
          flush=True)
    for i, n in enumerate(NAMES):
        row = ''
        for t in ADD:
            row += f'{FIRST_HALF[t][i]:>13.4g}{out[t][0][i]:>13.4g}'
        print(f'{n:10s}{row}', flush=True)
    print('\nDONE', flush=True)
