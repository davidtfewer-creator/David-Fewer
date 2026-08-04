"""
Re-fit NVDA and AVGO with the 12-week maximum hold in place.

The cap was validated with parameters frozen, which is the right structural test but leaves one
loose end: those parameters were fitted with no cap. The cap fires only 8 times in 2.3 years so
the interaction should be small, but "should be" is not a measurement, and the model is about to
be frozen.

Exhaustive grid on the two live parameters with the cap active, then the same walk-forward the
parameters have been held to throughout: fit on train weeks only, score unseen weeks against the
deployed values run with the cap. A consensus pass and the 169-cell neighbourhood follow.

The bar is the one every re-fit in this work has had to clear and only one has: beat the deployed
parameters out of sample in at least 2 of 3 folds, with parameters that do not scatter across
folds. Anything less and the answer is that the deployed values stand.
"""
import statistics, sys
from max_hold_test import run as wrun, _nvda_name, SPEC
from weekly_name import Name, pr

MAXWK = 12
CAPS = [round(0.02+0.005*i, 4) for i in range(37)]
PREMS = [round(0.02+0.005*i, 5) for i in range(37)]
PERT = (0.97, 1.03)
CUTS = (0.5, 0.667, 0.833, 1.0)


def name_for(s):
    return _nvda_name() if s == 'NVDA' else Name(s)


def seg(nm, c, q, w0, w1):
    r = wrun(nm, c, q, MAXWK, w0, w1)
    return r['ann'], r['trades'], r


def robust(nm, c, q, w0, w1, floor):
    def one(cc, qq):
        cc = min(max(cc, CAPS[0]), CAPS[-1]); qq = min(max(qq, PREMS[0]), PREMS[-1])
        a, t, _ = seg(nm, cc, qq, w0, w1)
        return -5.0 + t*1e-3 if t < floor else a
    base = one(c, q)
    sm = [one(c*f, q) for f in PERT] + [one(c, q*f) for f in PERT]
    return 0.5*base + 0.5*sum(sm)/len(sm)


def grid(nm, w0, w1, floor):
    best = None
    for c in CAPS:
        for q in PREMS:
            s = robust(nm, c, q, w0, w1, floor)
            if best is None or s > best[0]: best = (s, c, q)
    return best[1], best[2]


if __name__ == '__main__':
    for s in (sys.argv[1:] or ['NVDA', 'AVGO']):
        nm = name_for(s); N = nm.N
        dc, dq = SPEC[s]
        a_dep, t_dep, _ = seg(nm, dc, dq, 1, N-1)
        floor = max(8, int(0.4*t_dep))
        print(f'\n{"="*82}\n{s}: {N} weeks, 12-week cap active, floor {floor} trades', flush=True)
        print(f'  deployed  cap {dc:.4f} prem {dq:.4f} -> {a_dep*100:6.1f}%, {t_dep} trades',
              flush=True)
        bc, bq = grid(nm, 1, N-1, floor)
        a_opt, t_opt, _ = seg(nm, bc, bq, 1, N-1)
        print(f'  re-fitted cap {bc:.4f} prem {bq:.4f} -> {a_opt*100:6.1f}%, {t_opt} trades  '
              f'({(a_opt-a_dep)*100:+.1f}pp in sample)', flush=True)

        caps = [round(bc*(0.80+0.0333*i), 5) for i in range(13)]
        prems = [round(bq*(0.80+0.0333*i), 6) for i in range(13)]
        vals = sorted(seg(nm, c, q, 1, N-1)[0]*100 for c in caps for q in prems)
        print(f'  neighbourhood: median {statistics.median(vals):.1f}%  '
              f'25th {vals[len(vals)//4]:.1f}%  peak {vals[-1]:.1f}%  '
              f'within 10pp {sum(1 for v in vals if v > vals[-1]-10)}/169', flush=True)

        cuts = [int(N*f) for f in CUTS]
        print(f'\n  {"fold":5s}{"train":>10s}{"test":>10s}{"fitted":>18s}{"fitted OOS":>12s}'
              f'{"deployed OOS":>14s}{"winner":>11s}', flush=True)
        print('  ' + '-'*78, flush=True)
        wins = 0; d = []; picks = []
        for k in range(3):
            trhi = cuts[k]; telo, tehi = cuts[k], cuts[k+1]-1
            _, ttr, _ = seg(nm, dc, dq, 1, trhi-1)
            c, q = grid(nm, 1, trhi-1, max(4, int(0.4*ttr)))
            picks.append((c, q))
            a, _, _ = seg(nm, c, q, telo, tehi)
            b, _, _ = seg(nm, dc, dq, telo, tehi)
            wins += (a > b); d.append((a-b)*100)
            print(f'  {k+1:<5d}{f"1-{trhi-1}":>10s}{f"{telo}-{tehi}":>10s}'
                  f'{f"{c:.3f}/{q:.3f}":>18s}{a*100:>11.1f}%{b*100:>13.1f}%'
                  f'{("fitted" if a > b else "deployed"):>11s}', flush=True)
        print('  ' + '-'*78, flush=True)
        print(f'  fitted beats deployed in {wins}/3; mean {statistics.mean(d):+.1f}pp', flush=True)
        print(f'  fold picks: ' + '  '.join(f'{c:.3f}/{q:.3f}' for c, q in picks), flush=True)
        for j, lbl in ((0, 'cap '), (1, 'prem')):
            v = [p[j] for p in picks]
            print(f'    {lbl} spread {min(v):.3f} - {max(v):.3f}   '
                  f'ratio {max(v)/max(min(v),1e-9):.2f}x', flush=True)
        cc = statistics.median(p[0] for p in picks); cq = statistics.median(p[1] for p in picks)
        w2 = 0; d2 = []
        for k in range(3):
            telo, tehi = cuts[k], cuts[k+1]-1
            a, _, _ = seg(nm, cc, cq, telo, tehi); b, _, _ = seg(nm, dc, dq, telo, tehi)
            w2 += (a > b); d2.append((a-b)*100)
        print(f'  consensus cap {cc:.3f} prem {cq:.3f}: beats deployed in {w2}/3, '
              f'mean {statistics.mean(d2):+.1f}pp', flush=True)
    print('\nDONE', flush=True)
