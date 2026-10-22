"""
book20.py — the 20-name managed book as chosen 22 Oct 2026 (HANDOVER 3.93):

  core (tier 1)  the twelve, unchanged: TSM VRT VST AVGO MU GM VLO CF MRVL RTX DE NVDA
  bench (tier 2) rebound  PLTR TSLA RKLB  -- eligible while admitted: prior close
                                             >= 40% below trailing 252-session high,
                                             for 60 sessions after the last such day
                 divers.  NEM LEN DLTR RKT TEAM -- always eligible
  gate           breadth K>=6 of the twelve: a core name below its own 200dma while
                 >= 6 of the twelve are below theirs places no buy order, and its
                 share of the morning cash is held back
  E              that held-back cash is lent to the eligible bench orders (each at
                 most one ordinary sleeve's share); the rest stays in cash. The bench
                 has no other funding. Orders never exceed cash (cash account).
  overlays       PM rule (09:00, 4%) and ATH gate (eps 0) on all twenty; 50-day stop.

Writes book20.json (results) and deployed_book20.json (roster, tiers, rules,
vectors) in the deployed_book12.json format.
"""
import collections
import json

from fresh_opt import SPLIT
from lowdd_book import TWELVE, params
from book12 import pm_rule_for
from book_sim import load_all, simulate
from bear_stop import CAP
from parallel_book import gate_sets
from recap_9v12 import mdd
from managed20 import admitted
from dd_episodes_e import episodes

REBOUND = ['PLTR', 'TSLA', 'RKLB']
DIVERS = ['NEM', 'LEN', 'DLTR', 'RKT', 'TEAM']
BENCH = REBOUND + DIVERS
TWENTY = TWELVE + BENCH
X, N, K, EPS = 0.40, 60, 6, 0.0
KEYS = ('lam', 'phi_L', 'psi', 'k', 'premium', 'peak_cap', 'ou_buf_k', 'ou_prem', 'ou_cap', 'ou_W')


def main():
    po, basis = params(TWENTY)
    ek = {n: dict(ath_target_guard=EPS) for n in TWENTY}
    d, s_all, cal = load_all(engine_kwargs_per_name=ek, names=TWENTY, params_override=po)
    k = max(i for i, x in enumerate(cal) if x <= SPLIT)
    yrs = len(cal) / 252
    excl = pm_rule_for(d, set(TWENTY))
    g = gate_sets(TWELVE, K)[0]
    nb = {n: set(g[n]) for n in TWELVE}
    adm = {n: admitted(d[n], X, N, None) for n in REBOUND}
    nb.update({n: set(cal) - adm[n] for n in REBOUND})

    # the core's vectors must be the deployed twelve's, untouched
    dep12 = json.load(open('deployed_book12.json'))['params']
    for n in TWELVE:
        for key in KEYS:
            assert abs(float(getattr(d[n]['p'], key)) - float(dep12[n][key])) < 1e-9, (n, key)

    s12 = [x for x in s_all if x['name'] in TWELVE]
    r12 = simulate(d, s12, cal, capital=CAP, mode='pooled', collect_trades=True, excl_fn=excl)
    r = simulate(d, s_all, cal, capital=CAP, mode='pooled', collect_trades=True, excl_fn=excl,
                 no_buy=nb, gate_cash=True, tier2=set(BENCH))
    assert min(r['cash']) > -1e-6
    out = {}
    for tag, x in (('live twelve', r12), ('book20', r)):
        out[tag] = dict(full=x['full'], train=x['train'], test=x['test'], maxdd=x['maxdd'],
                        test_dd=mdd(x['equity'][k:]), fills_yr=x['fills'] / yrs)
        o = out[tag]
        print(f'  {tag:12s} full {o["full"]*100:5.1f}  train {o["train"]*100:5.1f}  test {o["test"]*100:5.1f}'
              f'  maxDD {o["maxdd"]*100:4.1f}  testDD {o["test_dd"]*100:4.1f}  fills/yr {o["fills_yr"]:.0f}')

    pn, fl = collections.defaultdict(float), collections.Counter()
    for t in r['trades']:
        pn[t['name']] += t['pnl']; fl[t['name']] += 1
    print('\n  P&L by name ($k, 2024-26), fills/yr:')
    for n in TWENTY:
        print(f'    {n:5s} {"core " if n in TWELVE else "bench"} {pn[n]/1e3:+8.0f}  {fl[n]/yrs:5.1f}')
    on = sorted({dd for n in TWELVE for dd in g[n]} & set(cal))
    print(f'\n  breadth gate active on {len(on)} sessions: {on[0] if on else "-"} -> {on[-1] if on else "-"}')
    for n in REBOUND:
        a = sorted(adm[n] & set(cal))
        print(f'  {n} admitted {len(a)} sessions' + (f' ({a[0]} -> {a[-1]})' if a else ''))
    ep = episodes(r['equity'], cal)[:5]
    print('\n  five worst drawdowns:')
    for e in ep:
        print(f'    {e["peak"]} -> {e["trough"]} -> {e["recovered"] or "open"}  {e["depth"]*100:.1f}%')
    out['pnl_by_name'] = dict(pn)
    out['fills_by_name_yr'] = {n: fl[n] / yrs for n in TWENTY}
    out['gate_sessions'] = [str(x) for x in on]
    out['worst_dd'] = [{a: (str(b) if a in ('peak', 'trough', 'recovered') else b) for a, b in e.items()}
                       for e in ep]
    json.dump(out, open('book20.json', 'w'), indent=1, default=float)

    cfg = {'_note': ('The 20-name managed book as chosen 22 Oct 2026 (HANDOVER 3.88-3.93). Core = the '
                     'deployed twelve, unchanged. Bench = tier 2, funded ONLY by cash the breadth gate '
                     'holds back from gated core names (option E); never more than one ordinary '
                     "sleeve's share per bench order; orders never exceed cash. APLD/AAOI excluded by "
                     'user decision (hindsight). 2024-26 backtest: see book20.json.'),
           'roster': TWENTY, 'core': TWELVE, 'bench': BENCH, 'capital': CAP,
           'overlays': {'pm_rule': {'names': TWENTY, 'cut': '09:00', 'thr': 0.04},
                        'ath_gate_eps': EPS, 'stop_days': 50,
                        'breadth_gate': {'names': TWELVE, 'K': K, 'held_cash': True,
                                         'dma': 200, 'note': 'core only; bench is never 200dma-gated'},
                        'option_E': {'lend_held_cash_to': BENCH, 'per_order_cap': 'one ordinary sleeve share'},
                        'admission': {'rebound': {'names': REBOUND, 'drop_from_252d_high': X,
                                                  'hold_sessions': N, 'min_history': 60},
                                      'always_eligible': DIVERS}},
           'vector_basis': {n: basis.get(n, 'live workbook / reference') for n in TWENTY},
           'params': {n: {key: getattr(d[n]['p'], key) for key in KEYS} for n in TWENTY}}
    json.dump(cfg, open('deployed_book20.json', 'w'), indent=1, default=float)
    print('\n  wrote book20.json and deployed_book20.json')


if __name__ == '__main__':
    main()
