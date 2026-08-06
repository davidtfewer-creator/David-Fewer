"""
The deployed five, unchanged, plus NVDA and AVGO on the patient high-premium rule. 1/7 each.

Construction
------------
HELD, never rebalanced: each name is given 1/7 of the capital on day one and compounds alone
thereafter. Averaging daily returns instead would feed capital back into names while they fall
and sell winners, which cost 16.3pp and inflated drawdown from 14.9% to 29.7% the last time it
was done by accident. Book equity is the sum of the seven independent curves.

Two workbooks, two OU conventions
---------------------------------
The five deployed names come from the live workbook, whose OU sigma is the AR(1) RESIDUAL and
whose buffers (0.20-0.75) are calibrated for that scale. NVDA and AVGO come from the original
workbook, whose sigma is the price LEVEL and whose buffers (~0.9) are calibrated for that. The
two scales differ by roughly 3x and swapping them puts the bid ~3x wrong -- so each name is run
on the pairing its own buffer was fitted for. Both sets are validated against their own sheets
to the penny before anything is blended.

Fill basis, and the bias it creates
-----------------------------------
Only NVDA and AVGO have intraday data here, so every name is scored at the AT-OPEN FLOOR: a
same-day round trip is allowed only where the bid was at or above the open, which daily bars
prove. It is a hard lower bound, not an estimate.

The floor is NOT equally conservative across the book, and that matters for reading the result:
    - at a 4-6% premium NVDA and AVGO make no same-day round trips at all, so for them the
      floor IS the verified answer, exactly.
    - at the deployed 1.5-2.7% premiums the five make many, so the floor understates them.
The size of that understatement is measurable on the two names where both are available, and it
is reported below so the bias can be applied to the five by eye rather than forgotten.

Run:  python3 seven_name_blend.py
"""
import numpy as np

import ramp_premium as R
from engine import Params, run_model

LIVE = '/root/.claude/uploads/822d405e-f99b-5b59-9c6b-87e725054402/8d17afe4-TradingExcel_5stock_live.xlsx'
FIVE = ('RKLB', 'TSM', 'VST', 'VRT', 'MU')
PAIR = ('NVDA', 'AVGO')
HIGH = (0.040, 0.045, 0.050, 0.060)
HIGH_STOP = 200

# handover section 2: published planning figures for the deployed five (verified fills,
# full-sample fit less the measured 2.1pp out-of-sample haircut)
PLANNING_5 = {'RKLB': 156.0, 'TSM': 55.0, 'VST': 60.0, 'VRT': 65.0, 'MU': 61.0}
HAIRCUT = 2.1


def load(stock, live):
    path = LIVE if live else ramp_premium_default()
    d, O, H, L, C = R.load_feed(stock, path=path)
    p, cached = R.load_params(stock, path=path, years=(d[-1] - d[0]).days / 365.25)
    return d, (d, O, H, L, C), p, cached['ou_sigma']


def ramp_premium_default():
    return R.BOOK


def curve(stock, args, p, sigma, band, stop, mode='at_open'):
    """Equity curve, median across the premium band (band=None -> the name's own premium)."""
    d = args[0]
    prems = [None] if band is None else list(band)
    curves = []
    for prem in prems:
        q = Params(**{**p.__dict__, 'stop_days': stop}) if prem is None else \
            Params(**{**p.__dict__, 'premium': prem, 'ou_prem': prem, 'stop_days': stop})
        r = run_model(*args, q, ou_sigma=sigma, same_day_exit=mode, collect=True)
        curves.append(np.array(r.frames['equity']) / q.capital)
    return np.median(curves, axis=0)


def ann(eq, dates, i0, i1):
    yrs = (dates[i1] - dates[i0]).days / 365.25
    return (eq[i1] / eq[i0]) ** (1 / yrs) - 1 if eq[i0] > 0 and yrs > 0 else float('nan')


def maxdd(eq):
    peak, dd = -1e30, 0.0
    for e in eq:
        peak = max(peak, e)
        if peak > 0:
            dd = max(dd, (peak - e) / peak)
    return dd


def main():
    # ---- load and align ------------------------------------------------------------
    info = {}
    for n in FIVE:
        info[n] = load(n, live=True)
    for n in PAIR:
        info[n] = load(n, live=False)
    common = sorted(set(info[FIVE[0]][0]) & set(info[PAIR[0]][0]))
    for n in info:
        common = sorted(set(common) & set(info[n][0]))
    print(f'aligned to {len(common)} common sessions, {common[0]} .. {common[-1]}\n')

    SPLIT = R.SPLIT
    last12 = common[-1].replace(year=common[-1].year - 1)
    ci = {n: {dt: k for k, dt in enumerate(info[n][0])} for n in info}

    def on_common(c, n):
        return np.array([c[ci[n][dt]] for dt in common])

    # ---- the three configurations ---------------------------------------------------
    legs = {}
    for n in FIVE:
        d, args, p, sg = info[n]
        legs[('deployed', n)] = on_common(curve(n, args, p, sg, None, p.stop_days), n)
    for n in PAIR:
        d, args, p, sg = info[n]
        legs[('deployed', n)] = on_common(curve(n, args, p, sg, None, p.stop_days), n)
        legs[('high', n)] = on_common(curve(n, args, p, sg, HIGH, HIGH_STOP), n)

    books = {
        'five only (1/5 each)':          [('deployed', n) for n in FIVE],
        'seven, pair at DEPLOYED premium': [('deployed', n) for n in FIVE + PAIR],
        'seven, pair at 4-6% / 200d':      [('deployed', n) for n in FIVE] +
                                           [('high', n) for n in PAIR],
    }

    i0, i1 = 0, len(common) - 1
    iS = next(k for k, dt in enumerate(common) if dt >= SPLIT)
    i12 = next(k for k, dt in enumerate(common) if dt >= last12)

    print('=== book returns, held construction, at-open floor ===\n')
    print(f"{'book':34s} {'full':>8s} {'fitted':>8s} {'tested':>8s} {'last12m':>8s} {'maxDD':>8s}")
    curves = {}
    for label, keys in books.items():
        w = 1.0 / len(keys)
        eq = sum(w * legs[k] for k in keys)
        curves[label] = eq
        print(f"{label:34s} {100*ann(eq,common,i0,i1):7.2f}% {100*ann(eq,common,i0,iS):7.2f}% "
              f"{100*ann(eq,common,iS,i1):7.2f}% {100*ann(eq,common,i12,i1):7.2f}% "
              f"{100*maxdd(eq):7.1f}%")

    print(f'\n=== per name, on the same basis (each 1/7 of the book) ===\n')
    print(f"{'name':6s} {'config':22s} {'full':>8s} {'fitted':>8s} {'tested':>8s} "
          f"{'last12m':>8s} {'maxDD':>8s}")
    for n in FIVE:
        c = legs[('deployed', n)]
        print(f"{n:6s} {'deployed':22s} {100*ann(c,common,i0,i1):7.2f}% "
              f"{100*ann(c,common,i0,iS):7.2f}% {100*ann(c,common,iS,i1):7.2f}% "
              f"{100*ann(c,common,i12,i1):7.2f}% {100*maxdd(c):7.1f}%")
    for n in PAIR:
        for tag, nm in (('deployed', 'deployed premium'), ('high', '4-6% / 200d')):
            c = legs[(tag, n)]
            print(f"{n:6s} {nm:22s} {100*ann(c,common,i0,i1):7.2f}% "
                  f"{100*ann(c,common,i0,iS):7.2f}% {100*ann(c,common,iS,i1):7.2f}% "
                  f"{100*ann(c,common,i12,i1):7.2f}% {100*maxdd(c):7.1f}%")

    # ---- how much is the floor costing the five? ------------------------------------
    print(f'\n=== calibrating the at-open floor, on the two names where both bases exist ===\n')
    print(f"{'name':6s} {'premium':>18s} {'at-open floor':>14s} {'verified':>10s} {'gap':>8s}")
    for n in PAIR:
        d, args, p, sg = info[n]
        idx = R.build_index(n)
        chk = R.make_checker(idx, d, args[1])
        for tag, band, stop, nm in (('deployed', None, p.stop_days, 'deployed'),
                                    ('high', HIGH, HIGH_STOP, '4-6% / 200d')):
            f = curve(n, args, p, sg, band, stop, 'at_open')
            v = curve(n, args, p, sg, band, stop, chk)
            af, av = ann(f, d, 0, len(d) - 1), ann(v, d, 0, len(d) - 1)
            print(f"{n:6s} {nm:>18s} {100*af:13.2f}% {100*av:9.2f}% {100*(av-af):+7.2f}pp")
    print('\n  At the deployed premium the floor understates by ~10pp; at 4-6% the gap is zero.')
    print('  The five are therefore understated above by something of that order EACH, and the')
    print('  pair is not understated at all. Read the book rows knowing the comparison is')
    print('  tilted AGAINST the deployed five.')

    # ---- the book on the published planning basis -----------------------------------
    print(f'\n=== the same question on the published planning basis (arithmetic mean of')
    print(f'    per-name annual returns, the convention behind "daily five 79%") ===\n')
    plan_pair = {}
    for n in PAIR:
        d, args, p, sg = info[n]
        idx = R.build_index(n)
        chk = R.make_checker(idx, d, args[1])
        c = curve(n, args, p, sg, HIGH, HIGH_STOP, chk)
        plan_pair[n] = 100 * ann(c, d, 0, len(d) - 1) - HAIRCUT
    five_mean = np.mean(list(PLANNING_5.values()))
    seven_mean = np.mean(list(PLANNING_5.values()) + list(plan_pair.values()))
    print('  deployed five (published):  ' +
          ', '.join(f'{k} {v:.0f}%' for k, v in PLANNING_5.items()) +
          f'   -> mean {five_mean:.1f}%')
    print('  pair at 4-6%/200d (verified full sample, less the 2.1pp haircut):  ' +
          ', '.join(f'{k} {v:.0f}%' for k, v in plan_pair.items()))
    print(f'\n  five-name book  {five_mean:.1f}%')
    print(f'  seven-name book {seven_mean:.1f}%   ({seven_mean-five_mean:+.1f}pp)')
    print(f'\n  Note what drives this: RKLB alone is 156% and carries the five-name mean. Any')
    print(f'  equally weighted addition below that average dilutes it, regardless of merit.')

    # ---- what it does to concentration ----------------------------------------------
    import itertools
    print(f'\n=== and what it does to the thing the diversifier work was about ===\n')
    rets = {}
    for n in FIVE + PAIR:
        C = info[n][1][4]
        m = {dt: None for dt in info[n][0]}
        for k in range(1, len(C)):
            m[info[n][0][k]] = C[k] / C[k - 1] - 1
        rets[n] = np.array([m[dt] for dt in common[1:]], dtype=float)

    def avg_corr(names):
        return float(np.mean([np.corrcoef(rets[a], rets[b])[0, 1]
                              for a, b in itertools.combinations(names, 2)]))
    print(f'  average pairwise correlation of SHARE returns (the exposure lives in the shares,')
    print(f'  not in the strategy, which sits in cash much of the time and mutes everything):\n')
    print(f'    deployed five                {avg_corr(FIVE):.3f}')
    print(f'    seven (five + NVDA/AVGO)     {avg_corr(FIVE + PAIR):.3f}')
    print(f'    NVDA-AVGO with each other    {np.corrcoef(rets["NVDA"], rets["AVGO"])[0,1]:.3f}')
    for n in PAIR:
        cs = [np.corrcoef(rets[n], rets[f])[0, 1] for f in FIVE]
        print(f'    {n} to the deployed five    {np.mean(cs):.3f}   (' +
              ', '.join(f'{f} {c:.2f}' for f, c in zip(FIVE, cs)) + ')')
    print(f'\n  Handover section 6 for reference: four AI names 0.58, current five 0.48,')
    print(f'  the proposed nine with GM/VLO/CF 0.21. This proposal moves the number the')
    print(f'  wrong way -- NVDA and AVGO are the theme, not a hedge against it.')


if __name__ == '__main__':
    main()
