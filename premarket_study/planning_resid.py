"""
Re-derive the planning figures with the corrected OU sleeve.

The planning basis has been, throughout: the 50/50 result plus whatever the Bayes tilt is worth
OUT OF SAMPLE, which was about +2pp against an in-sample curve suggesting +8. Both halves of that
have to be recomputed on the corrected sleeve -- the 50/50 level moves, and the tilt's realised
value may move with it, since the tilt was measured against a mis-specified OU.

The tilt gain is measured directly rather than by choosing: 75% and 50/50 are both frozen and
scored on unseen sessions across three expanding folds per name. Choosing the share on the
training window is a different and weaker question, already answered in the split re-test.

Weekly names are unaffected -- the correction fails out of sample on them and is not deployed
there -- so their planning figures stand.
"""
import copy, datetime, statistics
from engine import run_model
from daily_window_split import data, params
from five_min import make_checker as fm
from mu_rerun import from_workbook

data['MU'] = from_workbook()
DAILY = ['RKLB', 'TSM', 'VST', 'VRT', 'MU']
BUF = {'RKLB': 0.25, 'TSM': 0.20, 'VST': 0.65, 'VRT': 0.40, 'MU': 0.75}
WEEKLY_PLAN = {'NVDA': 58, 'AVGO': 60}
CUTS = (0.5, 0.667, 0.833, 1.0)
CHK = {}


def chk(s):
    if s not in CHK: CHK[s] = fm(s, data[s][0], data[s][1])[0]
    return CHK[s]


def curve(s, mode, bayes):
    dts, O, H, L, C = data[s]
    p = copy.copy(params[s]); p.bayes_pct = bayes
    if mode == 'resid': p.ou_buf_k = BUF[s]
    p.years = (dts[-1]-dts[0]).days/365.25
    r = run_model(dts, O, H, L, C, p, ou_sigma=mode, collect=True, same_day_exit=chk(s))
    return dts, r.frames['equity']


def ann(eq, dts, lo, hi):
    d = (dts[hi]-dts[lo]).days
    return ((eq[hi]/eq[lo])**(365.25/d)-1)*100 if eq[lo] > 0 and d else float('nan')


if __name__ == '__main__':
    print('=== 1. THE 50/50 LEVEL, old sleeve vs corrected ===')
    print(f'{"stock":7s}{"old 50/50":>12s}{"new 50/50":>12s}{"change":>9s}'
          f'{"old 75%":>10s}{"new 75%":>10s}')
    lv = {}
    for s in DAILY:
        row = {}
        for m in ('level', 'resid'):
            for b in (0.5, 0.75):
                d, e = curve(s, m, b); row[(m, b)] = ann(e, d, 0, len(d)-1)
        lv[s] = row
        print(f'{s:7s}{row[("level",0.5)]:>11.0f}%{row[("resid",0.5)]:>11.0f}%'
              f'{row[("resid",0.5)]-row[("level",0.5)]:>+8.0f}pp'
              f'{row[("level",0.75)]:>9.0f}%{row[("resid",0.75)]:>9.0f}%')

    print('\n=== 2. WHAT THE TILT IS WORTH OUT OF SAMPLE (75% vs 50/50, both frozen) ===')
    for m in ('level', 'resid'):
        d_ = []; wins = tot = 0
        for s in DAILY:
            dts = data[s][0]; N = len(dts); cuts = [int(N*f) for f in CUTS]
            e50 = curve(s, m, 0.5)[1]; e75 = curve(s, m, 0.75)[1]
            for j in range(3):
                lo, hi = cuts[j], cuts[j+1]-1
                a = e75[hi]/e75[lo]-1; b = e50[hi]/e50[lo]-1
                wins += (a > b); tot += 1; d_.append((a-b)*100)
        print(f'  {m:6s} 75% beats 50/50 in {wins:2d}/{tot} folds; '
              f'mean {statistics.mean(d_):+.1f}pp  median {statistics.median(d_):+.1f}pp')
        if m == 'level': tilt_old = statistics.mean(d_)
        else: tilt_new = statistics.mean(d_)

    print('\n=== 3. PLANNING FIGURES ===')
    print(f'{"stock":7s}{"model":>9s}{"50/50":>9s}{"tilt":>8s}{"planning":>11s}'
          f'{"previous":>11s}')
    plans = {}
    for s in DAILY:
        base = lv[s][('resid', 0.5)]
        plans[s] = base + tilt_new
        prev = {'RKLB': 97, 'TSM': 51, 'VST': 54, 'VRT': 44, 'MU': 50}[s]
        print(f'{s:7s}{"daily":>9s}{base:>8.0f}%{tilt_new:>+7.1f}{plans[s]:>10.0f}%'
              f'{prev:>10d}%')
    for s, v in WEEKLY_PLAN.items():
        plans[s] = v
        print(f'{s:7s}{"weekly":>9s}{"--":>9s}{"--":>8s}{v:>10d}%{v:>10d}%')
    allp = [plans[s] for s in DAILY + list(WEEKLY_PLAN)]
    exr = [plans[s] for s in DAILY + list(WEEKLY_PLAN) if s != 'RKLB']
    print(f'\n  book planning        {statistics.mean(allp):5.0f}%   (was 59%)')
    print(f'  book planning ex-RKLB {statistics.mean(exr):4.0f}%   (was 53%)')
    print(f'  daily five only       {statistics.mean([plans[s] for s in DAILY]):4.0f}%')
    print('DONE')
