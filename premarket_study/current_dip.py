"""
current_dip.py — the live book is ~$6.9m -> ~$6.1m in about two weeks.
How does that compare with the twelve-name book's own record?

Depth and SPEED are different questions and the answer differs between them,
so both are measured. The conditional "what happened next" is also computed,
with its sample size stated, because the archive contains very few episodes
this deep and a percentage from n=1 would be false precision.
"""
import json
import statistics
import sys

from baseline_check import ROSTER
from book12 import pm_rule_for
from book_sim import load_all, simulate
from cf_speed_g5 import params_from_vec
from cf_swap_test import t0
from fresh_opt_cands import aw_params
from parallel_book import load_rho, load_vecs
from two_day import x0_vector

HIGH, NOW, SESS = 6_900_000.0, 6_100_000.0, 10
ADDED = ['RTX', 'DE', 'NVDA']


def main():
    drop = NOW/HIGH - 1
    print('BOOK:', 'NINE (live)' if '--nine' in sys.argv else 'TWELVE')
    print(f'live: ${HIGH/1e6:.2f}m -> ${NOW/1e6:.2f}m over ~{SESS} sessions '
          f'= {drop*100:.1f}%\n')
    rho, vecs = load_rho(), load_vecs()
    c = json.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
          'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    for n in ADDED:
        r = rho.get(n)
        po[n] = params_from_vec(vecs[n] if (r is not None and r >= 0.20 and n in vecs)
                                else x0_vector(1), t0())
    names = ROSTER if '--nine' in sys.argv else ROSTER + ADDED
    d, s, cal = load_all(names=names, params_override=po)
    r = simulate(d, s, cal, capital=HIGH, mode='pooled', collect_trades=True,
                 excl_fn=pm_rule_for(d, set(names)))
    eq, N = r['equity'], len(cal)
    peak, dd = eq[0], []
    for v in eq:
        peak = max(peak, v)
        dd.append((peak - v)/peak)

    print('=== 1. SPEED: every 10-session window in the archive ===\n')
    w = [(eq[i]/eq[i-SESS] - 1) for i in range(SESS, N)]
    worse = sum(1 for x in w if x <= drop)
    print(f'  {len(w)} windows. {worse} were as bad or worse than {drop*100:.1f}% '
          f'({worse/len(w)*100:.1f}%)')
    print(f'  percentile of the current move : {sum(1 for x in w if x < drop)/len(w)*100:.1f}th')
    print(f'  worst 10-session window        : {min(w)*100:.1f}%')
    for q in (0.01, 0.05, 0.25, 0.50):
        print(f'  {q*100:>4.0f}th percentile window      : {sorted(w)[int(len(w)*q)]*100:>6.1f}%')

    print('\n=== 2. DEPTH: how often is the book this far off its high ===\n')
    deeper = sum(1 for x in dd if x >= -drop)
    print(f'  sessions at or beyond {-drop*100:.1f}% off the high: {deeper} of {N} '
          f'({deeper/N*100:.1f}%)')
    print(f'  deepest in the archive                : {max(dd)*100:.1f}%')

    print('\n=== 3. WHAT HAPPENED NEXT, from this depth ===\n')
    hits, i = [], 1
    while i < N:
        if dd[i] >= -drop and dd[i-1] < -drop:          # first crossing
            j, trough = i, dd[i]
            while j < N and dd[j] > 1e-9:
                trough = max(trough, dd[j])
                j += 1
            hits.append((cal[i], trough, (j - i) if j < N else None))
            i = j
        i += 1
    print(f'  episodes that ever reached {-drop*100:.1f}% off the high: {len(hits)}')
    for d0, tr, rec in hits:
        print(f'    crossed {d0}  went on to {tr*100:.1f}%  '
              + (f'back to the high {rec} sessions after crossing'
                 if rec else 'not recovered by archive end'))
    if len(hits) < 3:
        print(f'\n  >>> n = {len(hits)}. Too few to quote a probability from. What this')
        print(f'      says is that a drop of this size is RARE in the record, not what')
        print(f'      typically follows one.')

    print('\n=== 4. THE COMPARISON THAT ACTUALLY FITS ===\n')
    print(f'  worst episode (Feb-Apr 2025): 20.9% over 32 sessions '
          f'= {20.9/32:.2f}%/session')
    print(f'  the current move            : {-drop*100:.1f}% over {SESS} sessions '
          f'= {-drop*100/SESS:.2f}%/session')
    print(f'  worst 5 sessions in archive : -12.61% = 2.52%/session')
    json.dump(dict(drop=drop, windows=len(w), worse=worse,
                   pctile=sum(1 for x in w if x < drop)/len(w),
                   worst_window=min(w), deeper_sessions=deeper, n_sessions=N,
                   episodes=[(str(a), b, c) for a, b, c in hits]),
              open('current_dip_nine.json' if '--nine' in sys.argv else 'current_dip.json', 'w'), indent=1)
    print('\nwrote current_dip.json')


if __name__ == '__main__':
    main()
