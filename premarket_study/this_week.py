"""
This week's drop, and what followed drops like it.

Scope set by the user: ignore the months-old drawdowns (VRT 153 days past its
peak, VST 387, CF 42). The question is the move that started Monday 12 October,
after the US inflation print pushed yields up, plus a further 2-3% indicated in
Tuesday's pre-market.

The method is a conditional distribution, not a story. Build the equal-weight
book return series, measure the current 3-session move, find every past window
with a move at least as bad, and report what happened over the following 5, 10,
20 and 50 sessions. That answers "has the book come back from drops like this"
with the sample rather than with an opinion.

Two things are deliberately NOT done. No attempt is made to identify past
episodes as rate shocks: with 638 sessions there are too few to condition on a
cause, and pretending otherwise would be reading tea leaves. And the forward
windows overlap, so the outcomes are not independent draws -- the counts below
describe the sample, they are not a probability with a standard error.

PRE-MARKET: the --pm argument shifts every name by that fraction to approximate
where today opens, so the event is measured as the user is living it rather than
as of last night's close.

Usage:  python3 this_week.py <workbook.xlsx> [--since 2026-10-12] [--pm -0.025]
"""
import datetime as dt
import json
import statistics
import sys

from drawdown_now import BOOK, load_query

FWD = (5, 10, 20, 50)


def main():
    path = sys.argv[1]
    since = dt.date(2026, 10, 12)
    pm = 0.0
    if '--since' in sys.argv:
        since = dt.date.fromisoformat(sys.argv[sys.argv.index('--since')+1])
    if '--pm' in sys.argv:
        pm = float(sys.argv[sys.argv.index('--pm')+1])
    wb, dts, px = load_query(path)

    # index of the last close BEFORE the event
    i0 = max(i for i, d in enumerate(dts) if d < since)
    n_sess = len(dts) - 1 - i0
    print(f'event window: {dts[i0]} close -> {dts[-1]} close  ({n_sess} sessions)'
          f'{f", plus {pm*100:+.1f}% pre-market" if pm else ""}\n')

    print(f'{"name":6s}{"pre-event":>11s}{"last":>10s}{"week":>9s}'
          f'{"+pm":>9s}{"20d before":>12s}')
    moves = {}
    for nm in BOOK:
        C = px[nm]
        w = C[-1]/C[i0] - 1
        wp = (C[-1]*(1+pm))/C[i0] - 1
        before = C[i0]/C[i0-20] - 1 if i0 >= 20 else None
        moves[nm] = dict(pre=C[i0], last=C[-1], week=w, week_pm=wp, before=before)
        print(f'{nm:6s}{C[i0]:>11.2f}{C[-1]:>10.2f}{w*100:>8.1f}%{wp*100:>8.1f}%'
              f'{(f"{before*100:+.1f}%" if before is not None else "-"):>12s}', flush=True)

    # equal-weight book return series
    R = []
    for i in range(1, len(dts)):
        R.append(statistics.fmean([px[n][i]/px[n][i-1] - 1 for n in BOOK]))
    cur = 1.0
    for i in range(i0, len(dts)-1):
        cur *= 1 + R[i]
    cur -= 1
    cur_pm = (1 + cur)*(1 + pm) - 1
    print(f'\n  BOOK (equal weight): {cur*100:+.1f}% over {n_sess} sessions, '
          f'{cur_pm*100:+.1f}% including pre-market')

    # every past window of the same length, cumulative
    wins = []
    for s in range(len(R) - n_sess):
        c = 1.0
        for k in range(s, s + n_sess):
            c *= 1 + R[k]
        wins.append((s + n_sess, c - 1))         # index AFTER the window
    worse = [w for w in wins if w[1] <= cur_pm]
    print(f'  past {n_sess}-session book moves at least this bad: {len(worse)} of {len(wins)} '
          f'({len(worse)/len(wins)*100:.0f}% of all windows)\n')

    print(f'{"="*78}\nWHAT FOLLOWED, from the {len(worse)} comparable episodes\n')
    print(f'{"horizon":>10s}{"n":>6s}{"median":>10s}{"mean":>9s}{"25th":>9s}'
          f'{"75th":>9s}{"% positive":>13s}{"worst":>9s}')
    res = {}
    for f in FWD:
        outs = []
        for end, _ in worse:
            if end + f >= len(R):
                continue
            c = 1.0
            for k in range(end, end + f):
                c *= 1 + R[k]
            outs.append(c - 1)
        if not outs:
            continue
        o = sorted(outs)
        res[f] = dict(n=len(o), median=statistics.median(o), mean=statistics.fmean(o),
                      q25=o[len(o)//4], q75=o[3*len(o)//4],
                      pct_pos=sum(1 for x in o if x > 0)/len(o)*100, worst=o[0])
        print(f'{f"+{f} sess":>10s}{len(o):>6d}{statistics.median(o)*100:>9.1f}%'
              f'{statistics.fmean(o)*100:>8.1f}%{o[len(o)//4]*100:>8.1f}%'
              f'{o[3*len(o)//4]*100:>8.1f}%'
              f'{sum(1 for x in o if x > 0)/len(o)*100:>12.0f}%{o[0]*100:>8.1f}%', flush=True)

    # unconditional, for comparison -- is the conditional distribution different at all?
    print(f'\n  UNCONDITIONAL (every window, for comparison)')
    print(f'{"horizon":>10s}{"n":>6s}{"median":>10s}{"mean":>9s}{"":18s}{"% positive":>13s}')
    for f in FWD:
        outs = []
        for s in range(len(R) - f):
            c = 1.0
            for k in range(s, s + f):
                c *= 1 + R[k]
            outs.append(c - 1)
        o = sorted(outs)
        res.setdefault('uncond', {})[f] = dict(median=statistics.median(o),
                                               mean=statistics.fmean(o),
                                               pct_pos=sum(1 for x in o if x > 0)/len(o)*100)
        print(f'{f"+{f} sess":>10s}{len(o):>6d}{statistics.median(o)*100:>9.1f}%'
              f'{statistics.fmean(o)*100:>8.1f}%{"":18s}'
              f'{sum(1 for x in o if x > 0)/len(o)*100:>12.0f}%', flush=True)

    # the 200dma breadth gate -- the rule the book already carries for this
    nb = 0
    gate = {}
    for nm in BOOK:
        C = px[nm]
        m = sum(C[-200:])/200 if len(C) >= 200 else None
        c_pm = C[-1]*(1 + pm)
        b = m is not None and c_pm < m
        gate[nm] = dict(sma200=m, gap=(c_pm/m - 1) if m else None, below=b)
        nb += bool(b)
    print(f'\n{"="*78}\nTHE RULE THE BOOK ALREADY CARRIES (§3.23, K=4)\n')
    print(f'{"name":6s}{"close+pm":>11s}{"200dma":>10s}{"gap":>9s}   state')
    for nm in BOOK:
        g = gate[nm]
        m = f"{g['sma200']:.2f}" if g['sma200'] else '-'
        gp = f"{g['gap']*100:+.1f}%" if g['gap'] is not None else '-'
        st = 'BELOW 200dma' if g['below'] else 'above'
        print(f'{nm:6s}{px[nm][-1]*(1+pm):>11.2f}{m:>10s}{gp:>9s}   {st}', flush=True)
    print(f'\n  breadth {nb} of 9 below their 200dma; gate fires at K=4  ->  '
          f'{"ON: entries suppressed for the names below" if nb >= 4 else "OFF: the rule says trade normally"}')
    json.dump(dict(asof=str(dts[-1]), since=str(since), pm=pm, moves=moves,
                   book=cur, book_pm=cur_pm, n_comparable=len(worse),
                   forward=res, breadth=nb, gate_on=nb >= 4, gate=gate),
              open('this_week.json', 'w'), indent=1, default=str)
    print('\nDONE', flush=True)


if __name__ == '__main__':
    main()
