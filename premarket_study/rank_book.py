"""
The ten-name ranking: incumbents (deployed vectors) and candidates (reference
vectors), all on the verified single-split basis, plus the concentration lens.

Per name:
  ref TEST      tested-half annualised return of the full-sample-provenance vector
                (deployed for incumbents, diversifier/json/AVGO-fit for candidates)
                — comparable provenance, all carry the same lookahead flavour.
  A/B TEST      the train-only fits scored on the tested half — the genuinely
                out-of-sample number nothing has seen.
  buys/yr       tested-half verified buys, annualised.
  maxDD         peak-to-trough of the verified tested-half equity.
  AI beta       share-return beta to the equal-weight TSM/VRT/VST/MU factor.
  book corr     correlation of the name's verified daily strategy returns with the
                current five-name book's (deployed configs), tested half.
"""
import json

import numpy as np

from engine import run_model
from fresh_opt import SPLIT, annualise
from fresh_opt_cands import CANDS, REF, daily_from_5min, ref_params
from live5_load import load as load_book, STOCKS as BOOK
from minute_index import make_checker


def equity_series(s, dts, O, H, L, C, p, chk):
    r = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk, collect=True)
    return dict(zip(dts, r.frames['equity']))


def stats(dts, eq_map, lo_date):
    ds = [d for d in dts if d >= lo_date]
    eq = np.array([eq_map[d] for d in ds])
    rets = eq[1:] / eq[:-1] - 1
    peak = np.maximum.accumulate(eq)
    dd = float(((peak - eq) / peak).max())
    return ds, eq, rets, dd


def main():
    inc = json.load(open('fresh_opt_results.json'))
    cand = json.load(open('fresh_opt_cands.json'))
    book_data, book_params, _ = load_book()

    # daily data + reference params per name
    data, refp = {}, {}
    for s in BOOK:
        data[s] = book_data[s]
        refp[s] = book_params[s]
    for s in CANDS:
        data[s] = daily_from_5min(s)
        if REF[s] is not None:
            refp[s] = ref_params(s)
        else:
            from fresh_opt_cands import aw_params
            from engine import Params
            t0 = Params(capital=1_000_000, comm=0.005, interest=0.0314,
                        stop_days=50, bayes_pct=0.5, years=2.2, ou_W=80)
            refp[s] = aw_params(cand[s]['reference']['vec'], t0)

    # AI factor share returns (common dates of the four factor names)
    fnames = ['TSM', 'VRT', 'VST', 'MU']
    common = set(data[fnames[0]][0])
    for s in fnames[1:]:
        common &= set(data[s][0])
    fdates = sorted(common)
    closes = {s: dict(zip(data[s][0], data[s][4])) for s in data}
    frets = {}
    for j in range(1, len(fdates)):
        d0, d1 = fdates[j - 1], fdates[j]
        frets[d1] = np.mean([closes[s][d1] / closes[s][d0] - 1 for s in fnames])

    # book equity (deployed five), tested half
    eq_book = None
    for s in BOOK:
        dts, O, H, L, C = data[s]
        chk = make_checker(s, dts, O)
        em = equity_series(s, dts, O, H, L, C, refp[s], chk)
        if eq_book is None:
            eq_book = {d: em[d] for d in em}
        else:
            eq_book = {d: eq_book[d] + em[d] for d in em if d in eq_book}
    bdates = sorted(d for d in eq_book if d >= SPLIT)
    bser = np.array([eq_book[d] for d in bdates])
    brets = dict(zip(bdates[1:], bser[1:] / bser[:-1] - 1))

    rows = []
    for s in BOOK + CANDS:
        dts, O, H, L, C = data[s]
        chk = make_checker(s, dts, O)
        src = inc[s] if s in inc else cand[s]
        ref = src['deployed'] if 'deployed' in src else src['reference']
        em = equity_series(s, dts, O, H, L, C, refp[s], chk)
        ds, eq, rets, dd = stats(dts, em, SPLIT)
        rmap = dict(zip(ds[1:], rets))
        # AI beta on share returns (full sample)
        srets, fr = [], []
        for j in range(1, len(dts)):
            d = dts[j]
            if d in frets:
                srets.append(C[j] / C[j - 1] - 1)
                fr.append(frets[d])
        srets, fr = np.array(srets), np.array(fr)
        beta = float(np.cov(srets, fr)[0, 1] / np.var(fr))
        # strategy corr with the book, tested half
        cd = [d for d in rmap if d in brets]
        sc = np.array([rmap[d] for d in cd])
        bc = np.array([brets[d] for d in cd])
        corr = float(np.corrcoef(sc, bc)[0, 1]) if len(cd) > 30 else float('nan')
        span_y = (dts[-1] - dts[next(i for i, d in enumerate(dts) if d >= SPLIT)]).days / 365.25
        rows.append(dict(name=s, ref_test=ref['test'], a=src['A']['test'],
                         b=src['B']['test'], buys=ref['buys_test'] / span_y,
                         dd=dd, beta=beta, corr=corr,
                         incumbent=s in BOOK))

    rows.sort(key=lambda r: -r['ref_test'])
    print(f'{"name":6s}{"":2s}{"ref TEST":>9s}{"A TEST":>8s}{"B TEST":>8s}'
          f'{"buys/yr":>8s}{"maxDD":>7s}{"AI beta":>8s}{"bookcorr":>9s}')
    for r in rows:
        tag = ' ' if r['incumbent'] else '+'
        print(f'{r["name"]:6s}{tag:2s}{r["ref_test"]*100:>8.1f}%{r["a"]*100:>7.1f}%'
              f'{r["b"]*100:>7.1f}%{r["buys"]:>8.0f}{r["dd"]*100:>6.1f}%'
              f'{r["beta"]:>8.2f}{r["corr"]:>9.2f}')
    json.dump(rows, open('rank_book.json', 'w'), indent=1)
    print('\nwrote rank_book.json')


if __name__ == '__main__':
    main()
