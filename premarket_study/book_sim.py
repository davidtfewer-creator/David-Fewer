"""
The book simulator: the eight-name book as it actually trades.

Every backtest before this one used the HELD construction -- each sleeve owns a
fixed slice of capital and compounds alone. The live workbook does something
different: each morning Allocation!C25:C40 pools the cash on hand and divides it
across whichever of the sixteen sleeves are FREE (not holding). A sleeve blocked
from bidding (an earnings pause, the ATH guard) therefore doesn't idle -- its
capital thickens every other free sleeve's order the same morning. This simulator
replicates that loop so structural rules can be scored on the basis that matters.

Mechanics per session, in order:
  morning   pool = cash on hand. Each free sleeve with a live bid gets
            pool * w / sum(w over free-with-bid sleeves); equal weights here, so
            pool / n_free. (Sleeves whose bid is suppressed that day get nothing
            and their weight renormalises over the rest -- the user's point.)
  fills     a sleeve fills if the day's low reaches its bid; shares are
            fractional (engine convention), cost = shares * (bid + comm).
            Same-day exit only where the 5-minute checker proves the order of
            low and high (verified fills).
  exits     held sleeves: target hit (sell at target) else 50-calendar-day stop
            (sell at the open). Proceeds land in the pool, usable next morning.
  evening   interest at 3.14%/yr accrues on the cash balance.

Bids and targets come from the engine's own per-name series (X for Bayes, AM for
OU; target = bid + prevclose * premium), so every model detail -- residual sigma,
the ATH guard, pause days -- is inherited by passing the corresponding engine
options through.

VALIDATION: mode='captive' pins each sleeve to its own fixed slice (no pooling).
Captive results must track the engine's held construction closely (small drift
from interest conventions is expected and reported) before pooled numbers are
trusted.
"""
import datetime

from engine import run_model
from fresh_opt import SPLIT, annualise
from fresh_opt_cands import daily_from_5min, ref_params
from live5_load import load as load_book, STOCKS as BOOK
from minute_index import make_checker

NAMES = BOOK + ['GM', 'VLO', 'CF']
COMM = 0.005
INTEREST = 0.0314
STOP_DAYS = 50


def load_all(engine_kwargs_per_name=None, names=None, params_override=None):
    """Per-name data, params, engine bid series, checkers -- on a common calendar.
    names: book composition override; params_override: dict name -> Params for
    names outside the standard REF table (e.g. candidate reference vectors)."""
    book_data, book_params, _ = load_book()
    ek = engine_kwargs_per_name or {}
    po = params_override or {}
    data, sleeves = {}, []
    common = None
    for s in (names or NAMES):
        if s in BOOK:
            dts, O, H, L, C = book_data[s]
            p = book_params[s]
        else:
            dts, O, H, L, C = daily_from_5min(s)
            p = po.get(s) or ref_params(s)
        data[s] = dict(dts=dts, O=O, H=H, L=L, C=C, p=p,
                       idx={d: i for i, d in enumerate(dts)},
                       chk=make_checker(s, dts, O))
        r = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=True,
                      collect=True, **ek.get(s, {}))
        data[s]['X'] = r.frames['X']
        data[s]['AM'] = r.frames['AM']
        common = set(dts) if common is None else (common & set(dts))
    cal = sorted(common)
    for s in (names or NAMES):
        p = data[s]['p']
        sleeves.append(dict(name=s, kind='B', bids='X', prem=p.premium))
        sleeves.append(dict(name=s, kind='O', bids='AM', prem=p.ou_prem))
    return data, sleeves, cal


def simulate(data, sleeves, cal, capital=8_000_000, mode='pooled',
             no_buy=None, collect_trades=False, weights=None, cap_frac=None,
             date_lo=None, date_hi=None, breaker=None, price_stop=None):
    """no_buy: dict name -> set of dates with entries suppressed (both sleeves).
    weights: dict name -> relative weight (renormalised over the sleeves free each
    morning; equal when None). cap_frac: max fraction of the pool one sleeve may
    take in a morning (None = uncapped, the deployed behaviour). date_lo/date_hi
    restrict the simulated window (policy fitting on one half).
    breaker: (trip, reset, frac) book-level circuit breaker, pooled mode only:
    when yesterday's book equity sits more than `trip` below its running peak,
    every morning allocation is multiplied by `frac` (0 = no new entries; resting
    exits and stops run unchanged) until the drawdown recovers above `reset`.
    Decided each morning on yesterday's close equity -- strictly ex ante.
    price_stop: float fraction -- exit a held position at entry_bid*(1-frac) when
    the day's low reaches it before target or time stop (fill at the level, at the
    open on a gap through; pessimistic on target ties)."""
    if date_lo is not None or date_hi is not None:
        cal = [d for d in cal
               if (date_lo is None or d >= date_lo) and (date_hi is None or d <= date_hi)]
    n = len(sleeves)
    for s in sleeves:
        s.update(holding=False, shares=0.0, target=None, entry=None,
                 own=capital / n,
                 w=(weights or {}).get(s['name'], 1.0))
    cash = capital
    equity_curve = []
    trades = []
    fills = 0
    free_days = 0
    sleeve_days = 0
    bk_peak, bk_tripped, bk_trips, bk_days = capital, False, 0, 0
    prev_d = cal[0]
    for d in cal:
        # -------- circuit breaker state, from YESTERDAY's close equity
        if breaker is not None and equity_curve:
            trip, reset, _ = breaker
            eq_prev = equity_curve[-1]
            bk_peak = max(bk_peak, eq_prev)
            if not bk_tripped and eq_prev < bk_peak * (1 - trip):
                bk_tripped = True
                bk_trips += 1
            elif bk_tripped and eq_prev > bk_peak * (1 - reset):
                bk_tripped = False
            if bk_tripped:
                bk_days += 1
        # -------- interest on cash (calendar-day gap)
        gap = (d - prev_d).days
        if gap and mode == 'pooled':
            cash *= 1 + INTEREST * gap / 365.0
        elif gap:
            for s in sleeves:
                if not s['holding']:
                    s['own'] *= 1 + INTEREST * gap / 365.0
        prev_d = d

        # -------- morning: who is free and has a live bid?
        active = []
        for s in sleeves:
            nd = data[s['name']]
            i = nd['idx'][d]
            bid = nd[s['bids']][i]
            paused = no_buy and d in no_buy.get(s['name'], ())
            s['_i'] = i
            s['_bid'] = None if (paused or bid is None or i == 0) else bid
            if not s['holding']:
                sleeve_days += 1
                if s['_bid'] is not None:
                    active.append(s)
        free_days += len(active)
        if mode == 'pooled' and active:
            wsum = sum(s['w'] for s in active)
            bmul = breaker[2] if (breaker is not None and bk_tripped) else 1.0
            for s in active:
                a = cash * s['w'] / wsum * bmul
                if cap_frac is not None:
                    a = min(a, cap_frac * cash)
                s['_alloc'] = a

        # -------- exits on positions held from before today
        for s in sleeves:
            if not s['holding'] or s['entry'] == d:
                continue
            nd = data[s['name']]
            i = s['_i']
            H, O = nd['H'][i], nd['O'][i]
            stop = (d - s['entry']).days >= STOP_DAYS
            px = None
            ps_level = (s['bid'] * (1 - price_stop)) if price_stop is not None else None
            if ps_level is not None and nd['L'][i] <= ps_level + 1e-12:
                px = O if O <= ps_level else ps_level     # stop wins ties, pessimistic
            elif H >= s['target'] - 1e-12:
                px = s['target']
            elif stop:
                px = O
            if px is not None:
                proceeds = s['shares'] * (px - COMM)
                if mode == 'pooled':
                    cash += proceeds
                else:
                    s['own'] = proceeds
                if collect_trades:
                    trades.append(dict(name=s['name'], kind=s['kind'],
                                       entry=s['entry'], exit=d,
                                       pnl=proceeds - s['cost'],
                                       stopped=(px < s['target'] - 1e-12)))
                s.update(holding=False, shares=0.0, target=None, entry=None)

        # -------- fills for free sleeves
        for s in active:
            if s['holding']:
                continue
            nd = data[s['name']]
            i = s['_i']
            bid = s['_bid']
            if nd['L'][i] > bid + 1e-12:
                continue
            budget = s['_alloc'] if mode == 'pooled' else s['own']
            if budget <= 0:
                continue
            shares = budget / (bid + COMM)
            cost = budget
            target = bid + nd['C'][i - 1] * s['prem']
            if mode == 'pooled':
                cash -= cost
            else:
                s['own'] = 0.0
            fills += 1
            # verified same-day exit
            if nd['H'][i] >= target - 1e-12 and nd['chk'](i, bid, target):
                proceeds = shares * (target - COMM)
                if mode == 'pooled':
                    cash += proceeds
                else:
                    s['own'] = proceeds
                if collect_trades:
                    trades.append(dict(name=s['name'], kind=s['kind'],
                                       entry=d, exit=d, pnl=proceeds - cost,
                                       stopped=False))
            else:
                s.update(holding=True, shares=shares, target=target, entry=d,
                         cost=cost, bid=bid)

        # -------- mark to market
        mv = 0.0
        for s in sleeves:
            if s['holding']:
                nd = data[s['name']]
                mv += s['shares'] * nd['C'][s['_i']]
            elif mode == 'captive':
                mv += s['own']
        equity_curve.append((cash if mode == 'pooled' else 0.0) + mv)

    eq = equity_curve
    N = len(cal)
    cut = next((i for i, d in enumerate(cal) if d >= SPLIT), N - 1)
    cut = max(cut, 1)
    peak, dd = -1e30, 0.0
    for e in eq:
        peak = max(peak, e)
        if peak > 0:
            dd = max(dd, (peak - e) / peak)
    stops = sum(1 for t in trades if t['stopped']) if collect_trades else None
    return dict(full=annualise(eq[-1] / eq[0] - 1, cal, 0, N - 1),
                train=annualise(eq[cut] / eq[0] - 1, cal, 0, cut),
                test=annualise(eq[-1] / eq[cut] - 1, cal, cut, N - 1),
                maxdd=dd, fills=fills, fills_per_day=fills / N,
                cash_frac=free_days / sleeve_days if sleeve_days else 0.0,
                stops=stops, equity=eq, trades=trades,
                bk_trips=bk_trips, bk_days=bk_days)


def report(label, r):
    print(f'{label:34s} full {r["full"]*100:6.1f}%  train {r["train"]*100:6.1f}%  '
          f'test {r["test"]*100:6.1f}%  DD {r["maxdd"]*100:5.1f}%  '
          f'fills/d {r["fills_per_day"]:.2f}', flush=True)


if __name__ == '__main__':
    print('loading engine series for 8 names...', flush=True)
    data, sleeves, cal = load_all()
    print(f'common calendar: {len(cal)} sessions {cal[0]} to {cal[-1]}', flush=True)

    # validation: captive mode vs the engine's held construction
    r_cap = simulate(data, sleeves, cal, mode='captive')
    report('captive (validation vs held)', r_cap)
    # engine held-construction reference on the same calendar
    tot0 = tot1 = totc = 0.0
    for s in NAMES:
        nd = data[s]
        r = run_model(nd['dts'], nd['O'], nd['H'], nd['L'], nd['C'], nd['p'],
                      ou_sigma='resid', same_day_exit=nd['chk'], collect=True)
        eq = r.frames['equity']
        i0 = nd['idx'][cal[0]]
        ic = nd['idx'][next(d for d in cal if d >= SPLIT)]
        i1 = nd['idx'][cal[-1]]
        tot0 += eq[i0]; totc += eq[ic]; tot1 += eq[i1]
    print(f'engine held reference               full {annualise(tot1/tot0-1, cal, 0, len(cal)-1)*100:6.1f}%  '
          f'train {annualise(totc/tot0-1, cal, 0, next(i for i,d in enumerate(cal) if d>=SPLIT))*100:6.1f}%',
          flush=True)

    r_pool = simulate(data, sleeves, cal, mode='pooled', collect_trades=True)
    report('POOLED baseline (the live loop)', r_pool)
    print(f'  sleeves in cash {r_pool["cash_frac"]*100:.0f}% of sleeve-days, '
          f'{r_pool["fills"]} fills, {r_pool["stops"]} stops', flush=True)
