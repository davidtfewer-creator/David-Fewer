"""
The April 2024 episode, day by day: how fast down, how fast back.

The user's memory of "an event the model couldn't protect against" located to
April 2024 (episode_compare.py ranked its worst 3-session window 29th of 635,
almost exactly today's 25th). This traces the whole episode at daily resolution
and puts today's path alongside it on the same axes.

CAVEAT ON THE LEFT EDGE: the Query sheet starts 2024-04-01. If the pre-drop peak
was in late March the top is outside the data and the fall is understated. The
script reports where the local peak sits relative to the first row so that is
visible rather than assumed.

Book index = equal-weight average of the nine names' closes, rebased.

Usage:  python3 april2024.py <workbook.xlsx> [--pm -0.025]
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
    wb, dts, px = load_query(path)
    idx = [statistics.fmean([px[n][j]/px[n][0] for n in BOOK]) for j in range(len(dts))]

    # locate the April 2024 episode: peak, trough, recovery
    # constrain to APRIL: peak searched 1-15 Apr, trough to 30 Apr, recovery to 31 May.
    # A wider window finds the larger June 2024 episode instead, which is not the one asked about.
    p_hi = max(j for j, d in enumerate(dts) if d <= dt.date(2024, 4, 15))
    t_hi = max(j for j, d in enumerate(dts) if d <= dt.date(2024, 4, 30))
    r_hi = max(j for j, d in enumerate(dts) if d <= dt.date(2024, 5, 31))
    peak_i = max(range(0, p_hi + 1), key=lambda j: idx[j])
    trough_i = min(range(peak_i, t_hi + 1), key=lambda j: idx[j])
    rec_i = next((j for j in range(trough_i, r_hi + 1) if idx[j] >= idx[peak_i]), None)

    print(f'APRIL 2024 — book index (equal-weight, nine names)\n')
    print(f'  data starts {dts[0]}; local peak is row {peak_i} '
          f'({"AT THE LEFT EDGE - the top may be outside the data" if peak_i <= 2 else "inside the data"})')
    print(f'  peak     {dts[peak_i]}   index {idx[peak_i]:.4f}')
    print(f'  trough   {dts[trough_i]}   index {idx[trough_i]:.4f}   '
          f'= {(idx[trough_i]/idx[peak_i]-1)*100:+.1f}%')
    if rec_i:
        print(f'  recovered{dts[rec_i]}   index {idx[rec_i]:.4f}')
    dn_sess = trough_i - peak_i
    dn_cal = (dts[trough_i] - dts[peak_i]).days
    print(f'\n  DOWN: {dn_sess} sessions / {dn_cal} calendar days'
          f'   = {(idx[trough_i]/idx[peak_i]-1)*100/max(dn_sess,1):.2f}% per session')
    if rec_i:
        up_sess = rec_i - trough_i
        up_cal = (dts[rec_i] - dts[trough_i]).days
        print(f'  UP:   {up_sess} sessions / {up_cal} calendar days'
              f'   = {(idx[rec_i]/idx[trough_i]-1)*100/max(up_sess,1):.2f}% per session')
        print(f'  round trip peak-to-whole: {rec_i-peak_i} sessions / '
              f'{(dts[rec_i]-dts[peak_i]).days} calendar days')

    print(f'\n  day by day (index rebased to the peak = 100):')
    for j in range(peak_i, min((rec_i + 3) if rec_i else (trough_i + 12), len(dts))):
        bar = idx[j]/idx[peak_i]*100
        mark = ' <- peak' if j == peak_i else (' <- trough' if j == trough_i else
               (' <- whole' if rec_i and j == rec_i else ''))
        dayret = (idx[j]/idx[j-1]-1)*100 if j else 0
        print(f'    {dts[j]}  {bar:6.1f}   {dayret:+6.2f}%'
              f'  {"#"*max(0,int((bar-88)*2.2))}{mark}')

    print(f'\n  who fell, peak -> trough:')
    for n in BOOK:
        print(f'    {n:6s}{(px[n][trough_i]/px[n][peak_i]-1)*100:>7.1f}%'
              f'   recovery to {dts[rec_i] if rec_i else "-"}: '
              f'{(px[n][rec_i]/px[n][trough_i]-1)*100 if rec_i else float("nan"):>6.1f}%')
    print(f'    {"AI six":6s}{statistics.fmean([px[n][trough_i]/px[n][peak_i]-1 for n in AI])*100:>7.1f}%')
    print(f'    {"divers":6s}{statistics.fmean([px[n][trough_i]/px[n][peak_i]-1 for n in DIV])*100:>7.1f}%')

    # today on the same axes
    i = len(dts)-1
    t_peak = max(range(max(0, i-30), i+1), key=lambda j: idx[j])
    cur = idx[i]*(1+pm)
    print(f'\n{"="*72}\nTODAY on the same axes\n')
    print(f'  local peak {dts[t_peak]}   now {dts[i]} (+{pm*100:.1f}% pre-market)')
    print(f'  fall so far {(cur/idx[t_peak]-1)*100:+.1f}% over {i-t_peak} sessions / '
          f'{(dts[i]-dts[t_peak]).days} calendar days'
          f'   = {(cur/idx[t_peak]-1)*100/max(i-t_peak,1):.2f}% per session')
    print(f'\n  April 2024 fell {(idx[trough_i]/idx[peak_i]-1)*100:.1f}% in {dn_sess} sessions;'
          f' today is {(cur/idx[t_peak]-1)*100:.1f}% in {i-t_peak}.')
    json.dump(dict(peak=str(dts[peak_i]), trough=str(dts[trough_i]),
                   recovered=(str(dts[rec_i]) if rec_i else None),
                   depth=idx[trough_i]/idx[peak_i]-1,
                   down_sessions=dn_sess, up_sessions=(rec_i-trough_i if rec_i else None),
                   today_fall=cur/idx[t_peak]-1, today_sessions=i-t_peak),
              open('april2024.json', 'w'), indent=1)
    print('\nDONE', flush=True)


if __name__ == '__main__':
    main()
