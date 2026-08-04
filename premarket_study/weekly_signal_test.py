"""
Does the weekly model need the Bayes or OU signal at all?

The deployed weekly rule sets its bid at

    bid = min( Monday open , ATH x (1 - cap) )

which is the daily model's bid with the signal term deleted. The daily rule is

    bid = min( fair - k x sigma , open , ATH x (1 - cap) )

so the honest question is not "mean reversion versus Bayes" but whether adding a signal term to
the weekly bid earns anything. Five variants are fitted and scored on identical footing:

    MR          bid = min(open, ATH cap)                        2 parameters
    Bayes       bid = min(Kalman fair - k sigma, open, ATH cap)  6
    OU          bid = min(OU forecast - b sigma, open, ATH cap)  4
    Bayes-Fri   as Bayes, but exit at Friday's close if unfilled -- the original weekly design
    OU-Fri      as OU, with the same Friday exit

The first three carry an unfilled position into later weeks, as the deployed rule does; the last
two liquidate weekly. Splitting them separates the value of the SIGNAL from the value of the EXIT
DISCIPLINE, which the earlier weekly work confounded -- it changed both at once.

Identical throughout: one Monday-anchored tranche, whole capital, same commission and interest,
same holiday-safe week grouping, same verified same-day exits (1-minute NVDA, 5-minute AVGO),
same mark-to-market of any position open at the end, and the same search budget per parameter.
Scored on the full sample and on the half-sample split that decided the book.
"""
import copy, datetime, math, statistics, sys
from scipy.optimize import differential_evolution
from stop_sweep import load_book
from engine import Params, run_model
from weekly_anchor_test import group_weeks, wstats
from weekly_mr import P as MRP, verify_same_day
from five_min import make_checker as fm

DATA, PARAMS, _ = load_book()
COMM, INTEREST = 0.005, 0.0314
CUT = datetime.date(2025, 5, 23)

SPEC = {                       # name -> (bounds, keys)
    'MR':    ([(0.02, 0.20), (0.02, 0.20)], ['cap', 'prem']),
    'Bayes': ([(0.2, 1.6), (0.1, 1.0), (0.001, 0.1), (0.0, 3.0), (0.02, 0.20), (0.02, 0.20)],
              ['lam', 'phi_L', 'psi', 'k', 'cap', 'prem']),
    'OU':    ([(30, 150), (0.0, 2.5), (0.02, 0.20), (0.02, 0.20)],
              ['ou_W', 'ou_buf_k', 'cap', 'prem']),
}
SPEC['Bayes-Fri'] = SPEC['Bayes']
SPEC['OU-Fri'] = SPEC['OU']
PERT = (0.97, 1.03)


class Name:
    def __init__(self, stock):
        self.stock = stock
        self.S = DATA[stock]
        self.DTS, self.O, self.H, self.L, self.C = self.S
        self.check = (verify_same_day if stock == 'NVDA'
                      else fm(stock, self.DTS, self.O)[0])
        self.WS = [wstats(w, *self.S[1:]) for w in group_weeks(self.DTS, 0)]
        self.N = len(self.WS)
        self.k_cut = next(i for i, w in enumerate(self.WS)
                          if self.DTS[w['idxs'][0]] >= CUT)
        self._sig = {}

    def signals(self, kind, vec):
        """Per-session signal series, cached on the parameters that affect it."""
        key = (kind,) + tuple(round(x, 6) for x in vec)
        if key in self._sig: return self._sig[key]
        p = copy.copy(PARAMS[self.stock])
        if kind == 'Bayes':
            p.lam, p.phi_L, p.psi = vec[0], vec[1], vec[2]
        else:
            p.ou_W = int(round(vec[0]))
        fr = run_model(*self.S, p, collect=True).frames
        out = ([fr['Lvl'][i] + fr['Slp'][i] for i in range(len(self.C))], fr['W']) \
            if kind == 'Bayes' else (fr['OUf'], fr['OUsig'])
        if len(self._sig) > 200: self._sig.clear()
        self._sig[key] = out
        return out


def simulate(nm, variant, v, w0, w1):
    """One Monday tranche over weeks [w0,w1]; returns (return, trades)."""
    keys = SPEC[variant][1]
    p = dict(zip(keys, v))
    fri = variant.endswith('-Fri')
    base = variant.split('-')[0]
    if base == 'Bayes':
        fair, sig = nm.signals('Bayes', v[:3]); mult = p['k']
    elif base == 'OU':
        fair, sig = nm.signals('OU', v[:1]); mult = p['ou_buf_k']
    else:
        fair = sig = None

    DTS, O, H, L, C, WS = nm.DTS, nm.O, nm.H, nm.L, nm.C, nm.WS
    fund, shares, holding = 1.0, 0.0, False
    buy = tgt = None; trades = 0
    ath = max(H[i] for i in WS[w0]['idxs'])
    for wi in range(w0 + 1, min(w1, nm.N - 1) + 1):
        prev, cwk = WS[wi-1], WS[wi]
        ath = max(ath, prev['h'])
        if not holding:
            fund += fund*INTEREST*(DTS[cwk['idxs'][-1]] - DTS[prev['idxs'][-1]]).days/365.0
            j = prev['idxs'][-1]                      # signal as at last session of prior week
            lo = cwk['o']
            if fair is not None:
                s = fair[j]; g = sig[j]
                if s is None or g is None: continue
                lo = min(lo, s - mult*g)
            buy = min(lo, ath*(1 - p['cap']))
            tgt = buy + prev['c']*p['prem']
        idxs = cwk['idxs']
        if not holding:
            bd = next((k for k, i in enumerate(idxs) if L[i] <= buy), None)
            if bd is None: continue
            shares = fund/(buy + COMM); fund = 0.0; holding = True
            for k in range(bd, len(idxs)):
                i = idxs[k]
                if H[i] >= tgt:
                    if k == bd and nm.check(i, buy, tgt) is False: continue
                    fund = shares*(tgt - COMM); shares = 0.0; holding = False; trades += 1; break
        else:
            for i in idxs:
                if H[i] >= tgt:
                    fund = shares*(tgt - COMM); shares = 0.0; holding = False; trades += 1; break
        if fri and holding:                            # liquidate at the week's close
            fund = shares*(C[idxs[-1]] - COMM); shares = 0.0; holding = False; trades += 1
    last = WS[min(w1, nm.N-1)]['idxs'][-1]
    return fund + (shares*C[last] if holding else 0.0) - 1.0, trades


def ann(nm, r, w0, w1):
    y = (nm.DTS[nm.WS[min(w1, nm.N-1)]['idxs'][-1]] - nm.DTS[nm.WS[w0]['idxs'][0]]).days/365.25
    return (1+r)**(1/y) - 1 if r > -1 else -1.0


def fit(nm, variant, w0, w1, floor, budget=140):
    bounds = SPEC[variant][0]
    def one(v):
        r, t = simulate(nm, variant, v, w0, w1)
        return -5.0 + t*1e-3 if t < floor else r
    def robust(v):
        base = one(v); sm = []
        for i in range(len(bounds)):
            for f in PERT:
                u = list(v); u[i] = min(max(u[i]*f, bounds[i][0]), bounds[i][1]); sm.append(one(u))
        return 0.5*base + 0.5*sum(sm)/len(sm)
    it = max(6, budget//len(bounds))                   # same evaluations per parameter
    res = differential_evolution(lambda v: -robust(v), bounds, init='sobol', seed=7,
                                 maxiter=it, popsize=10, mutation=(0.5, 1.0),
                                 recombination=0.7, tol=1e-4, polish=True, disp=False,
                                 updating='immediate', workers=1)
    return list(res.x)


if __name__ == '__main__':
    for stock in (sys.argv[1:] or ['NVDA', 'AVGO']):
        nm = Name(stock)
        N, kc = nm.N, nm.k_cut
        print(f'\n{"="*84}\n{stock}: {N} weeks, split at week {kc} ({CUT})', flush=True)
        _, t_mr = simulate(nm, 'MR', [MRP['cap'], MRP['prem']], 1, N-1)
        floor = max(8, int(0.35*t_mr))
        print(f'deployed MR parameters: {t_mr} trades; floor {floor}\n', flush=True)
        print(f'{"variant":12s}{"full sample":>13s}{"trades":>8s}{"1st half":>11s}'
              f'{"tested half":>13s}{"fitted parameters":>20s}', flush=True)
        print('-'*84, flush=True)
        for variant in ('MR', 'Bayes', 'OU', 'Bayes-Fri', 'OU-Fri'):
            v = fit(nm, variant, 1, N-1, floor)
            r, t = simulate(nm, variant, v, 1, N-1)
            a, _ = simulate(nm, variant, v, 1, kc-1)
            b, _ = simulate(nm, variant, v, kc, N-1)
            ps = '  '.join(f'{k}={x:.3g}' for k, x in zip(SPEC[variant][1], v))
            print(f'{variant:12s}{ann(nm,r,1,N-1)*100:>12.1f}%{t:>8d}'
                  f'{ann(nm,a,1,kc-1)*100:>10.1f}%{ann(nm,b,kc,N-1)*100:>12.1f}%', flush=True)
            print(f'{"":12s}{ps}', flush=True)
        print('\ndeployed MR (workbook parameters, for reference):', flush=True)
        v = [MRP['cap'], MRP['prem']]
        r, t = simulate(nm, 'MR', v, 1, N-1)
        a, _ = simulate(nm, 'MR', v, 1, kc-1); b, _ = simulate(nm, 'MR', v, kc, N-1)
        print(f'{"MR deployed":12s}{ann(nm,r,1,N-1)*100:>12.1f}%{t:>8d}'
              f'{ann(nm,a,1,kc-1)*100:>10.1f}%{ann(nm,b,kc,N-1)*100:>12.1f}%', flush=True)
    print('\nDONE', flush=True)
