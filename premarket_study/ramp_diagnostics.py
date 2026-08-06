"""
Is trapped capital actually the binding constraint -- and if it is, does a ramp release it?

The proposal's premise is that a position which lingers costs the sleeve the trades it could
otherwise have made. That premise is testable directly, without reference to any P&L:

  BLOCKED ENTRIES  sessions on which the sleeve was holding stock AND that day's low reached
                   the bid it would have posted had it been free. These are the trades the
                   position genuinely cost. If there are few of them, no exit rule can pay for
                   itself, because the freed capital would have had nothing to do.

  CAPITAL-TIME     how held-time is distributed. If the median hold is short and a thin tail of
                   long holds consumes the time, then a schedule keyed to days 1-3 is aimed at
                   the wrong trades entirely.

That second point suggests the ramp may be pointing the wrong way. The stated rationale --
trapped capital has an opportunity cost -- argues for making it EASIER to leave a stale
position, i.e. a premium that DECAYS the longer the position is held. The proposal does the
reverse: it discounts the first days, when nothing is stuck yet, and charges full price from
day 3 onward, when the position is actually becoming expensive. So both directions are run.

Run:  python3 ramp_diagnostics.py
"""
import numpy as np

import ramp_premium as R
from ramp_nvda_oos import window_return

STOCK = 'NVDA'
MODE = 'verified'


def blocked_entries(res, L, X_key):
    """Sessions the sleeve was holding while its bid would have been hit."""
    tr = res.frames[X_key[0]]
    bid = res.frames[X_key[1]]
    blocked = held = 0
    for i in range(len(L)):
        if tr['AE'][i - 1] == 1 if i else False:
            held += 1
            if bid[i] is not None and L[i] <= bid[i]:
                blocked += 1
    return blocked, held


def escape(hold_full, floor, fade):
    """Full premium for `hold_full` sessions, then fade linearly to `floor` over `fade`."""
    s = [1.0] * hold_full
    for j in range(1, fade + 1):
        s.append(1.0 + (floor - 1.0) * j / fade)
    return tuple(s)


SCHEDULES = [
    ('fixed',                        None),
    ('-- proposal: cheap early --',  None),
    ('0.50 / 0.75 / 1.0',            (0.50, 0.75, 1.00)),
    ('0.60 / 0.80 / 1.0',            (0.60, 0.80, 1.00)),
    ('-- reverse: cheap when stale --', None),
    ('full 3d, fade to 0.75 / 5d',   escape(3, 0.75, 5)),
    ('full 5d, fade to 0.75 / 10d',  escape(5, 0.75, 10)),
    ('full 5d, fade to 0.50 / 10d',  escape(5, 0.50, 10)),
    ('full 10d, fade to 0.50 / 10d', escape(10, 0.50, 10)),
    ('full 10d, fade to 0.25 / 20d', escape(10, 0.25, 20)),
    ('full 20d, fade to 0.50 / 20d', escape(20, 0.50, 20)),
]


def main():
    d, O, H, L, C = R.load_feed(STOCK)
    yrs = (d[-1] - d[0]).days / 365.25
    p, _ = R.load_params(STOCK, years=yrs)
    idx = R.build_index(STOCK)
    data = (d, O, H, L, C)

    base = R.run(STOCK, ramp=None, mode=MODE, p=p, data=data, idx=idx)

    # ---- 1. is capital actually the constraint? -------------------------------------
    print('=== 1. what does a held position actually cost? (baseline, verified fills) ===\n')
    tot_blocked = 0
    for key, name, bidkey in (('t1', 'Bayes', 'X'), ('t2', 'OU', 'AM')):
        b, h = blocked_entries(base, L, (key, bidkey))
        tot_blocked += b
        print(f'  {name:6s} sleeve: held on {h:3d} of {len(d)} sessions; on {b:3d} of those '
              f'({100*b/max(h,1):.1f}%) its bid would have been hit')
    print(f'\n  blocked entries in total: {tot_blocked} over {yrs:.2f} years '
          f'= {tot_blocked/yrs:.1f} per year, against {base.total_buys/yrs:.1f} buys per year')

    trips = R.trades_of(base.frames['t1']) + R.trades_of(base.frames['t2'])
    held = np.array([t[2] for t in trips])
    print(f'\n  holding period (sessions): median {np.median(held):.0f}, mean {held.mean():.1f}, '
          f'p75 {np.percentile(held,75):.0f}, p90 {np.percentile(held,90):.0f}, max {held.max():.0f}')
    order = np.sort(held)[::-1]
    top10 = order[:max(1, len(order)//10)].sum()
    print(f'  share of all held-time consumed by the longest 10% of trades: '
          f'{100*top10/held.sum():.1f}%')
    print(f'  trades resolved within 3 sessions: {100*(held<=3).mean():.1f}%  '
          f'(the window the proposal targets)')
    print(f'  capital idle: {R.stats(base,p,len(d))["cash_pct"]:.1f}% of sleeve-sessions')

    # ---- 2. both directions ---------------------------------------------------------
    print(f'\n=== 2. cheap-early vs cheap-when-stale ({MODE} fills) ===\n')
    print(f"{'schedule':32s} {'full':>8s} {'1st half':>9s} {'tested':>8s} "
          f"{'trips':>6s} {'medhold':>8s} {'p90':>5s}")
    b_f = b_1 = b_2 = None
    for label, ramp in SCHEDULES:
        if label.startswith('--'):
            print(f'  {label}')
            continue
        r = R.run(STOCK, ramp=ramp, mode=MODE, p=p, data=data, idx=idx)
        s = R.stats(r, p, len(d))
        f = r.annual_return
        h1 = window_return(r, d, d[0], R.SPLIT)
        h2 = window_return(r, d, R.SPLIT)
        if b_f is None:
            b_f, b_1, b_2 = f, h1, h2
        tt = R.trades_of(r.frames['t1']) + R.trades_of(r.frames['t2'])
        hh = np.array([t[2] for t in tt])
        print(f"{label:32s} {100*f:7.2f}% {100*h1:8.2f}% {100*h2:7.2f}% "
              f"{s['trips']:6d} {np.median(hh):8.0f} {np.percentile(hh,90):5.0f}"
              f"   ({100*(f-b_f):+5.2f} / {100*(h1-b_1):+5.2f} / {100*(h2-b_2):+5.2f})")


if __name__ == '__main__':
    main()
