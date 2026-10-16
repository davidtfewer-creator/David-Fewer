"""
cf_speed_g5_12.py — G5 on speed-constrained CF, re-run on the TWELVE-name book.

User, 16 Oct 2026: *"run the speed-constrained CF through G5 on the twelve"*.

§3.51 declined the fast CF vector on the NINE: captive it cost CF 1.6pp, pooled
it cost the book 3.8pp, because CF's extra fills claimed a share of the same pot
the other eight bid from. The twelve is a different pooling problem and the
direction is genuinely unclear ex ante:

  AGAINST the fast vector — twelve sleeves already split the pot twenty-four ways,
    so capital is scarcer per sleeve and a name that bids on far more mornings
    competes harder for it.
  FOR the fast vector — §3.65 measured the twelve/eleven pooling uplift at
    +17.5pp against the nine's +6.8pp. That uplift exists BECAUSE free sleeves
    absorb capital the holders are not using; a CF that holds for one day instead
    of twelve is free far more often, which is the behaviour pooling rewards.

Config is §3.66's pick: PM rule on all twelve, PARR capped at $400k per order, no
breadth gate (the gate fires 0 times in the test half, §3.66). Deltas quoted
against RETURN-OPTIMAL, not deployed, because the deployed vector is a
full-sample fit (§3.51's convention — the deployed row is marked [lookahead]).

Usage: BAYES_WORKBOOK=<xlsx> python3 cf_speed_g5_12.py [--capital 6900000]
"""
import json
import sys

from baseline_check import ROSTER
from book12 import NEW, pm_rule_for
from book_sim import load_all, simulate
from cf_speed_g5 import cf_vectors, params_from_vec
from cf_swap_test import BAR, WINDOWS, shape_of, t0
from parallel_book import load_rho, load_vecs
from two_day import x0_vector

PARR_CAP = 400_000
OUT = 'cf_speed_g5_12.json'


def added_params():
    """RTX, DE and PARR exactly as the twelve-name runs set them (§3.64/§3.66)."""
    rho, vecs = load_rho(), load_vecs()
    po = {}
    for n in NEW:
        r = rho.get(n)
        po[n] = params_from_vec(vecs[n] if (r is not None and r >= 0.20 and n in vecs)
                                else x0_vector(1), t0())
    return po


def main():
    cap = 6_900_000
    if '--capital' in sys.argv:
        cap = float(sys.argv[sys.argv.index('--capital') + 1])
    base_po, cfvecs = cf_vectors()
    base_po = dict(base_po, **added_params())
    names12 = ROSTER + NEW
    cmap = {'PARR': PARR_CAP}
    res, runs, trades = {}, {}, {}

    print(f'pooled TWELVE-name book, PM on all 12, PARR<=${PARR_CAP/1e3:.0f}k, no breadth gate')
    print(f'capital ${cap/1e6:.2f}m — only CF\'s vector changes\n')
    print(f'  {"CF vector":24s}{"full":>8s}{"train":>8s}{"test":>8s}{"maxDD":>8s}'
          f'{"fills":>7s}{"/yr":>7s}    | delta vs return-optimal', flush=True)

    def run(names, po, tag):
        d, s, c = load_all(names=names, params_override=po)
        r = simulate(d, s, c, capital=cap, mode='pooled', collect_trades=True,
                     excl_fn=pm_rule_for(d, set(names)),
                     name_cap=cmap if 'PARR' in names else None)
        r['_yrs'], r['_cal'] = len(c)/252, c
        return r

    for tag, p in cfvecs.items():
        runs[tag] = run(names12, dict(base_po, CF=p), tag)

    def line(tag, r, bench):
        y = r['_yrs']
        d = ''
        if bench is not None:
            d = (f"    | {(r['full']-bench['full'])*100:+.1f} /"
                 f" {(r['train']-bench['train'])*100:+.1f} /"
                 f" {(r['test']-bench['test'])*100:+.1f} /"
                 f" {(r['maxdd']-bench['maxdd'])*100:+.1f}")
        print(f'  {tag:24s}{r["full"]*100:>8.1f}{r["train"]*100:>8.1f}{r["test"]*100:>8.1f}'
              f'{r["maxdd"]*100:>8.1f}{r["fills"]:>7d}{r["fills"]/y:>7.0f}{d}', flush=True)
        return dict(full=r['full'], train=r['train'], test=r['test'],
                    maxdd=r['maxdd'], fills=r['fills'], per_yr=r['fills']/y)

    bench = runs['return-optimal']
    for tag in cfvecs:
        res[tag] = line(tag, runs[tag], None if tag == 'return-optimal' else bench)
        trades[tag] = runs[tag]['trades']

    n11 = [n for n in names12 if n != 'CF']
    r11 = run(n11, base_po, 'drop CF')
    res['drop CF (eleven names)'] = line('drop CF (eleven names)', r11, bench)

    # ---- CF's own trade shape
    print(f'\nCF\'s OWN TRADES — the §3.32 bar: >={BAR["per_yr"]}/yr AND top third <'
          f'{BAR["top3"]*100:.0f}% of P&L\n')
    print(f'  {"CF vector":24s}{"/yr":>6s}{"avg":>8s}{"hold":>6s}{"stops":>7s}'
          f'{"losers":>8s}{"top3":>8s}{"CF P&L":>10s}  verdict')
    for tag in cfvecs:
        sh = shape_of(trades[tag], 'CF', runs[tag]['_yrs'])
        pnl = sum(t['pnl'] for t in trades[tag] if t['name'] == 'CF')
        ok = sh['per_yr'] >= BAR['per_yr'] and sh['top3'] is not None and sh['top3'] < BAR['top3']
        print(f'  {tag:24s}{sh["per_yr"]:>6.0f}{sh["avg"]*100:>7.2f}%{sh["med_hold"]:>6.1f}'
              f'{sh["stops"]:>7d}{sh["losers"]*100:>7.0f}%{sh["top3"]*100:>7.0f}%'
              f'{pnl/1e6:>9.2f}m  {"PASSES" if ok else "fails the bar"}')
        res.setdefault('shapes', {})[tag] = dict(sh, pnl=pnl)

    # ---- does the extra turnover come out of the other eleven?
    print(f'\nWHERE THE CAPITAL GOES — P&L by name, return-optimal -> speed-constrained\n')
    ro_t, sp_t = trades['return-optimal'], trades['speed-constrained']
    def bn(ts):
        d = {}
        for t in ts:
            d[t['name']] = d.get(t['name'], 0.0) + t['pnl']
        return d
    a, b = bn(ro_t), bn(sp_t)
    print(f'  {"name":6s}{"return-opt":>12s}{"speed":>12s}{"delta":>11s}')
    for n in sorted(set(a) | set(b), key=lambda k: (b.get(k, 0) - a.get(k, 0))):
        print(f'  {n:6s}{a.get(n,0)/1e3:>11.0f}k{b.get(n,0)/1e3:>11.0f}k'
              f'{(b.get(n,0)-a.get(n,0))/1e3:>10.0f}k')
    print(f'  {"TOTAL":6s}{sum(a.values())/1e3:>11.0f}k{sum(b.values())/1e3:>11.0f}k'
          f'{(sum(b.values())-sum(a.values()))/1e3:>10.0f}k')
    res['by_name'] = {n: dict(ro=a.get(n, 0), sp=b.get(n, 0)) for n in set(a) | set(b)}

    # ---- stress windows
    print(f'\nSTRESS WINDOWS — CF is carried for its correlation, not its return\n')
    print(f'  {"CF vector":24s}' + ''.join(f'{w[0][:21]:>23s}' for w in WINDOWS), flush=True)
    for tag in list(cfvecs) + ['drop CF (eleven names)']:
        r = r11 if tag.startswith('drop') else runs[tag]
        cal, eq = r['_cal'], r['equity']
        out = []
        for _, lo, hi in WINDOWS:
            ix = [i for i, d in enumerate(cal) if lo <= d <= hi]
            out.append((eq[ix[-1]]/eq[ix[0]] - 1)*100 if len(ix) > 1 else float('nan'))
        print(f'  {tag:24s}' + ''.join(f'{v:>22.1f}%' for v in out))
        res.setdefault('stress', {})[tag] = out

    json.dump(res, open(OUT, 'w'), indent=1, default=str)
    print(f'\nwrote {OUT}\nDONE', flush=True)


if __name__ == '__main__':
    main()
