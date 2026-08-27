"""
Earnings-pause study — NVDA first.

Hypothesis (user, 10 Aug 2026): some of the stops and long holds come from entering
around earnings dates; pausing new entries near earnings might help.

Two measurements, kept separate:

  DIAGNOSTIC  reconstruct every verified round trip under the baseline and classify
              it by WHERE ITS ENTRY sat relative to the nearest earnings date
              (week before / week of / week after / away). If the hypothesis is
              right, the near-earnings buckets show worse per-trade returns, more
              stops, longer holds.

  INTERVENTION  re-run with new entries suppressed on three calendar windows
              around each report --
                P1: the week of the report (Mon-Fri of its ISO week)
                P2: the week of + the week before
                P3: the week of + the week before + the week after
              Resting exits, targets and stops run unchanged; only the morning
              bid is withheld. Scored on verified fills, full sample and the
              tested half, against the untouched baseline.

Earnings dates are validated against the price data: a report (after the close)
should print an abnormal open gap the next session; any date without that
signature is flagged.

Basis: deployed NVDA daily vector (nvda_verified_bayesfloor.json), residual sigma,
verified same-day fills from the 5-minute bars.
"""
import datetime
import json

import numpy as np

from engine import Params, run_model
from fresh_opt_cands import daily_from_5min
from fresh_opt import SPLIT, annualise
from minute_index import make_checker

# Report dates verified against company filings/IR pages and the price data's gap
# signature; pre-market reporters (TSM, VRT, VST) gap on the report day, after-close
# reporters (NVDA, RKLB, MU) on the next session. Week-granular windows make a
# one-day dating error immaterial.
EARNINGS = {
    'NVDA': ['2024-05-22', '2024-08-28', '2024-11-20', '2025-02-26', '2025-05-28',
             '2025-08-27', '2025-11-19', '2026-02-25', '2026-05-20'],
    'TSM':  ['2024-04-18', '2024-07-18', '2024-10-17', '2025-01-16', '2025-04-17',
             '2025-07-17', '2025-10-16', '2026-01-15', '2026-04-16', '2026-07-16'],
    'VRT':  ['2024-04-24', '2024-07-24', '2024-10-23', '2025-02-12', '2025-04-23',
             '2025-07-30', '2025-10-22', '2026-02-11', '2026-04-22', '2026-07-29'],
    'VST':  ['2024-05-07', '2024-08-08', '2024-11-07', '2025-02-27', '2025-05-06',
             '2025-08-07', '2025-11-06', '2026-02-26', '2026-05-07', '2026-08-06'],
    'RKLB': ['2024-05-06', '2024-08-08', '2024-11-12', '2025-02-27', '2025-05-08',
             '2025-08-07', '2025-11-10', '2026-02-26', '2026-05-07', '2026-08-10'],
    'MU':   ['2024-06-26', '2024-09-25', '2024-12-18', '2025-03-20', '2025-06-25',
             '2025-09-23', '2025-12-17', '2026-03-18', '2026-06-24'],
    'TSLA': ['2024-04-23', '2024-07-23', '2024-10-23', '2025-01-29', '2025-04-22',
             '2025-07-23', '2025-10-22', '2026-01-28', '2026-04-22', '2026-07-22'],
    'AVGO': ['2024-06-12', '2024-09-05', '2024-12-12', '2025-03-06', '2025-06-05',
             '2025-09-04', '2025-12-11', '2026-03-04', '2026-06-03'],
    'MRVL': ['2024-05-30', '2024-08-29', '2024-12-03', '2025-03-05', '2025-05-29',
             '2025-08-28', '2025-12-02', '2026-03-05', '2026-05-28'],
    # GM and VLO report BEFORE the open (gap prints on the report day itself);
    # CF after the close. Post-2025 dates follow each company's quarterly
    # pattern; the gap validator flags any that look mis-dated, and the
    # week-granular pause windows make a one-day error immaterial.
    'GM':   ['2024-04-23', '2024-07-23', '2024-10-22', '2025-01-28', '2025-04-29',
             '2025-07-22', '2025-10-21', '2026-01-27', '2026-04-28', '2026-07-21'],
    'VLO':  ['2024-04-25', '2024-07-25', '2024-10-24', '2025-01-30', '2025-04-24',
             '2025-07-24', '2025-10-23', '2026-01-29', '2026-04-23', '2026-07-23'],
    'CF':   ['2024-05-01', '2024-08-07', '2024-10-30', '2025-02-19', '2025-05-07',
             '2025-08-06', '2025-10-29', '2026-02-18', '2026-05-06', '2026-08-05'],
}


def load_params(stock):
    if stock == 'NVDA':
        d = json.load(open('nvda_verified_bayesfloor.json'))
        d['ou_W'] = int(round(d['ou_W']))
        return Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                      bayes_pct=0.5, years=2.2, **d)
    from live5_load import load as load_book, STOCKS
    if stock in STOCKS:
        _, params, _ = load_book()
        return params[stock]
    from fresh_opt_cands import aw_params, ref_params
    if stock in ('GM', 'VLO', 'CF'):
        return ref_params(stock)
    t0 = Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                bayes_pct=0.5, years=2.2, ou_W=80)
    if stock == 'AVGO':   # reference fitted in the candidate sweep (full-sample, flagged)
        return aw_params(json.load(open('fresh_opt_cands.json'))['AVGO']['reference']['vec'], t0)
    if stock == 'TSLA':   # reference fitted for this study (full-sample, flagged)
        return aw_params(json.load(open('tsla_reference.json'))['vec'], t0)
    if stock == 'MRVL':   # admission reference (August 2026 round)
        return aw_params(json.load(open('fresh_opt_cands.json'))['MRVL']['reference']['vec'], t0)
    raise ValueError(stock)


def week_span(d):
    """Mon..Sun of the ISO week containing d."""
    mon = d - datetime.timedelta(days=d.weekday())
    return mon, mon + datetime.timedelta(days=6)


def pause_dates(earnings, mode):
    """mode 1: week of; 2: + week before; 3: + week before and after."""
    days = set()
    for e in earnings:
        mon, sun = week_span(e)
        spans = [(mon, sun)]
        if mode >= 2:
            spans.append((mon - datetime.timedelta(days=7), mon - datetime.timedelta(days=1)))
        if mode >= 3:
            spans.append((sun + datetime.timedelta(days=1), sun + datetime.timedelta(days=7)))
        for a, b in spans:
            d = a
            while d <= b:
                days.add(d)
                d += datetime.timedelta(days=1)
    return days


def validate_earnings(dts, O, C, earnings):
    """A report after the close should gap the next session's open abnormally."""
    idx = {d: i for i, d in enumerate(dts)}
    gaps = np.abs(np.array(O[1:]) / np.array(C[:-1]) - 1)
    thresh = np.percentile(gaps, 90)
    print(f'  gap sanity (90th pct of |open gap| = {thresh*100:.1f}%):')
    for e in earnings:
        nxt = next((d for d in dts if d > e), None)
        if nxt is None:
            print(f'    {e}: beyond sample')
            continue
        i = idx[nxt]
        g = abs(O[i] / C[i - 1] - 1)
        flag = 'OK' if g > thresh else '  <-- weak gap, check date'
        print(f'    {e} -> next session {nxt}: gap {g*100:5.1f}%  {flag}')


def trades_from_frames(dts, frames, tkey, bids):
    """Reconstruct round trips: (entry_i, exit_i, entry_px, exit_px, stopped)."""
    t = frames[tkey]
    out = []
    i = 0
    N = len(dts)
    while i < N:
        if t['Z'][i] == 1:
            bp = bids[i]
            j = i
            while j < N and not (t['AD'][j] == 1):
                j += 1
            if j >= N:                       # still open at sample end
                out.append((i, None, bp, None, False))
                break
            out.append((i, j, bp, t['AC'][j], t['AC'][j] < t['AB'][j] - 1e-9))
            i = j + 1
        else:
            i += 1
    return out


def bucket_of(entry_date, earnings):
    best = None
    for e in earnings:
        mon, sun = week_span(e)
        if mon <= entry_date <= sun:
            return 'week of'
        pm, ps = mon - datetime.timedelta(days=7), mon - datetime.timedelta(days=1)
        if pm <= entry_date <= ps:
            best = best or 'week before'
        nm, ns = sun + datetime.timedelta(days=1), sun + datetime.timedelta(days=7)
        if nm <= entry_date <= ns:
            best = best or 'week after'
    return best or 'away'


def main(stock='NVDA'):
    dts, O, H, L, C = daily_from_5min(stock)
    chk = make_checker(stock, dts, O)
    p = load_params(stock)
    earnings = [datetime.date.fromisoformat(s) for s in EARNINGS[stock]]
    N = len(C)
    cut = next(i for i, d in enumerate(dts) if d >= SPLIT)

    print(f'===== {stock}: {N} sessions {dts[0]} to {dts[-1]}, '
          f'{len(earnings)} reports in sample =====')
    validate_earnings(dts, O, C, earnings)

    # ---------------- diagnostic on the baseline
    r = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk, collect=True)
    fr = r.frames
    trades = (trades_from_frames(dts, fr, 't1', fr['X'])
              + trades_from_frames(dts, fr, 't2', fr['AM']))
    buckets = {}
    for (i, j, bp, xp, stopped) in trades:
        b = bucket_of(dts[i], earnings)
        d = buckets.setdefault(b, dict(n=0, ret=[], stops=0, hold=[], open=0))
        d['n'] += 1
        if j is None:
            d['open'] += 1
            continue
        d['ret'].append(xp / bp - 1)
        d['stops'] += stopped
        d['hold'].append((dts[j] - dts[i]).days)
    print(f'\n  DIAGNOSTIC — {len(trades)} verified round trips by entry timing '
          f'(baseline):')
    print(f'  {"entry bucket":13s}{"trades":>7s}{"avg ret":>9s}{"med ret":>9s}'
          f'{"stop rate":>10s}{"avg hold d":>11s}')
    for b in ['week before', 'week of', 'week after', 'away']:
        d = buckets.get(b)
        if not d or not d['ret']:
            print(f'  {b:13s}{d["n"] if d else 0:>7d}')
            continue
        rets = np.array(d['ret'])
        print(f'  {b:13s}{d["n"]:>7d}{rets.mean()*100:>8.2f}%{np.median(rets)*100:>8.2f}%'
              f'{d["stops"]/len(rets)*100:>9.0f}%{np.mean(d["hold"]):>11.1f}')
    # stops: where did their entries sit?
    stop_entries = [dts[i] for (i, j, bp, xp, st) in trades if j is not None and st]
    print(f'  stop-loss exits: {len(stop_entries)}; entry buckets: '
          f'{[bucket_of(d, earnings) for d in stop_entries]}')

    # ---------------- intervention
    print(f'\n  INTERVENTION — new entries paused, exits unchanged (verified):')
    print(f'  {"scheme":22s}{"full ann":>9s}{"test ann":>9s}{"buys":>6s}{"stops":>6s}'
          f'{"maxDD":>7s}{"paused d":>9s}')
    rows = {}
    for label, mode in [('baseline', 0), ('P1 week of', 1),
                        ('P2 + week before', 2), ('P3 + week after too', 3)]:
        if mode == 0:
            nb = None
            paused = 0
        else:
            pd_ = pause_dates(earnings, mode)
            nb = [d in pd_ for d in dts]
            paused = sum(nb)
        res = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk,
                        collect=True, no_buy=nb)
        eq = res.frames['equity']
        full = (eq[N - 1] / eq[0]) if eq[0] > 0 else 0
        test = (eq[N - 1] / eq[cut]) if eq[cut] > 0 else 0
        fa = annualise(full - 1, dts, 0, N - 1)
        ta = annualise(test - 1, dts, cut, N - 1)
        peak, dd = -1e30, 0.0
        for e in eq:
            peak = max(peak, e)
            if peak > 0:
                dd = max(dd, (peak - e) / peak)
        rows[label] = (fa, ta)
        print(f'  {label:22s}{fa*100:>8.1f}%{ta*100:>8.1f}%{res.total_buys:>6d}'
              f'{res.stop_loss_exits:>6d}{dd*100:>6.1f}%{paused:>9d}')
    return rows


if __name__ == '__main__':
    import sys
    main(*(sys.argv[1:] or ['NVDA']))
