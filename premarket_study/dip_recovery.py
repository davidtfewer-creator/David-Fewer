"""
How long is a name under water after a 10% dip, and does it differ across the book?

The question behind this is operational, not academic: the model buys at a
discount to the previous close, and sometimes the name keeps falling. With both
sleeves filled the name is frozen (§3.30) and the capital is committed until
either the target is reached or the 50-CALENDAR-DAY stop fires. So the number
that matters is not "how volatile is this name" but:

    once we are 10% down, what is the chance we get back before the stop?

Episodes are built from the underwater curve, which makes them non-overlapping
by construction: an episode opens when the close drops below the running peak,
and closes when the close regains that peak. Depth is the worst close inside it.
Episodes reaching -10% are the ones counted here.

Three clocks are reported because they answer different questions:
  peak -> recovery   the whole episode: how long the name is impaired
  -10% -> recovery   THE ONE THAT MATTERS: we are already 10% down and holding,
                     how long until whole
  trough -> recovery the rebound leg alone

Everything is also given in CALENDAR days, because the model's stop is in
calendar days, which makes P(recover within 50 calendar days) directly the
probability a 10%-underwater position gets out at target rather than at the stop.

Censoring is reported, never silently dropped: an episode still under water at
the end of the sample is a lower bound on its own recovery time, and a name with
many of them is worse than its median suggests, not better.

Usage:  python3 dip_recovery.py [--depth 0.10] [TICKER ...]
"""
import json
import statistics
import sys

from fresh_opt_cands import daily_from_5min

BOOK = ['TSM', 'VRT', 'VST', 'AVGO', 'MU', 'GM', 'VLO', 'CF', 'MRVL']
HORIZONS_CAL = (20, 50, 100)


def episodes(dts, C, depth):
    """Non-overlapping underwater episodes reaching `depth` below a running peak."""
    out = []
    peak, peak_i = C[0], 0
    i = 1
    n = len(C)
    while i < n:
        if C[i] >= peak:
            peak, peak_i = C[i], i
            i += 1
            continue
        # under water: walk to recovery or to the end
        start = i
        trough, trough_i = C[i], i
        hit_i = None
        j = i
        while j < n and C[j] < peak:
            if C[j] < trough:
                trough, trough_i = C[j], j
            if hit_i is None and C[j] <= peak*(1 - depth):
                hit_i = j
            j += 1
        recovered = j < n
        if hit_i is not None:
            out.append(dict(
                peak_i=peak_i, start_i=start, hit_i=hit_i, trough_i=trough_i,
                end_i=(j if recovered else n - 1), recovered=recovered,
                depth=trough/peak - 1,
                peak_date=str(dts[peak_i]), hit_date=str(dts[hit_i]),
                trough_date=str(dts[trough_i]),
                end_date=str(dts[j if recovered else n - 1]),
                sess_peak=(j if recovered else n - 1) - peak_i,
                sess_hit=(j if recovered else n - 1) - hit_i,
                sess_trough=(j if recovered else n - 1) - trough_i,
                cal_hit=(dts[j if recovered else n - 1] - dts[hit_i]).days,
                cal_peak=(dts[j if recovered else n - 1] - dts[peak_i]).days))
        if recovered:
            peak, peak_i = C[j], j
            i = j + 1
        else:
            break
    return out


def q(xs, p):
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, int(len(s)*p))]


def main():
    depth = 0.10
    if '--depth' in sys.argv:
        depth = float(sys.argv[sys.argv.index('--depth') + 1])
    names = [a for a in sys.argv[1:] if not a.startswith('--') and not a.replace('.', '').isdigit()] or BOOK
    print(f'dip = close {depth*100:.0f}% below a running peak of the close; '
          f'recovery = close regains that peak\n')
    print(f'{"name":6s}{"eps":>5s}{"/yr":>6s}{"med depth":>11s}{"worst":>8s}'
          f'{"-10%->rec (sessions)":>24s}{"cal days":>11s}'
          f'{"P(rec<=50cal)":>15s}{"unrec":>7s}{"%UW":>7s}')
    print(f'{"":6s}{"":5s}{"":6s}{"":11s}{"":8s}{"med   75th   90th":>24s}'
          f'{"med":>11s}{"":15s}{"":7s}')
    rows = []
    for nm in names:
        dts, O, H, L, C = daily_from_5min(nm)
        eps = episodes(dts, C, depth)
        yrs = (dts[-1] - dts[0]).days/365.25
        rec = [e for e in eps if e['recovered']]
        unrec = [e for e in eps if not e['recovered']]
        sh = [e['sess_hit'] for e in rec]
        ch = [e['cal_hit'] for e in rec]
        # P(recover within 50 calendar days of first being 10% down).
        # Censored episodes count as NOT recovered in time, which is correct:
        # they are still down at the end of the sample.
        within = sum(1 for e in eps if e['recovered'] and e['cal_hit'] <= 50)
        p50 = within/len(eps)*100 if eps else None
        uw = sum(e['end_i'] - e['hit_i'] for e in eps)/len(C)*100
        rows.append(dict(name=nm, n=len(eps), per_yr=len(eps)/yrs,
                         med_depth=statistics.median([e['depth'] for e in eps]) if eps else None,
                         worst=min((e['depth'] for e in eps), default=None),
                         med_sess=q(sh, 0.5), p75_sess=q(sh, 0.75), p90_sess=q(sh, 0.90),
                         med_cal=q(ch, 0.5), p_rec_50cal=p50,
                         unrecovered=len(unrec), pct_underwater=uw,
                         episodes=eps))
        r = rows[-1]
        f = lambda v, w=6: (f'{v:>{w}d}' if isinstance(v, int) else f'{"-":>{w}s}')
        print(f'{nm:6s}{r["n"]:>5d}{r["per_yr"]:>6.1f}'
              f'{r["med_depth"]*100:>10.1f}%{r["worst"]*100:>7.1f}%'
              f'{f(r["med_sess"],8)}{f(r["p75_sess"],7)}{f(r["p90_sess"],7)}'
              f'{f(r["med_cal"],11)}{(f"{p50:.0f}%" if p50 is not None else "-"):>15s}'
              f'{r["unrecovered"]:>7d}{uw:>6.0f}%', flush=True)
    print(f'\n  unrec = still below the peak at the end of the sample (a LOWER BOUND on its')
    print(f'          recovery time, and counted as a failure in P(rec<=50cal))')
    print(f'  %UW   = share of all sessions spent 10% or more below a running peak')
    print(f'  the model\'s stop is 50 CALENDAR days, so P(rec<=50cal) is roughly the chance a')
    print(f'  10%-underwater position gets out at target rather than at the stop.')
    with open('dip_recovery.json', 'w') as f:
        json.dump(rows, f, indent=1)
    print('\nDONE', flush=True)


if __name__ == '__main__':
    main()
