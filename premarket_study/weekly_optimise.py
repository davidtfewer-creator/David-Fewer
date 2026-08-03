"""
Optimise the WEEKLY model for the four low-return names (NVDA, SOFI, AVGO, SPOT).

Optimised against VERIFIED fills (1-minute NVDA, 5-minute the rest), so the result is an
honest, deployable figure rather than an optimistic one. Reports the daily model's verified
return alongside for a like-for-like comparison, plus how much of the weekly result still
depends on fill-day exits.
"""
import sys, statistics, json
from scipy.optimize import differential_evolution
from stop_sweep import load_book
from engine import Params, run_model
from weekly_engine import run_weekly
from five_min import make_checker as fm_checker, FILES as FM_FILES
from minute_engine import make_checker as nvda_checker

data, params, cached = load_book()
TARGETS = ['NVDA', 'SOFI', 'AVGO', 'SPOT', 'TSLA', 'PLTR']

# build checkers only for the names actually requested (each parses a large workbook)
_REQ = [a for a in sys.argv[1:] if a in TARGETS] or TARGETS
CHK = {}
for s in _REQ:
    dts, O, H, L, C = data[s]
    CHK[s] = (nvda_checker(dts, O)[0] if s == 'NVDA' else fm_checker(s, dts, O)[0])

NM = ['lam','phi_L','psi','k','premium','peak_cap','ou_buf_k','ou_prem','ou_cap','ou_W']
BOUNDS = [(0.2,1.6),(0.1,1.0),(0.001,0.1),(0.3,3.0),(0.005,0.15),(0.002,0.07),
          (0.1,2.5),(0.005,0.15),(0.005,0.12),(30,150)]
POLICY = [3, 4, 6, 7]
PERT = [0.97, 1.03]


def bvec(p): return [p.lam,p.phi_L,p.psi,p.k,p.premium,p.peak_cap,p.ou_buf_k,p.ou_prem,p.ou_cap,p.ou_W]

def mp(v, t):
    return Params(lam=v[0],phi_L=v[1],psi=v[2],k=v[3],premium=v[4],peak_cap=v[5],ou_buf_k=v[6],
                  ou_prem=v[7],ou_cap=v[8],ou_W=int(round(v[9])),comm=t.comm,capital=t.capital,
                  interest=t.interest,stop_days=t.stop_days,bayes_pct=t.bayes_pct,years=t.years)

def weekly(s, v):
    dts, O, H, L, C = data[s]
    return run_weekly(dts, O, H, L, C, mp(v, params[s]), checker=CHK[s])

def robust(s, v, floor):
    def one(x):
        r = weekly(s, x)
        return -5.0 + r['trades']*1e-3 if r['trades'] < floor else r['ann']
    base = one(v); sm = []
    for i in POLICY:
        for f in PERT:
            w = list(v); w[i] = min(max(w[i]*f, BOUNDS[i][0]), BOUNDS[i][1]); sm.append(one(w))
    return 0.5*base + 0.5*sum(sm)/len(sm)


if __name__ == '__main__':
    only = sys.argv[1:] or TARGETS
    out = {}
    for s in only:
        p0 = params[s]
        dts, O, H, L, C = data[s]
        dv = run_model(dts, O, H, L, C, p0, same_day_exit=CHK[s])       # daily, verified
        w0 = weekly(s, bvec(p0))                                        # weekly, current params
        floor = max(20, int(0.5 * w0['trades']))
        x0 = [min(max(v, BOUNDS[i][0]), BOUNDS[i][1]) for i, v in enumerate(bvec(p0))]
        res = differential_evolution(lambda v: -robust(s, v, floor), BOUNDS, x0=x0, init='sobol',
                                     seed=42, maxiter=9, popsize=8, mutation=(0.5,1.0),
                                     recombination=0.7, tol=1e-3, polish=False, disp=False,
                                     updating='immediate', workers=1)
        th = list(res.x); wo = weekly(s, th); pv = mp(th, p0)
        out[s] = {NM[i]: th[i] for i in range(10)}
        sd = wo['bayes']['sameday'] + wo['ou']['sameday']
        te = wo['bayes']['target_exits'] + wo['ou']['target_exits']
        print(f'\n===== {s} =====', flush=True)
        print(f'  daily model, verified fills : {dv.annual_return*100:5.0f}%  '
              f'({dv.total_buys/w0["yrs"]:.0f} trades/yr)', flush=True)
        print(f'  weekly, current params      : {w0["ann"]*100:5.0f}%  '
              f'({w0["trades"]/w0["yrs"]:.0f}/yr, Sharpe {w0["sharpe"]:.2f}, DD {w0["maxdd"]*100:.0f}%)',
              flush=True)
        print(f'  weekly, OPTIMISED           : {wo["ann"]*100:5.0f}%  '
              f'({wo["trades"]/wo["yrs"]:.0f}/yr, Sharpe {wo["sharpe"]:.2f}, DD {wo["maxdd"]*100:.0f}%)',
              flush=True)
        print(f'    premium {p0.premium:.4f} -> {pv.premium:.4f} | ou_prem {p0.ou_prem:.4f} -> {pv.ou_prem:.4f}'
              f' | k {p0.k:.2f} -> {pv.k:.2f} | ou_bufk {p0.ou_buf_k:.2f} -> {pv.ou_buf_k:.2f}', flush=True)
        print(f'    exits: {te} at target ({sd} on the fill day = {sd/max(te,1)*100:.0f}%), '
              f'{wo["bayes"]["friday_exits"]+wo["ou"]["friday_exits"]} forced at week close', flush=True)
    json.dump(out, open('/home/user/David-Fewer/premarket_study/weekly_params.json','w'), indent=1)
    print('\nDONE', flush=True)
