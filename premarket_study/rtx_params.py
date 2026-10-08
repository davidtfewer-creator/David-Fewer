"""
rtx_params.py — the deployable numbers for a candidate, per fitted vector
(8 Oct 2026).

§3.38 left RTX undecided because its two honest variants disagree at G5. That
makes "what would we actually deploy?" a real question with three different
answers, so this prints each vector's parameters side by side with the turnover
and premiums it implies, against CF for scale.

Two turnover measures, because they answer different questions:
  captive  buys from the single-name backtest (both sleeves), annualised over
           the segment they were counted on — what the name does on its own
  pooled   completed trades per year in the nine-name book with the live
           config — what the book would actually see, after the pre-market
           rule and competition for capital

Usage: BAYES_WORKBOOK=<workbook.xlsx> python rtx_params.py [TICKER]
"""
import json
import sys

from engine import Params, run_model
from fresh_opt import a_params, b_params
from fresh_opt_cands import aw_params, ref_params, daily_from_5min, SPLIT
from minute_index import make_checker

SESSIONS_PER_YEAR = 252


def t0():
    return Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                  bayes_pct=0.5, years=2.2, ou_W=80)


def buys_in(dts, O, H, L, C, p, lo, hi):
    r = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=True, collect=True)
    fr = r.frames
    return sum(fr['t1']['Z'][lo:hi + 1]) + sum(fr['t2']['Z'][lo:hi + 1])


def main():
    nm = (sys.argv[1] if len(sys.argv) > 1 else 'RTX').upper()
    c = json.load(open('fresh_opt_cands.json'))
    dts, O, H, L, C = daily_from_5min(nm)
    n = len(C)
    cut = next(i for i, d in enumerate(dts) if d >= SPLIT)

    ref = aw_params(c[nm]['reference']['vec'], t0())
    vecs = {'reference (full-sample, flagged)': ref,
            'variant A (train-half fit)': a_params(c[nm]['A']['vec'], ref),
            'variant B (train-half fit)': b_params(c[nm]['B']['vec'], ref, c[nm]['B']['mle'])}

    cf_ref = ref_params('CF')
    cf = {'CF deployed (the incumbent)': cf_ref,
          'CF variant A': a_params(c['CF']['A']['vec'], cf_ref),
          'CF variant B': b_params(c['CF']['B']['vec'], cf_ref, c['CF']['B']['mle'])}

    print(f'{nm}: {n} sessions {dts[0]} to {dts[-1]}, split {SPLIT}\n')
    print(f'  {"vector":34s}{"Bayes prem":>11s}{"OU prem":>9s}{"k":>7s}'
          f'{"OU buf":>8s}{"OU W":>6s}{"peak cap":>10s}{"OU cap":>8s}')
    rows = list(vecs.items()) + list(cf.items())
    for tag, p in rows:
        print(f'  {tag:34s}{p.premium*100:>10.2f}%{p.ou_prem*100:>8.2f}%{p.k:>7.3f}'
              f'{p.ou_buf_k:>8.3f}{p.ou_W:>6d}{p.peak_cap*100:>9.2f}%{p.ou_cap*100:>7.2f}%')

    print(f'\n  captive buys (both sleeves), annualised:')
    print(f'  {"vector":34s}{"full":>18s}{"train":>18s}{"tested half":>18s}')
    for tag, p in rows:
        src = (dts, O, H, L, C) if tag.startswith(nm) or tag in vecs else None
        d2 = (dts, O, H, L, C)
        if tag in cf:
            d2 = daily_from_5min('CF')
        nn = len(d2[4])
        cc = next(i for i, d in enumerate(d2[0]) if d >= SPLIT)
        cells = []
        for lo, hi in ((0, nn - 1), (0, cc - 1), (cc, nn - 1)):
            b = buys_in(*d2, p, lo, hi)
            yrs = (hi - lo + 1) / SESSIONS_PER_YEAR
            cells.append(f'{b:4.0f} = {b/yrs:5.1f}/yr')
        print(f'  {tag:34s}' + ''.join(f'{x:>18s}' for x in cells))

    print(f'\n  pooled, in the nine-name book with the live config (from §3.38):')
    print(f'    {nm} reference  24 trades/yr, 16-day median hold, top third 66%')
    print(f'    {nm} variant A  50 trades/yr,                     top third 84%')
    print(f'    {nm} variant B  32 trades/yr,                     top third 81%')
    print(f'    CF deployed    24 trades/yr, 12-day median hold, top third 102%')
    print(f'    CF variant A   29 trades/yr,                     top third 117%')
    print(f'    CF variant B   41 trades/yr,                     top third 107%')


if __name__ == '__main__':
    main()
