"""
dd_episodes_e.py — the ten worst drawdown episodes of the breadth K>=6 + E
managed book (§3.90 central arm), next to the live twelve over the same dates.
An episode runs from an equity high to the next new high; depth is the
deepest close below that high; episodes still open at the end are marked.
"""
import json

from lowdd_book import TWELVE, params
from book12 import pm_rule_for
from book_sim import load_all, simulate
from bear_stop import CAP
from parallel_book import gate_sets
from managed20 import BENCH, REBOUND, TWENTY, EPS, admitted


def episodes(eq, cal):
    out, pk, pi, ti = [], eq[0], 0, 0
    for i in range(1, len(eq)):
        if eq[i] >= pk:
            if ti != pi and 1 - eq[ti] / pk > 0:
                out.append(dict(peak=cal[pi], trough=cal[ti], recovered=cal[i],
                                depth=1 - eq[ti] / pk, down=ti - pi, up=i - ti))
            pk, pi, ti = eq[i], i, i
        elif eq[i] < eq[ti]:
            ti = i
    if ti != pi:
        out.append(dict(peak=cal[pi], trough=cal[ti], recovered=None,
                        depth=1 - eq[ti] / pk, down=ti - pi, up=None))
    return sorted(out, key=lambda e: -e['depth'])


def worst_in(eq, cal, lo, hi):
    ix = [i for i, d in enumerate(cal) if lo <= d <= hi]
    seg = [eq[i] for i in range(ix[0], ix[-1] + 1)]
    pk, m = seg[0], 0.0
    for v in seg:
        pk = max(pk, v); m = max(m, 1 - v / pk)
    return m


def main():
    po, _ = params(TWENTY)
    ek = {n: dict(ath_target_guard=EPS) for n in TWENTY}
    d, s_all, cal = load_all(engine_kwargs_per_name=ek, names=TWENTY, params_override=po)
    excl = pm_rule_for(d, set(TWENTY))
    g6 = gate_sets(TWELVE, 6)[0]
    nb = {n: set(cal) - admitted(d[n], 0.40, 60, None) for n in REBOUND}
    nb.update({n: set(g6[n]) for n in TWELVE})
    rE = simulate(d, s_all, cal, capital=CAP, mode='pooled', collect_trades=True, excl_fn=excl,
                  no_buy=nb, gate_cash=True, tier2=set(BENCH))
    assert abs(rE['maxdd'] - 0.135) < 0.001, rE['maxdd']
    s12 = [x for x in s_all if x['name'] in TWELVE]
    r12 = simulate(d, s12, cal, capital=CAP, mode='pooled', collect_trades=True, excl_fn=excl)
    epE = episodes(rE['equity'], cal)[:10]
    print(f'  {"#":>2s}  {"peak":10s}  {"trough":10s}  {"recovered":10s}{"depth":>7s}'
          f'{"down":>6s}{"up":>6s}   live twelve, same window')
    for j, e in enumerate(epE, 1):
        hi = e['recovered'] or cal[-1]
        w12 = worst_in(r12['equity'], cal, e['peak'], hi)
        print(f'  {j:>2d}  {e["peak"]}  {e["trough"]}  {str(e["recovered"] or "open"):10s}'
              f'{e["depth"]*100:>6.1f}%{e["down"]:>6d}{(e["up"] if e["up"] is not None else 0):>6d}'
              f'   {w12*100:5.1f}%')
    json.dump(dict(E=[{k: str(v) if k in ('peak', 'trough', 'recovered') else v for k, v in e.items()}
                      for e in epE]), open('dd_episodes_e.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
