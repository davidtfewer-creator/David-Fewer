"""
Can the near-misses be rescued by fitting FOR speed instead of only for return?

screen_speed.py declined four uncorrelated names (RTX, CF, DE, LEN) that clear
G1 and G2 and fail ONLY the turnover gate. That leaves a question the screen
cannot answer: is each one slow because of the NAME, or because the optimiser
was told to maximise return and a higher premium is the cheapest way to do that?

This refits the same names on the same train half with G4 written INTO the
objective, the same way the minimum-trade floor already is: every vector that
misses the gate scores below every vector that meets it, with a graded term so
the search is guided toward feasibility rather than wandering a flat penalty.
Then the frozen vector is scored on the unseen half as usual, and its turnover
re-measured there.

Three outcomes are possible and all three are informative:
  * feasible and the return holds   -> it was a parameter problem; the name is live
  * feasible but the return collapses -> the speed is purchasable, at a stated price
  * no feasible vector at all        -> it is the name, and the decline stands

CF is the useful control: at its DEPLOYED vector it does 25.7 fills/yr on a
12-day median (book_turnover.py), and at the train-half vector 42.6/yr on 5 days
-- so turnover already moved by two thirds on this name without anyone asking
for it. That is the evidence that the question is worth asking.

Usage:  python3 screen_speed_fast.py [TICKER ...]
"""
import json
import os
import sys

from scipy.optimize import differential_evolution

from screen_speed import G4_FILLS_YR, G4_MED_D, G4_WITHIN5
from two_day import Clock, FILLS_PER_YEAR_FLOOR, PERTURB, POLICY, x0_vector

NEAR_MISS = ['CF', 'RTX', 'DE', 'LEN']


def window(c, vec, lo, hi):
    """One engine run -> return, fills and holding periods for entries in [lo, hi]."""
    fr = c.run(vec).frames
    eq = fr['equity']
    r = eq[hi]/eq[lo] - 1.0 if eq[lo] > 0 else -1.0
    hd, b = [], 0
    for key in ('t1', 't2'):
        t = fr[key]
        e = None
        for i in range(c.N):
            if t['Z'][i] == 1:
                e = i
                if lo <= i <= hi:
                    b += 1
            if t['AD'][i] == 1 and e is not None:
                if lo <= e <= hi:
                    hd.append((c.D[i] - c.D[e]).days)
                e = None
    return r, b, sorted(hd)


def speed(hd, yrs):
    if not hd:
        return 0.0, None, 0.0
    return len(hd)/yrs, hd[len(hd)//2], sum(1 for h in hd if h <= 5)/len(hd)*100


def shortfall(fy, md, w5):
    """0 when the gate is met; grows with the distance from it."""
    if md is None:
        return 3.0
    return (max(0.0, G4_FILLS_YR - fy)/G4_FILLS_YR
            + max(0.0, md - G4_MED_D)/G4_MED_D
            + max(0.0, G4_WITHIN5 - w5)/G4_WITHIN5)


def score(c, vec, lo, hi, yrs, floor):
    r, b, hd = window(c, vec, lo, hi)
    if b < floor:
        return -9.0 + b*1e-3
    sf = shortfall(*speed(hd, yrs))
    return r if sf <= 0 else -5.0 + 1.0/(1.0 + sf)


def robust_fast(c, vec, lo, hi, yrs, floor):
    base = score(c, vec, lo, hi, yrs, floor)
    s = []
    for i in POLICY:
        for f in PERTURB:
            v = list(vec)
            v[i] = min(max(v[i]*f, c.bounds[i][0]), c.bounds[i][1])
            s.append(score(c, v, lo, hi, yrs, floor))
    return 0.5*base + 0.5*sum(s)/len(s)


def run(nm):
    c = Clock(nm, 1, 0)
    y_tr = (c.D[c.cut-1] - c.D[0]).days/365.25
    y_te = (c.D[c.N-1] - c.D[c.cut]).days/365.25
    floor = max(4, int(FILLS_PER_YEAR_FLOOR*y_tr))
    neg = lambda v: -robust_fast(c, v, 0, c.cut-1, y_tr, floor)
    res = differential_evolution(neg, c.bounds, x0=x0_vector(1), init='sobol', seed=42,
                                 maxiter=6, popsize=6, mutation=(0.5, 1.0),
                                 recombination=0.7, tol=1e-3, polish=False, disp=False,
                                 updating='immediate', workers=1)
    v = [float(x) for x in res.x]
    r_tr, b_tr, hd_tr = window(c, v, 0, c.cut-1)
    r_te, b_te, hd_te = window(c, v, c.cut, c.N-1)
    s_tr = speed(hd_tr, y_tr)
    s_te = speed(hd_te, y_te)
    feas_tr = shortfall(*s_tr) <= 0
    feas_te = shortfall(*s_te) <= 0
    a_tr, a_te = c.ann(r_tr, 0, c.cut-1), c.ann(r_te, c.cut, c.N-1)
    print(f'{nm:5s} speed-constrained: train {a_tr:6.1f}% ({s_tr[0]:5.1f}/yr, med {s_tr[1]}d, '
          f'{s_tr[2]:3.0f}% <=5d, {"FEASIBLE" if feas_tr else "infeasible"})', flush=True)
    print(f'{"":5s}   -> test {a_te:6.1f}% ({s_te[0]:5.1f}/yr, med {s_te[1]}d, '
          f'{s_te[2]:3.0f}% <=5d, G4 {"pass" if feas_te else "FAIL"})   '
          f'prem {v[4]:.4f}/{v[7]:.4f}', flush=True)
    return dict(name=nm, train=a_tr, test=a_te, feasible_train=feas_tr, feasible_test=feas_te,
                fills_yr_train=s_tr[0], med_train=s_tr[1], within5_train=s_tr[2],
                fills_yr_test=s_te[0], med_test=s_te[1], within5_test=s_te[2],
                vec=v, bound=c.on_bound(v))


if __name__ == '__main__':
    names = [a for a in sys.argv[1:] if not a.startswith('--')] or NEAR_MISS
    print(f'speed-constrained refit: >={G4_FILLS_YR:.0f} fills/yr, median <={G4_MED_D}d, '
          f'>={G4_WITHIN5:.0f}% within 5 days, fitted on the TRAIN half only\n', flush=True)
    out = []
    for n in names:
        out.append(run(n))
        with open(os.environ.get('OUT', 'screen_speed_fast.json'), 'w') as f:
            json.dump(out, f, indent=1)
    print('\nDONE', flush=True)
