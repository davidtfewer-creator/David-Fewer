"""
"Deep dip reserve": hold capital idle, buy when a name falls X% below its trailing L-day high,
then hold WITHOUT a stop until it recovers to that high.

The headline per-event gain is not the figure that matters. What matters is the return on the
RESERVED capital, which includes every day the money sits waiting for a trigger and every day
it sits in an unrecovered position. Both are measured here.

Also reported: recovery rate, time to recovery, the longest unresolved holding, and whether any
position is still under water at the end of the sample -- the risk the design has no answer to.
"""
import statistics
from stop_sweep import load_book

data, params, cached = load_book()
STOCKS = list(data)
INTEREST = 0.0314


def run_dip(stock, L=60, X=0.08, capital=1_000_000):
    """Single-slot reserve: one position at a time, bought X% below the trailing L-day high,
    sold when the close regains that high. Idle cash earns interest."""
    dts, O, H, Lo, C = data[stock]
    n = len(C)
    cash = capital; shares = 0.0; entry = None; ref = None; bd = None
    events = []          # (buy date, sell date, days held, return)
    deployed_days = 0
    for i in range(L, n):
        # interest on idle cash
        if shares == 0:
            cash += cash * INTEREST * (dts[i]-dts[i-1]).days / 365.0
        else:
            deployed_days += 1
        hi = max(H[i-L:i])                       # trailing high, excluding today
        if shares == 0:
            trigger = hi * (1 - X)
            if Lo[i] <= trigger:                 # limit buy fills
                px = min(trigger, O[i])          # gap-down fills at the open
                shares = cash / px; cash = 0.0
                entry = px; ref = hi; bd = dts[i]
        else:
            if H[i] >= ref:                      # recovered to the pre-drop high
                cash = shares * ref; shares = 0.0
                events.append((bd, dts[i], (dts[i]-bd).days, ref/entry - 1))
                entry = ref = bd = None
    yrs = (dts[-1]-dts[0]).days / 365.25
    open_pos = shares > 0
    final = cash + (shares * C[-1] if open_pos else 0.0)
    ann = (final/capital)**(1/yrs) - 1
    return dict(events=events, ann=ann, yrs=yrs, n=len(events),
                deployed=deployed_days/(n-L), open_pos=open_pos,
                stuck_days=(dts[-1]-bd).days if open_pos else 0,
                unreal=(C[-1]/entry - 1) if open_pos else 0.0)


if __name__ == '__main__':
    print('=== DEEP-DIP RESERVE, single slot per name (L=60d high, buy -8%, sell on recovery) ===\n')
    print(f'{"name":6s}{"events":>8s}{"/yr":>6s}{"avg gain":>10s}{"avg days":>10s}{"max days":>10s}'
          f'{"deployed":>10s}{"ann on reserve":>16s}{"still open":>12s}')
    print('-'*88)
    tot = []
    for s in STOCKS:
        r = run_dip(s)
        if r['n']:
            g = statistics.mean(e[3] for e in r['events'])*100
            dd = statistics.mean(e[2] for e in r['events'])
            mx = max(e[2] for e in r['events'])
        else:
            g = dd = mx = 0
        stuck = f"{r['stuck_days']}d {r['unreal']*100:+.0f}%" if r['open_pos'] else '-'
        tot.append(r['ann'])
        print(f'{s:6s}{r["n"]:>8d}{r["n"]/r["yrs"]:>6.1f}{g:>9.1f}%{dd:>10.0f}{mx:>10.0f}'
              f'{r["deployed"]*100:>9.0f}%{r["ann"]*100:>15.0f}%{stuck:>12s}')
    print('-'*88)
    print(f'{"MEAN":6s}{"":>44s}{statistics.mean(tot)*100:>39.0f}%')

    print('\n=== SENSITIVITY on NVDA: trigger depth and lookback ===')
    print(f'{"":8s}' + ''.join(f'{f"L={L}":>12s}' for L in (20, 60, 120)))
    for X in (0.05, 0.08, 0.12, 0.15, 0.20):
        row = []
        for L in (20, 60, 120):
            r = run_dip('NVDA', L=L, X=X)
            row.append(f'{r["ann"]*100:4.0f}% ({r["n"]:2d})')
        print(f'  X={X*100:2.0f}% ' + ''.join(f'{c:>12s}' for c in row))
    print('\n(cell = annualised return on reserved capital, with the number of events)')
