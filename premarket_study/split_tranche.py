"""
Split each sleeve into N half-size (or N-th size) slots that can hold positions concurrently.

Why. A sleeve holds at most one position, so every buy signal arriving while it is full is
simply lost: 74 such blocked entries a year on NVDA, 80 on AVGO, against 42 and 65 buys
actually made. That is an ENTRY-side constraint and no exit rule can reach it. Splitting the
sleeve gives it somewhere to put the second signal.

The rule that makes this a real change rather than a relabelling
----------------------------------------------------------------
Two slots posting the same bid on the same morning is one full-size order written on two
tickets -- identical fills, identical P&L. The split only means anything if the slots fill on
DIFFERENT days. So: at most one slot fills per sleeve per session, taken by the lowest-indexed
free slot. Slot 1 therefore behaves like today's sleeve at 1/N size, and slots 2..N exist
solely to catch the entries slot 1 was too full to take. The result decomposes cleanly:

    N-slot sleeve  =  (1/N) x today's strategy  +  (1/N) x the blocked-entry strategy

so the test is really "are the trades we are currently missing worth taking?"

Capital
-------
Two treatments, because they answer different questions and the standing finding is that
rebalancing between independently-compounding pots is what produced an earlier false result:

  'split'  each slot owns a fixed 1/N of the sleeve's capital and compounds independently
           forever. No rebalancing. This is the honest analogue of how sleeves are treated.
  'pool'   slots draw from one cash pool, each buy deploying pool/(free slots) -- which is what
           the live Allocation sheet's free-sleeve renormalisation actually does. Reported as a
           sensitivity, not as the headline.

Everything else -- Kalman bids, OU bids, premium, peak caps, 50-day stop, commission, interest,
fill verification -- is untouched and taken straight from the validated engine. With n_slots=1
and treatment='split' this module reproduces engine.run_model to the penny; test_split_tranche
asserts it.
"""
import math

from engine import Params, run_model


def _bids(dates, O, H, L, C, p, ou_sigma):
    """Kalman and OU bid series. Neither depends on tranche accounting, so they can be lifted
    out of a single engine run and reused for any slot configuration."""
    r = run_model(dates, O, H, L, C, p, ou_sigma=ou_sigma, collect=True)
    f = r.frames
    return f['X'], f['AM'], f['t1']['AO'], f['t1']['AN']


def run_sleeve(dates, O, H, L, C, bid, prem, total_fund, n_slots, p,
               same_day_exit, AO, AN, interest_start, treatment='split'):
    """One sleeve, N concurrent slots. Mirrors engine.run_tranche per slot."""
    N = len(O)
    S = range(n_slots)
    Y = [[0.0] * N for _ in S]      # fund held by the slot (cash)
    AA = [[0.0] * N for _ in S]     # shares
    AB = [[0.0] * N for _ in S]     # target
    AC = [[None] * N for _ in S]    # actual sale
    AD = [[0] * N for _ in S]       # sell flag
    AE = [[0] * N for _ in S]       # hold flag
    Z = [[0] * N for _ in S]        # buy flag
    AV = [[None] * N for _ in S]    # buy date
    AP = [[0.0] * N for _ in S]
    AQ = [[0.0] * N for _ in S]

    if treatment != 'split':
        raise ValueError("run_sleeve implements 'split'; use run_sleeve_pool for 'pool'")
    for s in S:
        Y[s][0] = total_fund / n_slots

    for i in range(1, N):
        # --- 1. carry cash forward and accrue interest, per slot ---------------------
        for s in S:
            prev_cash = (AA[s][i - 1] * (AC[s][i - 1] - p.comm)) if AD[s][i - 1] == 1 else Y[s][i - 1]
            accrue = (prev_cash * p.interest * AN[i] / 365.0
                      if (AE[s][i - 1] == 0 and i >= interest_start) else 0.0)
            AP[s][i] = (0.0 if AQ[s][i - 1] > 0 else AP[s][i - 1]) + accrue
            AQ[s][i] = AP[s][i] if (AO[i] == 1 and AE[s][i - 1] == 0) else 0.0
            Y[s][i] = prev_cash + AQ[s][i]

        # --- 2. arbitrate today's entry: one fill per sleeve, lowest free slot -------
        bp = bid[i]
        buyer = None
        if bp is not None and L[i] <= bp:
            for s in S:
                if AE[s][i - 1] == 0:
                    buyer = s
                    break

        # --- 3. per-slot accounting --------------------------------------------------
        for s in S:
            Z[s][i] = 1 if s == buyer else 0
            if Z[s][i] == 1:
                AA[s][i] = Y[s][i] / (bp + p.comm)
                AB[s][i] = bp + C[i - 1] * prem
                AV[s][i] = dates[i]
            elif AE[s][i - 1] == 1:
                AA[s][i] = AA[s][i - 1]
                AB[s][i] = AB[s][i - 1]
                AV[s][i] = AV[s][i - 1]
            else:
                AA[s][i] = 0.0
                AB[s][i] = 0.0
                AV[s][i] = None

            held_stop = (AE[s][i - 1] == 1 and AV[s][i - 1] is not None
                         and (dates[i] - AV[s][i - 1]).days >= p.stop_days)
            if same_day_exit == 'at_open':
                sd_ok = (Z[s][i] == 1 and bp >= O[i] - 1e-9)
            elif callable(same_day_exit):
                sd_ok = (Z[s][i] == 1 and same_day_exit(i, bp, AB[s][i]))
            else:
                sd_ok = (Z[s][i] == 1 and same_day_exit)
            tgt_ok = (AE[s][i - 1] == 1) or sd_ok
            AD[s][i] = 1 if ((tgt_ok and H[i] >= AB[s][i]) or held_stop) else 0
            AC[s][i] = (O[i] if (held_stop and H[i] < AB[s][i]) else AB[s][i]) if AD[s][i] == 1 else None
            if AE[s][i - 1] == 1:
                AE[s][i] = 0 if AD[s][i] == 1 else 1
            else:
                AE[s][i] = 1 if (Z[s][i] == 1 and AD[s][i] == 0) else 0
            if AD[s][i] == 1:
                AV[s][i] = None

    # Terminal cash uses the workbook's own convention: the fund column at the last row, which
    # does NOT settle a sale occurring ON that row (the sheet would book it one row further
    # down, and there is no such row). Mirrored deliberately so the split is compared against
    # the baseline on identical terms.
    term = sum(Y[s][N - 1] for s in S)
    equity = [0.0] * N
    for i in range(N):
        equity[i] = sum((AA[s][i] * C[i]) if AE[s][i] == 1 else Y[s][i] for s in S)
    buys = sum(sum(Z[s]) for s in S)
    stops = sum(1 for s in S for i in range(N)
                if AD[s][i] == 1 and AC[s][i] is not None and AC[s][i] < AB[s][i] - 1e-9)
    return dict(Y=Y, AA=AA, AB=AB, AC=AC, AD=AD, AE=AE, Z=Z, equity=equity,
                terminal=term, buys=buys, stops=stops, n_slots=n_slots)


def run_sleeve_pool(dates, O, H, L, C, bid, prem, total_fund, n_slots, p,
                    same_day_exit, AO, AN, interest_start):
    """Shared-cash variant: one cash account, each buy deploying cash/(free slots).

    A per-slot fund column cannot express this -- the sheet's fund->shares->fund cycle assumes
    nothing is left over -- so the pool is carried as a single account with per-slot share
    lots. Sales settle with the engine's one-day lag: proceeds of a sale flagged on row i-1
    are available to buy on row i, never on the day of the sale itself.
    """
    N = len(O)
    S = range(n_slots)
    cash = total_fund
    pot = 0.0
    shares = [0.0] * n_slots
    cost = [0.0] * n_slots          # cash deployed, so terminal can mirror the engine
    target = [0.0] * n_slots
    buydate = [None] * n_slots
    AE = [[0] * N for _ in S]
    Zc = 0
    stops = 0
    equity = [0.0] * N
    equity[0] = total_fund
    sold_last = []                  # (slot, proceeds) flagged on the previous row

    for i in range(1, N):
        for s, proceeds in sold_last:
            cash += proceeds
            cost[s] = 0.0
        sold_last = []

        if i >= interest_start and cash > 0:
            pot += cash * p.interest * AN[i] / 365.0
        if AO[i] == 1 and cash > 0 and pot > 0:
            cash += pot
            pot = 0.0

        bp = bid[i]
        free = [s for s in S if AE[s][i - 1] == 0]
        if bp is not None and L[i] <= bp and free and cash > 0:
            s = free[0]
            deploy = cash / len(free)
            cash -= deploy
            shares[s] = deploy / (bp + p.comm)
            cost[s] = deploy
            target[s] = bp + C[i - 1] * prem
            buydate[s] = dates[i]
            AE[s][i] = 1
            Zc += 1
            bought = s
        else:
            bought = None

        for s in S:
            if AE[s][i - 1] == 0 and s != bought:
                AE[s][i] = 0
                continue
            if s != bought:
                AE[s][i] = 1
            held_stop = (AE[s][i - 1] == 1 and buydate[s] is not None
                         and (dates[i] - buydate[s]).days >= p.stop_days)
            if same_day_exit == 'at_open':
                sd_ok = (s == bought and bp >= O[i] - 1e-9)
            elif callable(same_day_exit):
                sd_ok = (s == bought and same_day_exit(i, bp, target[s]))
            else:
                sd_ok = (s == bought and same_day_exit)
            tgt_ok = (AE[s][i - 1] == 1) or sd_ok
            if (tgt_ok and H[i] >= target[s]) or held_stop:
                px = O[i] if (held_stop and H[i] < target[s]) else target[s]
                if px < target[s] - 1e-9:
                    stops += 1
                sold_last.append((s, shares[s] * (px - p.comm)))
                shares[s] = 0.0
                buydate[s] = None
                AE[s][i] = 0

        # proceeds flagged today settle tomorrow, but they are still the sleeve's money today:
        # omitting them puts a spurious hole in the curve on every sale day.
        equity[i] = cash + sum(shares[s] * C[i] for s in S) + sum(pr for _s, pr in sold_last)

    # cost[s] is cleared only when a sale SETTLES, so an unsettled position -- whether still
    # open or sold on the final row -- is still carried at cost. That is exactly what the
    # engine's fund column does, including its habit of valuing open positions at cost.
    terminal = cash + sum(cost)
    return dict(AE=AE, equity=equity, terminal=terminal, buys=Zc, stops=stops, n_slots=n_slots)


def run_split(dates, O, H, L, C, p: Params, n_slots=2, ou_sigma='level',
              same_day_exit=True, treatment='split'):
    """Both sleeves, each split into n_slots. Returns the same headline fields as engine."""
    X, AM, AO, AN = _bids(dates, O, H, L, C, p, ou_sigma)
    runner = run_sleeve if treatment == 'split' else run_sleeve_pool
    kw = dict(treatment=treatment) if treatment == 'split' else {}
    t1 = runner(dates, O, H, L, C, X, p.premium, p.capital * p.bayes_pct, n_slots, p,
                same_day_exit, AO, AN, 1, **kw)
    t2 = runner(dates, O, H, L, C, AM, p.ou_prem, p.capital * (1 - p.bayes_pct), n_slots, p,
                same_day_exit, AO, AN, 2, **kw)
    terminal = t1['terminal'] + t2['terminal']
    equity = [t1['equity'][i] + t2['equity'][i] for i in range(len(O))]
    profit = terminal - p.capital
    ann = (terminal / p.capital) ** (1 / p.years) - 1
    peak = -1e30
    maxdd = 0.0
    for e in equity:
        peak = max(peak, e)
        if peak > 0:
            maxdd = max(maxdd, (peak - e) / peak)
    rets = [equity[i] / equity[i - 1] - 1 for i in range(1, len(equity)) if equity[i - 1] > 0]
    if len(rets) > 1:
        mu = sum(rets) / len(rets)
        sd = math.sqrt(sum((x - mu) ** 2 for x in rets) / (len(rets) - 1))
        sharpe = (mu / sd * math.sqrt(252)) if sd > 0 else 0.0
    else:
        sharpe = 0.0
    return dict(terminal=terminal, profit=profit, annual_return=ann, equity=equity,
                total_buys=t1['buys'] + t2['buys'], bayes_buys=t1['buys'], ou_buys=t2['buys'],
                stops=t1['stops'] + t2['stops'], max_drawdown=maxdd, sharpe=sharpe,
                t1=t1, t2=t2, X=X, AM=AM)


def blocked(res, L):
    """Entries still lost with every slot full -- what a further split could yet recover."""
    n = 0
    for tr, bid in ((res['t1'], res['X']), (res['t2'], res['AM'])):
        S = range(tr['n_slots'])
        for i in range(1, len(L)):
            if bid[i] is not None and L[i] <= bid[i] and all(tr['AE'][s][i - 1] == 1 for s in S):
                n += 1
    return n
