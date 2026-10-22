"""
managed20.py — the 20-name managed book, options D + A (user, 22 Oct 2026).

  core   the twelve, always live (PM rule, ATH gate on, 50-day stop -- live config)
  bench  PLTR TSLA RKLB APLD AAOI (drop-and-rebound) + NEM LEN DLTR (diversifiers)

  D  core first: book_sim tier2 -- core orders sized as in the twelve-only book,
     bench orders overbook and fill only from cash left after the core's fills.
  A  deep-drop admission: a bench name may bid only while ADMITTED. It is
     admitted at the open of a session when its prior close is >= X below its
     trailing 252-session high (>= 60 sessions of history needed), and stays
     admitted for N sessions after the last such day, ending early if a close
     comes back within R of the high. No wait for a bounce (§3.87: buying deep
     names below their 20dma beat buying them above).

2024-26 only (user: ignore 2022 for now). Train/test split as everywhere.
"""
import json
import sys

from fresh_opt import SPLIT
from lowdd_book import TWELVE, params
from book12 import pm_rule_for
from book_sim import load_all, simulate
from bear_stop import CAP
from recap_9v12 import mdd

BENCH = ['PLTR', 'TSLA', 'RKLB', 'APLD', 'AAOI', 'NEM', 'LEN', 'DLTR']
REBOUND = BENCH[:5]
TWENTY = TWELVE + BENCH
EPS = 0.0


def admitted(D, X, N, R):
    """Set of dates on which the name may bid (decided on prior closes only)."""
    C, dts = D['C'], D['dts']
    out, until = set(), -1
    for i in range(60, len(C)):
        hi = max(C[max(0, i - 252):i])
        dd = 1 - C[i - 1] / hi
        if dd >= X:
            until = i + N - 1
        if R is not None and dd <= R:
            until = -1
        if i <= until:
            out.add(dts[i])
    return out


def run(tag, d, s, cal, k, excl, out, names, no_buy=None, tier2=None, adm=None):
    r = simulate(d, s, cal, capital=CAP, mode='pooled', collect_trades=True, excl_fn=excl,
                 no_buy=no_buy, tier2=tier2)
    yrs = len(cal) / 252
    tr = r['trades']
    bp = sum(t['pnl'] for t in tr if t['name'] in BENCH)
    ap = sum(t['pnl'] for t in tr)
    bf = sum(1 for t in tr if t['name'] in BENCH) / yrs
    adm_share = (sum(len([x for x in adm[n] if x in set(cal)]) for n in adm) / (len(adm) * len(cal))
                 if adm else (1.0 if any(n in names for n in BENCH) else 0.0))
    row = dict(full=r['full'], train=r['train'], test=r['test'], maxdd=r['maxdd'],
               test_dd=mdd(r['equity'][k:]), fills_yr=r['fills'] / yrs, bench_fills_yr=bf,
               bench_pnl_share=bp / ap if ap else 0.0, admitted=adm_share,
               avg_cash=sum(c / e for c, e in zip(r['cash'], r['equity'])) / len(cal))
    out[tag] = row
    print(f'  {tag:34s}{row["full"]*100:>6.1f}{row["train"]*100:>7.1f}{row["test"]*100:>7.1f}'
          f'{row["maxdd"]*100:>7.1f}{row["test_dd"]*100:>7.1f}{row["fills_yr"]:>6.0f}{bf:>6.0f}'
          f'{row["bench_pnl_share"]*100:>6.0f}%{adm_share*100:>6.0f}%{row["avg_cash"]*100:>6.0f}%',
          flush=True)
    return row


def main():
    out = {}
    po, basis = params(TWENTY)
    for n in BENCH:
        print(f'  {n:5s} {basis.get(n, "workbook")}')
    ek = {n: dict(ath_target_guard=EPS) for n in TWENTY}
    d, s_all, cal = load_all(engine_kwargs_per_name=ek, names=TWENTY, params_override=po)
    k = max(i for i, x in enumerate(cal) if x <= SPLIT)
    excl = pm_rule_for(d, set(TWENTY))
    s12 = [x for x in s_all if x['name'] in TWELVE]
    print(f'  {len(cal)} sessions {cal[0]} -> {cal[-1]}, split {SPLIT}\n')
    print(f'  {"arm":34s}{"full":>6s}{"train":>7s}{"test":>7s}{"maxDD":>7s}{"tstDD":>7s}'
          f'{"fills":>6s}{"bench":>6s}{"bnch$":>7s}{"adm":>7s}{"cash":>7s}')
    run('twelve (live)', d, s12, cal, k, excl, out, TWELVE)
    run('twenty, flat pool, all on', d, s_all, cal, k, excl, out, TWENTY)
    run('D: twenty, core first, all on', d, s_all, cal, k, excl, out, TWENTY, tier2=set(BENCH))
    grid = [(X, N, R) for X in (0.30, 0.40, 0.50) for N in (40, 60, 120) for R in (None, 0.15)]
    for X, N, R in grid:
        adm = {n: admitted(d[n], X, N, R) for n in BENCH}
        nb = {n: set(cal) - adm[n] for n in BENCH}
        rr = f'R{int(R*100)}' if R is not None else 'noR'
        run(f'A only  X{int(X*100)} N{N} {rr}', d, s_all, cal, k, excl, out, TWENTY,
            no_buy=nb, adm=adm)
        run(f'D+A     X{int(X*100)} N{N} {rr}', d, s_all, cal, k, excl, out, TWENTY,
            no_buy=nb, tier2=set(BENCH), adm=adm)
    # variant: diversifiers always on (tier 2), rebound names drop-admitted
    for X, N in ((0.40, 60), (0.30, 60)):
        adm = {n: admitted(d[n], X, N, None) for n in REBOUND}
        nb = {n: set(cal) - adm[n] for n in REBOUND}
        run(f'D+A rebound only X{int(X*100)} N{N}', d, s_all, cal, k, excl, out, TWENTY,
            no_buy=nb, tier2=set(BENCH), adm=adm)
    json.dump(out, open('managed20.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
