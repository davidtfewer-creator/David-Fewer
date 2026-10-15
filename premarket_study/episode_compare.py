"""
Is this the kind of event the model cannot protect against?

§3.22 established the distinction that matters: an entry veto cannot protect a
book through a FAST, BROAD fall, because the damage sits in held inventory and
no rule about new orders touches it. A slow, narrow decline is a different
animal -- the gate works, positions rotate out, cash recycles.

So "is this like April" is answerable on three axes rather than on impression:

  SPEED    how much of the fall arrived in how few sessions
  BREADTH  how many of the nine fell together
  HEDGE    did GM, VLO and CF fall WITH the book, or hold up

The third is the one that separates a sector drawdown from a market event. §3.23
found 2022's plateau was exactly six names below their 200dma with the three
diversifiers holding; §6 found the diversifiers halved the Jan-Apr 2025 loss.
When the diversifiers go too, there is nothing left in the book that is not the
same trade.

Every window in the sample is ranked by 3-session book move, so April locates
itself rather than being assumed. Prices are the workbook's Query sheet.

Usage:  python3 episode_compare.py <workbook.xlsx> [--pm -0.025] [--from 2026-10-09]
"""
import datetime as dt
import json
import statistics
import sys

from drawdown_now import BOOK, load_query

AI = ['TSM', 'VRT', 'VST', 'AVGO', 'MU', 'MRVL']
DIV = ['GM', 'VLO', 'CF']


def main():
    path = sys.argv[1]
    pm = float(sys.argv[sys.argv.index('--pm')+1]) if '--pm' in sys.argv else 0.0
    ref = (dt.date.fromisoformat(sys.argv[sys.argv.index('--from')+1])
           if '--from' in sys.argv else dt.date(2026, 10, 9))
    wb, dts, px = load_query(path)
    i0 = max(i for i, d in enumerate(dts) if d <= ref)

    print(f'DROPS FROM {dts[i0]} CLOSE  ->  {dts[-1]} close'
          f'{f", plus {pm*100:+.1f}% pre-market" if pm else ""}\n')
    print(f'{"name":6s}{"9 Oct":>10s}{"14 Oct":>10s}{"drop":>9s}{"+pm":>9s}'
          f'{"$ held":>12s}   group')
    # shares held, from the blotter, to weight the drop by actual exposure
    at = wb['Active Trading']
    held = {}
    for r in range(19, 37):
        nm = at.cell(row=r, column=1).value
        st = at.cell(row=r, column=3).value
        sh = at.cell(row=r, column=8).value
        if isinstance(nm, str) and nm.strip() in BOOK and st == 'HOLDING' and sh:
            held[nm.strip()] = held.get(nm.strip(), 0) + float(sh)
    tot_now = tot_then = 0.0
    rows = {}
    for nm in BOOK:
        C = px[nm]
        d = C[-1]/C[i0] - 1
        dp = (C[-1]*(1+pm))/C[i0] - 1
        sh = held.get(nm, 0.0)
        tot_then += sh*C[i0]
        tot_now += sh*C[-1]*(1+pm)
        rows[nm] = dict(ref=C[i0], last=C[-1], drop=d, drop_pm=dp, shares=sh,
                        value_now=sh*C[-1]*(1+pm))
        print(f'{nm:6s}{C[i0]:>10.2f}{C[-1]:>10.2f}{d*100:>8.1f}%{dp*100:>8.1f}%'
              f'{sh*C[-1]*(1+pm):>12,.0f}   {"AI" if nm in AI else "diversifier"}',
              flush=True)
    print(f'\n  equal-weight book: {statistics.fmean([rows[n]["drop_pm"] for n in BOOK])*100:+.1f}%')
    print(f'  AI six           : {statistics.fmean([rows[n]["drop_pm"] for n in AI])*100:+.1f}%')
    print(f'  diversifiers     : {statistics.fmean([rows[n]["drop_pm"] for n in DIV])*100:+.1f}%')
    print(f'  HELD INVENTORY   : {tot_now - tot_then:+,.0f} on {tot_then:,.0f} '
          f'= {(tot_now/tot_then - 1)*100:+.1f}%   (what a veto cannot touch)')

    # ---- rank every 3-session window in the sample
    R = {n: [px[n][i]/px[n][i-1] - 1 for i in range(1, len(dts))] for n in BOOK}
    book = [statistics.fmean([R[n][i] for n in BOOK]) for i in range(len(dts)-1)]
    W = 3
    wins = []
    for s in range(len(book) - W + 1):
        c = 1.0
        for k in range(s, s + W):
            c *= 1 + book[k]
        e = s + W                                   # dts index at window end
        nfall = sum(1 for n in BOOK if px[n][e] < px[n][s])
        div = statistics.fmean([px[n][e]/px[n][s] - 1 for n in DIV])
        ai = statistics.fmean([px[n][e]/px[n][s] - 1 for n in AI])
        wins.append(dict(start=dts[s], end=dts[e], move=c-1, breadth=nfall,
                         ai=ai, div=div))
    wins.sort(key=lambda w: w['move'])
    cur = (1 + statistics.fmean([rows[n]['drop'] for n in BOOK]))*(1+pm) - 1

    print(f'\n{"="*92}\nTHE TEN WORST 3-SESSION BOOK MOVES IN THE SAMPLE\n')
    print(f'{"window":26s}{"book":>8s}{"AI six":>9s}{"divers":>9s}'
          f'{"n fell":>8s}   hedge held?')
    for w in wins[:10]:
        hedge = 'YES' if w['div'] > -0.01 else ('partly' if w['div'] > w['ai'] + 0.02 else 'NO')
        print(f'{str(w["start"]) + " -> " + str(w["end"]):26s}{w["move"]*100:>7.1f}%'
              f'{w["ai"]*100:>8.1f}%{w["div"]*100:>8.1f}%{w["breadth"]:>8d}   {hedge}',
              flush=True)
    rank = sum(1 for w in wins if w['move'] <= cur)
    print(f'\n  TODAY ({cur*100:+.1f}% incl. pre-market) ranks {rank+1}th worst of '
          f'{len(wins)} three-session windows')
    print(f'  current: AI six {statistics.fmean([rows[n]["drop_pm"] for n in AI])*100:+.1f}%, '
          f'diversifiers {statistics.fmean([rows[n]["drop_pm"] for n in DIV])*100:+.1f}%, '
          f'{sum(1 for n in BOOK if rows[n]["drop_pm"] < 0)} of 9 fell')

    # ---- April, both years, located rather than assumed
    print(f'\n{"="*92}\nAPRIL, LOCATED\n')
    for yr in (2024, 2025):
        sel = [w for w in wins if w['end'].year == yr and w['end'].month == 4]
        if not sel:
            print(f'  April {yr}: no 3-session window ends in April {yr} '
                  f'(sample starts {dts[0]})')
            continue
        worst = min(sel, key=lambda w: w['move'])
        pos = sum(1 for w in wins if w['move'] <= worst['move'])
        print(f'  April {yr}: worst 3-session window {worst["start"]} -> {worst["end"]}  '
              f'book {worst["move"]*100:+.1f}%  (rank {pos} of {len(wins)})')
        print(f'            AI six {worst["ai"]*100:+.1f}%, diversifiers '
              f'{worst["div"]*100:+.1f}%, {worst["breadth"]} of 9 fell', flush=True)
        # and the month as a whole
        a = next(i for i, d in enumerate(dts) if d >= dt.date(yr, 4, 1))
        b = max(i for i, d in enumerate(dts) if d <= dt.date(yr, 4, 30))
        mb = statistics.fmean([px[n][b]/px[n][a] - 1 for n in BOOK])
        mai = statistics.fmean([px[n][b]/px[n][a] - 1 for n in AI])
        md = statistics.fmean([px[n][b]/px[n][a] - 1 for n in DIV])
        print(f'            whole month {dts[a]}..{dts[b]}: book {mb*100:+.1f}%, '
              f'AI {mai*100:+.1f}%, diversifiers {md*100:+.1f}%\n', flush=True)

    json.dump(dict(asof=str(dts[-1]), ref=str(dts[i0]), pm=pm, rows=rows,
                   current_move=cur, rank=rank+1, n_windows=len(wins),
                   worst10=[{**w, 'start': str(w['start']), 'end': str(w['end'])}
                            for w in wins[:10]]),
              open('episode_compare.json', 'w'), indent=1, default=str)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
