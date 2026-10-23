"""
bear20_gates.py — the 20-name managed book (§3.93) through the 2022 bear, and
whether the core gate should fire more often so the bench is used more
(user, 23 Oct 2026). Every variant is run in BOTH periods:

  2024-26  load_all, PM rule + ATH gate, train/test split as everywhere
  2022     data_bear, Jan 2022 - Jun 2023, ATH gate, no PM rule (no cache);
           the twelve now includes NVDA (5-minute file uploaded 23 Oct)

Core gate variants (the bench is never gated; E lends the held cash to it):
  breadth  core name below its own N-day average while >= K of the twelve are
  per-name K = 1
  N        200 (as deployed in §3.93), 100, 50
Plus the live twelve with no gate and the §3.83 hold-cash gate with no bench.

Bear-period files for NVDA, PLTR, TSLA, DLTR, RKT and TEAM start 25 Oct 2021,
so the calendar starts there and short-history averages use the expanding
window of bear_replay.dma_gate_dates (min 100 days, or N if shorter).
"""
import collections
import functools
import json

import bear12_breadth as bb
from bear_replay import dma_gate_dates
from bear_stop import CAP
from book12 import pm_rule_for
from book20 import TWELVE, BENCH, REBOUND, X, N as HOLD, EPS
from book_sim import load_all, simulate
from fresh_opt import SPLIT
from fresh_opt_cands import daily_from_5min
from lowdd_book import params
from managed20 import admitted
from recap_9v12 import mdd

VARIANTS = ([('no gate (live twelve)', None, None, False)]
            + [('200dma K>=6, cash, no bench', 200, 6, False)]
            + [(f'200dma K>={K} + E', 200, K, True) for K in (6, 5, 4, 3)]
            + [('200dma per-name + E', 200, 1, True)]
            + [(f'100dma K>={K} + E', 100, K, True) for K in (6, 4)]
            + [('100dma per-name + E', 100, 1, True)]
            + [(f'50dma K>={K} + E', 50, K, True) for K in (6, 4)]
            + [('50dma per-name + E', 50, 1, True)])


def breach_full(dts, C, n):
    """2024-26 convention (parallel_book.gate_sets): needs n full prior closes."""
    return {dts[i] for i in range(n, len(dts)) if C[i - 1] < sum(C[i - n:i]) / n}


def gates(breach, K):
    cnt = collections.Counter(d for b in breach.values() for d in b)
    return {n: {d for d in b if cnt[d] >= K} for n, b in breach.items()}


def run_period(label, d, s_all, cal, sim_kw, breach_fn, k, out):
    yrs = len(cal) / 252
    calset = set(cal)
    nb_bench = {n: set(cal) - admitted(d[n], X, HOLD, None) for n in REBOUND}
    cache = {}
    for tag, dma, K, with_bench in VARIANTS:
        names = TWELVE + (BENCH if with_bench else [])
        sl = [x for x in s_all if x['name'] in names]
        nb, kw = {}, {}
        if dma:
            if dma not in cache:
                cache[dma] = {n: breach_fn(d[n], dma) for n in TWELVE}
            g = gates(cache[dma], K)
            nb.update({n: g[n] for n in TWELVE})
            kw['gate_cash'] = True
        if with_bench:
            nb.update(nb_bench)
            kw['tier2'] = set(BENCH)
        r = simulate(d, sl, cal, capital=CAP, mode='pooled', collect_trades=True,
                     no_buy=nb or None, **kw, **sim_kw)
        assert min(r['cash']) > -1e-6, tag
        c, eq = r['cal'], r['equity']
        gated = (sum(len(nb[n] & set(c)) for n in TWELVE) / (12 * len(c))) if dma else 0.0
        bp = sum(t['pnl'] for t in r['trades'] if t['name'] in BENCH)
        if label == '2022':
            i22 = max(i for i, x in enumerate(c) if x <= bb.Y1)
            row = dict(y2022=eq[i22] / eq[0] - 1, to_jun23=eq[-1] / eq[0] - 1,
                       maxdd=r['maxdd'], fills_yr=r['fills'] / (len(c) / 252),
                       gated=gated, bench_pnl=bp)
            print(f'  {tag:30s}{row["y2022"]*100:>7.1f}%{row["to_jun23"]*100:>9.1f}%'
                  f'{row["maxdd"]*100:>7.1f}%{row["fills_yr"]:>6.0f}{gated*100:>6.0f}%{bp/1e3:>+8.0f}k',
                  flush=True)
        else:
            tg = (sum(len(nb[n] & set(cal[k:])) for n in TWELVE) / (12 * (len(cal) - k))) if dma else 0.0
            row = dict(full=r['full'], train=r['train'], test=r['test'], maxdd=r['maxdd'],
                       test_dd=mdd(eq[k:]), fills_yr=r['fills'] / yrs, gated=gated,
                       gated_test=tg, bench_pnl=bp)
            print(f'  {tag:30s}{row["full"]*100:>6.1f}{row["train"]*100:>7.1f}{row["test"]*100:>7.1f}'
                  f'{row["maxdd"]*100:>7.1f}{row["test_dd"]*100:>7.1f}{row["fills_yr"]:>6.0f}'
                  f'{gated*100:>6.0f}%{tg*100:>6.0f}%{bp/1e3:>+8.0f}k', flush=True)
        out[f'{label} | {tag}'] = row


def main():
    out = {}
    names = TWELVE + BENCH
    # ---------------- 2024-26
    po, _ = params(names)
    ek = {n: dict(ath_target_guard=EPS) for n in names}
    d, s_all, cal = load_all(engine_kwargs_per_name=ek, names=names, params_override=po)
    k = max(i for i, x in enumerate(cal) if x <= SPLIT)
    daily = {n: daily_from_5min(n) for n in TWELVE}

    def breach24(D, n):
        nm = next(m for m in TWELVE if d[m] is D)
        dts, _, _, _, C = daily[nm]
        return breach_full(dts, C, n)

    print('===== 2024-26 =====')
    print(f'  {"variant":30s}{"full":>6s}{"train":>7s}{"test":>7s}{"maxDD":>7s}{"tstDD":>7s}'
          f'{"fills":>6s}{"gated":>7s}{"test":>7s}{"bench$":>9s}')
    run_period('2024-26', d, s_all, cal, dict(excl_fn=pm_rule_for(d, set(names))), breach24, k, out)

    # ---------------- 2022 bear
    orig = bb.run_model
    bb.run_model = functools.partial(orig, ath_target_guard=EPS)
    bb.NAMES = names
    data, sleeves, bcal = bb.build()
    bb.run_model = orig
    print(f'\n===== 2022 bear (calendar {bcal[0]} -> {bcal[-1]}, sim from {bb.Y0}) =====')
    print(f'  {"variant":30s}{"2022":>8s}{"Jan22-Jun23":>10s}{"maxDD":>8s}{"fills":>6s}{"gated":>7s}{"bench$":>9s}')
    run_period('2022', data, sleeves, bcal, dict(date_lo=bb.Y0, date_hi=bb.END),
               lambda D, n: dma_gate_dates(D['dts'], D['C'], n=n, min_n=min(n, 100)), None, out)
    json.dump(out, open('bear20_gates.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
