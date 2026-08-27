"""
Week-end profit-exit study (user, 26 Aug 2026): any position still open at the
Friday close (target not reached) that stands in profit is sold at that close
instead of being carried into the next week.

Effects in tension: the sale frees capital for Monday's pooled allocation and
dodges weekend gaps, but truncates the premium the resting target was waiting
for. Both engine and book_sim gained `week_end_exit='profit'` (sell at the
week-end close when close - comm > fill + comm; positions bought that week and
older holds alike; default None reproduces hold-to-target — invariance asserted
in-run).

DIAGNOSTIC first, on the baseline: every Friday close at which a position stood
open and in profit — what did the position's profit look like THEN, and what did
the same position finally earn (and when)? If the remaining hold typically adds
more than it risks, the rule dies before the intervention does.

INTERVENTION: per name (deployed params, verified fills, both halves) and the
pooled nine-name book on the live config (09:00/4% PM rule both sides).
"""
import json
import pickle

import numpy as np

from book_sim import NAMES as N8, load_all, simulate
from engine import Params, run_model
from fresh_opt import SPLIT, annualise
from fresh_opt_cands import aw_params

OUT = 'weekly_close.json'
NAMES = ['TSM', 'VRT', 'VST', 'RKLB', 'MU', 'GM', 'VLO', 'CF', 'MRVL']


def score(res, dts, cut):
    eq = res.frames['equity']
    N = len(dts)
    return (annualise(eq[N - 1] / eq[0] - 1, dts, 0, N - 1),
            annualise(eq[cut] / eq[0] - 1, dts, 0, cut),
            annualise(eq[N - 1] / eq[cut] - 1, dts, cut, N - 1))


def friday_diag(dts, C, frames, comm):
    """Every (position, week-end) where the position was open and in profit at the
    close: Friday profit vs the position's eventual exit profit."""
    N = len(dts)
    wk_end = [i < N - 1 and dts[i].isocalendar()[:2] != dts[i + 1].isocalendar()[:2]
              for i in range(N)]
    rows = []
    for tkey, bkey in (('t1', 'X'), ('t2', 'AM')):
        t = frames[tkey]
        bids = frames[bkey]
        i = 0
        while i < N:
            if t['Z'][i] != 1:
                i += 1
                continue
            bp = bids[i]
            j = i
            while j < N and t['AD'][j] != 1:
                j += 1
            if j >= N:
                break
            for f in range(i, j):                       # open through day f's close
                if wk_end[f] and C[f] - comm > bp + comm:
                    rows.append((C[f] / bp - 1, t['AC'][j] / bp - 1,
                                 (dts[j] - dts[f]).days,
                                 t['AC'][j] < t['AB'][j] - 1e-9))
            i = j + 1
    return rows


def main():
    t0 = Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                bayes_pct=0.5, years=2.2, ou_W=80)
    mrvl = aw_params(json.load(open('fresh_opt_cands.json'))['MRVL']['reference']['vec'], t0)
    data, sleeves, cal = load_all(names=NAMES, params_override={'MRVL': mrvl})
    pm = pickle.load(open('data_pm/pm_last_cuts.pkl', 'rb'))['09:00']
    def pm_rule(name, i, bid):
        pml = pm[name].get(data[name]['dts'][i])
        return pml is not None and bid < pml * (1 - 0.04)

    res = {}
    all_rows = []
    print('===== per name: hold-to-target vs week-end profit exit =====')
    print(f"  {'name':6s}{'':10s}{'full':>8s}{'train':>8s}{'test':>8s}"
          f"{'buys':>6s}{'stops':>6s}{'wk exits':>9s}")
    for s in NAMES:
        d = data[s]
        dts, O, H, L, C, p, chk = d['dts'], d['O'], d['H'], d['L'], d['C'], d['p'], d['chk']
        cut = next(i for i, x in enumerate(dts) if x >= SPLIT)
        base = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk,
                         collect=True)
        rows = friday_diag(dts, C, base.frames, p.comm)
        all_rows += rows
        we = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk,
                       collect=True, week_end_exit='profit')
        b3, w3 = score(base, dts, cut), score(we, dts, cut)
        wex = we.frames['t1']['we_exits'] + we.frames['t2']['we_exits']
        res[s] = dict(base=list(b3), week=list(w3), we_exits=wex,
                      base_buys=base.total_buys, week_buys=we.total_buys)
        print(f"  {s:6s}{'baseline':10s}{b3[0]*100:>7.1f}%{b3[1]*100:>7.1f}%"
              f"{b3[2]*100:>7.1f}%{base.total_buys:>6d}{base.stop_loss_exits:>6d}{'':>9s}")
        print(f"  {'':6s}{'wk exit':10s}{w3[0]*100:>7.1f}%{w3[1]*100:>7.1f}%"
              f"{w3[2]*100:>7.1f}%{we.total_buys:>6d}{we.stop_loss_exits:>6d}{wex:>9d}",
              flush=True)

    a = np.array(all_rows, dtype=float)
    fri, fin, days, stopped = a[:, 0], a[:, 1], a[:, 2], a[:, 3].astype(bool)
    print(f"\nDIAGNOSTIC — {len(a)} (position x week-end) observations open and in "
          f"profit at a Friday close (baseline):")
    print(f"  profit at the Friday close:   avg {fri.mean()*100:+.2f}%  med {np.median(fri)*100:+.2f}%")
    print(f"  the position's final outcome: avg {fin.mean()*100:+.2f}%  med {np.median(fin)*100:+.2f}%")
    print(f"  final exit beat the Friday close in {int((fin > fri).sum())}/{len(a)} "
          f"({(fin > fri).mean()*100:.0f}%); median further hold {np.median(days):.0f} days")
    print(f"  of these, {int(stopped.sum())} ({stopped.mean()*100:.1f}%) eventually exited "
          f"below target (time stop) — avg final {fin[stopped].mean()*100:+.2f}% vs their "
          f"Friday {fri[stopped].mean()*100:+.2f}%")

    print('\n===== pooled nine-name book (09:00/4% PM rule both sides) =====')
    book = {}
    for lab, kw in (('baseline', {}), ('week-end profit exit', dict(week_end_exit='profit'))):
        r = simulate(data, sleeves, cal, mode='pooled', excl_fn=pm_rule, **kw)
        book[lab] = dict(full=r['full'], train=r['train'], test=r['test'],
                         maxdd=r['maxdd'], fills=r['fills'], we_exits=r['we_exits'])
        print(f"  {lab:22s} full {r['full']*100:6.1f}%  train {r['train']*100:6.1f}%  "
              f"test {r['test']*100:6.1f}%  DD {r['maxdd']*100:5.1f}%  fills {r['fills']:5d}"
              f"  wk exits {r['we_exits']}", flush=True)
    assert abs(book['baseline']['test'] - 1.184) < 0.01, 'baseline invariance failed'

    with open(OUT, 'w') as f:
        json.dump(dict(per_name=res, book=book), f, indent=1)
    print(f'\nsaved {OUT}')


if __name__ == '__main__':
    main()
