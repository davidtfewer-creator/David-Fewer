"""
lowdd_book.py — a lower-drawdown book at ~60% return (user, 21 Oct 2026).

User: *"I'd be happy enough with an overall 60% return if we could bring the max
drawdown down significantly."* So the objective is a different point on the
risk/return frontier, not more return.

Two levers, tested side by side because the user's tolerance for lower return
makes the second one available:
  ADD     uncorrelated, FITTABLE names (beta to the AI factor < 0.20 and
          train->test rho >= 0.20) -- dilutes the AI exposure
  REMOVE  the highest-beta AI names -- VRT and MRVL fall hardest on the AI
          factor's worst days (-10.3%, -10.4%), so removing them attacks the
          drawdown directly rather than diluting it

Every name gets the PM rule (cache rebuilt 21 Oct to cover the Box additions),
no breadth gate (§3.66). Vectors by the established rho rule.

Usage: BAYES_WORKBOOK=<xlsx> python3 lowdd_book.py ADD1,ADD2,... [--drop VRT,MRVL]
       arms are passed as roster specs on the command line, see main()
"""
import json
import sys

from baseline_check import ROSTER
from book12 import pm_rule_for
from book_sim import load_all, simulate
from cf_speed_g5 import params_from_vec
from cf_swap_test import WINDOWS, t0
from fresh_opt_cands import aw_params
from parallel_book import load_rho, load_vecs
from two_day import x0_vector

CAP = 6_900_000
TWELVE = ROSTER + ['RTX', 'DE', 'NVDA']
AI = {'AVGO', 'MU', 'TSM', 'MRVL', 'VRT', 'VST', 'NVDA'}


def params(names):
    rho, vecs = load_rho(), load_vecs()
    c = json.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
          'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    basis = {}
    for n in names:
        if n in ROSTER and n not in ('MRVL', 'AVGO'):
            continue                                  # live workbook vector
        if n in po:
            continue
        r = rho.get(n)
        fit = r is not None and r >= 0.20 and n in vecs
        po[n] = params_from_vec(vecs[n] if fit else x0_vector(1), t0())
        basis[n] = f'{"fitted" if fit else "NEUTRAL"} ({r:+.2f})' if r is not None else 'NEUTRAL (no rho)'
    return po, basis


def run(tag, names, po, out):
    d, s, cal = load_all(names=names, params_override=po)
    r = simulate(d, s, cal, capital=CAP, mode='pooled', collect_trades=True,
                 excl_fn=pm_rule_for(d, set(names)))
    y = len(cal) / 252
    cs = [t['cost'] for t in r['trades']]
    ai = sum(t['cost'] for t in r['trades'] if t['name'] in AI) / sum(cs)
    eq, st = r['equity'], []
    for _, lo, hi in WINDOWS:
        ix = [i for i, dd in enumerate(cal) if lo <= dd <= hi]
        st.append((eq[ix[-1]]/eq[ix[0]]-1)*100 if len(ix) > 1 else float('nan'))
    rd = r['full'] / r['maxdd']
    print(f'  {tag:38s}{len(names):>3d}{r["full"]*100:>7.1f}{r["test"]*100:>7.1f}'
          f'{r["maxdd"]*100:>7.1f}{rd:>7.2f}{r["fills"]/y:>8.0f}{ai*100:>6.0f}%  '
          + ' / '.join(f'{x:+.1f}' for x in st), flush=True)
    out[tag] = dict(names=names, full=r['full'], train=r['train'], test=r['test'],
                    maxdd=r['maxdd'], ret_dd=rd, per_yr=r['fills']/y, ai_share=ai, stress=st)
    return out[tag]


def main():
    """argv: one roster spec per arm, as  'label=+A+B-C'  relative to TWELVE."""
    specs = [a for a in sys.argv[1:] if '=' in a]
    arms = [('TWELVE (current)', TWELVE)]
    for sp in specs:
        lbl, ops = sp.split('=', 1)
        names = list(TWELVE)
        for tok in ops.replace('-', ' -').replace('+', ' +').split():
            nm = tok[1:]
            if tok[0] == '+' and nm not in names:
                names.append(nm)
            elif tok[0] == '-' and nm in names:
                names.remove(nm)
        arms.append((lbl, names))
    allnames = sorted({n for _, ns in arms for n in ns})
    po, basis = params(allnames)
    for n, b in sorted(basis.items()):
        print(f'  {n:5s} {b}')
    print(f'  capital ${CAP/1e6:.2f}m\n')
    print(f'  {"arm":38s}{"n":>3s}{"full":>7s}{"test":>7s}{"maxDD":>7s}{"r/DD":>7s}'
          f'{"fills":>8s}{"AI$":>7s}  stress Jan-Apr25 / Feb-Jun25 / Jun-Jul26')
    out = {}
    for tag, names in arms:
        run(tag, names, po, out)
    json.dump(out, open('lowdd_book.json', 'w'), indent=1)
    print('\nwrote lowdd_book.json')


if __name__ == '__main__':
    main()
