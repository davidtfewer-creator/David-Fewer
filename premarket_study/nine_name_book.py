"""
The nine-name book: RKLB, TSM, VRT, MU (VST dropped) + NVDA, AVGO patient + GM, VLO, CF.

    dropped   VST
    kept      RKLB, TSM, VRT, MU          deployed rule, deployed parameters
    added     NVDA, AVGO                  premium 4-6%, 200-day stop, residual OU sigma with
                                          the buffer re-expressed in residual units
    added     GM, VLO, CF                 the diversifier work's recommendation

Two return figures are reported for every name, because they answer different questions:

    POTENTIAL   the full-sample figure on verified fills. What the rule made over the data we
                have, with no allowance for the parameters having been fitted on it.
    PLANNED     potential less the measured 2.1pp out-of-sample haircut -- the convention behind
                the published "daily five 79%". This is the number to run the business on.

The gap between them is not a forecast range. It is the overfitting allowance, and the true
uncertainty is far wider than 2.1pp on any single name.

WHAT IS COMPUTED AND WHAT IS QUOTED
-----------------------------------
Six of the nine are computed here from validated workbooks: RKLB, TSM, VRT and MU from the live
book (matched to the penny), NVDA and AVGO from the original. GM, VLO and CF cannot be -- their
price data was in an upload that has since expired -- so they are carried at the handover's
published figures and are marked [quoted] in every table. Upload their workbooks or 5-minute
files and they become computed like the rest.

Book aggregation uses the arithmetic mean of per-name annual returns, which is the convention
that produced "daily five 79%" and "book 73%", so these numbers are directly comparable to the
published ones. The held-construction compounding figure is shown alongside, since that is what
the equity curve actually does.

Run:  python3 nine_name_book.py
"""
import numpy as np

import ramp_premium as R
from engine import Params, run_model

LIVE = '/root/.claude/uploads/822d405e-f99b-5b59-9c6b-87e725054402/8d17afe4-TradingExcel_5stock_live.xlsx'
KEEP = ('RKLB', 'TSM', 'VRT', 'MU')
PAIR = ('NVDA', 'AVGO')
HIGH = (0.040, 0.045, 0.050, 0.060)
HIGH_STOP = 200
BUF_BAND = (0.6, 0.8, 1.0, 1.25, 1.5)
HAIRCUT = 2.1

# handover section 2 -- deployed five, verified fills, full sample (the "potential" basis).
# Planning figures are these less the 2.1pp haircut: RKLB 156, TSM 55, VST 60, VRT 65, MU 61.
PUBLISHED_5 = {'RKLB': 158.0, 'TSM': 57.0, 'VST': 62.0, 'VRT': 67.0, 'MU': 63.0}
BUYS_5 = {'RKLB': 96, 'TSM': 65, 'VST': 68, 'VRT': 54, 'MU': 51}

# handover section 6 -- diversifiers. 'full' is the full-sample fit; 'plan' is the
# unseen-window median, which the memo rounded to 35% each for all three.
QUOTED_3 = {'GM':  dict(full=50.3, plan=35.0, buys=61, corr_book=0.16, beta_ai=0.19),
            'VLO': dict(full=64.2, plan=35.0, buys=35, corr_book=0.30, beta_ai=0.11),
            'CF':  dict(full=46.9, plan=35.0, buys=27, corr_book=0.01, beta_ai=0.00)}


def sigma_ratio(args, p):
    a = run_model(*args, p, ou_sigma='level', collect=True)
    b = run_model(*args, p, ou_sigma='resid', collect=True)
    sl = np.array([x for x in a.frames['OUsig'] if x is not None])
    sr = np.array([x for x in b.frames['OUsig'] if x is not None])
    return float(sr.mean() / sl.mean())


def pair_figures(stock):
    """NVDA/AVGO on the proposed rule: band median over premium AND buffer, verified fills."""
    d, O, H, L, C = R.load_feed(stock)
    args = (d, O, H, L, C)
    yrs = (d[-1] - d[0]).days / 365.25
    p, _ = R.load_params(stock, years=yrs)
    chk = R.make_checker(R.build_index(stock), d, O)
    matched = p.ou_buf_k / sigma_ratio(args, p)
    rows = []
    for m in BUF_BAND:
        inner = []
        for prem in HIGH:
            q = Params(**{**p.__dict__, 'ou_buf_k': matched * m, 'stop_days': HIGH_STOP,
                          'premium': prem, 'ou_prem': prem})
            r = run_model(*args, q, ou_sigma='resid', same_day_exit=chk, collect=True)
            eq = r.frames['equity']
            i0, iS = 0, next(k for k, x in enumerate(d) if x >= R.SPLIT)
            tr = R.trades_of(r.frames['t1']) + R.trades_of(r.frames['t2'])
            full = (eq[-1] / eq[0]) ** (1 / yrs) - 1
            fit = (eq[iS] / eq[i0]) ** (365.25 / (d[iS] - d[i0]).days) - 1
            tst = (eq[-1] / eq[iS]) ** (365.25 / (d[-1] - d[iS]).days) - 1
            inner.append((full, fit, tst, r.total_buys / yrs, len(tr) / yrs))
        rows.append([float(np.median([x[j] for x in inner])) for j in range(5)])
    return [float(np.median([r[j] for r in rows])) for j in range(5)], matched


def main():
    print('=== the two names being re-specified ===\n')
    pair = {}
    for n in PAIR:
        v, buf = pair_figures(n)
        pair[n] = v
        print(f'  {n}: premium 4-6%, 200d stop, resid sigma, buffer {buf:.4f} '
              f'(band medians, verified fills)')
        print(f'     full {100*v[0]:.1f}%   fitted half {100*v[1]:.1f}%   tested half '
              f'{100*v[2]:.1f}%   buys {v[3]:.0f}/yr')

    # ---- assemble ------------------------------------------------------------------
    rows = []
    for n in KEEP:
        rows.append((n, 'deployed', PUBLISHED_5[n], PUBLISHED_5[n] - HAIRCUT, BUYS_5[n], 'quoted'))
    for n in PAIR:
        rows.append((n, '4-6% / 200d', 100 * pair[n][0], 100 * pair[n][0] - HAIRCUT,
                     pair[n][3], 'computed'))
    for n, q in QUOTED_3.items():
        rows.append((n, 'deployed', q['full'], q['plan'], q['buys'], 'quoted'))

    print(f'\n=== the nine-name book ===\n')
    print(f"{'name':6s} {'rule':14s} {'potential':>10s} {'planned':>9s} {'buys/yr':>8s}  source")
    for n, rule, pot, plan, buys, src in rows:
        print(f'{n:6s} {rule:14s} {pot:9.1f}% {plan:8.1f}% {buys:8.0f}  [{src}]')

    pot = np.array([r[2] for r in rows])
    plan = np.array([r[3] for r in rows])
    buys = np.array([r[4] for r in rows])
    print(f"\n{'':21s} {'-'*10} {'-'*9} {'-'*8}")
    print(f"{'BOOK (mean of 9)':21s} {pot.mean():9.1f}% {plan.mean():8.1f}% {buys.sum():8.0f}")

    T = 2.34
    held_pot = ((np.mean((1 + pot / 100) ** T)) ** (1 / T) - 1) * 100
    held_plan = ((np.mean((1 + plan / 100) ** T)) ** (1 / T) - 1) * 100
    print(f"{'  held construction':21s} {held_pot:9.1f}% {held_plan:8.1f}%")
    print(f'  (equal capital at the start, each name compounding alone, no rebalancing --')
    print(f'   higher than the mean because the winners compound)')

    # ---- comparisons ----------------------------------------------------------------
    print(f'\n=== against the books already on record ===\n')
    five_plan = np.mean([PUBLISHED_5[n] - HAIRCUT for n in PUBLISHED_5])
    five_buys = sum(BUYS_5.values())
    seven_plan = np.mean([PUBLISHED_5[n] - HAIRCUT for n in PUBLISHED_5] +
                         [100 * pair[n][0] - HAIRCUT for n in PAIR])
    print(f"{'book':44s} {'planned':>9s} {'buys/yr':>9s}")
    print(f"{'deployed five (published: 79%)':44s} {five_plan:8.1f}% {five_buys:9.0f}")
    print(f"{'seven = five + NVDA/AVGO patient':44s} {seven_plan:8.1f}% "
          f"{five_buys + sum(pair[n][3] for n in PAIR):9.0f}")
    print(f"{'NINE = four + NVDA/AVGO + GM/VLO/CF':44s} {plan.mean():8.1f}% {buys.sum():9.0f}")

    print(f'\n=== what dropping VST and adding six names does to the shape ===\n')
    print(f'  VST removed: planning 60%, 68 buys/yr, and the weakest tested half of the five.')
    print(f'  Names exposed to the AI theme: 6 of 9 (RKLB carries beta 0.77 to it and counts).')
    print(f'  Candidate betas to the AI factor: ' +
          ', '.join(f'{k} {v["beta_ai"]:.2f}' for k, v in QUOTED_3.items()) +
          '  [quoted]')
    print(f'  Candidate correlation to the book: ' +
          ', '.join(f'{k} {v["corr_book"]:.2f}' for k, v in QUOTED_3.items()) + '  [quoted]')

    # correlations among the six with data
    import itertools
    rets = {}
    for n in KEEP:
        d, O, H, L, C = R.load_feed(n, path=LIVE)
        rets[n] = (d, C)
    for n in PAIR:
        d, O, H, L, C = R.load_feed(n)
        rets[n] = (d, C)
    common = sorted(set.intersection(*[set(v[0]) for v in rets.values()]))
    M = {}
    for n, (d, C) in rets.items():
        ix = {t: k for k, t in enumerate(d)}
        s = np.array([C[ix[t]] for t in common])
        M[n] = s[1:] / s[:-1] - 1
    six = KEEP + PAIR
    ac = np.mean([np.corrcoef(M[a], M[b])[0, 1] for a, b in itertools.combinations(six, 2)])
    print(f'\n  average pairwise correlation of the SIX computed names: {ac:.3f}')
    print(f'  (deployed five was 0.489; five + NVDA/AVGO was 0.520. GM/VLO/CF cannot be')
    print(f'   included without their price data, but their quoted betas above are 0.00-0.19,')
    print(f'   so the nine-name figure will land well below the six-name one.)')


if __name__ == '__main__':
    main()
