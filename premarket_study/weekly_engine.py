"""
WEEKLY variant of the harvester.

Cycle: on the first session of each week set a limit bid from the signal as at the prior week's
close. The order rests through the week. If it fills, a target sell (bid + prior-week close x
premium) rests until hit; if the target is not reached by the week's end, exit at the final
close. Capital is then free for the next Monday. No 50-day stop is needed -- the week is the stop.

Signals (Kalman fair value / sigma, OU forecast / sigma, running ATH) are taken from the
validated daily engine so they are identical to the deployed model.

Structural advantage: only a Monday fill + Monday target is same-day ambiguous. Exits on
Tue-Fri are provable from daily bars, so the weekly model is far less exposed to the fill-rate
problem that halves the daily model's returns.
"""
from dataclasses import dataclass
from engine import Params, run_model
import math, statistics


def week_groups(dates):
    """Contiguous index groups, one per ISO week."""
    groups, cur = [], [0]
    for i in range(1, len(dates)):
        if dates[i].isocalendar()[:2] != dates[i-1].isocalendar()[:2]:
            groups.append(cur); cur = []
        cur.append(i)
    if cur:
        groups.append(cur)
    return groups


def run_weekly(dates, O, H, L, C, p: Params, same_day_exit=True, checker=None, collect=False):
    """Returns dict with terminal equity, annual return, trades, sharpe, maxdd per tranche+combined."""
    fr = run_model(dates, O, H, L, C, p, collect=True).frames
    Lvl, Slp, W, G = fr['Lvl'], fr['Slp'], fr['W'], fr['G']
    OUf, OUsig = fr['OUf'], fr['OUsig']
    N = len(C)
    groups = [g for g in week_groups(dates) if g and g[0] >= 1]

    def tranche(is_bayes, fund0):
        fund = fund0
        equity = [fund0] * N
        trades = 0; fills = 0; target_exits = 0; friday_exits = 0; sameday_exits = [0]
        for g in groups:
            i0, iN = g[0], g[-1]
            s = i0 - 1                                  # signal as at prior week's close
            if is_bayes:
                fair = Lvl[s] + Slp[s]; sig = W[s]
                if sig <= 0:
                    for i in g: equity[i] = fund
                    continue
                bid = min(fair - p.k * sig, O[i0], G[s] * (1 - p.peak_cap))
                prem = p.premium
            else:
                if OUf[s] is None or OUsig[s] is None:
                    for i in g: equity[i] = fund
                    continue
                bid = min(OUf[s] - p.ou_buf_k * OUsig[s], O[i0], G[s] * (1 - p.ou_cap))
                prem = p.ou_prem
            if bid is None or bid <= 0:
                for i in g: equity[i] = fund
                continue
            target = bid + C[s] * prem

            # find fill: first session in the week whose low reaches the bid
            fill = None
            for i in g:
                if L[i] <= bid + 1e-12:
                    fill = i; break
            if fill is None:                            # no fill: cash earns interest for the week
                days = (dates[iN] - dates[i0]).days + 1
                fund += fund * p.interest * days / 365.0
                for i in g: equity[i] = fund
                continue

            fills += 1
            fund_before = fund
            shares = fund / (bid + p.comm)
            # exit: first session at/after the fill whose high reaches the target
            exit_i, exit_px = None, None
            for i in range(fill, iN + 1):
                if H[i] < target - 1e-12:
                    continue
                if i == fill:                           # fill-day exit: the ambiguous case
                    if same_day_exit is False:
                        continue
                    if callable(checker) and not checker(i, bid, target):
                        continue
                same_day = (i == fill)
                exit_i, exit_px = i, target; break
            if exit_i is None:                          # forced exit at the week's final close
                exit_i, exit_px = iN, C[iN]
                friday_exits += 1
                same_day = False
            else:
                target_exits += 1
                if exit_i == fill:
                    sameday_exits[0] += 1
            fund = shares * (exit_px - p.comm)
            trades += 1
            for i in g:                                 # mark the equity curve through the week
                if i < fill:
                    equity[i] = fund_before
                elif i <= exit_i:
                    equity[i] = shares * C[i]
                else:
                    equity[i] = fund
        return fund, equity, dict(trades=trades, fills=fills, target_exits=target_exits,
                                  friday_exits=friday_exits, sameday=sameday_exits[0])

    fb, eqb, sb = tranche(True,  p.capital * p.bayes_pct)
    fo, eqo, so = tranche(False, p.capital * (1 - p.bayes_pct))
    total = fb + fo
    yrs = (dates[-1] - dates[0]).days / 365.25
    ann = (total / p.capital) ** (1 / yrs) - 1 if total > 0 else -1
    eq = [eqb[i] + eqo[i] for i in range(N)]
    rets = [eq[i]/eq[i-1]-1 for i in range(1, N) if eq[i-1] > 0]
    sd = statistics.pstdev(rets) if len(rets) > 2 else 0
    sharpe = (statistics.mean(rets)/sd*math.sqrt(252)) if sd > 0 else 0
    peak = -1e30; mdd = 0
    for e in eq:
        peak = max(peak, e)
        if peak > 0: mdd = max(mdd, (peak-e)/peak)
    return dict(terminal=total, ann=ann, sharpe=sharpe, maxdd=mdd,
                bayes=sb, ou=so, trades=sb['trades']+so['trades'],
                weeks=len(groups), yrs=yrs, equity=eq)
