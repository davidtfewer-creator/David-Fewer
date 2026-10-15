"""
Can each candidate be FITTED at all?

§3.54 found PARR's train half anti-predicts its test half: across 400 random
vectors the rank correlation between train and test performance was -0.53, so
the optimiser was systematically selecting vectors that would fail, and the
fitted result landed below the name's own 25th percentile. GM scored +0.33 and
CF +0.08 on the same test.

That makes this the cheapest disqualifier available, and it has to run BEFORE a
book is built on these names: a single train-half fit reports a number for every
name, but the number only means something where fitting works.

Reads: rho well above zero = fitting earns something. Near zero = the fitted
vector is arbitrary and the planning figure should be the distribution. Negative
= fitting actively hurts.

Usage:  python3 fittability.py TICKER [TICKER ...]
"""
import json
import random
import statistics
import sys

import numpy as np

from two_day import Clock, bounds_for, x0_vector

DRAWS = 300


def rank(x):
    o = sorted(range(len(x)), key=lambda i: x[i])
    r = [0.0]*len(x)
    for p, i in enumerate(o):
        r[i] = p
    return r


def main():
    names = [a for a in sys.argv[1:] if not a.startswith('--')]
    bnd = bounds_for(1)
    rng = random.Random(42)
    vecs = [[rng.uniform(lo, hi) for lo, hi in bnd] for _ in range(DRAWS)]
    print(f'{DRAWS} random vectors per name, scored on BOTH halves\n')
    print(f'{"name":6s}{"usable":>8s}{"test median":>13s}{"25th":>9s}{"75th":>9s}'
          f'{"train->test rho":>17s}   reading')
    out = []
    for nm in names:
        c = Clock(nm, 1, 0)
        tr, te = [], []
        for v in vecs:
            a, ba = c.seg(v, 0, c.cut-1)
            b, bb = c.seg(v, c.cut, c.N-1)
            if ba < 5 or bb < 5:
                continue
            tr.append(c.ann(a, 0, c.cut-1)); te.append(c.ann(b, c.cut, c.N-1))
        if len(tr) < 20:
            print(f'{nm:6s}  too few usable vectors'); continue
        rho = float(np.corrcoef(rank(tr), rank(te))[0, 1])
        s = sorted(te)
        read = ('fitting earns something' if rho >= 0.20 else
                'FITTING HURTS — vector is a guess' if rho <= -0.20 else
                'fitting is ~useless; plan on the distribution')
        out.append(dict(name=nm, n=len(tr), median=statistics.median(te),
                        q25=s[len(s)//4], q75=s[3*len(s)//4], rho=rho, reading=read))
        print(f'{nm:6s}{len(tr):>8d}{statistics.median(te):>12.1f}%{s[len(s)//4]:>8.1f}%'
              f'{s[3*len(s)//4]:>8.1f}%{rho:>+17.2f}   {read}', flush=True)
        json.dump(out, open('fittability.json', 'w'), indent=1)
    print('\nDONE', flush=True)


if __name__ == '__main__':
    main()
