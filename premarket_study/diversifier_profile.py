"""
diversifier_profile.py — can a name be both uncorrelated and fast? (7 Oct 2026)

Companion to cf_profile.py, which confirmed the user's reading of CF: slowest
in the book (24 trades/yr), longest held (12d), and its best third of trades
carries 102% of its P&L -- the other two thirds lose money net.

The question that decides whether a replacement exists: is that profile CF's,
or is it what being uncorrelated costs in this era? 3.14 already found genuine
diversifier candidates scarce ("the premium engine needs volatility, and in
this era volatility itself is AI-correlated") and screened candidates on daily
RANGE, rejecting LEN as too quiet to pay the premium.

Two things are measured here:
  1. Across the nine, how book correlation relates to turnover and to yield.
  2. Which candidate screen actually predicts how often the model trades a
     name -- range (the 3.14 screen), mean absolute move, dip frequency, or
     dip-and-recovery.

Usage: BAYES_WORKBOOK=<workbook.xlsx> python diversifier_profile.py
"""
import json

import numpy as np

from baseline_check import load

OUT = 'diversifier_profile.json'
AI_NAMES = ('TSM', 'VRT', 'VST', 'AVGO', 'MU', 'MRVL')


def series(data, cal, nm):
    d = data[nm]
    return ([d[k][d['idx'][x]] for x in cal] for k in ('O', 'H', 'L', 'C'))


def dip_recover(O, H, L, C, dip=0.02, rec=0.025, win=10):
    """The model's round trip without the model: sessions whose low dips `dip`
    below the prior close, and the subset that regains dip+`rec` within `win`."""
    n, opps, hits = len(C), 0, 0
    for i in range(1, n - win):
        thr = C[i - 1] * (1 - dip)
        if L[i] <= thr:
            opps += 1
            hits += max(H[i + 1:i + 1 + win]) >= thr * (1 + rec)
    return opps / n, hits / n


def main():
    data, sleeves, cal, _ = load()
    names = sorted(data)
    shape = json.load(open('cf_profile.json'))['shape']

    R = {}
    for nm in names:
        d = data[nm]
        C = [d['C'][d['idx'][x]] for x in cal]
        R[nm] = np.array([0.0] + [C[i] / C[i - 1] - 1 for i in range(1, len(C))])
    factor = np.mean([R[n] for n in AI_NAMES if n in R], axis=0)

    rows = []
    print('fit for the model vs independence from the AI trade\n')
    print(f'  {"name":6s}{"AI beta":>9s}{"corr book":>11s}{"range%":>8s}'
          f'{"dip+rec":>9s}{"trades/yr":>11s}{"hold":>6s}{"%/$-day":>9s}{"top 3rd":>9s}')
    for nm in names:
        O, H, L, C = series(data, cal, nm)
        O, H, L, C = list(O), list(H), list(L), list(C)
        beta = float(np.polyfit(factor, R[nm], 1)[0])
        others = np.mean([R[n] for n in names if n != nm], axis=0)
        cb = float(np.corrcoef(others, R[nm])[0, 1])
        rng = float(np.mean([(H[i] - L[i]) / C[i] for i in range(len(C))]))
        absm = float(np.mean(np.abs(R[nm][1:])))
        opp, hit = dip_recover(O, H, L, C)
        s = shape[nm]
        rows.append(dict(name=nm, beta=beta, corr_book=cb, rng=rng, absm=absm,
                         dip=opp, dip_rec=hit, per_yr=s['per_yr'],
                         hold=s['med_hold'], dollar_day=s['dollar_day'],
                         top3=s['top3'] or 0))
        print(f'  {nm:6s}{beta:>9.2f}{cb:>11.2f}{rng*100:>8.2f}{hit*100:>9.1f}'
              f'{s["per_yr"]:>11.0f}{s["med_hold"]:>6.0f}{s["dollar_day"]*100:>8.3f}%'
              f'{(s["top3"] or 0)*100:>8.0f}%')

    g = lambda k: np.array([r[k] for r in rows])
    print('\n  the trade-off, across the nine:')
    for a, b, lab in (('corr_book', 'per_yr', 'book correlation vs trades/yr'),
                      ('beta', 'per_yr', 'AI beta vs trades/yr'),
                      ('beta', 'dollar_day', 'AI beta vs yield per dollar-day'),
                      ('beta', 'top3', 'AI beta vs P&L concentration')):
        print(f'    {lab:38s} {np.corrcoef(g(a), g(b))[0, 1]:+.2f}')

    print('\n  which screen predicts how often the model trades a name?')
    scr = {}
    for lab, k in (('daily range (the 3.14 screen)', 'rng'),
                   ('mean |daily move|', 'absm'),
                   ('dip frequency', 'dip'),
                   ('dip AND recovery', 'dip_rec')):
        c1 = float(np.corrcoef(g(k), g('per_yr'))[0, 1])
        c2 = float(np.corrcoef(g(k), g('dollar_day'))[0, 1])
        scr[lab] = dict(vs_trades=c1, vs_yield=c2)
        print(f'    {lab:32s} trades/yr {c1:+.2f}   %/dollar-day {c2:+.2f}')

    cf = next(r for r in rows if r['name'] == 'CF')
    gm = next(r for r in rows if r['name'] == 'GM')
    print(f'\n  but no price screen separates CF from GM:')
    print(f'    CF  dip+recover {cf["dip_rec"]*100:.1f}% of sessions -> '
          f'{cf["per_yr"]:.0f} trades/yr   (k={data["CF"]["p"].k:.2f}, '
          f'premium {data["CF"]["p"].premium*100:.2f}/{data["CF"]["p"].ou_prem*100:.2f}%)')
    print(f'    GM  dip+recover {gm["dip_rec"]*100:.1f}% of sessions -> '
          f'{gm["per_yr"]:.0f} trades/yr   (k={data["GM"]["p"].k:.2f}, '
          f'premium {data["GM"]["p"].premium*100:.2f}/{data["GM"]["p"].ou_prem*100:.2f}%)')
    print('    Nearly the same dip behaviour, 2.5x the turnover. The difference is')
    print('    what each name\'s FIT asks for: CF waits for 4.66-5.91%, GM for')
    print('    0.97-4.51%. Turnover is a property of the fitted premium, not of the')
    print('    price series -- so a candidate cannot be pre-screened on price')
    print('    statistics alone; the fit has to be run and the profile read off it.')

    with open(OUT, 'w') as f:
        json.dump(dict(names=rows, screens=scr), f, indent=1, default=str)
    print(f'\nsaved {OUT}')


if __name__ == '__main__':
    main()
