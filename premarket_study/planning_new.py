"""
Planning returns for GM, VLO and CF -- and the book on the same basis, which is the harder half.

There is a basis problem to clear first. The book's published planning figures (RKLB 156%, TSM 55%,
VST 60%, VRT 65%, MU 61%) come from the full-sample fit less a 2.1pp haircut, and the book's
"tested half" numbers come from those same full-sample parameters scored on the second half. The
parameters saw the whole sample in both cases. The new names' 37.1 / 35.2 / 42.4 came from
parameters fitted on the FIRST HALF ONLY and frozen. Quoting one against the other overstates the
book by however much in-sample fitting is worth, and on this model that is a lot -- the walk-
forward showed deployed parameters beating refitted ones by 50 to 80pp per fold, which is the size
of the lookahead, not a result.

So the planning figure here rests on observations where nothing had seen the window it was scored
on. For every name that is the three walk-forward folds; for the three new names there is also the
half-sample test, which is a fourth such observation and the one closest to how the model would
actually be run (fit once, freeze, leave it).

The median is used rather than the mean, as elsewhere in this work: with three or four
observations a single fold like VLO's +50.6% would otherwise set the number on its own.

Fold returns are period returns over roughly four and a half months and have to be annualised on
the actual day counts, which differ slightly between folds.
"""
import statistics
from datetime import date

# (start, end) of each walk-forward test window
FOLDS = [(date(2025, 5, 28), date(2025, 10, 13)),
         (date(2025, 10, 14), date(2026, 3, 4)),
         (date(2026, 3, 5), date(2026, 7, 23))]

# per-name PERIOD returns on each unseen fold, parameters fitted on that fold's training window
OOS = {
    'RKLB': [32.2, -0.7, -28.6],
    'TSM':  [35.6, 26.9, 24.3],
    'VST':  [64.9, -7.3, 3.1],
    'VRT':  [25.4, 47.9, 4.3],
    'MU':   [15.0, 55.0, 81.1],
    'GM':   [13.0, 10.3, 10.4],
    'VLO':  [12.0, 12.1, 50.6],
    'CF':   [0.6, 14.0, 20.2],
}
# fit on the first half only, frozen, scored on the tested half -- new names only, since the
# book's equivalent figures were produced with full-sample parameters and are not comparable
HALF = {'GM': 37.1, 'VLO': 35.2, 'CF': 42.4}
BOOK = ['RKLB', 'TSM', 'VST', 'VRT', 'MU']
NEW = ['GM', 'VLO', 'CF']
# the currently published planning figures, on the full-sample-fit basis
PUBLISHED = {'RKLB': 156, 'TSM': 55, 'VST': 60, 'VRT': 65, 'MU': 61}


def annualise(pct, d0, d1):
    yrs = (d1 - d0).days / 365.25
    return ((1 + pct/100) ** (1/yrs) - 1) * 100


if __name__ == '__main__':
    print('=== every name on one basis: annualised return on windows nothing had seen ===\n',
          flush=True)
    print(f'{"name":6s}{"fold 1":>9s}{"fold 2":>9s}{"fold 3":>9s}{"half-sample":>13s}'
          f'{"median":>9s}{"published":>11s}', flush=True)
    print('-'*66, flush=True)
    med = {}
    for s in BOOK + NEW:
        a = [annualise(OOS[s][j], *FOLDS[j]) for j in range(3)]
        obs = a + ([HALF[s]] if s in HALF else [])
        med[s] = statistics.median(obs)
        pub = f'{PUBLISHED[s]}%' if s in PUBLISHED else '--'
        half = f'{HALF[s]:.1f}%' if s in HALF else '--'
        print(f'{s:6s}{a[0]:>8.1f}%{a[1]:>8.1f}%{a[2]:>8.1f}%{half:>13s}'
              f'{med[s]:>8.1f}%{pub:>11s}', flush=True)
    print('-'*66, flush=True)

    bm = statistics.mean(med[s] for s in BOOK)
    nm = statistics.mean(med[s] for s in NEW)
    pm = statistics.mean(PUBLISHED[s] for s in BOOK)
    print(f'\n  five book names   median-of-OOS mean {bm:5.1f}%   published mean {pm:5.1f}%'
          f'   lookahead {pm-bm:+.0f}pp', flush=True)
    print(f'  three new names   median-of-OOS mean {nm:5.1f}%', flush=True)

    print('\n=== what to plan on ===\n', flush=True)
    print('Two internally consistent ways to write it down. Mixing them is the error to avoid.\n',
          flush=True)
    print(f'{"":26s}{"GM":>8s}{"VLO":>8s}{"CF":>8s}{"3 new":>9s}{"book 5":>9s}{"book 8":>9s}',
          flush=True)
    print('-'*77, flush=True)
    r1 = [med[s] for s in NEW]
    print(f'{"A  strict OOS median":26s}' + ''.join(f'{v:>7.0f}%' for v in r1) +
          f'{statistics.mean(r1):>8.0f}%{bm:>8.0f}%'
          f'{(bm*5 + statistics.mean(r1)*3)/8:>8.0f}%', flush=True)
    # scale the new names onto the published basis by the book's own lookahead ratio
    k = pm/bm
    r2 = [med[s]*k for s in NEW]
    print(f'{"B  published basis":26s}' + ''.join(f'{v:>7.0f}%' for v in r2) +
          f'{statistics.mean(r2):>8.0f}%{pm:>8.0f}%'
          f'{(pm*5 + statistics.mean(r2)*3)/8:>8.0f}%', flush=True)
    print(f'\n  Basis B scales the new names by the book\'s own lookahead ratio ({k:.2f}x), which is'
          f'\n  what it would take to quote them beside the published figures. It is an estimate of'
          f'\n  a bias, not a measurement, and the honest number to plan on is basis A.', flush=True)
    print('DONE', flush=True)
