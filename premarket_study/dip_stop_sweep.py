"""
Does a name's dip-recovery profile tell us how long its stop should be?

The model runs ONE stop length for every name: 50 calendar days. dip_recovery.py
shows the names do not behave alike once they are 10% down -- MU is back inside
50 days 80% of the time, GM 0% -- so a uniform stop is either cutting MU
positions that would have recovered, or holding GM positions that never will.
Which one is an empirical question, and this is the cheapest form of it: hold
the fitted vector fixed, move only `stop_days`, and rescore.

Nothing is refitted. The vector is each name's stored reference vector, so the
sweep answers "what would this name have done under a different stop", not
"what is the best stop and vector together" -- the latter would just be another
10-parameter fit on 600 bars, which §3.1 says not to trust.

LIMITATION: only five of the nine run. TSM, VRT, VST and MU keep their deployed
vectors in the workbook alone, which is not attached (§3.54, open item 7), and
MU is precisely the fastest-recovering name -- the most interesting end of the
spread is missing. Five names is also too few to establish that optimal stop
tracks recovery; this is a direction, not a result.

Usage:  python3 dip_stop_sweep.py
"""
import json

from engine import Params, run_model
from fresh_opt_cands import REF, daily_from_5min, ref_params
from minute_index import make_checker

STOPS = (20, 30, 50, 80, 120, 100000)
# P(recover within 50 calendar days of being 10% down), from dip_recovery.py
P_REC = {'AVGO': 50, 'GM': 0, 'VLO': 67, 'CF': 33, 'MRVL': 40}


def score(nm, p, stop, dts, O, H, L, C, chk):
    q = Params(**{**p.__dict__, 'stop_days': stop})
    r = run_model(dts, O, H, L, C, q, ou_sigma='resid', same_day_exit=chk, collect=True)
    fr = r.frames
    eq = fr['equity']
    yrs = (dts[-1] - dts[0]).days/365.25
    ann = ((eq[-1]/eq[0])**(1/yrs) - 1)*100
    peak, dd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        dd = max(dd, 1 - v/peak)
    stops = fr['t1']['stops'] + fr['t2']['stops']
    return ann, dd*100, r.total_buys, stops


def main():
    out = {}
    print('stop-length sweep at the stored reference vector (nothing refitted)\n')
    print(f'{"name":6s}{"P(rec<=50cal)":>14s}' +
          ''.join(f'{(f"{s}d" if s < 10000 else "none"):>9s}' for s in STOPS) +
          f'{"best":>8s}')
    for nm, prec in sorted(P_REC.items(), key=lambda kv: -kv[1]):
        if nm not in REF or not REF[nm]:
            print(f'{nm:6s}  no stored vector'); continue
        dts, O, H, L, C = daily_from_5min(nm)
        p = ref_params(nm)
        chk = make_checker(nm, dts, O)
        row = []
        for s in STOPS:
            row.append(score(nm, p, s, dts, O, H, L, C, chk))
        best = max(range(len(STOPS)), key=lambda i: row[i][0])
        out[nm] = dict(p_rec=prec, stops=list(STOPS),
                       ann=[r[0] for r in row], maxdd=[r[1] for r in row],
                       buys=[r[2] for r in row], stopped=[r[3] for r in row],
                       best_stop=STOPS[best])
        print(f'{nm:6s}{prec:>13d}%' + ''.join(f'{r[0]:>8.1f}%' for r in row) +
              f'{(f"{STOPS[best]}d" if STOPS[best] < 10000 else "none"):>8s}', flush=True)
    print(f'\n  the same sweep, max drawdown:')
    print(f'{"name":6s}{"":14s}' + ''.join(f'{(f"{s}d" if s < 10000 else "none"):>9s}' for s in STOPS))
    for nm in sorted(out, key=lambda n: -P_REC[n]):
        print(f'{nm:6s}{"":14s}' + ''.join(f'{v:>8.1f}%' for v in out[nm]['maxdd']), flush=True)
    print(f'\n  stops fired:')
    print(f'{"name":6s}{"":14s}' + ''.join(f'{(f"{s}d" if s < 10000 else "none"):>9s}' for s in STOPS))
    for nm in sorted(out, key=lambda n: -P_REC[n]):
        print(f'{nm:6s}{"":14s}' + ''.join(f'{v:>9d}' for v in out[nm]['stopped']), flush=True)
    json.dump(out, open('dip_stop_sweep.json', 'w'), indent=1)
    print('\nDONE', flush=True)


if __name__ == '__main__':
    main()
