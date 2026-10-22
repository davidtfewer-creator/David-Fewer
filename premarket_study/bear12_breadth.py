"""
bear12_breadth.py — the twelve-name book through 2022 with the breadth gate
(user, 22 Oct 2026: "run the 12 stock book with the breadth gate in 2022").

ELEVEN names, not twelve: no 2021-23 data for NVDA exists in Box (its folder
holds only Apr 2024 - Aug 2026) and the environment's network policy blocks
outside price sources. NVDA fell ~50% in calendar 2022, so the book shown here
is the twelve minus one of its worst 2022 names.

Gate threshold. The twelve's breadth gate is K>=6 of 12. NVDA spent most of
2022 below its own 200dma, so it would have been one of the six; among the
eleven present, K>=5 is therefore the closest equivalent and K>=6 the stricter
reading. Both are shown, at the 50-day stop.

Same construction as bear_stop.py / bear_breadth.py: bear-period 5-minute
verified fills, residual OU sigma, every vector fitted on 2024-26 (out of
sample). No pre-market rule (no cache for the period).
"""
import collections
import datetime as dt
import json

from bear_replay import _load, bear_checker, dma_gate_dates
from bear_stop import NAMES, CAP
from engine import run_model
from fresh_opt_cands import ref_params
from live5_load import load as load_book, STOCKS as BOOK
from lowdd_book import params as extra_params
import book_sim

Y0, Y1, END = dt.date(2022, 1, 1), dt.date(2022, 12, 31), dt.date(2023, 6, 30)


def build():
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
    return data, sleeves, cal


def episodes(days, cal):
    """Contiguous runs of trading days on which the gate was armed."""
    on = [d for d in cal if d in days]
    runs, cur = [], []
    pos = {d: i for i, d in enumerate(cal)}
    for d in on:
        if cur and pos[d] == pos[cur[-1]] + 1:
            cur.append(d)
        else:
            if cur:
                runs.append(cur)
            cur = [d]
    if cur:
        runs.append(cur)
    return runs


def dd_episode(eq, cal):
    pk, pki, best = eq[0], 0, (0.0, 0, 0)
    for i, v in enumerate(eq):
        if v > pk:
            pk, pki = v, i
        dd = (pk - v) / pk
        if dd > best[0]:
            best = (dd, pki, i)
    depth, p, t = best
    rec = next((j for j in range(t, len(eq)) if eq[j] >= eq[p]), None)
    return depth, cal[p], cal[t], (cal[rec] if rec is not None else None)


def main():
    data, sleeves, cal = build()
    breach = {s: dma_gate_dates(data[s]['dts'], data[s]['C']) for s in NAMES}
    cnt = collections.Counter(d for s in NAMES for d in breach[s])
    gate = {K: {s: {d for d in breach[s] if cnt[d] >= K} for s in NAMES} for K in (5, 6)}
    arms = [('no gate', {}), ('breadth K>=5 of 11', {'no_buy': gate[5]}),
            ('breadth K>=6 of 11', {'no_buy': gate[6]})]

    print('names below their own 200dma, 2022 (of 11):')
    for m in range(1, 13):
        ds = [d for d in cal if d.year == 2022 and d.month == m]
        c = [cnt[d] for d in ds]
        print(f'  {dt.date(2022, m, 1):%b}  avg {sum(c)/len(c):4.1f}  min {min(c):2d}  max {max(c):2d}')

    for K in (5, 6):
        runs = [r for r in episodes({d for v in gate[K].values() for d in v}, cal)
                if r[-1] >= Y0 and r[0] <= END]
        print(f'\nbreadth K>={K}: armed on {sum(len(r) for r in runs)} sessions in '
              f'{len(runs)} spells (Jan 2022 - Jun 2023)')
        for r in runs:
            if len(r) >= 5:
                print(f'    {r[0]} -> {r[-1]}  ({len(r)} sessions)')

    out = {}
    res = {}
    for tag, kw in arms:
        r = book_sim.simulate(data, sleeves, cal, capital=CAP, collect_trades=True,
                              date_lo=Y0, date_hi=END, **kw)
        res[tag] = r
    print(f'\n===== MONTHLY BOOK RETURN, 2022 =====')
    print(f'  {"month":6s}' + ''.join(f'{t:>20s}' for t, _ in arms))
    monthly = {t: [] for t, _ in arms}
    for m in range(1, 13):
        row = f'  {dt.date(2022, m, 1):%b}   '
        for tag, _ in arms:
            r = res[tag]
            c, eq = r['cal'], r['equity']
            ix = [i for i, d in enumerate(c) if d.year == 2022 and d.month == m]
            prev = ix[0] - 1 if ix[0] > 0 else ix[0]
            v = eq[ix[-1]] / eq[prev] - 1
            monthly[tag].append(v)
            row += f'{v*100:>19.1f}%'
        print(row)

    print(f'\n===== SUMMARY =====')
    print(f'  {"arm":22s}{"2022":>8s}{"to Jun23":>10s}{"maxDD":>8s}{"worst mth":>11s}'
          f'{"fills":>7s}{"stops":>7s}   drawdown peak -> trough -> recovered')
    for tag, _ in arms:
        r = res[tag]
        c, eq = r['cal'], r['equity']
        i22 = max(i for i, d in enumerate(c) if d <= Y1)
        y22 = eq[i22] / eq[0] - 1
        tot = eq[-1] / eq[0] - 1
        depth, p, t, rec = dd_episode(eq, c)
        print(f'  {tag:22s}{y22*100:>7.1f}%{tot*100:>9.1f}%{r["maxdd"]*100:>7.1f}%'
              f'{min(monthly[tag])*100:>10.1f}%{r["fills"]:>7d}{r["stops"]:>7d}   '
              f'{p} -> {t} -> {rec or "not by Jun 2023"}')
        out[tag] = dict(y2022=y22, to_jun23=tot, maxdd=r['maxdd'], worst_month=min(monthly[tag]),
                        fills=r['fills'], stops=r['stops'], dd_peak=str(p), dd_trough=str(t),
                        dd_recovered=str(rec), monthly=monthly[tag])

    print(f'\n===== PER NAME, trades ENTERED in 2022 =====')
    print(f'  {"name":6s}{"B&H 2022":>10s}' + ''.join(f'{t[:18]:>20s}' for t, _ in arms))
    for s in NAMES:
        ds, C = data[s]['dts'], data[s]['C']
        i0 = next(i for i, d in enumerate(ds) if d >= Y0)
        i1 = max(i for i, d in enumerate(ds) if d <= Y1)
        row = f'  {s:6s}{(C[i1]/C[i0]-1)*100:>9.1f}%'
        for tag, _ in arms:
            ts = [x for x in res[tag]['trades'] if x['name'] == s and Y0 <= x['entry'] <= Y1]
            pnl = sum(x['pnl'] for x in ts)
            row += f'{pnl/1e3:>12.0f}k ({len(ts):>3d})'
        print(row)
    print('  (P&L in $k on $6.9m, number of trades in brackets)')
    json.dump(out, open('bear12_breadth.json', 'w'), indent=1, default=str)
    print('\nwrote bear12_breadth.json')


if __name__ == '__main__':
    main()
