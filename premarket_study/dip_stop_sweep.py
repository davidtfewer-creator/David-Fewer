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

All nine now run. The four core vectors that previously lived only in the
workbook are read from deployed_params.json (§3.54 open item 7, closed), AVGO
and MRVL from fresh_opt_cands.json, GM/VLO/CF from the REF table. Nine names is
still few for establishing that the optimal stop TRACKS recovery, and the sweep
moves one parameter on a vector fitted with the stop at 50, so a long stop is
being judged on a vector chosen under a short one. Read it as "what does this
name lose or gain from the uniform 50", not as a per-name optimum.

Usage:  python3 dip_stop_sweep.py
"""
import json

from engine import Params, run_model
from fresh_opt_cands import REF, aw_params, daily_from_5min, ref_params
from minute_index import make_checker

STOPS = (20, 30, 50, 80, 120, 100000)
# P(recover within 50 calendar days of being 10% down), from dip_recovery.py
P_REC = {'MU': 80, 'VLO': 67, 'TSM': 57, 'VST': 57, 'AVGO': 50,
         'MRVL': 40, 'CF': 33, 'VRT': 29, 'GM': 0}


def params_for(nm):
    """Deployed where one exists, reference otherwise; sources differ by name."""
    dep = json.load(open('deployed_params.json'))['params']
    if nm in dep:
        from cf_swap_test import t0
        v = dep[nm]
        return Params(**{**{k: v[k] for k in v}, 'comm': t0().comm,
                         'capital': t0().capital, 'interest': t0().interest,
                         'stop_days': 50, 'bayes_pct': 0.5, 'years': t0().years})
    c = json.load(open('fresh_opt_cands.json'))
    if nm in c and 'vec' in c[nm].get('reference', {}):
        from cf_swap_test import t0
        return aw_params(c[nm]['reference']['vec'], t0())
    if nm in REF and REF[nm]:
        return ref_params(nm)
    return None


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
        p = params_for(nm)
        if p is None:
            print(f'{nm:6s}  no stored vector'); continue
        dts, O, H, L, C = daily_from_5min(nm)
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
