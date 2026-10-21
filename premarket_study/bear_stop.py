"""
bear_stop.py — the stop sweep through the 2022 bear (user, 21 Oct 2026).

§3.81 found stop length barely moves the 2024-26 drawdown, because that
sample's one deep fall recovered fast: a shorter stop crystallised the trough
instead of avoiding it. The caveat was that a stop exists for a bear that KEEPS
falling. Aug 2021 - Jun 2023 is that bear: these names fell 40-80% in 2022.

Construction follows bear_replay.py exactly (same loader, verified fills from
the bear-period 5-minute index, residual OU sigma) and uses the twelve-name
book's vectors, all fitted on 2024-26 -- so everything here is out of sample.

Limits, stated up front:
  - ELEVEN names, not twelve: there is no 2021-23 data for NVDA, which fell
    about two-thirds peak to trough in 2022. Its absence flatters the book.
  - no pre-market rule: there is no pre-market cache for the period. It is
    missing from every arm equally, so the stop COMPARISON is unaffected.
Also tests the per-name stop set chosen in §3.81 on 2024-26 train data -- a
genuinely unseen test of it.
"""
import datetime
import json

from bear_replay import _load, bear_checker, dma_gate_dates
from engine import run_model
from live5_load import load as load_book, STOCKS as BOOK
from lowdd_book import params as extra_params
from fresh_opt_cands import ref_params
import book_sim

NAMES = ['TSM', 'VRT', 'VST', 'AVGO', 'MU', 'GM', 'VLO', 'CF', 'MRVL', 'RTX', 'DE']
CAP = 6_900_000
NONE = 10_000
UNIFORM = [10, 20, 30, 40, 50, 60, 75, 100, NONE]
WINDOWS = [('CALENDAR 2022', datetime.date(2022, 1, 1), datetime.date(2022, 12, 31)),
           ('FULL SPAN Jan 2022 - Jun 2023', datetime.date(2022, 1, 1), datetime.date(2023, 6, 30))]


def lab(x):
    return 'none' if (isinstance(x, int) and x >= NONE) else (f'{x}d' if isinstance(x, int) else x)


def main():
    _, book_params, _ = load_book()
    po, _ = extra_params(NAMES)
    data, src = {}, {}
    for s in NAMES:
        (dts, O, H, L, C), idx = _load(s)
        p = book_params[s] if s in BOOK else (po.get(s) or ref_params(s))
        src[s] = 'workbook' if s in BOOK else ('fitted 2024-26' if s in po else 'reference')
        chk = bear_checker(idx, dts, O)
        r = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk, collect=True)
        data[s] = dict(dts=dts, O=O, H=H, L=L, C=C, p=p, idx={d: i for i, d in enumerate(dts)},
                       chk=chk, X=r.frames['X'], AM=r.frames['AM'])
    print('vectors: ' + ', '.join(f'{s} {src[s]}' for s in NAMES))
    sleeves = []
    for s in NAMES:
        p = data[s]['p']
        sleeves += [dict(name=s, kind='B', bids='X', prem=p.premium),
                    dict(name=s, kind='O', bids='AM', prem=p.ou_prem)]
    cal = sorted(set.intersection(*(set(data[s]['dts']) for s in NAMES)))
    gate = {s: dma_gate_dates(data[s]['dts'], data[s]['C']) for s in NAMES}
    per_name = json.load(open('stop_study.json'))['per_name']
    pn = {n: (NONE if v == 'none' else int(v[:-1])) for n, v in per_name.items() if n in NAMES}

    out = {}
    for wlbl, lo, hi in WINDOWS:
        # equal-weight buy and hold of the eleven over the window, for context
        bh = []
        for s in NAMES:
            ds, C = data[s]['dts'], data[s]['C']
            i0 = next(i for i, d in enumerate(ds) if d >= lo)
            i1 = max(i for i, d in enumerate(ds) if d <= hi)
            bh.append(C[i1] / C[i0] - 1)
        print(f'\n===== {wlbl}   (equal-weight buy & hold of the eleven: '
              f'{sum(bh)/len(bh)*100:+.1f}%) =====')
        for glbl, kw0 in (('no gate', {}), ('200dma gate', {'no_buy': gate})):
            print(f'\n  --- {glbl} ---')
            print(f'  {"stop":>14s}{"ann":>8s}{"total":>8s}{"maxDD":>8s}{"fills":>7s}{"stops":>7s}')
            arms = [(x, x) for x in UNIFORM] + [('per-name set', pn)]
            for tag, st in arms:
                r = book_sim.simulate(data, sleeves, cal, capital=CAP, collect_trades=True,
                                      date_lo=lo, date_hi=hi, stop_days=st, **kw0)
                eq = r['equity']
                tot = eq[-1] / eq[0] - 1
                print(f'  {lab(tag):>14s}{r["full"]*100:>7.1f}%{tot*100:>7.1f}%'
                      f'{r["maxdd"]*100:>7.1f}%{r["fills"]:>7d}{r["stops"]:>7d}', flush=True)
                out[f'{wlbl} | {glbl} | {lab(tag)}'] = dict(ann=r['full'], total=tot,
                                                            maxdd=r['maxdd'], fills=r['fills'],
                                                            stops=r['stops'])
    print('\nper-name set (from §3.81): ' + ', '.join(f'{n} {lab(v)}' for n, v in pn.items()))
    json.dump(out, open('bear_stop.json', 'w'), indent=1)
    print('wrote bear_stop.json')


if __name__ == '__main__':
    main()
