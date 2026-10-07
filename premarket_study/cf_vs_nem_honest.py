"""
cf_vs_nem_honest.py — the symmetric test: CF and NEM each on their OWN
train-half vectors (7 Oct 2026).

§3.33 declined NEM because the swap only won on NEM's full-sample reference
vector and lost the tested half on its honest train-half fits. That comparison
was asymmetric in one respect worth closing: it set NEM-honest against
CF-DEPLOYED, and the deployed CF vector is itself a full-sample fit (§6). CF's
own A/B vectors were lost with the original fresh_opt_cands.json, so they were
refitted (`python fresh_opt_cands.py CF`) and this runs variant against
matching variant.

Note one residual asymmetry, which favours CF slightly and is the established
convention rather than a choice made here: a name WITH a reference vector is
fitted with ou_W frozen at deployed (the one parameter that held still between
halves), so CF's A is 8-dim and B 6-dim, while NEM — having no prior reference
— was fitted with ou_W free, 9 and 7 dims. Fewer free parameters is the more
conservative fit, so if anything this understates CF's train-half edge and
flatters NEM's.

Usage: BAYES_WORKBOOK=<workbook.xlsx> python cf_vs_nem_honest.py
"""
import json

from fresh_opt import a_params, b_params
from fresh_opt_cands import aw_params, ref_params
from book_sim import load_all, simulate
from baseline_check import ROSTER
from cf_swap_test import pm_rule_for, shape_of, t0

OUT = 'cf_vs_nem_honest.json'


def main():
    c = json.load(open('fresh_opt_cands.json'))
    po0 = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
           'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    nem_ref = aw_params(c['NEM']['reference']['vec'], t0())
    vec = {
        ('CF', 'A'): lambda: a_params(c['CF']['A']['vec'], ref_params('CF')),
        ('CF', 'B'): lambda: b_params(c['CF']['B']['vec'], ref_params('CF'),
                                      c['CF']['B']['mle']),
        ('NEM', 'A'): lambda: a_params(c['NEM']['A']['vec'], nem_ref),
        ('NEM', 'B'): lambda: b_params(c['NEM']['B']['vec'], nem_ref,
                                       c['NEM']['B']['mle']),
    }

    print('captive, verified fills (straight from the fits):')
    print(f'  {"":5s}{"reference full":>16s}{"A train/test":>16s}{"B train/test":>16s}')
    for s in ('CF', 'NEM'):
        r = c[s]
        print(f'  {s:5s}{r["reference"]["full"]*100:>15.1f}%'
              f'{r["A"]["train"]*100:>9.1f}/{r["A"]["test"]*100:<6.1f}'
              f'{r["B"]["train"]*100:>9.1f}/{r["B"]["test"]*100:<6.1f}')

    print('\npooled book, live config — each name on its OWN honest vector\n')
    print(f'  {"":32s}{"full":>7s}{"train":>7s}{"test":>7s}{"maxDD":>7s}'
          f'{"fills":>7s}{"/yr":>6s}{"top3rd":>8s}')
    res, rows = {}, {}
    for var in ('A', 'B'):
        for nm in ('CF', 'NEM'):
            names = ROSTER if nm == 'CF' else [n for n in ROSTER if n != 'CF'] + ['NEM']
            po = dict(po0)
            po[nm] = vec[(nm, var)]()
            d, sl, cal = load_all(names=names, params_override=po)
            r = simulate(d, sl, cal, excl_fn=pm_rule_for(d), collect_trades=True)
            sh = shape_of(r['trades'], nm, len(cal) / 252)
            rows[(nm, var)] = r
            res[f'{nm} {var}'] = dict(full=r['full'], train=r['train'], test=r['test'],
                                      maxdd=r['maxdd'], fills=r['fills'],
                                      per_yr=sh['per_yr'], top3=sh['top3'])
            print(f'  {f"{nm} on its variant {var}":32s}{r["full"]*100:>7.1f}'
                  f'{r["train"]*100:>7.1f}{r["test"]*100:>7.1f}{r["maxdd"]*100:>7.1f}'
                  f'{r["fills"]:>7d}{sh["per_yr"]:>6.0f}{(sh["top3"] or 0)*100:>7.0f}%')
        a, b = rows[('CF', var)], rows[('NEM', var)]
        print(f'  {"   swap delta (NEM - CF)":32s}{(b["full"]-a["full"])*100:>+7.1f}'
              f'{(b["train"]-a["train"])*100:>+7.1f}{(b["test"]-a["test"])*100:>+7.1f}'
              f'{(b["maxdd"]-a["maxdd"])*100:>+7.1f}\n')
        res[f'delta {var}'] = dict(full=b['full'] - a['full'], train=b['train'] - a['train'],
                                   test=b['test'] - a['test'], maxdd=b['maxdd'] - a['maxdd'])

    with open(OUT, 'w') as f:
        json.dump(res, f, indent=1, default=str)
    print(f'saved {OUT}')


if __name__ == '__main__':
    main()
