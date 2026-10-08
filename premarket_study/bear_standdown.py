"""
bear_standdown.py — can decisive human stand-down replace the diversifiers?
(user, 8 Oct 2026)

The user's sharpened argument, which §3.41 did not test: a GRINDING bear is
both (a) what the diversifiers protect against and (b) what a person watching
daily can see coming. A sudden AI crash is unprotectable either way. So if the
protectable case is one you can also spot, the diversifiers are insurance
against a risk already covered by cheaper means — drop them, run the AI book,
take a one-year view.

My §3.41 reply cited §3.22 ("entry vetoes cannot protect inventory"), but that
finding is about FAST crashes. In a slow bear there is time to act, and acting
means SELLING, not just not buying. That is a different instrument and it was
never measured. book_sim gained `regime_exit` for it: on a signal, liquidate
everything at the open and place no orders until the signal clears.

Signal = the same breadth rule the gate uses (a fraction of the roster below
its own 200dma), so "spotting the bear" is held to a mechanical, strictly ex
ante standard rather than assumed to be prescient. Also reported: the
DETECTION LAG — how much of the fall had already happened when it first fired,
which is the honest limit on what any stand-down can save.

Both windows are run, because a rule that saves 2022 and costs 2024-26 is not
free.

Usage: BAYES_WORKBOOK=<workbook.xlsx> python bear_standdown.py
"""
import datetime
import json

import book_sim
from engine import run_model
from bear_replay import (_load, params_for, bear_checker, dma_gate_dates,
                         NAMES, Y22a, Y22b)
from live5_load import load as load_book

OUT = 'bear_standdown.json'
AI6 = ['TSM', 'VRT', 'VST', 'AVGO', 'MU', 'MRVL']
K_FRAC = 4 / 9
FULL_END = datetime.date(2023, 6, 30)


def build_bear():
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
    return data, {s: dma_gate_dates(data[s]['dts'], data[s]['C']) for s in NAMES}


def signal_dates(roster, gate, cal, frac=K_FRAC):
    k = max(1, round(frac * len(roster)))
    out = set()
    per = {s: set() for s in roster}
    for d in cal:
        below = [s for s in roster if d in gate[s]]
        if len(below) >= k:
            out.add(d)
            for s in below:
                per[s].add(d)
    return out, per, k


def sleeves_for(data, roster):
    sl = []
    for s in roster:
        p = data[s]['p']
        sl.append(dict(name=s, kind='B', bids='X', prem=p.premium))
        sl.append(dict(name=s, kind='O', bids='AM', prem=p.ou_prem))
    return sl


def cal_for(data, roster):
    common = None
    for s in roster:
        common = set(data[s]['dts']) if common is None else common & set(data[s]['dts'])
    return sorted(common)


def row(tag, r):
    eq = r['equity']
    return f'{(eq[-1]/eq[0]-1)*100:+7.1f}% DD{r["maxdd"]*100:5.1f}'


def main():
    data, gate = build_bear()
    res = {}
    for label, lo, hi in [('CALENDAR 2022', Y22a, Y22b),
                          ('FULL SPAN Jan 2022 - Jun 2023', Y22a, FULL_END)]:
        print(f'\n===== {label} =====')
        print(f'  {"roster":22s}{"n":>3s}{"nothing":>18s}{"gate (no new buys)":>21s}'
              f'{"STAND DOWN (sell all)":>24s}')
        for rlabel, roster in (('nine (current book)', NAMES), ('AI six only', AI6)):
            cal = cal_for(data, roster)
            sig, per, k = signal_dates(roster, gate, cal)
            sl = sleeves_for(data, roster)
            cap = 1_000_000 * len(roster)
            cells = []
            for kw in ({}, dict(no_buy=per), dict(regime_exit=sig)):
                r = book_sim.simulate(data, sl, cal, capital=cap, collect_trades=True,
                                      date_lo=lo, date_hi=hi, **kw)
                cells.append(row(rlabel, r))
                res[f'{label}|{rlabel}|{len(cells)}'] = dict(
                    total=r['equity'][-1] / r['equity'][0] - 1, maxdd=r['maxdd'])
            print(f'  {rlabel:22s}{len(roster):>3d}{cells[0]:>18s}{cells[1]:>21s}'
                  f'{cells[2]:>24s}')

    # ---- detection lag: what had already happened when the signal first fired
    print('\n===== DETECTION LAG in 2022 — the honest limit on any stand-down =====')
    for rlabel, roster in (('nine', NAMES), ('AI six', AI6)):
        cal = [d for d in cal_for(data, roster) if Y22a <= d <= Y22b]
        sig, per, k = signal_dates(roster, gate, cal)
        first = min(sig) if sig else None
        if first is None:
            print(f'  {rlabel}: never fired')
            continue
        # equal-weight buy-and-hold index of the roster, peak-to-signal
        idx0 = {s: data[s]['C'][data[s]['idx'][cal[0]]] for s in roster}
        series = [(d, sum(data[s]['C'][data[s]['idx'][d]] / idx0[s] for s in roster) / len(roster))
                  for d in cal]
        peak_d, peak_v = max(series[:len(series)], key=lambda t: t[1])
        at_sig = next(v for d, v in series if d == first)
        trough_d, trough_v = min(series, key=lambda t: t[1])
        print(f'  {rlabel:7s} signal needs {k}/{len(roster)} below their 200dma; '
              f'first fired {first} ({sum(1 for d in cal if d < first)} sessions into 2022)')
        print(f'          index peaked {peak_d} at {peak_v:.3f}, was {at_sig:.3f} when it fired '
              f'({(at_sig/peak_v-1)*100:+.1f}% from the peak), trough {trough_v:.3f} '
              f'({(trough_v/peak_v-1)*100:+.1f}%)')
        print(f'          so the fall was {(1-at_sig/peak_v)/(1-trough_v/peak_v)*100:.0f}% '
              f'complete before any stand-down could act; '
              f'{len(sig)} of {len(cal)} sessions flagged')

    with open(OUT, 'w') as f:
        json.dump(res, f, indent=1, default=str)
    print(f'\nsaved {OUT}')


if __name__ == '__main__':
    main()
