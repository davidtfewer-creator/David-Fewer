"""
G5 on PARR: swap it for VLO, do not add it alongside.

§3.54 settled what PARR is. It correlates 0.72 with VLO against the book's own
0.30 average pairwise, so adding it is a second helping of refining, not
diversification. What it might be is a FASTER VLO: 109.6 fills/yr on a zero-day
median against VLO's 25.1 on four days, at essentially the same exposure. So the
marginal test is the swap, and the eight-name book (VLO dropped, nothing added)
is the third arm that says whether either refiner earns its slot at all.

THE VECTOR. §3.54 also found PARR's train half ANTI-predicts its test half
(rank correlation -0.53 over 400 random vectors, against GM +0.33 and CF +0.08).
Fitting PARR therefore selects a vector to fail, and the fitted one duly landed
below its own 25th percentile. The vector used here is the component-wise median
of the stored reference vectors -- the same neutral seed the screens use, chosen
with no reference to PARR's history at all. That is the honest choice for a name
that cannot be fitted, and it is not lookahead: nothing about PARR informed it.

Everything else follows cf_speed_g5.py: pooled nine-name book, live config with
the 09:00/4% pre-market rule, both halves, drawdown, the §3.32 shape bar and the
stress windows, since a diversifier is carried for its behaviour in those.

Usage: BAYES_WORKBOOK=<xlsx> python3 parr_g5.py
"""
import json

from baseline_check import ROSTER
from book_sim import load_all, simulate
from cf_speed_g5 import params_from_vec
from cf_swap_test import BAR, WINDOWS, pm_rule_for, shape_of, t0
from fresh_opt_cands import aw_params
from two_day import x0_vector

OUT = 'parr_g5.json'


def main():
    c = json.load(open('fresh_opt_cands.json'))
    base_po = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
               'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    parr = params_from_vec(x0_vector(1), t0())
    print(f'PARR on the un-fitted reference-median vector: prem {parr.premium:.5f} / '
          f'{parr.ou_prem:.5f}, peak_cap {parr.peak_cap:.4f}, ou_W {parr.ou_W}\n', flush=True)

    arms = {
        'nine names (with VLO)': (ROSTER, {}),
        'swap VLO -> PARR':      ([n for n in ROSTER if n != 'VLO'] + ['PARR'], {'PARR': parr}),
        'add PARR (ten names)':  (ROSTER + ['PARR'], {'PARR': parr}),
        'drop VLO (eight names)':([n for n in ROSTER if n != 'VLO'], {}),
    }
    print(f'  {"":24s}{"full":>8s}{"train":>8s}{"test":>8s}{"maxDD":>8s}{"fills":>7s}'
          f'    | delta vs nine', flush=True)
    res, runs, shapes = {}, {}, {}
    for tag, (names, extra) in arms.items():
        po = dict(base_po); po.update(extra)
        data, sleeves, cal = load_all(names=names, params_override=po)
        r = simulate(data, sleeves, cal, excl_fn=pm_rule_for(data), collect_trades=True)
        runs[tag] = r
        yrs = len(cal)/252
        for nm in ('VLO', 'PARR'):
            if nm in names and nm not in shapes:
                shapes[nm] = shape_of(r['trades'], nm, yrs)
    b = runs['nine names (with VLO)']
    for tag in arms:
        r = runs[tag]
        d = ''
        if tag != 'nine names (with VLO)':
            d = (f'   | {(r["full"]-b["full"])*100:+6.1f}{(r["train"]-b["train"])*100:+7.1f}'
                 f'{(r["test"]-b["test"])*100:+7.1f}{(r["maxdd"]-b["maxdd"])*100:+7.1f}')
        print(f'  {tag:24s}{r["full"]*100:>8.1f}{r["train"]*100:>8.1f}{r["test"]*100:>8.1f}'
              f'{r["maxdd"]*100:>8.1f}{r["fills"]:>7d}{d}', flush=True)
        res[tag] = dict(full=r['full'], train=r['train'], test=r['test'],
                        maxdd=r['maxdd'], fills=r['fills'])

    print(f'\n  SHAPE in the pooled book, §3.32 bar (>={BAR["per_yr"]}/yr, '
          f'top third <{BAR["top3"]*100:.0f}%)\n')
    print(f'  {"name":6s}{"/yr":>6s}{"avg":>8s}{"hold":>6s}{"stops":>7s}{"lose%":>7s}'
          f'{"%/$-day":>9s}{"top 3rd":>9s}{"P&L $":>12s}   verdict', flush=True)
    for nm, v in shapes.items():
        if not v:
            print(f'  {nm:6s}  no trades'); continue
        ok = v['per_yr'] >= BAR['per_yr'] and (v['top3'] or 1) < BAR['top3']
        print(f'  {nm:6s}{v["per_yr"]:>6.0f}{v["avg"]*100:>+7.2f}%{v["med_hold"]:>6.0f}'
              f'{v["stops"]:>7d}{v["losers"]*100:>6.0f}%{v["dollar_day"]*100:>8.3f}%'
              f'{(v["top3"] or 0)*100:>8.0f}%{v["pnl"]:>12,.0f}   '
              f'{"CLEARS the bar" if ok else "fails the bar"}', flush=True)
        res.setdefault('shapes', {})[nm] = v

    print(f'\n  STRESS WINDOWS\n')
    print(f'  {"":24s}' + ''.join(f'{w[0][:21]:>23s}' for w in WINDOWS), flush=True)
    for tag, (names, extra) in arms.items():
        po = dict(base_po); po.update(extra)
        d2, s2, c2 = load_all(names=names, params_override=po)
        kw = dict(excl_fn=pm_rule_for(d2), collect_trades=True)
        cells = []
        for lbl, lo, hi in WINDOWS:
            r = simulate(d2, s2, c2, date_lo=lo, date_hi=hi, **kw)
            cells.append(f'{r["full"]*100:+9.1f}% DD{r["maxdd"]*100:5.1f}')
            res.setdefault('stress', {}).setdefault(tag, []).append(
                dict(window=lbl, ret=r['full'], maxdd=r['maxdd']))
        print(f'  {tag:24s}' + ''.join(f'{x:>23s}' for x in cells), flush=True)

    json.dump(res, open(OUT, 'w'), indent=1, default=str)
    print(f'\nsaved {OUT}\nDONE', flush=True)


if __name__ == '__main__':
    main()
