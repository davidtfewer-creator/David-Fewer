"""
The complete earnings map (user, 26 Aug 2026). Two studies, one calendar theme:

PART 1 — complete the per-name earnings-pause map. MU's P3 pause is adopted
(+5.2pp book), MRVL's post-report weeks are its BEST trades (no pause), AVGO is
pending its September report. The remaining seven book names have never been
through the decomposition: TSM, VRT, VST, RKLB (dates already in
earnings_pause.EARNINGS) and GM, VLO, CF (dates added there this session,
gap-validated). Per name: entry-timing diagnostic + P1/P2/P3 pause intervention,
full/train/test annualised. A pause is adoption-grade only on a both-halves win
(the MU bar).

PART 2 — the cross-name earnings veto. The AI complex gaps together on
bellwether report nights the model cannot see. Rule: no new bids in the six
AI-correlated names (TSM, VRT, VST, RKLB, MU, MRVL) for the 1 or 2 sessions
after an NVDA (or NVDA+AVGO) report. Diagnostic first (what did entries on
those sessions actually earn?), then the pooled book on the live config
(09:00/4% PM rule both sides).

Same protocol as everything else: verified fills, deployed/reference vectors,
split 2025-05-23.
"""
import datetime
import json
import pickle

import numpy as np

from book_sim import NAMES as N8, load_all, simulate
from earnings_pause import (EARNINGS, bucket_of, load_params, pause_dates,
                            trades_from_frames, validate_earnings)
from engine import Params, run_model
from fresh_opt import SPLIT, annualise
from fresh_opt_cands import aw_params, daily_from_5min
from minute_index import make_checker

OUT = 'earnings_map.json'
PART1 = ['TSM', 'VRT', 'VST', 'RKLB', 'GM', 'VLO', 'CF']
AI_SIX = ['TSM', 'VRT', 'VST', 'RKLB', 'MU', 'MRVL']


def scores(res, dts, cut):
    eq = res.frames['equity']
    N = len(dts)
    return (annualise(eq[N - 1] / eq[0] - 1, dts, 0, N - 1),
            annualise(eq[cut] / eq[0] - 1, dts, 0, cut),
            annualise(eq[N - 1] / eq[cut] - 1, dts, cut, N - 1))


def part1():
    out = {}
    winners = []
    for s in PART1:
        dts, O, H, L, C = daily_from_5min(s)
        chk = make_checker(s, dts, O)
        p = load_params(s)
        earnings = [datetime.date.fromisoformat(x) for x in EARNINGS[s]
                    if datetime.date.fromisoformat(x) <= dts[-1]]
        N = len(dts)
        cut = next(i for i, d in enumerate(dts) if d >= SPLIT)
        print(f'\n===== {s}: {len(earnings)} reports in sample =====')
        validate_earnings(dts, O, C, earnings)

        base = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk,
                         collect=True)
        fr = base.frames
        trades = (trades_from_frames(dts, fr, 't1', fr['X'])
                  + trades_from_frames(dts, fr, 't2', fr['AM']))
        buck = {}
        for (i, j, bp, xp, stopped) in trades:
            if j is None:
                continue
            b = bucket_of(dts[i], earnings)
            buck.setdefault(b, []).append((xp / bp - 1, stopped))
        print('  entry-timing buckets (avg ret / n / stops):')
        diag = {}
        for b in ('week before', 'week of', 'week after', 'away'):
            v = buck.get(b, [])
            if v:
                r = np.array([x[0] for x in v])
                st = sum(x[1] for x in v)
                diag[b] = dict(n=len(v), avg=float(r.mean()), stops=st)
                print(f'    {b:12s} {r.mean()*100:+6.2f}%  n={len(v):3d}  stops={st}')

        rows = {}
        b3 = scores(base, dts, cut)
        rows['baseline'] = list(b3)
        print(f'  {"scheme":16s}{"full":>8s}{"train":>8s}{"test":>8s}')
        print(f'  {"baseline":16s}{b3[0]*100:>7.1f}%{b3[1]*100:>7.1f}%{b3[2]*100:>7.1f}%')
        for label, mode in (('P1 week of', 1), ('P2 +before', 2), ('P3 +after', 3)):
            pd_ = pause_dates(earnings, mode)
            nb = [d in pd_ for d in dts]
            r = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk,
                          collect=True, no_buy=nb)
            v3 = scores(r, dts, cut)
            rows[label] = list(v3)
            win = v3[1] > b3[1] and v3[2] > b3[2]
            print(f'  {label:16s}{v3[0]*100:>7.1f}%{v3[1]*100:>7.1f}%{v3[2]*100:>7.1f}%'
                  f'{"   <-- BOTH HALVES" if win else ""}', flush=True)
            if win:
                winners.append((s, label))
        out[s] = dict(diag=diag, rows=rows)
    return out, winners


def sessions_after(dts, report_dates, n):
    """The n trading sessions strictly after each report date, on this calendar."""
    ds = set()
    for e in report_dates:
        after = [d for d in dts if d > e]
        ds.update(after[:n])
    return ds


def part2():
    t0 = Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                bayes_pct=0.5, years=2.2, ou_W=80)
    mrvl = aw_params(json.load(open('fresh_opt_cands.json'))['MRVL']['reference']['vec'], t0)
    names = N8 + ['MRVL']
    data, sleeves, cal = load_all(names=names, params_override={'MRVL': mrvl})
    pm = pickle.load(open('data_pm/pm_last_cuts.pkl', 'rb'))['09:00']
    def pm_rule(name, i, bid):
        pml = pm[name].get(data[name]['dts'][i])
        return pml is not None and bid < pml * (1 - 0.04)

    nvda = [datetime.date.fromisoformat(x) for x in EARNINGS['NVDA']]
    avgo = [datetime.date.fromisoformat(x) for x in EARNINGS['AVGO']]

    # ---- diagnostic: what do the AI six's entries earn on post-bellwether sessions?
    print('\n===== PART 2 diagnostic: AI-six completed trades by entry session =====')
    for lab, reps, n in (('post-NVDA (2 sessions)', nvda, 2),
                         ('post-AVGO (2 sessions)', avgo, 2)):
        rets, stops, n_tr = [], 0, 0
        rets_o = []
        for s in AI_SIX:
            d = data[s]
            r = run_model(d['dts'], d['O'], d['H'], d['L'], d['C'], d['p'],
                          ou_sigma='resid', same_day_exit=d['chk'], collect=True)
            fr = r.frames
            post = sessions_after(d['dts'], reps, n)
            trades = (trades_from_frames(d['dts'], fr, 't1', fr['X'])
                      + trades_from_frames(d['dts'], fr, 't2', fr['AM']))
            for (i, j, bp, xp, stopped) in trades:
                if j is None:
                    continue
                if d['dts'][i] in post:
                    rets.append(xp / bp - 1)
                    stops += stopped
                    n_tr += 1
                else:
                    rets_o.append(xp / bp - 1)
        a, b = np.array(rets), np.array(rets_o)
        print(f'  {lab:24s} entries {n_tr:3d}: avg {a.mean()*100:+.2f}% med '
              f'{np.median(a)*100:+.2f}% stops {stops}  |  elsewhere avg {b.mean()*100:+.2f}%',
              flush=True)

    # ---- intervention grid, pooled book
    print('\n===== PART 2 intervention: pooled book, PM rule both sides =====')
    print(f'  {"config":34s}{"full":>8s}{"train":>8s}{"test":>8s}{"maxDD":>8s}')
    rows = {}
    base = simulate(data, sleeves, cal, mode='pooled', excl_fn=pm_rule)
    rows['baseline'] = dict(full=base['full'], train=base['train'],
                            test=base['test'], maxdd=base['maxdd'])
    assert abs(base['test'] - 1.184) < 0.01
    print(f"  {'baseline':34s}{base['full']*100:>7.1f}%{base['train']*100:>7.1f}%"
          f"{base['test']*100:>7.1f}%{base['maxdd']*100:>7.1f}%")
    for lab, reps in (('NVDA', nvda), ('NVDA+AVGO', nvda + avgo)):
        for n in (1, 2):
            nb = {s: sessions_after(data[s]['dts'], reps, n) for s in AI_SIX}
            r = simulate(data, sleeves, cal, mode='pooled', excl_fn=pm_rule, no_buy=nb)
            key = f'{lab}, {n} session(s)'
            rows[key] = dict(full=r['full'], train=r['train'], test=r['test'],
                             maxdd=r['maxdd'])
            win = r['train'] > base['train'] and r['test'] > base['test']
            print(f"  {key:34s}{r['full']*100:>7.1f}%{r['train']*100:>7.1f}%"
                  f"{r['test']*100:>7.1f}%{r['maxdd']*100:>7.1f}%"
                  f"{'   <-- BOTH HALVES' if win else ''}", flush=True)
    return rows


def main():
    p1, winners = part1()
    print(f'\nPART 1 both-halves winners: {winners or "none"}')
    p2 = part2()
    with open(OUT, 'w') as f:
        json.dump(dict(part1=p1, part1_winners=winners, part2=p2), f, indent=1)
    print(f'saved {OUT}')


if __name__ == '__main__':
    main()
