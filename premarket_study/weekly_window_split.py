"""
Where in the sample does each name's weekly-model return actually sit?

A full-sample figure hides its own timing. Weeks 1-59 are inside every walk-forward training
window, so any advantage concentrated there is never tested; weeks 60-120 are the part that was
scored out of sample in at least one fold. Splitting the two separates a configuration that works
from one that fitted an early run.

This is the check that settled the four laggards: PLTR's optimised parameters return 365% over
the first half and 3.1% over the second, which is why a 126% full-sample headline survives no
walk-forward. It is also the check that supports NVDA, whose second half is the stronger of the
two.
"""
from weekly_name import Name, pr, P

CONFIGS = {
    'TSLA': (0.200, 0.070),
    'PLTR': (0.065, 0.145),
    'SOFI': (0.105, 0.095),
    'SPOT': (0.045, 0.105),
}


def split(stock, cap, prem):
    nm = Name(stock); N = nm.N
    print(f'\n{stock}  (optimised cap {cap:.3f} prem {prem:.3f})')
    print(f'  {"window":20s}{"optimised":>12s}{"NVDA params":>14s}{"gap":>11s}')
    for lbl, lo, hi in (('weeks 1-59 (train)', 1, 59), ('weeks 60-120 (tested)', 60, N-1),
                        ('full sample', 1, N-1)):
        a, _ = nm.seg(pr(cap, prem), lo, hi)
        b, _ = nm.seg(P, lo, hi)
        aa, bb = nm.ann(a, lo, hi)*100, nm.ann(b, lo, hi)*100
        print(f'  {lbl:20s}{aa:>11.1f}%{bb:>13.1f}%{aa-bb:>+10.1f}pp')


if __name__ == '__main__':
    for s, (c, q) in CONFIGS.items():
        split(s, c, q)
    print('\nFor NVDA and AVGO see weekly_mr_2param.py and weekly_avgo.py; NVDA runs 41.5% over '
          'weeks 1-59\nand 81.7% over 60-120, so its result is not front-loaded.')
