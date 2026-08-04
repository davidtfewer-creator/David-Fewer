"""
Walk-forward MU on the weekly Monday-tranche model.

MU came out of the 2.5 test as the strongest of the seven names on the weekly rule -- 124%
annualised at cap 0.035 / prem 0.18 -- which is high enough to be worth distrusting. It is
currently a daily-book name, so adopting it weekly would be a change, and every parameter fit
in this work that was not walk-forwarded has failed.

Same pipeline the other names went through: binding-constraint check, anchor sweep, exhaustive
grid on the two live parameters, the 169-cell neighbourhood around the optimum, three expanding
folds with a consensus pass, and the holding-period and terminal-mark checks.

MU uses its corrected and extended daily history to 3 August 2026, and its own 5-minute bars to
verify same-day exits.
"""
import statistics
import weekly_anchor_test as WAT
from mu_rerun import from_workbook
import five_min

five_min.FILES.setdefault('MU', '/root/.claude/uploads/'
                          '2d71f10a-e19f-51b2-8457-2cd547c34dff/94f1080f-MU_5min_Apr2024Aug2026.xlsx')
WAT.data['MU'] = from_workbook()
if 'MU' not in WAT.NAMES:
    WAT.NAMES.append('MU')

import weekly_name as WN
WN.DATA['MU'] = WAT.data['MU']

from weekly_name import Name, pr, report
from weekly_mr import P as MRP


if __name__ == '__main__':
    r = report('MU')
    nm = Name('MU'); N = nm.N
    cuts = [int(N*f) for f in (0.5, 0.667, 0.833, 1.0)]

    print('\n=== CONSENSUS AND HALF-SAMPLE (MU) ===', flush=True)
    picks = []
    for k in range(3):
        trhi = cuts[k]
        _, ttr = nm.seg(pr(r['cap'], r['prem']), 1, trhi-1)
        picks.append(nm.grid(1, trhi-1, max(4, int(0.4*ttr))))
    cc = statistics.median(p[0] for p in picks); cq = statistics.median(p[1] for p in picks)
    print(f'  fold picks: ' + '  '.join(f'{c:.3f}/{q:.3f}' for c, q in picks), flush=True)
    print(f'  consensus cap {cc:.3f} prem {cq:.3f}', flush=True)
    w = 0; d = []
    for k in range(3):
        telo, tehi = cuts[k], cuts[k+1]-1
        a, _ = nm.seg(pr(cc, cq), telo, tehi)
        b, _ = nm.seg(pr(r['cap'], r['prem']), telo, tehi)
        w += (a > b); d.append((a-b)*100)
        print(f'  fold {k+1}: consensus {nm.ann(a,telo,tehi)*100:7.1f}%   '
              f'full-sample fit {nm.ann(b,telo,tehi)*100:7.1f}%', flush=True)
    print(f'  consensus beats the full-sample fit in {w}/3; mean {statistics.mean(d):+.1f}pp',
          flush=True)
    rc, tc = nm.seg(pr(cc, cq), 1, N-1)
    print(f'  consensus full sample: {nm.ann(rc,1,N-1)*100:.1f}%, {tc} trades', flush=True)

    kc = next(i for i, wk in enumerate(nm.WS)
              if nm.DTS[wk['idxs'][0]] >= __import__('datetime').date(2025, 5, 23))
    for lbl, (c, q) in (('full-sample fit', (r['cap'], r['prem'])), ('consensus', (cc, cq))):
        a, _ = nm.seg(pr(c, q), 1, kc-1); b, _ = nm.seg(pr(c, q), kc, N-1)
        print(f'  {lbl:16s} first half {nm.ann(a,1,kc-1)*100:7.1f}%   '
              f'tested half {nm.ann(b,kc,N-1)*100:7.1f}%', flush=True)
    print('DONE', flush=True)
