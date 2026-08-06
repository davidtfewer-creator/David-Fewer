"""
Does splitting each sleeve into N concurrent slots pay?

Structure of the test, in the order that decides it:

  1. NVDA and AVGO on VERIFIED fills (5-minute bars), N = 1..4, both capital treatments,
     scored full sample / fitted half / tested half, and as neighbourhood medians over
     premium scalings of +/-10%.
  2. All ten names in the workbook at the AT-OPEN FLOOR -- an exit allowed only where the bid
     was at or above the open, so the same-day round trip is provable from daily bars alone.
     It understates the level, but it is a hard bound and it needs no intraday data, which
     makes a ten-name transport test possible. That test is what retired the ramp ideas, and
     this change has to face the same one.
  3. What the split leaves on the table: entries still blocked with every slot full.

No parameter is re-fitted anywhere.

Run:  python3 split_study.py
"""
import numpy as np

import ramp_premium as R
from split_tranche import run_split, blocked

VERIFIED = ('NVDA', 'AVGO')
ALL_NAMES = ('NVDA', 'AVGO', 'TSM', 'RKLB', 'VST', 'VRT', 'TSLA', 'PLTR', 'SOFI', 'SPOT')
SLOTS = (1, 2, 3, 4)
PERTURB = (0.90, 0.95, 1.00, 1.05, 1.10)
from engine import Params


def wret(equity, dates, start, end=None):
    i0 = next(i for i, d in enumerate(dates) if d >= start)
    i1 = (len(dates) - 1) if end is None else max(i for i, d in enumerate(dates) if d <= end)
    yrs = (dates[i1] - dates[i0]).days / 365.25
    if equity[i0] <= 0 or yrs <= 0:
        return float('nan')
    return (equity[i1] / equity[i0]) ** (1 / yrs) - 1


def ctx_for(stock, mode):
    d, O, H, L, C = R.load_feed(stock)
    yrs = (d[-1] - d[0]).days / 365.25
    p, _ = R.load_params(stock, years=yrs)
    if mode == 'verified':
        sde = R.make_checker(R.build_index(stock), d, O)
    elif mode == 'at_open':
        sde = 'at_open'
    else:
        sde = {'sheet': True, 'none': False}[mode]
    return d, (d, O, H, L, C), p, sde


def go(args, p, n, sde, treatment='split', scale=1.0):
    d, O, H, L, C = args
    q = Params(**{**p.__dict__, 'premium': p.premium * scale, 'ou_prem': p.ou_prem * scale}) \
        if scale != 1.0 else p
    return run_split(d, O, H, L, C, q, n_slots=n, ou_sigma='level',
                     same_day_exit=sde, treatment=treatment)


def main():
    # ---------------- 1. the two names with verified fills ---------------------------
    print('=== 1. verified fills, N slots per sleeve ===\n')
    for stock in VERIFIED:
        d, args, p, sde = ctx_for(stock, 'verified')
        print(f'-- {stock} --')
        print(f"{'slots':>5s} {'treatment':>10s} {'profit $':>13s} {'full':>8s} {'fitted':>8s} "
              f"{'tested':>8s} {'buys':>5s} {'maxDD':>7s} {'blocked':>8s}")
        base = {}
        for treatment in ('split', 'pool'):
            for n in SLOTS:
                r = go(args, p, n, sde, treatment)
                f = r['annual_return']
                h1 = wret(r['equity'], d, d[0], R.SPLIT)
                h2 = wret(r['equity'], d, R.SPLIT)
                if n == 1:
                    base[treatment] = (f, h1, h2)
                b = base[treatment]
                print(f"{n:5d} {treatment:>10s} {r['profit']:13,.0f} {100*f:7.2f}% {100*h1:7.2f}% "
                      f"{100*h2:7.2f}% {r['total_buys']:5d} {100*r['max_drawdown']:6.1f}% "
                      f"{blocked(r, args[3]):8d}"
                      f"   ({100*(f-b[0]):+5.2f} / {100*(h1-b[1]):+5.2f} / {100*(h2-b[2]):+5.2f})")
        # neighbourhood medians
        print(f"\n  neighbourhood medians over premium scalings {PERTURB}:")
        nb = {}
        for n in SLOTS:
            v = [go(args, p, n, sde, 'split', sc) for sc in PERTURB]
            nb[n] = (float(np.median([x['annual_return'] for x in v])),
                     float(np.median([wret(x['equity'], d, d[0], R.SPLIT) for x in v])),
                     float(np.median([wret(x['equity'], d, R.SPLIT) for x in v])))
        for n in SLOTS:
            dd = tuple(100 * (nb[n][j] - nb[1][j]) for j in range(3))
            print(f"    {n} slot(s): full {100*nb[n][0]:6.2f}%  fitted {100*nb[n][1]:6.2f}%  "
                  f"tested {100*nb[n][2]:6.2f}%   ({dd[0]:+5.2f} / {dd[1]:+5.2f} / {dd[2]:+5.2f})")
        print()

    # ---------------- 2. ten-name transport test -------------------------------------
    print('=== 2. all ten names at the at-open floor: does 2 slots beat 1? ===\n')
    print(f"{'name':6s} {'1 slot':>18s} {'2 slots':>18s} {'Δ full':>8s} {'Δ fitted':>9s} "
          f"{'Δ tested':>9s} {'buys 1':>7s} {'buys 2':>7s}")
    print(f"{'':6s} {'full  fitted tested':>18s} {'full  fitted tested':>18s}")
    deltas = []
    for stock in ALL_NAMES:
        d, args, p, sde = ctx_for(stock, 'at_open')
        r1 = go(args, p, 1, sde)
        r2 = go(args, p, 2, sde)
        a = (r1['annual_return'], wret(r1['equity'], d, d[0], R.SPLIT), wret(r1['equity'], d, R.SPLIT))
        b = (r2['annual_return'], wret(r2['equity'], d, d[0], R.SPLIT), wret(r2['equity'], d, R.SPLIT))
        deltas.append((stock,) + tuple(b[j] - a[j] for j in range(3)))
        print(f"{stock:6s} {100*a[0]:6.1f}{100*a[1]:7.1f}{100*a[2]:7.1f} "
              f"{100*b[0]:6.1f}{100*b[1]:7.1f}{100*b[2]:7.1f} "
              f"{100*(b[0]-a[0]):+7.2f} {100*(b[1]-a[1]):+8.2f} {100*(b[2]-a[2]):+8.2f} "
              f"{r1['total_buys']:7d} {r2['total_buys']:7d}")
    for j, nm in ((1, 'full sample'), (2, 'fitted half'), (3, 'tested half')):
        v = np.array([x[j] for x in deltas])
        print(f"\n  {nm:12s}: median {100*np.median(v):+.2f}pp, mean {100*v.mean():+.2f}pp, "
              f"{sum(1 for x in v if x > 0)}/{len(v)} names positive")

    # ---------------- 3. drawdown, and where the return goes -------------------------
    print(f'\n=== 3. drawdown across the ten names (at-open floor) ===\n')
    print(f"{'name':6s} " + ' '.join(f'{n:>7s}' for n in ('1 slot', '2', '3', '4')))
    dds = {n: [] for n in SLOTS}
    for stock in ALL_NAMES:
        d, args, p, sde = ctx_for(stock, 'at_open')
        row = []
        for n in SLOTS:
            r = go(args, p, n, sde)
            dds[n].append(r['max_drawdown'])
            row.append(100 * r['max_drawdown'])
        print(f"{stock:6s} " + ' '.join(f'{x:6.1f}%' for x in row))
    print(f"{'median':6s} " + ' '.join(f'{100*np.median(dds[n]):6.1f}%' for n in SLOTS))
    print(f"  lower than 1 slot: " + ', '.join(
        f"{n} slots {sum(1 for a, b in zip(dds[n], dds[1]) if a < b)}/10" for n in SLOTS[1:]))

    print(f'\n=== 4. the split decomposes exactly -- and that is what settles it ===\n')
    print("  Slot 1 has first refusal on every entry, so it is free exactly when the unsplit")
    print("  sleeve would be: its trade sequence is IDENTICAL. And a sleeve's compounding rate")
    print("  is scale-invariant here -- shares = fund/(bid+comm), commission is per share, and")
    print("  interest is proportional -- so running it at half size changes nothing but the")
    print("  units. The identity below is therefore not an approximation:")
    print()
    print("      2-slot sleeve  =  half in TODAY'S strategy  +  half in the BLOCKED-ENTRY one")
    print()
    print("  which means splitting pays if and only if the entries currently being missed")
    print("  compound FASTER than the trades already being made. The blocked capital was")
    print("  never idle, so 'more trades' is not by itself worth anything.\n")
    for stock in VERIFIED:
        d, args, p, sde = ctx_for(stock, 'verified')
        yrs = (d[-1] - d[0]).days / 365.25
        one = go(args, p, 1, sde)
        two = go(args, p, 2, sde)
        print(f'  -- {stock} --')
        for nm, k, fund in (('Bayes', 't1', p.capital * p.bayes_pct),
                            ('OU', 't2', p.capital * (1 - p.bayes_pct))):
            r_un = (one[k]['Y'][0][-1] / fund) ** (1 / yrs) - 1
            r_s1 = (two[k]['Y'][0][-1] / (fund / 2)) ** (1 / yrs) - 1
            r_s2 = (two[k]['Y'][1][-1] / (fund / 2)) ** (1 / yrs) - 1
            ok = 'yes' if abs(r_s1 - r_un) < 1e-9 else 'NO'
            verdict = 'blocked entries BETTER' if r_s2 > r_un else 'blocked entries worse'
            print(f'     {nm:5s}: unsplit {100*r_un:7.2f}% ({sum(one[k]["Z"][0]):3d} buys) | '
                  f'slot 1 {100*r_s1:7.2f}% (identical: {ok}) | '
                  f'slot 2 {100*r_s2:7.2f}% ({sum(two[k]["Z"][1]):3d} buys) -> {verdict}')


if __name__ == '__main__':
    main()
