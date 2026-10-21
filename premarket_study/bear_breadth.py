"""Does the BREADTH-conditional 200dma gate -- the version that never fires in
the 2024-26 test half (§3.66), so costs almost nothing in normal markets --
capture the protection the per-name gate gave in the 2022 bear? Eleven names,
same construction as bear_stop.py."""
import datetime
import json

from bear_replay import _load, bear_checker, dma_gate_dates
from bear_stop import NAMES, CAP, WINDOWS
from engine import run_model
from fresh_opt_cands import ref_params
from live5_load import load as load_book, STOCKS as BOOK
from lowdd_book import params as extra_params
import book_sim


def main():
    _, book_params, _ = load_book()
    po, _ = extra_params(NAMES)
    data = {}
    for s in NAMES:
        (dts, O, H, L, C), idx = _load(s)
        p = book_params[s] if s in BOOK else (po.get(s) or ref_params(s))
        chk = bear_checker(idx, dts, O)
        r = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk, collect=True)
        data[s] = dict(dts=dts, O=O, H=H, L=L, C=C, p=p, idx={d: i for i, d in enumerate(dts)},
                       chk=chk, X=r.frames['X'], AM=r.frames['AM'])
    sleeves = []
    for s in NAMES:
        p = data[s]['p']
        sleeves += [dict(name=s, kind='B', bids='X', prem=p.premium),
                    dict(name=s, kind='O', bids='AM', prem=p.ou_prem)]
    cal = sorted(set.intersection(*(set(data[s]['dts']) for s in NAMES)))
    breach = {s: dma_gate_dates(data[s]['dts'], data[s]['C']) for s in NAMES}
    cnt = {}
    for s in NAMES:
        for d in breach[s]:
            cnt[d] = cnt.get(d, 0) + 1

    def breadth(K):
        return {s: {d for d in breach[s] if cnt.get(d, 0) >= K} for s in NAMES}

    gates = [('no gate', None), ('per-name (K>=1)', breach),
             ('breadth K>=5 of 11', breadth(5)), ('breadth K>=6 of 11', breadth(6))]
    out = {}
    for wlbl, lo, hi in WINDOWS:
        n_on = {g: len({d for v in (gs or {}).values() for d in v if lo <= d <= hi})
                for g, gs in gates}
        print(f'\n===== {wlbl} =====')
        print(f'  {"gate":22s}{"days on":>8s}{"stop":>6s}{"ann":>8s}{"maxDD":>8s}{"fills":>7s}')
        for glbl, gs in gates:
            for st in (50, 20):
                kw = {'no_buy': gs} if gs else {}
                r = book_sim.simulate(data, sleeves, cal, capital=CAP, collect_trades=True,
                                      date_lo=lo, date_hi=hi, stop_days=st, **kw)
                print(f'  {glbl:22s}{n_on[glbl]:>8d}{st:>5d}d{r["full"]*100:>7.1f}%'
                      f'{r["maxdd"]*100:>7.1f}%{r["fills"]:>7d}', flush=True)
                out[f'{wlbl} | {glbl} | {st}d'] = dict(ann=r['full'], maxdd=r['maxdd'],
                                                       fills=r['fills'], days_on=n_on[glbl])
    json.dump(out, open('bear_breadth.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
