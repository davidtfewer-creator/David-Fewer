"""
Walk-forward of the BAYES-CONSTRAINED minute-verified optimisation for NVDA.

Three expanding folds. Each fold re-optimises all 10 params on the TRAIN window using
minute-VERIFIED fills, under the same constraints as the full-sample fit:
    * Bayes buys >= 25/yr (scaled to the train window)
    * total buys >= 80% of the original params' train count
then freezes them and scores the unseen TEST slice --- also on verified fills --- against the
original workbook params on that same slice.

The honest test of whether the deeper-bid / tighter-cap configuration generalises.
Speed: robustness perturbs only the four policy params (k, premium, ou_buf_k, ou_prem).
"""
import statistics
from scipy.optimize import differential_evolution
from stop_sweep import load_book
from engine import Params, run_model
from minute_engine import make_checker

data, params, cached = load_book()
dts, O, H, L, C = data['NVDA']
P0 = params['NVDA']
CHK, _ = make_checker(dts, O)
N = len(C)

BOUNDS = [(0.2,1.6),(0.1,1.0),(0.001,0.1),(0.3,3.0),(0.005,0.20),(0.002,0.07),
          (0.1,2.5),(0.008,0.20),(0.005,0.12),(30,150)]
POLICY = [3, 4, 6, 7]
PERT = [0.97, 1.03]
CUTS = (0.5, 0.667, 0.833, 1.0)
BAYES_PER_YR = 25


def bvec(p): return [p.lam,p.phi_L,p.psi,p.k,p.premium,p.peak_cap,p.ou_buf_k,p.ou_prem,p.ou_cap,p.ou_W]

def mp(v):
    return Params(lam=v[0],phi_L=v[1],psi=v[2],k=v[3],premium=v[4],peak_cap=v[5],ou_buf_k=v[6],
                  ou_prem=v[7],ou_cap=v[8],ou_W=int(round(v[9])),comm=P0.comm,capital=P0.capital,
                  interest=P0.interest,stop_days=P0.stop_days,bayes_pct=P0.bayes_pct,years=P0.years)

def frames(v):
    return run_model(dts, O, H, L, C, mp(v), collect=True, same_day_exit=CHK).frames

def seg(fr, lo, hi):
    """(segment return, bayes buys, total buys) over [lo,hi]."""
    eq = fr['equity']
    ret = eq[hi]/eq[lo]-1 if eq[lo] > 0 else -1.0
    b = sum(fr['t1']['Z'][lo:hi+1]); o = sum(fr['t2']['Z'][lo:hi+1])
    return ret, b, b + o

def yrs(lo, hi):
    return max((dts[hi] - dts[lo]).days / 365.25, 1e-6)

def robust(v, lo, hi, bfloor, tfloor):
    def one(x):
        r, b, t = seg(frames(x), lo, hi)
        if b < bfloor: return -5.0 + b*1e-3          # Bayes must stay active
        if t < tfloor: return -5.0 + t*1e-3
        return r
    base = one(v); sm = []
    for i in POLICY:
        for f in PERT:
            w = list(v); w[i] = min(max(w[i]*f, BOUNDS[i][0]), BOUNDS[i][1]); sm.append(one(w))
    return 0.5*base + 0.5*sum(sm)/len(sm)

def optimise(lo, hi, bfloor, tfloor):
    x0 = [min(max(v, BOUNDS[i][0]), BOUNDS[i][1]) for i, v in enumerate(bvec(P0))]
    res = differential_evolution(lambda v: -robust(v, lo, hi, bfloor, tfloor), BOUNDS, x0=x0,
                                 init='sobol', seed=42, maxiter=7, popsize=6, mutation=(0.5,1.0),
                                 recombination=0.7, tol=1e-3, polish=False, disp=False,
                                 updating='immediate', workers=1)
    return list(res.x)


if __name__ == '__main__':
    print('NVDA walk-forward, Bayes-constrained, MINUTE-VERIFIED fills', flush=True)
    print('(each fold re-optimises on train only, then scores the unseen slice)\n', flush=True)
    cuts = [int(N*f) for f in CUTS]
    of = frames(bvec(P0))
    print(f'{"fold":5s}{"train":>11s}{"test":>12s}{"reopt OOS":>11s}{"orig OOS":>10s}'
          f'{"reopt B/tot":>13s}{"winner":>8s}', flush=True)
    print('-'*72, flush=True)
    rs, os_, wins, thetas = [], [], 0, []
    for k in range(3):
        trlo, trhi = 0, cuts[k]
        telo, tehi = cuts[k], cuts[k+1]-1
        _, otr_b, otr_t = seg(of, trlo, trhi-1)
        bfloor = max(6, int(BAYES_PER_YR * yrs(trlo, trhi-1)))
        tfloor = max(10, int(0.8 * otr_t))
        th = optimise(trlo, trhi-1, bfloor, tfloor); thetas.append(th)
        rr, rb, rt = seg(frames(th), telo, tehi)
        oo, ob, ot = seg(of, telo, tehi)
        rs.append(rr); os_.append(oo); wins += (rr > oo)
        print(f'{k+1:<5d}[0:{trhi:<4d}] [{telo:>3d}:{tehi:<4d}]{rr*100:>10.1f}%{oo*100:>9.1f}%'
              f'{f"{rb}/{rt}":>13s}{("reopt" if rr>oo else "orig"):>8s}', flush=True)
    print('-'*72, flush=True)
    print(f'reopt beats original OOS in {wins}/3 folds', flush=True)
    print(f'mean OOS return: reopt {statistics.mean(rs)*100:.1f}%   original {statistics.mean(os_)*100:.1f}%',
          flush=True)
    print('\nper-fold fitted policy params:', flush=True)
    for i, th in enumerate(thetas, 1):
        p = mp(th)
        print(f'  fold {i}: k {p.k:.2f}  prem {p.premium:.4f}  peak_cap {p.peak_cap:.4f}  '
              f'ou_bufk {p.ou_buf_k:.2f}  ou_prem {p.ou_prem:.4f}  ou_W {p.ou_W}', flush=True)
    print(f'  original: k {P0.k:.2f}  prem {P0.premium:.4f}  peak_cap {P0.peak_cap:.4f}  '
          f'ou_bufk {P0.ou_buf_k:.2f}  ou_prem {P0.ou_prem:.4f}  ou_W {P0.ou_W}', flush=True)
    print('DONE', flush=True)
