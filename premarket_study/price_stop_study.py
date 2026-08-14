"""
Price stop: exit at buy_px*(1-frac) whenever it comes before the 50-day time stop.

Motivation (bear-protection discussion, 14 Aug 2026): the 50-day time stop is the
book's only loss-taking exit, so in a sustained downtrend losses arrive in 50-day
quanta at full sleeve size. A price stop caps the per-cycle loss quantum. This
study prices it on the current (bull) sample -- the premium side of the insurance;
the cover side needs the 2022 replay.

  DIAGNOSTIC   max adverse excursion (MAE): for every verified round trip of the
               deployed baseline, the deepest low during the holding window
               relative to entry. How many trades ever touch -10/-15/-20/-25%?
               (Those are the trades a price stop would cut, at those levels.)

  INTERVENTION price_stop in {10%, 15%, 20%, 25%} on the untouched deployed
               configuration. Execution: fill at the stop level, at the open if
               the session gaps below, stop wins same-session ties with the
               target (pessimistic; ambiguous sessions counted). Scored full /
               train / test, with exit-type counts.

Verified fills; split 2025-05-23; deployed parameters untouched.
"""
import json
import sys

import numpy as np

from engine import Params, run_model
from fresh_opt import SPLIT, annualise
from fresh_opt_cands import daily_from_5min, ref_params, aw_params
from live5_load import load as load_book, STOCKS as BOOK
from minute_index import make_checker
from earnings_pause import trades_from_frames

NAMES = BOOK + ['GM', 'VLO', 'CF', 'MRVL']
FRACS = [0.10, 0.15, 0.20, 0.25]


def params_for(s, book_params):
    if s in BOOK:
        return book_params[s]
    if s == 'MRVL':
        t0 = Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                    bayes_pct=0.5, years=2.2, ou_W=80)
        return aw_params(json.load(open('fresh_opt_cands.json'))['MRVL']['reference']['vec'], t0)
    return ref_params(s)


def seg(dts, O, H, L, C, p, chk, lo, hi, **kw):
    r = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk,
                  collect=True, **kw)
    eq = r.frames['equity']
    return (eq[hi] / eq[lo] - 1.0 if eq[lo] > 0 else -1.0), r


def main(only=None):
    book_data, book_params, _ = load_book()
    results = {}
    agg_mae = []
    for s in (only or NAMES):
        dts, O, H, L, C = book_data[s] if s in BOOK else daily_from_5min(s)
        p = params_for(s, book_params)
        chk = make_checker(s, dts, O)
        N = len(C)
        cut = next(i for i, d in enumerate(dts) if d >= SPLIT)
        a = lambda r_, lo, hi: annualise(r_, dts, lo, hi) * 100
        print(f'\n===== {s}  (N={N}) =====', flush=True)

        # ---------------- diagnostic: MAE of every baseline round trip
        b_f, rr = seg(dts, O, H, L, C, p, chk, 0, N - 1)
        fr = rr.frames
        trades = (trades_from_frames(dts, fr, 't1', fr['X'])
                  + trades_from_frames(dts, fr, 't2', fr['AM']))
        maes = []
        for (i, j, bp, xp, st) in trades:
            jj = j if j is not None else N - 1
            maes.append(min(L[i:jj + 1]) / bp - 1)
        maes = np.array(maes)
        agg_mae.append(maes)
        counts = {f: int((maes <= -f).sum()) for f in FRACS}
        print(f'  MAE over {len(maes)} trades: median {np.median(maes)*100:+.1f}%, '
              f'worst {maes.min()*100:+.1f}%; touch -10% {counts[0.10]}, '
              f'-15% {counts[0.15]}, -20% {counts[0.20]}, -25% {counts[0.25]}', flush=True)

        # ---------------- intervention
        b_t, _ = seg(dts, O, H, L, C, p, chk, cut, N - 1)
        print(f'  baseline : full {a(b_f,0,N-1):6.1f}%  TEST {a(b_t,cut,N-1):6.1f}%', flush=True)
        res = dict(base=dict(full=a(b_f, 0, N - 1), test=a(b_t, cut, N - 1)),
                   mae_counts=counts, n_trades=len(maes))
        for f in FRACS:
            g_f, rg = seg(dts, O, H, L, C, p, chk, 0, N - 1, price_stop=f)
            g_t, _ = seg(dts, O, H, L, C, p, chk, cut, N - 1, price_stop=f)
            pse = rg.frames['t1']['ps_exits'] + rg.frames['t2']['ps_exits']
            amb = rg.frames['t1']['ps_ambig'] + rg.frames['t2']['ps_ambig']
            print(f'    stop -{f*100:.0f}%: full {a(g_f,0,N-1):6.1f}%  TEST {a(g_t,cut,N-1):6.1f}%  '
                  f'(price-stop exits {pse}, ambiguous {amb})', flush=True)
            res[f'{f:.2f}'] = dict(full=a(g_f, 0, N - 1), test=a(g_t, cut, N - 1),
                                   ps_exits=pse, ambig=amb)
        results[s] = res
        with open('price_stop.json', 'w') as fh:
            json.dump(results, fh, indent=1, default=str)

    all_mae = np.concatenate(agg_mae)
    print(f'\nBOOK: {len(all_mae)} trades; touch -10% {int((all_mae<=-0.10).sum())}, '
          f'-15% {int((all_mae<=-0.15).sum())}, -20% {int((all_mae<=-0.20).sum())}, '
          f'-25% {int((all_mae<=-0.25).sum())}', flush=True)
    print(f'\n{"name":6s}{"base full":>10s}{"-20% full":>10s}{"base TEST":>10s}{"-20% TEST":>10s}{"ps exits":>9s}')
    for s, r_ in results.items():
        print(f'{s:6s}{r_["base"]["full"]:>9.1f}%{r_["0.20"]["full"]:>9.1f}%'
              f'{r_["base"]["test"]:>9.1f}%{r_["0.20"]["test"]:>9.1f}%{r_["0.20"]["ps_exits"]:>9d}')


if __name__ == '__main__':
    main(sys.argv[1:] or None)
