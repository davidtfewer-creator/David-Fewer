"""
Split-date sensitivity for the weekly half-sample freeze.

weekly_freeze.py cuts at the book's own split, 2025-05-23. NEM's train and test
halves picked opposite corners of the (cap, prem) box, which is the tell that a
surface has moved rather than been measured. If the frozen edge is real it should
survive moving the cut; if it is an artefact of where the blade happened to fall,
it will not.

Cuts at the base week and at +/-8 and +/-16 weeks. Each cut refits on its own train
half and scores its own test half, so the test halves differ -- compare each frozen
number against the NVDA-parameter number for the SAME test half, not across rows.

Usage:  python3 weekly_freeze_shift.py RTX NEM
"""
import json
import sys

from weekly_mr import P
from weekly_name import Name, pr
from weekly_freeze import cut_week, nbhd


def shift(stock, offsets=(-16, -8, 0, 8, 16)):
    nm = Name(stock)
    N, base = nm.N, cut_week(stock and nm)
    print(f'\n{"="*78}\n{stock}: {N} weeks, base cut week {base}', flush=True)
    print(f'{"cut":>5s}{"date":>13s}{"tr/te wks":>11s}{"NVDA te":>9s}{"frozen":>9s}'
          f'{"edge":>8s}{"cap/prem":>12s}{"nbhd med":>10s}{"trades":>8s}', flush=True)
    rows = []
    for off in offsets:
        cut = base + off
        if cut < 12 or N - cut < 12:
            continue
        r0, t0 = nm.seg(P, 1, cut-1)
        rt0, tt0 = nm.seg(P, cut, N-1)
        c, q = nm.grid(1, cut-1, max(4, int(0.4*t0)))
        rf, tf = nm.seg(pr(c, q), cut, N-1)
        a0 = nm.ann(rt0, cut, N-1)*100
        af = nm.ann(rf, cut, N-1)*100
        med, q25, _ = nbhd(nm, c, q, cut, N-1)
        d = nm.DTS[nm.WS[cut]['idxs'][0]]
        d = d.date() if hasattr(d, 'date') else d
        print(f'{cut:>5d}{str(d):>13s}{f"{cut-1}/{N-cut}":>11s}{a0:>8.1f}%{af:>8.1f}%'
              f'{af-a0:>+7.1f}p{f"{c:.3f}/{q:.3f}":>12s}{med:>9.1f}%{tf:>8d}', flush=True)
        rows.append(dict(stock=stock, cut=cut, date=str(d), nvda_test=a0, frozen_test=af,
                         edge_pp=af-a0, cap=c, prem=q, nbhd_test_median=med,
                         nbhd_test_q25=q25, test_trades=tf))
    beat = sum(1 for r in rows if r['edge_pp'] > 0)
    print(f'  frozen beats the no-fit baseline on {beat}/{len(rows)} cuts; '
          f'cap range {min(r["cap"] for r in rows):.3f}-{max(r["cap"] for r in rows):.3f}, '
          f'prem range {min(r["prem"] for r in rows):.3f}-{max(r["prem"] for r in rows):.3f}',
          flush=True)
    return rows


if __name__ == '__main__':
    out = []
    for s in (sys.argv[1:] or ['RTX', 'NEM']):
        out += shift(s)
    with open('weekly_freeze_shift.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('DONE', flush=True)
