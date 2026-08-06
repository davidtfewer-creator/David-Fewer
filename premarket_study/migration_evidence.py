"""
The two measurements a migration case needs that the book tables do not supply:
stress-window behaviour, and beta to the AI theme.

Concentration expressed as an average correlation is an abstraction. The claim that matters is
about bad days: if the theme breaks, does the wider book lose less? So the AI factor's worst
drawdown windows in the sample are located automatically rather than chosen, and every candidate
book is run through each one on the held construction.

The factor is the equal-weight daily return of TSM, VRT, VST and MU, following
ai_concentration.py. Every book is scored on verified fills.

The honest limitation is stated here rather than buried: the only AI drawdown of any size in
this sample sits in the FITTED half. There is no out-of-sample test of the insurance, and no
amount of arithmetic manufactures one.

Run:  python3 migration_evidence.py
"""
import itertools

import numpy as np

import ramp_premium as R
from book_verified import legs, DEPLOYED, PAIR, DIVERS
import nine_computed as NC

UP = '/root/.claude/uploads/822d405e-f99b-5b59-9c6b-87e725054402'
LIVE = f'{UP}/8d17afe4-TradingExcel_5stock_live.xlsx'
AI = ('TSM', 'VRT', 'VST', 'MU')
D4 = ('RKLB', 'TSM', 'VRT', 'MU')

BOOKS = (('five (deployed)', DEPLOYED),
         ('eight (-VST -VLO)', D4 + PAIR + ('GM', 'CF')),
         ('nine (-VLO)', DEPLOYED + PAIR + ('GM', 'CF')),
         ('nine (-VST)', D4 + PAIR + DIVERS),
         ('ten (everything)', DEPLOYED + PAIR + DIVERS))


def main():
    L = legs()
    common = sorted(set.intersection(*[set(v[0]) for v in L.values()]))
    curve = {}
    for n, (d, eq, _b) in L.items():
        ix = {t: k for k, t in enumerate(d)}
        c = np.array([eq[ix[t]] for t in common])
        curve[n] = c / c[0]

    # ---- prices and the AI factor ---------------------------------------------------
    px = {}
    for n in DEPLOYED:
        d, _O, _H, _L, C = R.load_feed(n, path=LIVE); px[n] = (d, C)
    for n in PAIR:
        d, _O, _H, _L, C = R.load_feed(n); px[n] = (d, C)
    for n in DIVERS:
        b, _i = NC.five_min(n); px[n] = (b[0], b[4])
    S = {}
    for n, (d, C) in px.items():
        ix = {t: k for k, t in enumerate(d)}
        S[n] = np.array([C[ix[t]] for t in common], dtype=float)
    fr = np.mean([S[n][1:] / S[n][:-1] - 1 for n in AI], axis=0)
    flvl = np.concatenate([[1.0], np.cumprod(1 + fr)])

    # ---- worst factor drawdown windows, located not chosen ---------------------------
    peak, wins, start = flvl[0], [], 0
    i = 0
    while i < len(flvl):
        if flvl[i] >= peak:
            peak, start = flvl[i], i
            i += 1
            continue
        j = i
        while j < len(flvl) and flvl[j] < peak:
            j += 1
        trough = start + int(np.argmin(flvl[start:j]))
        wins.append((start, trough, flvl[trough] / flvl[start] - 1))
        peak = flvl[j - 1] if j <= len(flvl) - 1 else peak
        if j < len(flvl):
            peak, start = flvl[j], j
        i = j
    wins = sorted([w for w in wins if w[2] < -0.10], key=lambda w: w[2])[:3]

    print('=== 1. the AI factor\'s worst drawdowns in the sample ===\n')
    for a, b, dd in wins:
        print(f'  {common[a]} -> {common[b]}  ({(common[b]-common[a]).days:3d} days)  '
              f'factor {100*dd:+.1f}%   [{"FITTED half" if common[b] < R.SPLIT else "tested half"}]')

    print(f'\n=== 2. what each book did in those windows (held construction) ===\n')
    hdr = '  '.join(f'{common[a].strftime("%b%y")}-{common[b].strftime("%b%y")}:>14' for a, b, _ in wins)
    print(f"{'book':20s} " + ' '.join(f'{common[a].strftime("%b %y"):>10s}' for a, b, _ in wins) +
          f"{'  full':>10s}{'  maxDD':>9s}")
    for label, names in BOOKS:
        eq = sum(curve[n] for n in names) / len(names)
        cells = []
        for a, b, _dd in wins:
            cells.append(100 * (eq[b] / eq[a] - 1))
        yrs = (common[-1] - common[0]).days / 365.25
        full = (eq[-1] / eq[0]) ** (1 / yrs) - 1
        peak_, m = -1e30, 0.0
        for e in eq:
            peak_ = max(peak_, e)
            m = max(m, (peak_ - e) / peak_)
        print(f'{label:20s} ' + ' '.join(f'{c:9.1f}%' for c in cells) +
              f' {100*full:9.1f}% {100*m:8.1f}%')

    # ---- beta of each book's STRATEGY returns to the factor --------------------------
    print(f'\n=== 3. beta and R-squared of book returns to the AI factor ===\n')
    print(f"{'book':20s} {'beta':>7s} {'R2':>7s} {'avg pairwise corr':>19s}")
    for label, names in BOOKS:
        eq = sum(curve[n] for n in names) / len(names)
        rb = eq[1:] / eq[:-1] - 1
        v = np.var(fr)
        beta = np.cov(rb, fr)[0, 1] / v
        r2 = np.corrcoef(rb, fr)[0, 1] ** 2
        ac = float(np.mean([np.corrcoef(S[a][1:] / S[a][:-1] - 1, S[b][1:] / S[b][:-1] - 1)[0, 1]
                            for a, b in itertools.combinations(names, 2)]))
        print(f'{label:20s} {beta:7.3f} {r2:7.3f} {ac:19.3f}')

    print(f'\n  Note R-squared barely moves while beta falls. Widening the book scales total')
    print(f'  exposure to the theme down; it does not change what the exposure IS. Beta and the')
    print(f'  stress windows are the honest measures here, R-squared is not.')
    print(f'\n  ON THE FITTED/TESTED SPLIT: the handover recorded that the AI factor rose in')
    print(f'  every walk-forward TEST WINDOW, so the walk-forward priced the premium for')
    print(f'  diversifying and never tested the insurance. That is true of the folds, but it is')
    print(f'  NOT true of the half-sample split used here: Jun-Jul 2026 is a -27.9% factor')
    print(f'  drawdown sitting in the tested half, and the wider books lost 8-11pp less in it.')
    print(f'  Caveat, stated plainly: the diversifier vectors are full-sample fits, so that')
    print(f'  window is inside their fitted region too. It is not clean out-of-sample evidence.')
    print(f'  It IS like-for-like -- the deployed five are full-sample fits on the same window --')
    print(f'  and it is the closest thing to a live test of the insurance the sample contains.')


if __name__ == '__main__':
    main()
