"""
Re-optimise NVDA against minute-VERIFIED fills, with the Bayes sleeve constrained to remain
active: >= 25 Bayes buys per year (the unconstrained optimum hollowed Bayes out to ~8/yr by
making it deep-and-patient and letting OU carry all the turnover).

Constraints in the objective:
  * Bayes buys >= 25/yr  (58 over the 2.31y sample)
  * total buys >= 80% of the current verified count
Logs ALL ten fitted parameters so the result is exactly reproducible.
"""
import copy, json
from scipy.optimize import differential_evolution
from stop_sweep import load_book
from engine import Params, run_model
from minute_engine import make_checker

data, params, cached = load_book()
dts, O, H, L, C = data['NVDA']
P0 = params['NVDA']
CHK, _ = make_checker(dts, O)
YRS = (dts[-1] - dts[0]).days / 365.25

NM = ['lam','phi_L','psi','k','premium','peak_cap','ou_buf_k','ou_prem','ou_cap','ou_W']
BOUNDS = [(0.2,1.6),(0.1,1.0),(0.001,0.1),(0.3,3.0),(0.005,0.20),(0.002,0.07),
          (0.1,2.5),(0.008,0.20),(0.005,0.12),(30,150)]
POLICY = [3, 4, 6, 7]
PERT = [0.97, 1.03]

BAYES_FLOOR = int(round(25 * YRS))            # >= 25 Bayes buys per year


def bvec(p): return [p.lam,p.phi_L,p.psi,p.k,p.premium,p.peak_cap,p.ou_buf_k,p.ou_prem,p.ou_cap,p.ou_W]

def mp(v):
    return Params(lam=v[0],phi_L=v[1],psi=v[2],k=v[3],premium=v[4],peak_cap=v[5],ou_buf_k=v[6],
                  ou_prem=v[7],ou_cap=v[8],ou_W=int(round(v[9])),comm=P0.comm,capital=P0.capital,
                  interest=P0.interest,stop_days=P0.stop_days,bayes_pct=P0.bayes_pct,years=P0.years)

def verified(p):
    return run_model(dts, O, H, L, C, p, same_day_exit=CHK)


def score(v, tot_floor):
    r = verified(mp(v))
    if r.bayes_buys < BAYES_FLOOR:                       # Bayes must stay active
        return -5.0 + r.bayes_buys * 1e-3
    if r.total_buys < tot_floor:
        return -5.0 + r.total_buys * 1e-3
    return r.annual_return

def robust(v, tot_floor):
    base = score(v, tot_floor); sm = []
    for i in POLICY:
        for f in PERT:
            w = list(v); w[i] = min(max(w[i]*f, BOUNDS[i][0]), BOUNDS[i][1])
            sm.append(score(w, tot_floor))
    return 0.5*base + 0.5*sum(sm)/len(sm)


if __name__ == '__main__':
    r0 = verified(P0)
    tot_floor = max(40, int(0.8 * r0.total_buys))
    print(f'NVDA verified-fill optimisation with Bayes floor', flush=True)
    print(f'  sample {YRS:.2f}y | Bayes floor {BAYES_FLOOR} buys (25/yr) | total floor {tot_floor}',
          flush=True)
    print(f'  baseline (original params): {r0.annual_return*100:.0f}% ann, '
          f'{r0.total_buys} buys = Bayes {r0.bayes_buys} + OU {r0.ou_buys}\n', flush=True)

    x0 = [min(max(v, BOUNDS[i][0]), BOUNDS[i][1]) for i, v in enumerate(bvec(P0))]
    res = differential_evolution(lambda v: -robust(v, tot_floor), BOUNDS, x0=x0, init='sobol',
                                 seed=42, maxiter=10, popsize=8, mutation=(0.5,1.0),
                                 recombination=0.7, tol=1e-3, polish=False, disp=False,
                                 updating='immediate', workers=1)
    theta = list(res.x); pv = mp(theta); rv = verified(pv)

    print('=== RESULT (Bayes-constrained, verified fills) ===', flush=True)
    print(f'  ann {rv.annual_return*100:.0f}%   Sharpe {rv.sharpe:.2f}   maxDD {rv.max_drawdown*100:.0f}%',
          flush=True)
    print(f'  buys {rv.total_buys} ({rv.total_buys/YRS:.0f}/yr) = '
          f'Bayes {rv.bayes_buys} ({rv.bayes_buys/YRS:.0f}/yr) + OU {rv.ou_buys} ({rv.ou_buys/YRS:.0f}/yr)',
          flush=True)
    print(f'  stops {rv.stop_loss_exits}', flush=True)
    print('\n=== FITTED PARAMS (all ten) ===', flush=True)
    for i, n in enumerate(NM):
        orig = bvec(P0)[i]
        val = int(round(theta[i])) if n == 'ou_W' else theta[i]
        print(f'  {n:9s} {orig:>8.4f} -> {val:>8.4f}' if n != 'ou_W'
              else f'  {n:9s} {int(orig):>8d} -> {val:>8d}', flush=True)
    json.dump({NM[i]: theta[i] for i in range(10)},
              open('/home/user/David-Fewer/premarket_study/nvda_verified_bayesfloor.json', 'w'), indent=1)

    print('\n=== COMPARISON (all on verified fills) ===', flush=True)
    unc = copy.copy(P0); unc.k=1.96; unc.premium=0.130; unc.ou_buf_k=0.26; unc.ou_prem=0.009; unc.ou_W=40
    print(f'{"model":30s}{"ann":>7s}{"tot/yr":>8s}{"Bayes/yr":>10s}{"OU/yr":>7s}{"Sharpe":>8s}', flush=True)
    for nm, p in (('original params', P0), ('unconstrained opt (approx)', unc), ('Bayes-floor opt', pv)):
        r = verified(p)
        print(f'{nm:30s}{r.annual_return*100:>6.0f}%{r.total_buys/YRS:>8.0f}{r.bayes_buys/YRS:>10.0f}'
              f'{r.ou_buys/YRS:>7.0f}{r.sharpe:>8.2f}', flush=True)
    print('DONE', flush=True)
