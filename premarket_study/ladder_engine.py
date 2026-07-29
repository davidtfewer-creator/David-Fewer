"""
Laddered scale-in overlay on the validated engine. Each tranche, instead of one bid,
places R rungs at increasing σ-depths (equal budget each), builds a position over days
as deeper rungs fill, and exits the whole position at one blended take-profit (avg fill
+ prev_close·premium) or the 50-day stop. The Bayes/OU decorrelation is untouched — each
sleeve ladders around its OWN signal (Bayes fair / OU forecast) and its OWN sigma.

Signal series (fair, sigma, ATH, OU forecast/sigma) are taken from the validated
run_model so nothing about the model's learning changes — only the entry mechanic.
1-rung config reproduces the baseline (to within the daily-vs-monthly interest approx).
"""
import math
from engine import Params, run_model


def _tranche(dates, O, H, L, C, p, rung_fn, prem, pot0, first_valid, R, tp_mode='blended',
             weights=None):
    N = len(C)
    if weights is None:
        weights = [1.0 / R] * R
    fund = pot0
    shares = 0.0; cost_px = 0.0; filled = set(); incyc = False; bd = None
    anchor_px = 0.0                                 # shallowest (highest) filled rung price
    budgets = None; trades = 0
    equity = [0.0] * N; daily_trades = [0] * N
    for i in range(N):
        if i > 0:                                   # interest on idle cash
            fund += fund * p.interest * (dates[i] - dates[i-1]).days / 365.0
        rp = rung_fn(i) if i >= first_valid else None
        if rp is not None:
            if not incyc:                           # snapshot pot at cycle start
                budgets = [fund * w for w in weights]; filled = set(); anchor_px = 0.0
            for j, price in enumerate(rp):          # fill any rung the low reaches
                if j in filled or price is None or price <= 0:
                    continue
                bj = budgets[j]
                if L[i] <= price and fund >= bj - 1e-9 and bj > 0:
                    sh = bj / (price + p.comm)
                    shares += sh; cost_px += sh * price; fund -= bj
                    anchor_px = max(anchor_px, price)   # shallowest rung = highest fill price
                    filled.add(j); trades += 1; daily_trades[i] += 1
                    if not incyc:
                        incyc = True; bd = dates[i]
            if incyc and shares > 0:                # exit check (TP or 50-day stop)
                # 'blended': sell at avg cost + premium.  'first': sell all at the
                # shallowest rung's target (anchor + premium) so deep rungs book bigger margin.
                ref_px = anchor_px if tp_mode == 'first' else cost_px / shares
                target = ref_px + C[i-1] * prem
                held = (dates[i] - bd).days >= p.stop_days
                if H[i] >= target:
                    sell = target
                elif held:
                    sell = O[i]
                else:
                    sell = None
                if sell is not None:
                    fund += shares * (sell - p.comm)
                    shares = 0.0; cost_px = 0.0; filled = set(); incyc = False; bd = None
        equity[i] = fund + shares * C[i]
    return equity, trades, daily_trades


def run_ladder(dates, O, H, L, C, p: Params, mult_bayes, mult_ou, tp_mode='blended',
               w_bayes=None, w_ou=None):
    """mult_bayes / mult_ou: lists of sigma-multipliers (deeper = larger). [k] == baseline.
    tp_mode: 'blended' (sell at avg cost + premium) or 'first' (sell all at shallowest
    rung's target, so deeper rungs book a larger margin).
    w_bayes / w_ou: optional per-rung capital weights (sum to 1); default equal."""
    f = run_model(dates, O, H, L, C, p, collect=True).frames
    N = len(C)

    def bayes_rungs(i):
        if i < 1:
            return None
        ref = f['Lvl'][i-1] + f['Slp'][i-1]; sig = f['W'][i-1]
        peak = f['G'][i-1] * (1 - p.peak_cap)
        return [min(ref - m * sig, O[i], peak) for m in mult_bayes]

    def ou_rungs(i):
        r = f['OUf'][i]
        if r is None:
            return None
        sig = f['OUsig'][i]; peak = f['G'][i-1] * (1 - p.ou_cap)
        return [min(r - m * sig, O[i], peak) for m in mult_ou]

    first_ou = next((i for i in range(N) if f['OUf'][i] is not None), N)
    eqB, tB, dtB = _tranche(dates, O, H, L, C, p, bayes_rungs, p.premium,
                       p.capital * p.bayes_pct, 1, len(mult_bayes), tp_mode, w_bayes)
    eqO, tO, dtO = _tranche(dates, O, H, L, C, p, ou_rungs, p.ou_prem,
                       p.capital * (1 - p.bayes_pct), first_ou, len(mult_ou), tp_mode, w_ou)

    eq = [eqB[i] + eqO[i] for i in range(N)]
    ann = (eq[-1] / p.capital) ** (1 / p.years) - 1
    rets = [eq[i]/eq[i-1] - 1 for i in range(1, N) if eq[i-1] > 0]
    mu = sum(rets)/len(rets); sd = math.sqrt(sum((x-mu)**2 for x in rets)/(len(rets)-1))
    sharpe = mu/sd*math.sqrt(252) if sd > 0 else 0.0
    peak = -1e30; mdd = 0.0
    for e in eq:
        peak = max(peak, e); mdd = max(mdd, (peak-e)/peak if peak > 0 else 0)
    # Bayes-OU daily-return correlation (hedge check)
    rB = [eqB[i]/eqB[i-1]-1 for i in range(1, N) if eqB[i-1] > 0 and eqO[i-1] > 0]
    rO = [eqO[i]/eqO[i-1]-1 for i in range(1, N) if eqB[i-1] > 0 and eqO[i-1] > 0]
    mB, mO = sum(rB)/len(rB), sum(rO)/len(rO)
    cov = sum((rB[i]-mB)*(rO[i]-mO) for i in range(len(rB)))
    sB = math.sqrt(sum((x-mB)**2 for x in rB)); sO = math.sqrt(sum((x-mO)**2 for x in rO))
    corr = cov/(sB*sO) if sB > 0 and sO > 0 else 0.0

    return dict(annual=ann, sharpe=sharpe, maxdd=mdd, trades=tB+tO,
                bayes_trades=tB, ou_trades=tO, corr=corr, equity=eq, terminal=eq[-1],
                daily_trades=[dtB[i] + dtO[i] for i in range(N)])
