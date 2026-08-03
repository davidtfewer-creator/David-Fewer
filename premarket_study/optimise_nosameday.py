"""
Experiment: re-optimise parameters AND take-profit premia under the HONEST constraint that
same-day exits are not allowed (same_day_exit=False). Hypothesis: the original fit was pulled
toward tight premia to farm same-day round trips; forbidding them should push premia WIDER,
cut trade volume, and lift the (realistic, no-same-day) return.

For each name compare three states:
  A  original params, same-day ALLOWED   (the published backtest)
  B  original params, NO same-day        (the floor with today's params)
  C  RE-OPTIMISED params, NO same-day    (what the model looks like built honestly)
and show how the premia / key params move from original -> C.
"""
import copy
from scipy.optimize import differential_evolution
from stop_sweep import load_book
from engine import Params, run_model

data, params, cached = load_book()
STOCKS = list(data)

NM     = ['lam','phi_L','psi','k','premium','peak_cap','ou_buf_k','ou_prem','ou_cap','ou_W']
BOUNDS = [(0.2,1.6),(0.1,1.0),(0.001,0.1),(0.3,3.0),(0.005,0.20),(0.002,0.07),
          (0.1,2.5),(0.008,0.20),(0.005,0.12),(30,150)]   # premia bounds widened for the test
PERT   = [0.97, 1.03]


def bvec(p): return [p.lam,p.phi_L,p.psi,p.k,p.premium,p.peak_cap,p.ou_buf_k,p.ou_prem,p.ou_cap,p.ou_W]

def mp(vec, t):
    return Params(lam=vec[0],phi_L=vec[1],psi=vec[2],k=vec[3],premium=vec[4],peak_cap=vec[5],
                  ou_buf_k=vec[6],ou_prem=vec[7],ou_cap=vec[8],ou_W=int(round(vec[9])),
                  comm=t.comm,capital=t.capital,interest=t.interest,stop_days=t.stop_days,
                  bayes_pct=t.bayes_pct,years=t.years)

def run_nosd(s, vec, t):
    dts,O,H,L,C = data[s]
    return run_model(dts,O,H,L,C, mp(vec,t), collect=False, same_day_exit=False)

def robust(s, vec, t, floor):
    def one(v):
        r = run_nosd(s, v, t)
        return -5.0 + r.total_buys*1e-3 if r.total_buys < floor else r.annual_return
    base = one(vec)
    sm = []
    for i in range(9):
        for f in PERT:
            v = list(vec); v[i] = min(max(v[i]*f, BOUNDS[i][0]), BOUNDS[i][1]); sm.append(one(v))
    return 0.5*base + 0.5*sum(sm)/len(sm)

def optimise(s, t, floor):
    neg = lambda v: -robust(s, v, t, floor)
    x0 = [min(max(v, BOUNDS[i][0]), BOUNDS[i][1]) for i, v in enumerate(bvec(t))]  # clamp seed
    res = differential_evolution(neg, BOUNDS, x0=x0, init='sobol', seed=42, maxiter=10,
                                 popsize=8, mutation=(0.5,1.0), recombination=0.7, tol=1e-3,
                                 polish=False, disp=False, updating='immediate', workers=1)
    return list(res.x)


if __name__ == '__main__':
    print(f'{"stock":6s}{"A opt-orig":>11s}{"B floor-orig":>13s}{"C reopt-nosd":>13s}'
          f'{"prem o->C":>16s}{"ouprem o->C":>16s}{"buys B->C":>11s}', flush=True)
    print('-'*86, flush=True)
    rows = []
    for s in STOCKS:
        p0 = params[s]; t = p0
        dts,O,H,L,C = data[s]
        A = run_model(dts,O,H,L,C,p0, same_day_exit=True).annual_return
        Br = run_model(dts,O,H,L,C,p0, same_day_exit=False)
        B = Br.annual_return; Bbuys = Br.total_buys
        floor = max(10, int(0.4*Bbuys))
        theta = optimise(s, t, floor)
        Cr = run_nosd(s, theta, t); C = Cr.annual_return
        pnew = mp(theta, t)
        rows.append((s, A, B, C, p0.premium, pnew.premium, p0.ou_prem, pnew.ou_prem,
                     Bbuys, Cr.total_buys, theta, p0))
        print(f'{s:6s}{A*100:>10.0f}%{B*100:>12.0f}%{C*100:>12.0f}%'
              f'{f"{p0.premium:.3f}->{pnew.premium:.3f}":>16s}'
              f'{f"{p0.ou_prem:.3f}->{pnew.ou_prem:.3f}":>16s}'
              f'{f"{Bbuys}->{Cr.total_buys}":>11s}', flush=True)

    print('\n=== param shifts (original -> reopt-no-same-day) ===', flush=True)
    for s,A,B,Cv,pmo,pmn,opo,opn,bb,cb,theta,p0 in rows:
        pn = mp(theta, p0)
        print(f'{s}: k {p0.k:.2f}->{pn.k:.2f}  prem {p0.premium:.3f}->{pn.premium:.3f}  '
              f'ou_bufk {p0.ou_buf_k:.2f}->{pn.ou_buf_k:.2f}  ou_prem {p0.ou_prem:.3f}->{pn.ou_prem:.3f}  '
              f'ou_W {p0.ou_W}->{pn.ou_W}', flush=True)
    # averages
    import statistics
    print(f'\navg premium {statistics.mean(r[4] for r in rows):.3f} -> {statistics.mean(r[5] for r in rows):.3f}; '
          f'avg ou_prem {statistics.mean(r[6] for r in rows):.3f} -> {statistics.mean(r[7] for r in rows):.3f}', flush=True)
    print(f'avg floor return  B {statistics.mean(r[2] for r in rows)*100:.0f}%  ->  C {statistics.mean(r[3] for r in rows)*100:.0f}%', flush=True)
    print('SUMMARY DONE', flush=True)
