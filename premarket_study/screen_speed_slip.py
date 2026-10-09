"""
Does the speed-constrained fit survive execution cost?

screen_speed_fast.py buys the book's turnover profile on four names, but it buys
it by cutting the premium -- CF's Bayes sleeve ends at 0.74%, with a median hold
of zero days. A 0.74% premium is roughly fifteen times the modelled commission,
so the result stands or falls on getting the limit fill at the posted price.
The backtest charges p.comm per share each way and models no slippage at all.

This re-scores the fitted vectors with the per-share cost raised, which is the
cleanest available proxy: every extra cent is charged on both the buy and the
sell, exactly where slippage would land. Nothing is refitted -- the question is
whether the EXISTING answer is robust, not whether a costlier world has its own
optimum.

Cost levels are quoted in basis points of each name's median price so they are
comparable across a $40 stock and a $500 one.

Usage:  python3 screen_speed_slip.py
"""
import json
import statistics

from engine import Params, run_model
from two_day import Clock

LEVELS = [0.005, 0.02, 0.05, 0.10]      # $/share each way; 0.005 is the deployed figure


def rescore(c, vec, comm):
    p = c.params(vec)
    p = Params(**{**p.__dict__, 'comm': comm})
    fr = run_model(c.D, c.Ob, c.Hb, c.Lb, c.Cb, p, ou_sigma='resid',
                   same_day_exit=c.chk, collect=True).frames
    eq = fr['equity']
    lo, hi = c.cut, c.N-1
    r = eq[hi]/eq[lo] - 1.0 if eq[lo] > 0 else -1.0
    b = sum(fr['t1']['Z'][lo:hi+1]) + sum(fr['t2']['Z'][lo:hi+1])
    return c.ann(r, lo, hi), b


def main():
    fast = {r['name']: r['vec'] for f in ('ssf_a.json', 'ssf_b.json')
            for r in json.load(open(f))}
    slow = {r['name']: r['vec'] for r in json.load(open('screen_speed.json'))}
    out = []
    print('test-half return at rising per-share cost (nothing refitted)\n')
    print(f'{"name":6s}{"vector":16s}{"px":>7s}' +
          ''.join(f'{f"{c*100:.1f}c":>9s}' for c in LEVELS) + f'{"bp @10c":>9s}{"fills":>7s}')
    for nm in sorted(fast):
        c = Clock(nm, 1, 0)
        px = statistics.median(c.Cb)
        for lbl, vecs in (('speed-constrained', fast), ('return-optimal', slow)):
            if nm not in vecs:
                continue
            res = [rescore(c, vecs[nm], k) for k in LEVELS]
            out.append(dict(name=nm, vector=lbl, px=px,
                            levels=LEVELS, ann=[a for a, _ in res], fills=res[0][1]))
            print(f'{nm:6s}{lbl:16s}{px:>7.0f}' +
                  ''.join(f'{a:>8.1f}%' for a, _ in res) +
                  f'{0.10/px*1e4:>8.0f}b{res[0][1]:>7d}')
    with open('screen_speed_slip.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('\n  10c on a $40 stock is 25bp each way; on a $500 stock, 2bp.')
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
