"""
GENUINE out-of-sample holdout for the Hybrid10 new candidates.

Protocol (true OOS, not sub-period consistency):
  * split each name at 60% of its history
  * optimise the 10 structural params on the TRAIN window [0, 0.6N) ONLY
  * freeze them; measure return on the untouched TEST window [0.6N, N)
Report train vs test annualised return and buy counts. A large positive test return with
the parameters blind to that window is the real evidence the edge is structural.
"""
import math, datetime
from engine import Params, run_model
from optimise_candidates import mp as make_params, optimise, seg
from newfeed import load, NEW, NEW_TK


def span_years(dts, lo, hi):
    return max((dts[hi] - dts[lo]).days / 365.25, 1e-6)


if __name__ == '__main__':
    new = load(NEW, NEW_TK)
    print(f'{"tick":5s}{"train ann":>10s}{"test ann(OOS)":>15s}{"train buys":>12s}'
          f'{"test buys":>11s}{"verdict":>10s}', flush=True)
    for t in NEW_TK:
        dts, O, H, L, C = new[t]; N = len(C)
        split = int(N * 0.6)
        yrs = (dts[-1] - dts[0]).days / 365.25
        tmpl = Params(capital=6_000_000, comm=0.005, interest=0.0314, stop_days=50,
                      bayes_pct=0.5, years=yrs)
        data = dict(dts=dts, O=O, H=H, L=L, C=C)
        floor = max(12, int(0.4 * split / 5))
        theta = optimise(data, tmpl, 0, split - 1, floor, maxiter=9, popsize=8)
        tr_ret, tr_buys = seg(data, theta, tmpl, 0, split - 1)
        te_ret, te_buys = seg(data, theta, tmpl, split, N - 1)
        tr_ann = (1 + tr_ret) ** (1 / span_years(dts, 0, split - 1)) - 1
        te_ann = (1 + te_ret) ** (1 / span_years(dts, split, N - 1)) - 1 if te_ret > -1 else -1
        verdict = 'holds' if te_ret > 0.05 else ('weak' if te_ret > 0 else 'FAILS')
        print(f'{t:5s}{tr_ann*100:>9.0f}%{te_ann*100:>14.0f}%{tr_buys:>12d}{te_buys:>11d}'
              f'{verdict:>10s}', flush=True)
