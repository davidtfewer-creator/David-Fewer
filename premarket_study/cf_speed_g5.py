"""
G5 on speed-constrained CF: the cleanest marginal test this book has had.

§3.50 found CF's slowness is a parameter choice, not the name — the same stock
runs at 25.7, 42.6 or 89.4 fills a year on three different vectors — and that the
speed-constrained vector costs only 1.6pp on the unseen half. G5 is the gate that
has actually killed every candidate declined since §3.14a, and none of §3.50 went
through it.

This is a cleaner G5 than any swap attempted before, because NOTHING about the
book changes except one name's parameter vector. No roster change, no new data,
no correlation argument — the AI beta, the capacity and the stress behaviour of
the slot are all held fixed by construction. If the book improves, it is the
vector.

Three arms, identical in every other respect:
  deployed        REF['CF'] — what the workbook runs. A FULL-SAMPLE fit, so it
                  carries lookahead and is shown for continuity, not as a fair
                  comparator.
  return-optimal  the train-half fit from screen_speed.py. THIS is the honest
                  baseline: same protocol, same half, fitted for return alone.
  speed           the train-half fit from screen_speed_fast.py, G4 in the
                  objective.

§3.33 made exactly this mistake once — it set an honest candidate against
CF-DEPLOYED and had to refit CF's own vectors to get a symmetric comparison. The
deltas below are therefore quoted against RETURN-OPTIMAL, not against deployed.

Also reported: CF's shape in the pooled book against the §3.32 bar (book
correlation <=0.30, >=50 trades/yr, top third of trades carrying <80% of P&L) —
which already demanded 50 trades a year of any REPLACEMENT for CF, and was never
once turned on CF itself.

Usage: BAYES_WORKBOOK=<workbook.xlsx> python3 cf_speed_g5.py
"""
import datetime as dt
import json
import statistics

from baseline_check import ROSTER
from book_sim import load_all, simulate
from cf_swap_test import BAR, WINDOWS, pm_rule_for, shape_of, t0
from engine import Params
from fresh_opt_cands import aw_params, ref_params

OUT = 'cf_speed_g5.json'


def params_from_vec(vec, t):
    """The 10-dim optimise_candidates vector -> Params (aw_params takes the 9-dim A form)."""
    return Params(lam=vec[0], phi_L=vec[1], psi=vec[2], k=vec[3], premium=vec[4],
                  peak_cap=vec[5], ou_buf_k=vec[6], ou_prem=vec[7], ou_cap=vec[8],
                  ou_W=int(round(vec[9])), comm=t.comm, capital=t.capital,
                  interest=t.interest, stop_days=t.stop_days, bayes_pct=t.bayes_pct,
                  years=t.years)


def cf_vectors():
    c = json.load(open('fresh_opt_cands.json'))
    base = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
            'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    ro = next(r['vec'] for r in json.load(open('screen_speed.json')) if r['name'] == 'CF')
    sp = next(r['vec'] for r in json.load(open('ssf_a.json')) if r['name'] == 'CF')
    return base, {
        'deployed [lookahead]': ref_params('CF'),
        'return-optimal': params_from_vec(ro, t0()),
        'speed-constrained': params_from_vec(sp, t0()),
    }


def line(tag, r, b=None):
    d = ''
    if b:
        d = (f'   | {(r["full"]-b["full"])*100:+6.1f}{(r["train"]-b["train"])*100:+7.1f}'
             f'{(r["test"]-b["test"])*100:+7.1f}{(r["maxdd"]-b["maxdd"])*100:+7.1f}')
    print(f'  {tag:24s}{r["full"]*100:>8.1f}{r["train"]*100:>8.1f}{r["test"]*100:>8.1f}'
          f'{r["maxdd"]*100:>8.1f}{r["fills"]:>7d}{d}', flush=True)
    return dict(full=r['full'], train=r['train'], test=r['test'],
                maxdd=r['maxdd'], fills=r['fills'])


def main():
    base_po, cfvecs = cf_vectors()
    res, runs, shapes = {}, {}, {}

    print(f'pooled nine-name book, live config (PM rule on), only CF\'s vector changes\n')
    print(f'  {"CF vector":24s}{"full":>8s}{"train":>8s}{"test":>8s}{"maxDD":>8s}'
          f'{"fills":>7s}    | delta vs return-optimal', flush=True)
    for tag, p in cfvecs.items():
        po = dict(base_po); po['CF'] = p
        data, sleeves, cal = load_all(names=ROSTER, params_override=po)
        r = simulate(data, sleeves, cal, excl_fn=pm_rule_for(data), collect_trades=True)
        runs[tag] = r
        shapes[tag] = shape_of(r['trades'], 'CF', len(cal)/252)
    bench = runs['return-optimal']
    for tag in cfvecs:
        res[tag] = line(tag, runs[tag], None if tag == 'return-optimal' else bench)

    # the book without CF at all, for scale
    d8, s8, c8 = load_all(names=[n for n in ROSTER if n != 'CF'], params_override=base_po)
    r8 = simulate(d8, s8, c8, excl_fn=pm_rule_for(d8), collect_trades=True)
    res['drop CF (eight)'] = line('drop CF (eight names)', r8, bench)

    print(f'\nCF\'s SHAPE in the pooled book, against the §3.32 bar '
          f'(>={BAR["per_yr"]}/yr, top third <{BAR["top3"]*100:.0f}%)\n')
    print(f'  {"CF vector":24s}{"/yr":>6s}{"avg":>8s}{"hold":>6s}{"stops":>7s}'
          f'{"lose%":>7s}{"%/$-day":>9s}{"top 3rd":>9s}{"P&L $":>11s}   verdict', flush=True)
    for tag, v in shapes.items():
        if not v:
            print(f'  {tag:24s}  no CF trades', flush=True)
            continue
        ok = v['per_yr'] >= BAR['per_yr'] and (v['top3'] or 1) < BAR['top3']
        print(f'  {tag:24s}{v["per_yr"]:>6.0f}{v["avg"]*100:>+7.2f}%{v["med_hold"]:>6.0f}'
              f'{v["stops"]:>7d}{v["losers"]*100:>6.0f}%{v["dollar_day"]*100:>8.3f}%'
              f'{(v["top3"] or 0)*100:>8.0f}%{v["pnl"]:>11,.0f}   '
              f'{"CLEARS the bar" if ok else "fails the bar"}', flush=True)
        res.setdefault('shapes', {})[tag] = v

    print(f'\nSTRESS WINDOWS — CF is carried for its correlation, not its return\n')
    print(f'  {"CF vector":24s}' + ''.join(f'{w[0][:21]:>23s}' for w in WINDOWS), flush=True)
    for tag, p in list(cfvecs.items()) + [('drop CF (eight names)', None)]:
        if p is None:
            names, po = [n for n in ROSTER if n != 'CF'], base_po
        else:
            names, po = ROSTER, dict(base_po, CF=p)
        d2, s2, c2 = load_all(names=names, params_override=po)
        kw = dict(excl_fn=pm_rule_for(d2), collect_trades=True)
        cells = []
        for _, lo, hi in WINDOWS:
            r = simulate(d2, s2, c2, date_lo=lo, date_hi=hi, **kw)
            cells.append(f'{r["full"]*100:+9.1f}% DD{r["maxdd"]*100:5.1f}')
            res.setdefault('stress', {}).setdefault(tag, []).append(
                dict(window=_, ret=r['full'], maxdd=r['maxdd']))
        print(f'  {tag:24s}' + ''.join(f'{c:>23s}' for c in cells), flush=True)

    with open(OUT, 'w') as f:
        json.dump(res, f, indent=1, default=str)
    print(f'\nsaved {OUT}\nDONE', flush=True)


if __name__ == '__main__':
    main()
