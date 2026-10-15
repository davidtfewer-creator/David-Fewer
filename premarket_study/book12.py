"""
The twelve-name book: the nine plus PARR, RTX and DE, gates on the nine only.

User's design, and the two judgements in it are both supported by what has been
measured. §3.61 found the PM rule COSTS the three-name set 5.8pp and nearly
doubles its drawdown, and the breadth gate adds nothing on top, so the overlays
are applied to the original nine and withheld from the three. And spreading the
same capital over twelve names rather than nine shrinks the typical order, which
is the constraint PARR runs into: §3.58 showed the nine-name book already
breaches its own liquidity gate on CF, and PARR is thinner than CF.

PARR's liquidity is ESTIMATED, not measured — its Box file carries no volume
column (§3.61). On the user's figure of ~1m shares/day at ~$70 (ADV ~$70m) and
the at-bid ratio RTX and DE both show (~42% of ADV), the median at-bid is ~$29m,
so §3.37's 1% leg caps an order at ~$0.29m. The thin-day leg works out looser
(~$0.45m) on those names' p10/median ratio, so the median leg binds.

Vectors: the nine as deployed/reference; PARR on the NEUTRAL seed (rho −0.49,
unfittable), RTX and DE on their fitted train-half vectors (+0.36, +0.38).

Usage: BAYES_WORKBOOK=<xlsx> python3 book12.py [--capital 6900000]
"""
import json
import pickle
import statistics
import sys

from baseline_check import ROSTER
from book_sim import load_all, simulate
from cf_speed_g5 import params_from_vec
from cf_swap_test import t0
from fresh_opt_cands import aw_params, daily_from_5min
from parallel_book import gate_sets, load_rho, load_vecs
from two_day import x0_vector

NEW = ['PARR', 'RTX', 'DE']
PARR_CAP = 0.29e6                      # estimated, see docstring
GATE_K = 4                             # §3.23, on the nine only


def pm_rule_for(data, only, cut='09:00', thr=0.04):
    """The §3.16 pre-market rule, applied ONLY to the named set."""
    pm = pickle.load(open('data_pm/pm_last_cuts.pkl', 'rb'))[cut]
    def f(name, i, bid):
        if name not in only:
            return False
        p = pm.get(name, {}).get(data[name]['dts'][i])
        return p is not None and bid < p*(1 - thr)
    return f


def main():
    cap = 6_900_000
    if '--capital' in sys.argv:
        cap = float(sys.argv[sys.argv.index('--capital')+1])
    rho, vecs = load_rho(), load_vecs()
    c = json.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
          'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    basis = {}
    for n in NEW:
        r = rho.get(n)
        if r is not None and r >= 0.20 and n in vecs:
            po[n] = params_from_vec(vecs[n], t0()); basis[n] = f'fitted ({r:+.2f})'
        else:
            po[n] = params_from_vec(x0_vector(1), t0()); basis[n] = f'NEUTRAL ({r:+.2f})'
    print('added names:', ', '.join(f'{n} {basis[n]}' for n in NEW))
    print(f'capital ${cap/1e6:.1f}m\n')

    names12 = ROSTER + NEW
    d12, s12, c12 = load_all(names=names12, params_override=po)
    d9, s9, c9 = load_all(names=ROSTER, params_override=po)
    yrs = len(c12)/252
    pm9_12 = pm_rule_for(d12, set(ROSTER))
    pm_all = pm_rule_for(d12, set(names12))
    pm9_9 = pm_rule_for(d9, set(ROSTER))
    nb9, _ = gate_sets(ROSTER, GATE_K)

    out = {}
    print(f'  {"arm":34s}{"full":>8s}{"train":>8s}{"test":>8s}{"maxDD":>8s}'
          f'{"fills":>8s}{"/yr":>8s}')

    def row(tag, data, sl, cal, **kw):
        r = simulate(data, sl, cal, capital=cap, collect_trades=True, **kw)
        y = len(cal)/252
        print(f'  {tag:34s}{r["full"]*100:>8.1f}{r["train"]*100:>8.1f}{r["test"]*100:>8.1f}'
              f'{r["maxdd"]*100:>8.1f}{r["fills"]:>8d}{r["fills"]/y:>8.1f}', flush=True)
        out[tag] = dict(full=r['full'], train=r['train'], test=r['test'],
                        maxdd=r['maxdd'], fills=r['fills'], per_yr=r['fills']/y)
        return r

    base = row('NINE, live config (baseline)', d9, s9, c9, mode='pooled', excl_fn=pm9_9)
    row('TWELVE, no overlays', d12, s12, c12, mode='pooled')
    row('TWELVE, PM on all 12', d12, s12, c12, mode='pooled', excl_fn=pm_all)
    r12 = row('TWELVE, PM on the NINE only', d12, s12, c12, mode='pooled', excl_fn=pm9_12)
    rg = row(f'TWELVE, PM + breadth K>={GATE_K} on NINE', d12, s12, c12,
             mode='pooled', excl_fn=pm9_12, no_buy=nb9)
    cp = row('TWELVE captive (for uplift)', d12, s12, c12, mode='captive', excl_fn=pm9_12)

    print(f'\n  vs the nine-name baseline: full {(r12["full"]-base["full"])*100:+.1f}pp'
          f'   test {(r12["test"]-base["test"])*100:+.1f}pp'
          f'   maxDD {(r12["maxdd"]-base["maxdd"])*100:+.1f}pp')
    print(f'  pooling uplift within the twelve: full '
          f'{(r12["full"]-cp["full"])*100:+.1f}pp   test {(r12["test"]-cp["test"])*100:+.1f}pp')

    # ---- does spreading over twelve actually fix PARR's order size?
    print(f'\n  PARR ORDER SIZES in the twelve-name book (cap ~${PARR_CAP/1e6:.2f}m, estimated)\n')
    by = {}
    for t in r12['trades']:
        by.setdefault(t['name'], []).append(t['cost'])
    for n in NEW:
        cs = sorted(by.get(n, []))
        if not cs:
            continue
        p95 = cs[min(len(cs)-1, int(len(cs)*0.95))]
        over = sum(1 for x in cs if x > PARR_CAP) if n == 'PARR' else None
        line = (f'    {n:6s} orders {len(cs):>4d}  median ${statistics.median(cs)/1e6:.2f}m'
                f'  95th ${p95/1e6:.2f}m  max ${max(cs)/1e6:.2f}m')
        if n == 'PARR':
            line += f'   OVER CAP {over}/{len(cs)} ({over/len(cs)*100:.0f}%)'
        print(line, flush=True)
        out.setdefault('orders', {})[n] = dict(n=len(cs), median=statistics.median(cs),
                                               p95=p95, mx=max(cs))
    cs = sorted(by.get('PARR', []))
    if cs:
        out['parr_over_cap'] = sum(1 for x in cs if x > PARR_CAP)/len(cs)*100
    json.dump(out, open('book12.json', 'w'), indent=1)
    print('\nDONE', flush=True)


if __name__ == '__main__':
    main()
