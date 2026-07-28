"""
Fair-fight: re-optimise NVDA parameters for the ACTUAL-OPEN signal, then judge OOS.

Config: OU anchor = open; Bayes fair nudged toward open with free gain; execution =
correct limit mechanics (cap at actual open). Optimise all 11 params (10 model + gain)
to MAXIMISE annual return with a trade-count floor (profit + buys, per the §5 objective).

Reports (a) full-history in-sample max (the mirage) and (b) expanding-window walk-forward
vs the frozen close-signal baseline — the honest test of whether we're missing something.
"""
import numpy as np
from scipy.optimize import differential_evolution
from engine import Params, run_model
from experiment_nvda import load

NAMES  = ['lam','phi_L','psi','k','premium','peak_cap','ou_buf_k','ou_prem','ou_cap','ou_W','bayes_gain']
BASE   = [0.604475,0.320751,0.007398,1.140966,0.017306,0.019635,0.907335,0.024772,0.056198,51,0.0]
BOUNDS = [(0.2,1.5),(0.1,1.0),(0.001,0.05),(0.3,3.0),(0.005,0.05),(0.002,0.06),
          (0.3,2.5),(0.008,0.06),(0.01,0.12),(20,90),(0.0,1.0)]
PERTURB = [0.97, 1.03]

d = load('nvda_joined.csv')
DATES, O, H, L, C = d['dates'], d['O'], d['H'], d['L'], d['C']
OPEN = list(O)
N = len(C)


def make_params(v):
    return Params(lam=v[0], phi_L=v[1], psi=v[2], k=v[3], premium=v[4], peak_cap=v[5],
                  ou_buf_k=v[6], ou_prem=v[7], ou_cap=v[8], ou_W=int(round(v[9])))


def seg(equity, lo, hi):
    return -1.0 if equity[lo] <= 0 else equity[hi] / equity[lo] - 1.0


def run_open(vec, collect=True):
    return run_model(DATES, O, H, L, C, make_params(vec),
                     ou_anchor=OPEN, bayes_signal=OPEN, bayes_gain=vec[10], collect=collect)


def run_frozen():
    return run_model(DATES, O, H, L, C, Params(), collect=True)   # close signal, frozen params


def evalslice(vec, lo, hi):
    r = run_open(vec)
    z = r.frames['t1']['Z']; g = r.frames['t2']['Z']
    return seg(r.frames['equity'], lo, hi), sum(z[lo:hi+1]) + sum(g[lo:hi+1])


def robust(vec, lo, hi, min_buys):
    def one(v):
        ret, buys = evalslice(v, lo, hi)
        return (-5.0 + buys*0.001) if buys < min_buys else ret
    base = one(vec)
    samp = []
    for i in range(11):
        for f in PERTURB:
            v = list(vec); lo_b, hi_b = BOUNDS[i]
            v[i] = min(max(v[i]*f, lo_b), hi_b); samp.append(one(v))
    return 0.5*base + 0.5*(sum(samp)/len(samp))


def optimize(lo, hi, min_buys, maxiter=12, popsize=8, seed=42):
    res = differential_evolution(lambda v: -robust(v, lo, hi, min_buys), BOUNDS, x0=BASE,
        init='sobol', seed=seed, maxiter=maxiter, popsize=popsize, mutation=(0.5,1.0),
        recombination=0.7, tol=1e-4, polish=False, updating='immediate', workers=1)
    return res.x


if __name__ == '__main__':
    fr = run_frozen()
    print(f'NVDA fair-fight: re-optimise for the ACTUAL-OPEN signal   (N={N})\n')
    print(f'Frozen close-signal baseline (full history): '
          f'ann={fr.annual_return*100:.1f}%  buys={fr.total_buys}  Sharpe={fr.sharpe:.2f}\n')

    # (a) full-history in-sample optimise for the open signal
    _, base_buys = evalslice(BASE, 0, N-1)
    floor = max(20, int(0.6 * fr.total_buys))
    print(f'Optimising open-signal on FULL history (min buys floor={floor}) ...')
    theta = optimize(0, N-1, floor)
    ro = run_open(theta)
    print(f'  IN-SAMPLE open-signal optimum: ann={ro.annual_return*100:.1f}%  '
          f'buys={ro.total_buys}  Sharpe={ro.sharpe:.2f}  (gain={theta[10]:.2f}, W={int(round(theta[9]))})')
    print(f'  -> in-sample Δ vs frozen: {(ro.annual_return-fr.annual_return)*100:+.1f}pp\n')

    # (b) walk-forward OOS
    cuts = [int(N*f) for f in (0.5, 0.667, 0.833, 1.0)]
    folds = [(0, cuts[i]-1, cuts[i], cuts[i+1]-1) for i in range(3)]
    print('WALK-FORWARD (optimise open-signal on train, judge unseen test):')
    print(f'  {"fold":4s}{"test":>14s}{"frozen close":>15s}{"reopt open-sig":>17s}   winner')
    wins = 0
    for k,(trlo,trhi,telo,tehi) in enumerate(folds,1):
        _, bbuys = evalslice(BASE, trlo, trhi)
        fl = max(10, int(0.6*bbuys))
        th = optimize(trlo, trhi, fl)
        ftest = seg(fr.frames['equity'], telo, tehi)
        otest, obuys = evalslice(th, telo, tehi)
        win = 'reopt-open' if otest > ftest else 'frozen'
        wins += (otest > ftest)
        print(f'  {k:<4d}[{telo:>3d}:{tehi:<3d}]  {ftest*100:>13.1f}%  {otest*100:>13.1f}% (buys~{obuys:d})   {win}')
    print(f'\n  Re-optimised open-signal beats frozen close-signal OOS in {wins}/3 folds.')
