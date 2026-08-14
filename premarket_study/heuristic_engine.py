"""
The pre-Bayesian fixed-parameter mean-reversion heuristic (maths doc §2), run the way the
Bayes and OU sleeves are run today: same tranche accounting, 50-day stop, commission,
monthly-credited idle interest, and the same same-day-fill discipline options.

Entry (daily bars, causal — everything from t-1):

    B_t = min( avg( a·(H_{t-1}+L_{t-1})/2 , w·C_{t-1} ) + ρ·log10(R_{t-1}),  O_t,  (1−c)·P_{t-1} )

with avg(x,y) = (x+y)/2 and R = H−L. Exit at B_t + π·C_{t-1}, carried until hit, 50-day stop
at the open. Five fixed parameters: w, a, ρ, π, c.

`run_bid` is the tranche accounting lifted verbatim from engine.run_model's run_tranche —
validated in heuristic_fixed.py by feeding it the engine's own Bayes bid array and requiring
penny-exact agreement — so any heuristic-vs-deployed difference is the bid rule, not the
bookkeeping. Note the ρ·log10(R) cushion is an absolute-dollar term: on a ~$10 name the
daily range straddles $1 so log10(R) crosses zero and the term changes sign — a scale
dependence the σ-scaled models don't have.
"""
from dataclasses import dataclass
import math

from engine import Result


@dataclass
class HeurParams:
    w: float = 0.98       # previous-close weighting            (old sheet F8)
    a: float = 0.98       # min/max average multiplier          (old sheet F12)
    rho: float = -2.0     # log-range multiplier, $ per decade  (old sheet F11)
    prem: float = 0.02    # sale premium, fraction of prev close (old sheet F10)
    cap: float = 0.03     # peak cap, fraction below running peak (old sheet F9)
    comm: float = 0.005
    capital: float = 1_000_000
    interest: float = 0.0314
    stop_days: int = 50


def heuristic_bid(O, H, L, C, p: HeurParams):
    N = len(O)
    G = [0.0] * N
    G[0] = H[0]
    for i in range(1, N):
        G[i] = max(H[i], G[i - 1])
    B = [None] * N
    for i in range(1, N):
        anchor = 0.5 * (p.a * 0.5 * (H[i - 1] + L[i - 1]) + p.w * C[i - 1])
        cushion = p.rho * math.log10(max(H[i - 1] - L[i - 1], 1e-2))
        B[i] = min(anchor + cushion, O[i], G[i - 1] * (1 - p.cap))
    return B


def run_bid(dates, O, H, L, C, buy_price, prem, p, same_day_exit=True,
            init_fund=None, interest_start=1) -> Result:
    """Single tranche driven by an arbitrary bid array. Accounting copied from engine.py."""
    N = len(O)
    AO = [0] * N
    for i in range(N):
        if i == N - 1 or dates[i].month != dates[i + 1].month:
            AO[i] = 1
    AN = [1] + [(dates[i] - dates[i - 1]).days for i in range(1, N)]

    buy_px = None
    Y = [0.0] * N; AA = [0.0] * N; AB = [0.0] * N
    AD = [0] * N; AE = [0] * N; Z = [0] * N
    AC = [None] * N; AV = [None] * N
    AP = [0.0] * N; AQ = [0.0] * N
    Y[0] = p.capital if init_fund is None else init_fund
    for i in range(1, N):
        basis = (AA[i - 1] * (AC[i - 1] - p.comm)) if AD[i - 1] == 1 else Y[i - 1]
        accrue = (basis * p.interest * AN[i] / 365.0
                  if (AE[i - 1] == 0 and i >= interest_start) else 0.0)
        AP[i] = (0.0 if AQ[i - 1] > 0 else AP[i - 1]) + accrue
        AQ[i] = AP[i] if (AO[i] == 1 and AE[i - 1] == 0) else 0.0
        Y[i] = ((AA[i - 1] * (AC[i - 1] - p.comm)) if AD[i - 1] == 1 else Y[i - 1]) + AQ[i]
        bp = buy_price[i]
        Z[i] = 1 if (AE[i - 1] == 0 and bp is not None and L[i] <= bp) else 0
        AA[i] = (Y[i] / (bp + p.comm)) if Z[i] == 1 else (AA[i - 1] if AE[i - 1] == 1 else 0.0)
        if Z[i] == 1:
            buy_px = bp
            AB[i] = bp + C[i - 1] * prem
        elif AE[i - 1] == 1:
            AB[i] = AB[i - 1]
        else:
            AB[i] = 0.0
        held = AE[i - 1] == 1 and AV[i - 1] is not None and (dates[i] - AV[i - 1]).days >= p.stop_days
        if same_day_exit == 'at_open':
            sd_ok = (Z[i] == 1 and bp is not None and bp >= O[i] - 1e-9)
        elif callable(same_day_exit):
            sd_ok = (Z[i] == 1 and bp is not None and same_day_exit(i, bp, AB[i]))
        else:
            sd_ok = (Z[i] == 1 and same_day_exit)
        tgt_ok = (AE[i - 1] == 1) or sd_ok
        AD[i] = 1 if ((tgt_ok and H[i] >= AB[i]) or held) else 0
        if AD[i] == 1:
            AC[i] = O[i] if (held and H[i] < AB[i]) else AB[i]
        else:
            AC[i] = None
        if AE[i - 1] == 1:
            AE[i] = 0 if AD[i] == 1 else 1
        else:
            AE[i] = 1 if (Z[i] == 1 and AD[i] == 0) else 0
        AV[i] = dates[i] if Z[i] == 1 else (AV[i - 1] if AE[i - 1] == 1 else None)
    stops = sum(1 for i in range(N) if AD[i] == 1 and AC[i] is not None and AC[i] < AB[i])

    equity = [0.0] * N
    for i in range(N):
        equity[i] = AA[i] * C[i] if AE[i] == 1 else Y[i]
    rets = [equity[i] / equity[i - 1] - 1 for i in range(1, N) if equity[i - 1] > 0]
    if len(rets) > 1:
        mu = sum(rets) / len(rets)
        var = sum((x - mu) ** 2 for x in rets) / (len(rets) - 1)
        sd = math.sqrt(var)
        sharpe = (mu / sd * math.sqrt(252)) if sd > 0 else 0.0
    else:
        sharpe = 0.0
    peak = -1e30; maxdd = 0.0
    for e in equity:
        peak = max(peak, e)
        if peak > 0:
            maxdd = max(maxdd, (peak - e) / peak)

    cap0 = Y[0]
    terminal = Y[-1] if AE[-1] == 0 else equity[-1]
    yrs = max((dates[-1] - dates[0]).days, 1) / 365.25
    ann = (terminal / cap0) ** (1 / yrs) - 1 if cap0 > 0 else 0.0
    frames = dict(Y=Y, Z=Z, AE=AE, AD=AD, AB=AB, AC=AC, equity=equity, stops=stops)
    return Result(terminal, terminal - cap0, ann, sum(Z), sum(Z), 0, stops,
                  Y[-1], 0.0, sharpe, maxdd, frames)


def run_heuristic(dates, O, H, L, C, p: HeurParams, same_day_exit=True) -> Result:
    B = heuristic_bid(O, H, L, C, p)
    return run_bid(dates, O, H, L, C, B, p.prem, p, same_day_exit=same_day_exit)
