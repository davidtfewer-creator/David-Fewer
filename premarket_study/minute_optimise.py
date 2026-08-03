"""
Find the OPTIMAL position against minute-verified reality for NVDA.

(a) Premium frontier: sweep the Bayes/OU take-profit premia (other params fixed) and record the
    verified return and trade count -> the return-vs-turnover trade-off curve.
(b) Full re-optimisation of all 10 params against verified fills -> the genuine optimum.
Compare with the two artefacts: original params (fit on optimistic fills) and the no-same-day
wide-premium fit.
"""
import copy
from scipy.optimize import differential_evolution
from stop_sweep import load_book
from engine import Params, run_model
from minute_engine import make_checker

data, params, cached = load_book()
dts, O, H, L, C = data['NVDA']
P0 = params['NVDA']
CHK, IDX = make_checker(dts, O)
YRS = (dts[-1] - dts[0]).days / 365.25

BOUNDS = [(0.2,1.6),(0.1,1.0),(0.001,0.1),(0.3,3.0),(0.005,0.20),(0.002,0.07),
          (0.1,2.5),(0.008,0.20),(0.005,0.12),(30,150)]
PERT = [0.97, 1.03]


def bvec(p): return [p.lam,p.phi_L,p.psi,p.k,p.premium,p.peak_cap,p.ou_buf_k,p.ou_prem,p.ou_cap,p.ou_W]

def mp(v, t=P0):
    return Params(lam=v[0],phi_L=v[1],psi=v[2],k=v[3],premium=v[4],peak_cap=v[5],ou_buf_k=v[6],
                  ou_prem=v[7],ou_cap=v[8],ou_W=int(round(v[9])),comm=t.comm,capital=t.capital,
                  interest=t.interest,stop_days=t.stop_days,bayes_pct=t.bayes_pct,years=t.years)

def verified(p):
    return run_model(dts, O, H, L, C, p, same_day_exit=CHK)


if __name__ == '__main__':
    print('=== (a) PREMIUM FRONTIER (verified fills; other params at original) ===')
    print(f'{"premium":>9s}{"ou_prem":>9s}{"ann":>8s}{"buys":>7s}{"/yr":>6s}{"maxDD":>8s}{"Sharpe":>8s}')
    print('-' * 55)
    best = None
    for mult in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0):
        p = copy.copy(P0)
        p.premium = min(P0.premium * mult, 0.20)
        p.ou_prem = min(P0.ou_prem * mult, 0.20)
        r = verified(p)
        star = ''
        if best is None or r.annual_return > best[1]:
            best = (mult, r.annual_return, r.total_buys); star = ''
        print(f'{p.premium:>9.3f}{p.ou_prem:>9.3f}{r.annual_return*100:>7.0f}%{r.total_buys:>7d}'
              f'{r.total_buys/YRS:>6.0f}{r.max_drawdown*100:>7.0f}%{r.sharpe:>8.2f}{star}')
    print(f'\nbest premium multiple on this axis: {best[0]}x -> {best[1]*100:.0f}% ann, {best[2]} buys')

    print('\n=== (b) FULL RE-OPTIMISATION AGAINST VERIFIED FILLS ===', flush=True)
    def robust(v, floor):
        def one(x):
            r = verified(mp(x))
            return -5.0 + r.total_buys*1e-3 if r.total_buys < floor else r.annual_return
        base = one(v); sm = []
        for i in range(9):
            for f in PERT:
                w = list(v); w[i] = min(max(w[i]*f, BOUNDS[i][0]), BOUNDS[i][1]); sm.append(one(w))
        return 0.5*base + 0.5*sum(sm)/len(sm)

    base_buys = verified(P0).total_buys
    floor = max(40, int(0.8 * base_buys))          # keep turnover: >=80% of current verified buys
    x0 = [min(max(v, BOUNDS[i][0]), BOUNDS[i][1]) for i, v in enumerate(bvec(P0))]
    res = differential_evolution(lambda v: -robust(v, floor), BOUNDS, x0=x0, init='sobol', seed=42,
                                 maxiter=10, popsize=8, mutation=(0.5,1.0), recombination=0.7,
                                 tol=1e-3, polish=False, disp=False, updating='immediate', workers=1)
    pv = mp(list(res.x)); rv = verified(pv)
    print(f'trade floor imposed: >= {floor} buys (80% of current verified {base_buys})')
    print(f'  optimised verified: {rv.annual_return*100:.0f}% ann, {rv.total_buys} buys '
          f'({rv.total_buys/YRS:.0f}/yr), maxDD {rv.max_drawdown*100:.0f}%, Sharpe {rv.sharpe:.2f}')
    print(f'  params: k {P0.k:.2f}->{pv.k:.2f}  prem {P0.premium:.3f}->{pv.premium:.3f}  '
          f'ou_bufk {P0.ou_buf_k:.2f}->{pv.ou_buf_k:.2f}  ou_prem {P0.ou_prem:.3f}->{pv.ou_prem:.3f}  '
          f'ou_W {P0.ou_W}->{pv.ou_W}')

    print('\n=== COMPARISON (all on verified fills) ===')
    from optimise_nosameday import mp as mp2
    rows = [('original params', P0)]
    pw = copy.copy(P0); pw.premium = 0.120; pw.ou_prem = 0.133; pw.k = 0.81; pw.ou_buf_k = 0.76; pw.ou_W = 48
    rows.append(('no-same-day wide fit', pw))
    rows.append(('optimised on verified', pv))
    print(f'{"model":24s}{"ann":>8s}{"buys":>7s}{"/yr":>6s}{"Sharpe":>8s}')
    for nm, p in rows:
        r = verified(p)
        print(f'{nm:24s}{r.annual_return*100:>7.0f}%{r.total_buys:>7d}{r.total_buys/YRS:>6.0f}{r.sharpe:>8.2f}')
    print('DONE', flush=True)
