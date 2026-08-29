"""
Premia at book level (user question, 29 Aug 2026): the per-name premia were
fitted with each name's capital CAPTIVE — CF's 4.66%/5.91% is optimal for CF
compounding its own slice. The live book pools capital, so the true opportunity
cost of a CF held-day is the POOL's marginal return, which the isolation fit
never saw. Do the slow diversifiers' premia survive the pooled objective, or
would earlier exits (smaller premia) serve the book better?

This is NOT a re-fit of the model (bids, sigmas, buffers untouched; the fitted
vectors stand). It is a book-routing question about one policy knob per name,
tested on a NEW objective (the pooled loop) the original fit never optimised —
the one legitimate opening the re-fitting law leaves.

DIAGNOSTIC — yield per invested dollar-day, from the pooled baseline's trades:
  per name: sum(pnl) / sum(cost x occupied-days). If CF's held capital yields
  less per dollar-day than the book average, its premium is charging the pool
  rent; if not, the patience pays.

INTERVENTION — premium multipliers m in {0.5, 0.65, 0.8, 1.0} for CF, VLO, GM
  (AI names untouched; a nine-name search would be noise-mining). Standard
  book-policy protocol: fit the 64-cell grid on one half, freeze, score the
  unseen half — run in BOTH directions; adoptable only if the directions agree
  and each improves its unseen half. Plus a CF-only ladder for the direct
  question. Baseline = live config (09:00/4% PM rule both sides).
"""
import itertools
import json
import pickle

import numpy as np

from book_sim import NAMES as N8, load_all, simulate
from engine import Params
from fresh_opt import SPLIT
from fresh_opt_cands import aw_params

OUT = 'premia_at_book.json'
DIV = ['CF', 'VLO', 'GM']
GRID = [0.5, 0.65, 0.8, 1.0]


def load():
    t0 = Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                bayes_pct=0.5, years=2.2, ou_W=80)
    mrvl = aw_params(json.load(open('fresh_opt_cands.json'))['MRVL']['reference']['vec'], t0)
    names = N8 + ['MRVL']
    data, sleeves, cal = load_all(names=names, params_override={'MRVL': mrvl})
    pm = pickle.load(open('data_pm/pm_last_cuts.pkl', 'rb'))['09:00']
    def pm_rule(name, i, bid):
        pml = pm[name].get(data[name]['dts'][i])
        return pml is not None and bid < pml * (1 - 0.04)
    return data, sleeves, cal, pm_rule, names


def scaled_sleeves(sleeves, mults):
    return [dict(s, prem=s['prem'] * mults.get(s['name'], 1.0)) for s in sleeves]


def diagnostic(data, sleeves, cal, pm_rule, names):
    r = simulate(data, sleeves, cal, mode='pooled', excl_fn=pm_rule, collect_trades=True)
    assert abs(r['test'] - 1.184) < 0.01, 'baseline invariance failed'
    print('DIAGNOSTIC — yield per invested dollar-day (pooled baseline trades):')
    print(f"  {'name':6s}{'trades':>7s}{'same-day':>9s}{'med hold d':>11s}"
          f"{'avg ret':>9s}{'%/dollar-day':>13s}")
    stats = {}
    tot_pnl = tot_cd = 0.0
    for n in names:
        tr = [t for t in r['trades'] if t['name'] == n]
        if not tr:
            continue
        holds = [max((t['exit'] - t['entry']).days, 1) for t in tr]
        sd = sum(1 for t in tr if t['entry'] == t['exit'])
        pnl = sum(t['pnl'] for t in tr)
        capdays = sum(t['cost'] * h for t, h in zip(tr, holds))
        y = pnl / capdays * 100
        rets = np.array([t['pnl'] / t['cost'] for t in tr])
        stats[n] = dict(trades=len(tr), same_day=sd, med_hold=float(np.median(holds)),
                        avg_ret=float(rets.mean()), yield_pdd=y)
        tot_pnl += pnl
        tot_cd += capdays
        print(f"  {n:6s}{len(tr):>7d}{sd:>9d}{np.median(holds):>11.0f}"
              f"{rets.mean()*100:>8.2f}%{y:>12.3f}%")
    book_y = tot_pnl / tot_cd * 100
    print(f"  {'BOOK':6s}{'':7s}{'':9s}{'':11s}{'':9s}{book_y:>12.3f}%")
    return stats, book_y


def run(data, sleeves, cal, pm_rule, mults, lo=None, hi=None):
    r = simulate(data, scaled_sleeves(sleeves, mults), cal, mode='pooled',
                 excl_fn=pm_rule, date_lo=lo, date_hi=hi)
    return r


def main():
    data, sleeves, cal, pm_rule, names = load()
    stats, book_y = diagnostic(data, sleeves, cal, pm_rule, names)

    halves = dict(A=(None, SPLIT), B=(SPLIT, None))     # fit window per direction
    results = {}
    print('\nINTERVENTION — diversifier premium multipliers, both-directions protocol')
    for dname, (fit_lo, fit_hi) in (('fit-train/score-test', (None, SPLIT)),
                                    ('fit-test/score-train', (SPLIT, None))):
        f_lo, f_hi = fit_lo, fit_hi
        s_lo, s_hi = (SPLIT, None) if f_hi == SPLIT else (None, SPLIT)
        base_fit = run(data, sleeves, cal, pm_rule, {}, f_lo, f_hi)['full']
        base_scr = run(data, sleeves, cal, pm_rule, {}, s_lo, s_hi)['full']
        best, best_v = {}, base_fit
        for combo in itertools.product(GRID, repeat=3):
            mults = dict(zip(DIV, combo))
            v = run(data, sleeves, cal, pm_rule, mults, f_lo, f_hi)['full']
            if v > best_v:
                best, best_v = mults, v
        scr = run(data, sleeves, cal, pm_rule, best, s_lo, s_hi)['full'] if best else base_scr
        results[dname] = dict(pick=best or 'baseline (1,1,1)',
                              fit_base=base_fit, fit_best=best_v,
                              score_base=base_scr, score_pick=scr,
                              unseen_improves=bool(best) and scr > base_scr)
        print(f"  {dname}: pick {best or 'baseline'} | fit {base_fit*100:.1f}->{best_v*100:.1f}"
              f" | UNSEEN half {base_scr*100:.1f}->{scr*100:.1f}"
              f" {'IMPROVES' if results[dname]['unseen_improves'] else 'fails'}", flush=True)

    print('\nCF-only premium ladder (full/train/test, frozen grid — no picking):')
    lad = {}
    for m in GRID:
        r_tr = run(data, sleeves, cal, pm_rule, {'CF': m}, None, SPLIT)['full']
        r_te = run(data, sleeves, cal, pm_rule, {'CF': m}, SPLIT, None)['full']
        r_fu = run(data, sleeves, cal, pm_rule, {'CF': m})['full']
        lad[m] = (r_fu, r_tr, r_te)
        print(f"  CF x{m:<5} full {r_fu*100:6.1f}%  train {r_tr*100:6.1f}%  test {r_te*100:6.1f}%",
              flush=True)

    with open(OUT, 'w') as f:
        json.dump(dict(diagnostic={k: v for k, v in stats.items()}, book_yield=book_y,
                       directions=results,
                       cf_ladder={str(k): list(v) for k, v in lad.items()}), f, indent=1)
    print(f'saved {OUT}')


if __name__ == '__main__':
    main()
