"""
The same first-half / second-half blade, applied to the daily book.

The split eliminated PLTR from the weekly model: 365% over weeks 1-59 and 3.1% over 60-120. That
test is only fair if it is also run on the names being kept, so this applies the identical date
boundary to every name in the daily book, on verified fills.

The boundary is taken from the weekly model's week 59 so the daily and weekly halves cover the
same calendar, and every name is scored at the deployed 50/50 sleeve split rather than at the
in-sample Bayes tilt.

A name whose return sits mostly in the first half is in the same position PLTR was: the figure
exists, but the part of the sample that tested it does not support it.
"""
import copy, datetime, statistics
from stop_sweep import load_book
from engine import run_model
from five_min import make_checker as fm
from minute_engine import make_checker as nv
import five_min
from newcands import load as load_cand

five_min.FILES['MU'] = ('/root/.claude/uploads/2d71f10a-e19f-51b2-8457-2cd547c34dff/'
                        '94f1080f-MU_5min_Apr2024Aug2026.xlsx')

SURVIVORS = {'RKLB', 'VST', 'TSM', 'MU', 'VRT'}          # daily names that clear 50%
data, params, cached = load_book()

# MU comes from its own workbook rather than the book file
_mu = load_cand('MU')
data['MU'] = (_mu[0], _mu[1], _mu[2], _mu[3], _mu[4])
params['MU'] = _mu[5]


def boundary():
    """Last session of weekly week 59, so the daily halves match the weekly ones."""
    from weekly_anchor_test import group_weeks
    dts = data['NVDA'][0]
    wks = [w for w in group_weeks(dts, 0)]
    return dts[wks[59]['idxs'][-1] if isinstance(wks[59], dict) else wks[59][-1]]


def curve(stock, bayes=0.5):
    dts, O, H, L, C = data[stock]
    chk = nv(dts, O)[0] if stock == 'NVDA' else fm(stock, dts, O)[0]
    p = copy.copy(params[stock]); p.bayes_pct = bayes
    r = run_model(dts, O, H, L, C, p, collect=True, same_day_exit=chk)
    return dts, r.frames['equity']


def ann(eq, dts, lo, hi):
    if eq[lo] <= 0: return float('nan')
    yrs = (dts[hi] - dts[lo]).days/365.25
    return (eq[hi]/eq[lo])**(1/yrs) - 1


if __name__ == '__main__':
    cut = boundary()
    print(f'boundary date {cut} (last session of weekly week 59)\n')
    print(f'{"stock":7s}{"":3s}{"first half":>12s}{"second half":>13s}{"full":>9s}'
          f'{"shift":>10s}', flush=True)
    print('-'*56, flush=True)
    rows = []
    for s in sorted(data, key=lambda x: (x not in SURVIVORS, x)):
        dts, eq = curve(s)
        k = next(i for i, d in enumerate(dts) if d >= cut)
        a = ann(eq, dts, 0, k)*100
        b = ann(eq, dts, k, len(dts)-1)*100
        f = ann(eq, dts, 0, len(dts)-1)*100
        tag = '*' if s in SURVIVORS else ' '
        rows.append((s, a, b, f, tag))
        print(f'{s:7s}{tag:3s}{a:>11.1f}%{b:>12.1f}%{f:>8.1f}%{b-a:>+9.1f}pp', flush=True)
    print('-'*56, flush=True)
    sv = [r for r in rows if r[4] == '*']
    ot = [r for r in rows if r[4] == ' ']
    print(f'{"survivors":10s}mean first {statistics.mean(r[1] for r in sv):5.1f}%   '
          f'second {statistics.mean(r[2] for r in sv):5.1f}%', flush=True)
    print(f'{"others":10s}mean first {statistics.mean(r[1] for r in ot):5.1f}%   '
          f'second {statistics.mean(r[2] for r in ot):5.1f}%', flush=True)
    print('\n* = name kept in the seven-name book', flush=True)
    print('NVDA and AVGO are on the weekly model; their split is in weekly_window_split.py',
          flush=True)
