"""
Stop autopsy (user question, 3 Sep 2026): the pooled book takes ~20 time-stops
a year. Is there causal structure in them, or are they the flat tax the stop
memo priced?

Baseline: the live-config pooled book (current roster, PM rule), collect all
trades, split stops (hold >= 50 calendar days) from the rest, then profile:

  1. WHO   - stops by name and sleeve.
  2. WHEN  - clustering of stop ENTRIES in time (month buckets) and overlap
             with known episodes; how many stops share the same entry week.
  3. ENTRY TAPE - conditions on the entry day, stops vs non-stops:
             prior 5-session return, distance below the trailing 20d high,
             below/above own 200dma, book breadth that morning, days from
             the nearest earnings report (|d| <= 7 flagged).
  4. COST  - P&L of stops vs winners; the stop bucket's total drag.
  5. AFTER - for each stop, did the name reach the original entry price / the
             original target within the NEXT 50 sessions (was the stop a
             trough-crystalliser or a real regime exit)?

Diagnostic only -- no rule is proposed here; anything suggestive goes through
the standard both-halves protocol separately.
"""
import datetime as dt
import json
import pickle
import statistics

from book_sim import NAMES as N8, load_all, simulate
from engine import Params
from fresh_opt_cands import aw_params
from earnings_pause import EARNINGS

OUT = 'stop_autopsy.json'
ROSTER = [n if n != 'RKLB' else 'AVGO' for n in N8] + ['MRVL']
STOP_HOLD = 50


def load():
    t0 = Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                bayes_pct=0.5, years=2.2, ou_W=80)
    cands = json.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(cands['MRVL']['reference']['vec'], t0),
          'AVGO': aw_params(cands['AVGO']['reference']['vec'], t0)}
    data, sleeves, cal = load_all(names=ROSTER, params_override=po)
    pm = pickle.load(open('data_pm/pm_last_cuts.pkl', 'rb'))['09:00']

    def pm_rule(name, i, bid):
        pml = pm.get(name, {}).get(data[name]['dts'][i]) if name in pm else None
        return pml is not None and bid < pml * (1 - 0.04)
    return data, sleeves, cal, pm_rule


def d_of(x):
    return x.date() if hasattr(x, 'date') else x


def entry_context(data, name, entry, breadth_by_day):
    d = data[name]
    i = d['idx'][entry] if 'idx' in d else [j for j, x in enumerate(d['dts'])
                                            if d_of(x) == entry][0]
    C = d['C']
    ret5 = C[i - 1] / C[i - 6] - 1 if i >= 6 else None
    hi20 = max(C[max(0, i - 20):i]) if i >= 1 else None
    vs20 = C[i - 1] / hi20 - 1 if hi20 else None
    dma = statistics.fmean(C[max(0, i - 200):i]) if i >= 100 else None
    below = (C[i - 1] < dma) if dma else None
    reps = [dt.date.fromisoformat(s) for s in EARNINGS.get(name, [])]
    dnear = min((abs((entry - r).days) for r in reps), default=None)
    return dict(ret5=ret5, vs20=vs20, below=below,
                breadth=breadth_by_day.get(entry), earn_d=dnear, i=i)


def after_stop(data, name, i_exit, entry_px, target_px):
    C, H = data[name]['C'], data[name]['H']
    win = H[i_exit + 1:i_exit + 51]
    if not win:
        return None, None
    return (max(win) >= entry_px, max(win) >= target_px)


def main():
    data, sleeves, cal, pm_rule = load()
    for n in ROSTER:
        data[n]['idx'] = {d_of(x): j for j, x in enumerate(data[n]['dts'])}
    # book breadth per day (names below own trailing 200dma, ex ante)
    breadth = {}
    for day in cal:
        k = 0
        for n in ROSTER:
            j = data[n]['idx'].get(d_of(day))
            if j and j >= 100:
                C = data[n]['C']
                if C[j - 1] < statistics.fmean(C[max(0, j - 200):j]):
                    k += 1
        breadth[d_of(day)] = k

    r = simulate(data, sleeves, cal, mode='pooled', excl_fn=pm_rule,
                 collect_trades=True)
    assert abs(r['full'] - 0.724) < 0.01
    trades = r['trades']
    for t in trades:
        t['entry_d'], t['exit_d'] = d_of(t['entry']), d_of(t['exit'])
        t['hold'] = (t['exit_d'] - t['entry_d']).days
    stops = [t for t in trades if t['stopped']]
    rest = [t for t in trades if not t['stopped']]
    yrs = (d_of(cal[-1]) - d_of(cal[0])).days / 365.25
    print(f'trades {len(trades)}, stops {len(stops)} ({len(stops)/yrs:.1f}/yr), '
          f'stop P&L {sum(t["pnl"] for t in stops):,.0f} vs book P&L '
          f'{sum(t["pnl"] for t in trades):,.0f}')

    print('\n1. WHO — stops by name (count | avg loss % | total $):')
    byname = {}
    for t in stops:
        byname.setdefault(t['name'], []).append(t)
    for n in sorted(byname, key=lambda n: -len(byname[n])):
        ts = byname[n]
        print(f'  {n:5s} {len(ts):3d}  {statistics.fmean(t["pnl"]/t["cost"] for t in ts)*100:+7.2f}%'
              f'  {sum(t["pnl"] for t in ts):>12,.0f}')

    print('\n2. WHEN — stop entries by month:')
    bym = {}
    for t in stops:
        bym.setdefault(t['entry_d'].strftime('%Y-%m'), []).append(t)
    for m in sorted(bym):
        names = ', '.join(sorted({t['name'] for t in bym[m]}))
        print(f'  {m}  {len(bym[m]):3d}  ({names})')

    print('\n3. ENTRY TAPE — stops vs non-stops (medians):')
    ctx_s = [entry_context(data, t['name'], t['entry_d'], breadth) for t in stops]
    ctx_r = [entry_context(data, t['name'], t['entry_d'], breadth) for t in rest]

    def med(cs, k):
        v = [c[k] for c in cs if c[k] is not None]
        return statistics.median(v) if v else None
    for k, lab in (('ret5', 'prior 5-session return'),
                   ('vs20', 'close vs trailing 20d high'),
                   ('breadth', 'book breadth at entry')):
        print(f'  {lab:28s} stops {med(ctx_s,k)*100 if k!="breadth" else med(ctx_s,k):+.2f}'
              f'{"%" if k != "breadth" else ""}   others '
              f'{med(ctx_r,k)*100 if k!="breadth" else med(ctx_r,k):+.2f}'
              f'{"%" if k != "breadth" else ""}')
    for cs, lab in ((ctx_s, 'stops'), (ctx_r, 'others')):
        n_bel = sum(1 for c in cs if c['below'])
        n_earn = sum(1 for c in cs if c['earn_d'] is not None and c['earn_d'] <= 7)
        print(f'  {lab:6s}: below own 200dma at entry {n_bel}/{len(cs)}'
              f'  | entry within 7d of a report {n_earn}/{len(cs)}')

    print('\n4. AFTER — the 50 sessions following each stop exit:')
    # entry price recovered from the exit-day open and the trade's return
    # (stop sells at the open of day 50; fees are a rounding error here);
    # target = entry x (1 + that sleeve's premium)
    prem = {(s['name'], s['kind']): s['prem'] for s in sleeves}
    rec_e = rec_t = 0
    for t in stops:
        i_exit = data[t['name']]['idx'][t['exit_d']]
        px = data[t['name']]['O'][i_exit] / (1 + t['pnl'] / t['cost'])
        tgt = px * (1 + prem[(t['name'], t['kind'])])
        re_, rt_ = after_stop(data, t['name'], i_exit, px, tgt)
        rec_e += bool(re_)
        rec_t += bool(rt_)
    print(f'  recovered to ENTRY within 50 sessions after the stop: {rec_e}/{len(stops)}')
    print(f'  reached original target (or +3% proxy): {rec_t}/{len(stops)}')

    with open(OUT, 'w') as f:
        json.dump(dict(
            n_trades=len(trades), n_stops=len(stops),
            stop_pnl=sum(t['pnl'] for t in stops),
            by_name={n: len(v) for n, v in byname.items()},
            by_month={m: len(v) for m, v in bym.items()},
            medians=dict(stops={k: med(ctx_s, k) for k in ('ret5', 'vs20', 'breadth')},
                         others={k: med(ctx_r, k) for k in ('ret5', 'vs20', 'breadth')}),
            below_dma=dict(stops=sum(1 for c in ctx_s if c['below']),
                           others=sum(1 for c in ctx_r if c['below'])),
            near_earnings=dict(stops=sum(1 for c in ctx_s if c['earn_d'] is not None and c['earn_d'] <= 7),
                               others=sum(1 for c in ctx_r if c['earn_d'] is not None and c['earn_d'] <= 7)),
            recovered_entry=rec_e, recovered_target=rec_t), f, indent=1)
    print(f'\nsaved {OUT}')


if __name__ == '__main__':
    main()
