"""
bear_roster.py — in the one real bear we have, what actually did the
protecting: the diversifiers, or the gate? (user, 8 Oct 2026)

User's proposition: diversifier candidates keep failing, the AI names drive
the live book's return, and if the AI trade takes a 25% hit the diversifiers
will not save the book anyway — so should this be run as an avowedly AI
strategy, watched closely in a bear rather than structurally armoured?

Most of that is testable on the 2021-23 data (restored from Box, §3.34). The
claim that matters is the third one, and it decomposes: over calendar 2022,
how much of the book's protection came from HOLDING GM/VLO/CF, and how much
from the 200dma/breadth gate that would still be there without them?

Rosters:
  nine      the current book
  AI six    TSM VRT VST AVGO MU MRVL — the avowedly-AI book
  (and the AI six plus each diversifier singly, to price them one at a time)

Protection, applied identically to each roster:
  nothing | per-name 200dma gate | breadth gate
The breadth gate fires only when a FRACTION of the roster is below its own
200dma, so the rule means the same thing at different roster sizes; the
default 4/9 is §3.23's adopted K=4.

Invariance: the nine-name rows must reproduce §3.28b — unprotected −13.8%
(DD 23.7), breadth K=4 +1.7% (DD 15.7).

Usage: BAYES_WORKBOOK=<workbook.xlsx> python bear_roster.py
"""
import datetime
import json

import book_sim
from engine import run_model
from bear_replay import (_load, params_for, bear_checker, dma_gate_dates, wstat,
                         NAMES, Y22a, Y22b)
from live5_load import load as load_book

OUT = 'bear_roster.json'
AI6 = ['TSM', 'VRT', 'VST', 'AVGO', 'MU', 'MRVL']
DIVERS = ['GM', 'VLO', 'CF']
K_FRAC = 4 / 9                     # §3.23's adopted K=4 of nine, as a fraction
FULL_END = datetime.date(2023, 6, 30)


def build():
    _, book_params, _ = load_book()
    data = {}
    for s in NAMES:
        (dts, O, H, L, C), idx = _load(s)
        p = params_for(s, book_params)
        chk = bear_checker(idx, dts, O)
        r = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk,
                      collect=True)
        data[s] = dict(dts=dts, O=O, H=H, L=L, C=C, p=p,
                       idx={d: i for i, d in enumerate(dts)}, chk=chk,
                       X=r.frames['X'], AM=r.frames['AM'])
    gate = {s: dma_gate_dates(data[s]['dts'], data[s]['C']) for s in NAMES}
    return data, gate


def breadth_gate(roster, gate, cal, frac=K_FRAC):
    """A name is gated only when at least `frac` of the roster is below its own
    200dma that morning — §3.23's rule, expressed proportionally."""
    k = max(1, round(frac * len(roster)))
    out = {s: set() for s in roster}
    for d in cal:
        below = [s for s in roster if d in gate[s]]
        if len(below) >= k:
            for s in below:
                out[s].add(d)
    return out, k


def run(data, roster, kw, lo, hi, capital):
    sleeves = []
    for s in roster:
        p = data[s]['p']
        sleeves.append(dict(name=s, kind='B', bids='X', prem=p.premium))
        sleeves.append(dict(name=s, kind='O', bids='AM', prem=p.ou_prem))
    common = None
    for s in roster:
        common = set(data[s]['dts']) if common is None else common & set(data[s]['dts'])
    cal = sorted(common)
    r = book_sim.simulate(data, sleeves, cal, capital=capital, collect_trades=True,
                          date_lo=lo, date_hi=hi, **kw)
    return r, cal


def main():
    data, gate = build()
    rosters = [('nine (current book)', NAMES),
               ('AI six only', AI6),
               ('AI six + GM', AI6 + ['GM']),
               ('AI six + VLO', AI6 + ['VLO']),
               ('AI six + CF', AI6 + ['CF'])]
    res = {}
    for label, lo, hi in [('CALENDAR 2022', Y22a, Y22b),
                          ('FULL SPAN Jan 2022 - Jun 2023', Y22a, FULL_END)]:
        print(f'\n===== pooled book, {label} =====')
        print(f'  {"roster":22s}{"n":>3s}  {"nothing":>16s}{"per-name gate":>18s}'
              f'{"breadth gate":>18s}')
        for rlabel, roster in rosters:
            cap = 1_000_000 * len(roster)
            _, cal = run(data, roster, {}, lo, hi, cap)
            bg, k = breadth_gate(roster, gate, cal)
            cells = []
            for kw in ({}, dict(no_buy={s: gate[s] for s in roster}), dict(no_buy=bg)):
                r, _ = run(data, roster, kw, lo, hi, cap)
                eq = r['equity']
                tot = eq[-1] / eq[0] - 1
                cells.append(f'{tot*100:+7.1f}% DD{r["maxdd"]*100:5.1f}')
                res[f'{label}|{rlabel}|{len(cells)}'] = dict(
                    total=tot, maxdd=r['maxdd'], fills=r['fills'], k=k)
            print(f'  {rlabel:22s}{len(roster):>3d}  ' + ''.join(f'{c:>18s}' for c in cells))
        print(f'  (breadth gate fires at {round(K_FRAC*9)}/9 for the nine, '
              f'{round(K_FRAC*6)}/6 for the six — the same proportion)')

    with open(OUT, 'w') as f:
        json.dump(res, f, indent=1, default=str)
    print(f'\nsaved {OUT}')


if __name__ == '__main__':
    main()
