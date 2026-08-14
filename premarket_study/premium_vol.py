"""
Vol-scaled take-profit premium (colleague's suggestion, 14 Aug 2026).

The model is asymmetric: the BUY price is volatility-aware (bid = fair - k*sigma)
but the SELL target asks a fixed premium (bid + prevclose * prem) whatever sigma
says that morning. Should the premium breathe with sigma too?

The change touches ONLY the target -- the bid, and therefore every fill, is
identical to deployed. That isolates exit policy.

  DIAGNOSTIC   for every verified round trip, bucket by the entry-day sigma
               (the sleeve's own sigma: Kalman predictive W for Bayes, AR(1)
               residual std for OU, both relative to prev close) into train-set
               terciles, and measure HEADROOM: how far the holding window's high
               ran above the fixed target, max(H)/target - 1. If high-sigma
               entries systematically leave headroom, a fatter premium there has
               something to take; if headroom is flat in sigma, it doesn't.

  INTERVENTION prem_mult[i] = clip((sigma_i / sigma_tilde)^alpha, 0.25, 4) per
               sleeve, where sigma_tilde is the TRAIN-half median of that
               sleeve's sigma -- level-preserving by construction (at median
               vol the premium is exactly deployed; the level was already
               optimised, only the dynamics are on trial). alpha in
               {0.25, 0.5, 0.75, 1.0}; alpha chosen on the TRAIN half
               (baseline alpha=0 included), frozen, scored on the tested half.

Deployed parameters untouched throughout; verified fills; split 2025-05-23.
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
ALPHAS = [0.25, 0.5, 0.75, 1.0]


def params_for(s, book_params):
    if s in BOOK:
        return book_params[s]
    if s == 'MRVL':
        t0 = Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                    bayes_pct=0.5, years=2.2, ou_W=80)
        return aw_params(json.load(open('fresh_opt_cands.json'))['MRVL']['reference']['vec'], t0)
    return ref_params(s)


def seg_p(dts, O, H, L, C, p, chk, lo, hi, **kw):
    r = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk,
                  collect=True, **kw)
    eq = r.frames['equity']
    buys = sum(r.frames['t1']['Z'][lo:hi + 1]) + sum(r.frames['t2']['Z'][lo:hi + 1])
    return (eq[hi] / eq[lo] - 1.0 if eq[lo] > 0 else -1.0), buys


def main(only=None):
    book_data, book_params, _ = load_book()
    try:
        results = json.load(open('premium_vol.json'))
    except FileNotFoundError:
        results = {}
    for s in (only or NAMES):
        dts, O, H, L, C = book_data[s] if s in BOOK else daily_from_5min(s)
        p = params_for(s, book_params)
        chk = make_checker(s, dts, O)
        N = len(C)
        cut = next(i for i, d in enumerate(dts) if d >= SPLIT)
        print(f'\n===== {s}  (N={N}) =====', flush=True)

        # baseline run supplies the sigma series (bids identical in every variant)
        r = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk, collect=True)
        fr = r.frames
        # per-row sleeve sigma at bid formation, relative to prev close
        sigB = [None] + [fr['W'][i - 1] / C[i - 1] for i in range(1, N)]
        sigO = [fr['OUsig'][i] / C[i - 1] if fr['OUsig'][i] is not None else None
                for i in range(N)]
        medB = float(np.median([v for i, v in enumerate(sigB) if v is not None and i < cut]))
        medO = float(np.median([v for i, v in enumerate(sigO) if v is not None and i < cut]))

        # ---------------- diagnostic: headroom by entry-sigma tercile
        print('  DIAGNOSTIC — headroom above the fixed target by entry-sigma tercile:', flush=True)
        for label, tkey, bids, sig, med in (('Bayes', 't1', 'X', sigB, medB),
                                            ('OU', 't2', 'AM', sigO, medO)):
            trades = trades_from_frames(dts, fr, tkey, fr[bids])
            rows = []
            for (i, j, bp, xp, st) in trades:
                if j is None or sig[i] is None:
                    continue
                tgt = fr[tkey]['AB'][j]                  # resting target
                hi_px = max(H[i:j + 1])
                rows.append((sig[i], hi_px / tgt - 1, st, (dts[j] - dts[i]).days))
            if len(rows) < 9:
                print(f'    {label}: too few trades ({len(rows)})', flush=True)
                continue
            qs = np.percentile([r_[0] for r_ in rows], [33.3, 66.7])
            for name_, sel in (('low ', lambda v: v <= qs[0]),
                               ('mid ', lambda v: qs[0] < v <= qs[1]),
                               ('high', lambda v: v > qs[1])):
                sub = [r_ for r_ in rows if sel(r_[0])]
                hr = [r_[1] for r_ in sub]
                print(f'    {label:5s} sigma {name_}: n {len(sub):4d}  '
                      f'headroom avg {np.mean(hr)*100:+6.2f}% med {np.median(hr)*100:+6.2f}%  '
                      f'stops {sum(r_[2] for r_ in sub):2d}  hold {np.mean([r_[3] for r_ in sub]):5.1f}d',
                      flush=True)

        # ---------------- intervention
        d_tr, _ = seg_p(dts, O, H, L, C, p, chk, 0, cut - 1)
        d_te, _ = seg_p(dts, O, H, L, C, p, chk, cut, N - 1)
        a = lambda r_, lo, hi: annualise(r_, dts, lo, hi)
        print(f'  baseline (alpha=0): train {a(d_tr,0,cut-1)*100:6.1f}%  '
              f'TEST {a(d_te,cut,N-1)*100:6.1f}%', flush=True)
        cells = [(0.0, a(d_tr, 0, cut - 1), a(d_te, cut, N - 1))]
        for al in ALPHAS:
            pmB = [None if v is None else float(np.clip((v / medB) ** al, 0.25, 4.0))
                   for v in sigB]
            pmO = [None if v is None else float(np.clip((v / medO) ** al, 0.25, 4.0))
                   for v in sigO]
            g_tr, _ = seg_p(dts, O, H, L, C, p, chk, 0, cut - 1, prem_mult=(pmB, pmO))
            g_te, _ = seg_p(dts, O, H, L, C, p, chk, cut, N - 1, prem_mult=(pmB, pmO))
            cells.append((al, a(g_tr, 0, cut - 1), a(g_te, cut, N - 1)))
            print(f'    alpha {al:.2f}: train {cells[-1][1]*100:6.1f}%  '
                  f'test {cells[-1][2]*100:6.1f}%', flush=True)
        pick = max(cells, key=lambda c: c[1])
        print(f'  train-pick alpha {pick[0]:.2f} -> frozen TEST {pick[2]*100:6.1f}% '
              f'(baseline {cells[0][2]*100:.1f}%)', flush=True)
        results[s] = dict(med_sigma=dict(bayes=medB, ou=medO),
                          cells=[(c[0], c[1], c[2]) for c in cells],
                          pick=pick[0], pick_train=pick[1], pick_test=pick[2],
                          base_train=cells[0][1], base_test=cells[0][2])
        with open('premium_vol.json', 'w') as fh:
            json.dump(results, fh, indent=1, default=str)

    print(f'\n{"name":6s}{"base TEST":>10s}{"pick a":>7s}{"pick TEST":>10s}{"delta":>8s}', flush=True)
    for s, r_ in results.items():
        print(f'{s:6s}{r_["base_test"]*100:>9.1f}%{r_["pick"]:>7.2f}{r_["pick_test"]*100:>9.1f}%'
              f'{(r_["pick_test"]-r_["base_test"])*100:>+7.1f}%', flush=True)


if __name__ == '__main__':
    main(sys.argv[1:] or None)
