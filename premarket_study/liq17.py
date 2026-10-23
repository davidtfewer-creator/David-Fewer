"""
liq17.py — a per-name LIQUIDITY cap for the chosen book at ~$10m (user, 23 Oct
2026; §3.99 found CF's p95 order at 56% of first-hour at-bid volume at $10m).

Cap, decidable each morning: a name's total new orders <= L x the median of its
FIRST-HOUR total dollar volume over the previous 20 sessions (needs >= 10).
Excess held in cash (book_sim order_cap). Names without a volume column are
uncapped and flagged. Book = (b) + 25% exposure cap, $10m start.
Reported: return/drawdown both periods, and the resulting participation
(order / first-hour AT-BID volume, as participation.py) for the tight names.
"""
import functools
import json
import statistics

import bear12_breadth as bb
import participation as P_
from bear_replay import dma_gate_dates
from book12 import pm_rule_for
from book20 import TWELVE, DIVERS, EPS
from book_sim import load_all, simulate
from fresh_opt import SPLIT
from lowdd_book import params
from parallel_book import gate_sets
from recap_9v12 import mdd
from bear20_gates import gates

CAPITAL = 10_000_000
LS = (None, 0.10, 0.05, 0.03, 0.02, 0.01)
TIGHT = ['CF', 'VLO', 'GM', 'RTX', 'DE', 'LEN', 'VST', 'VRT']


def trailing_h1(bars):
    """{date: median first-hour $ volume of the previous 20 sessions}."""
    days = sorted(bars)
    h1 = {d: sum(x[3] for x in bars[d] if x[0] < P_.HOUR1) for d in days}
    out = {}
    for i, d in enumerate(days):
        prev = [h1[x] for x in days[max(0, i - 20):i] if h1[x] > 0]
        if len(prev) >= 10:
            out[d] = statistics.median(prev)
    return out


def load_vol(names, folder):
    P_.DIR = folder
    bars, med = {}, {}
    for n in names:
        b = P_.load_bars(n)
        if any(x[3] > 0 for day in list(b.values())[:30] for x in day):
            bars[n], med[n] = b, trailing_h1(b)
    return bars, med


def main():
    out = {}
    names = TWELVE + DIVERS
    po, _ = params(names)
    ek = {n: dict(ath_target_guard=EPS) for n in names}
    d, s_all, cal = load_all(engine_kwargs_per_name=ek, names=names, params_override=po)
    k = max(i for i, x in enumerate(cal) if x <= SPLIT)
    excl = pm_rule_for(d, set(names))
    bars24, med24 = load_vol(names, 'data_5min')
    orig = bb.run_model
    bb.run_model = functools.partial(orig, ath_target_guard=EPS)
    bb.NAMES = names
    bd, bs, bcal = bb.build()
    bb.run_model = orig
    bars22, med22 = load_vol(names, 'data_bear')
    print('uncapped (no volume): 2024-26', [n for n in names if n not in med24],
          '| 2022', [n for n in names if n not in med22])
    g24 = gate_sets(TWELVE, 6)[0]
    g22 = gates({n: dma_gate_dates(bd[n]['dts'], bd[n]['C']) for n in TWELVE}, 6)
    hdr = ''.join(f'{n:>11s}' for n in TIGHT)
    print(f'\n  {"L":6s}| 24-26 full  test maxDD fills held | 2022  maxDD | p95 / %>5% of first-hour at-bid vol:{hdr}')
    for L in LS:
        oc24 = {n: {dd: L * v for dd, v in m.items()} for n, m in med24.items()} if L else None
        oc22 = {n: {dd: L * v for dd, v in m.items()} for n, m in med22.items()} if L else None
        common = dict(capital=CAPITAL, mode='pooled', collect_trades=True, gate_cash=True,
                      tier2=set(DIVERS), exp_cap=0.25, exp_to='cash')
        r = simulate(d, s_all, cal, excl_fn=excl, no_buy={n: set(g24[n]) for n in TWELVE},
                     order_cap=oc24, **common)
        rb = simulate(bd, bs, bcal, date_lo=bb.Y0, date_hi=bb.END,
                      no_buy={n: set(g22[n]) for n in TWELVE}, order_cap=oc22, **common)
        assert min(r['cash']) > -1e-6 and min(rb['cash']) > -1e-6
        rows, _ = P_.measure(r['trades'], bars24)
        part = {}
        for n in TIGHT:
            xs = sorted(x['p_blend'] for x in rows if x['name'] == n and x['p_blend'] is not None)
            part[n] = (xs[int(0.95 * (len(xs) - 1))], sum(1 for x in xs if x > 0.05) / len(xs)) if xs else None
        c, eq = rb['cal'], rb['equity']
        i22 = max(i for i, x in enumerate(c) if x <= bb.Y1)
        spent = sum(t['cost'] for t in r['trades'])
        row = dict(full=r['full'], test=r['test'], maxdd=r['maxdd'], test_dd=mdd(r['equity'][k:]),
                   fills_yr=r['fills'] / (len(cal) / 252), liq_held_share=r['liq_freed'] / (spent + r['liq_freed']),
                   y2022=eq[i22] / eq[0] - 1, maxdd22=rb['maxdd'], participation=part)
        out[str(L)] = row
        lab = 'none' if L is None else f'{L*100:g}%'
        print(f'  {lab:6s}| {row["full"]*100:5.1f} {row["test"]*100:6.1f} {row["maxdd"]*100:5.1f} {row["fills_yr"]:4.0f}'
              f' {row["liq_held_share"]*100:4.1f}% | {row["y2022"]*100:5.1f}% {row["maxdd22"]*100:5.1f}% |'
              + ''.join(f'{p[0]*100:>6.1f}/{p[1]*100:>3.0f}%' if p else f'{"-":>11s}' for p in part.values()),
              flush=True)
    json.dump(out, open('liq17.json', 'w'), indent=1, default=float)


if __name__ == '__main__':
    main()
