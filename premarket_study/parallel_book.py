"""
The parallel book, pooled and gated — does 15% standalone become 30% together?

The brief's premise is that names clearing a modest standalone bar become much
better pooled, because free capital is reallocated every morning instead of
sitting in sleeves that cannot use it. That premise is why a 15% floor might be
acceptable where a 20% one is not, and it has never been tested on anything but
the nine-name book.

VECTOR CHOICE IS PER NAME, and it is the point of §3.59. A fitted vector is only
meaningful where the train half predicts the test half, so:

    rho >= +0.20  ->  the fitted train-half vector (RTX +0.36, DE +0.38, NVDA +0.41)
    otherwise     ->  the NEUTRAL seed vector, never fitted to this name at all
                      (PARR -0.49, AMD -0.59, DVN -0.47, OXY -0.33)

Using a fitted vector on a negative-rho name is choosing a vector selected to
fail; using the neutral one is the §3.54 convention and is not lookahead, since
nothing about the name informed it.

Arms, each adding one layer, so the uplift is attributable:
  captive          each sleeve on its own fixed slice -- the standalone basis
  pooled           one pot, free sleeves divide it each morning
  + PM rule        live config, the 09:00 / 4% pre-market exclusion (§3.16)
  + breadth gate   §3.23 scaled to a six-name book: a name below its own 200dma
                   is gated only when K of the six are below theirs, decided on
                   the PRIOR close so the rule is ex ante

Usage: BAYES_WORKBOOK=<xlsx> python3 parallel_book.py
"""
import datetime as dt
import json
import pickle
import statistics
import sys

from book_sim import load_all, simulate
from cf_speed_g5 import params_from_vec
from cf_swap_test import t0
from fresh_opt_cands import daily_from_5min
from two_day import x0_vector

SET6 = ['PARR', 'RTX', 'DVN', 'OXY', 'DE', 'AMD']
RHO_MIN = 0.20


def load_rho():
    out = {}
    for f in ('fittability.json', 'fittability2.json', 'fittability3.json'):
        try:
            for r in json.load(open(f)):
                out[r['name']] = r['rho']
        except (FileNotFoundError, ValueError):
            pass
    return out


def load_vecs():
    out = {}
    for f in ('screen_speed.json', 'su_a.json', 'su_b.json', 'su_c.json',
              'su_dvn.json', 'fit_ai.json'):
        try:
            for r in json.load(open(f)):
                if 'vec' in r:
                    out[r['name']] = r['vec']
        except (FileNotFoundError, ValueError):
            pass
    return out


def gate_sets(names, K):
    """Dates to suppress entries: name below its own 200dma on the PRIOR close,
    and at least K of the set below theirs that same prior close."""
    breach = {}
    for n in names:
        dts, O, H, L, C = daily_from_5min(n)
        s = set()
        for i in range(200, len(dts)):
            m = sum(C[i-200:i])/200                 # prior 200 closes, excludes today
            if C[i-1] < m:
                s.add(dts[i])
        breach[n] = s
    cnt = {}
    for n in names:
        for d in breach[n]:
            cnt[d] = cnt.get(d, 0) + 1
    return {n: {d for d in breach[n] if cnt.get(d, 0) >= K} for n in names}, cnt


def pm_rule_for(data, cut='09:00', thr=0.04):
    pm = pickle.load(open('data_pm/pm_last_cuts.pkl', 'rb'))[cut]
    def f(name, i, bid):
        p = pm.get(name, {}).get(data[name]['dts'][i])
        return p is not None and bid < p*(1 - thr)
    return f


def main():
    rho, vecs = load_rho(), load_vecs()
    names = SET6
    po, basis = {}, {}
    for n in names:
        r = rho.get(n)
        if r is not None and r >= RHO_MIN and n in vecs:
            po[n] = params_from_vec(vecs[n], t0()); basis[n] = f'fitted (rho {r:+.2f})'
        else:
            po[n] = params_from_vec(x0_vector(1), t0())
            basis[n] = f'NEUTRAL (rho {r:+.2f})' if r is not None else 'NEUTRAL (untested)'
    print('vector basis, per §3.59:')
    for n in names:
        print(f'  {n:6s} {basis[n]}')

    data, sleeves, cal = load_all(names=names, params_override=po)
    print(f'\ncalendar {cal[0]} .. {cal[-1]} ({len(cal)} sessions)\n')
    pmf = pm_rule_for(data)
    out = {}
    print(f'  {"arm":30s}{"full":>8s}{"train":>8s}{"test":>8s}{"maxDD":>8s}{"fills":>8s}'
          f'{"fills/yr":>10s}')
    yrs = len(cal)/252

    def row(tag, **kw):
        r = simulate(data, sleeves, cal, **kw)
        print(f'  {tag:30s}{r["full"]*100:>8.1f}{r["train"]*100:>8.1f}{r["test"]*100:>8.1f}'
              f'{r["maxdd"]*100:>8.1f}{r["fills"]:>8d}{r["fills"]/yrs:>10.1f}', flush=True)
        out[tag] = dict(full=r['full'], train=r['train'], test=r['test'],
                        maxdd=r['maxdd'], fills=r['fills'], per_yr=r['fills']/yrs)
        return r

    cap = row('captive (standalone basis)', mode='captive')
    pl = row('pooled', mode='pooled')
    pg = row('pooled + PM rule', mode='pooled', excl_fn=pmf)
    for K in (2, 3, 4):
        nb, cnt = gate_sets(names, K)
        row(f'pooled + PM + breadth K>={K}', mode='pooled', excl_fn=pmf, no_buy=nb)
    print(f'\n  POOLING UPLIFT  full {(pl["full"]-cap["full"])*100:+.1f}pp   '
          f'test {(pl["test"]-cap["test"])*100:+.1f}pp'
          f'   <- the premise the 15% floor rests on')

    print(f'\n  per-name standalone, same vectors (captive, for the record):')
    for n in names:
        d1, s1, c1 = load_all(names=[n], params_override={n: po[n]})
        r1 = simulate(d1, s1, c1, mode='captive')
        print(f'    {n:6s}{r1["full"]*100:>8.1f} full{r1["test"]*100:>8.1f} test'
              f'{r1["fills"]:>6d} fills   {basis[n]}', flush=True)
        out.setdefault('standalone', {})[n] = dict(full=r1['full'], test=r1['test'],
                                                   fills=r1['fills'])
    json.dump(out, open('parallel_book.json', 'w'), indent=1)
    print('\nDONE', flush=True)


if __name__ == '__main__':
    main()
