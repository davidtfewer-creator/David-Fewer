"""
bear_brkb.py — BRK.B through the 2022 bear (user, 22 Oct 2026), live config:
ATH gate on (eps 0), 50-day stop, no PM rule (no bear-period cache). BRK.B's
2021-23 file was exported at 1-minute resolution and resampled by
ops/box_1min_to_5min.py; it starts 25 Oct 2021, so its own 200dma reading only
exists from ~mid-March 2022 (expanding window, 100-day minimum). No NVDA: its
1-minute file is too large for the Box connector.
"""
import collections
import functools
import json

import bear12_breadth as bb
from bear_replay import dma_gate_dates
from bear_stop import CAP, NAMES as ELEVEN
from book_sim import simulate
from recap_9v12 import arms

EPS = 0.0


def main():
    out = {}
    orig = bb.run_model
    bb.run_model = functools.partial(orig, ath_target_guard=EPS)
    for book, names, Ks in (('eleven', list(ELEVEN), (6,)), ('+BRKB', list(ELEVEN) + ['BRKB'], (6, 7))):
        bb.NAMES = names
        data, sleeves, bcal = bb.build()
        breach = {x: dma_gate_dates(data[x]['dts'], data[x]['C']) for x in names}
        cnt = collections.Counter(dd for x in names for dd in breach[x])
        gk = {K: {x: {dd for dd in breach[x] if cnt[dd] >= K} for x in names} for K in Ks}
        for tag, kw in arms(gk, breach):
            r = simulate(data, sleeves, bcal, capital=CAP, collect_trades=True,
                         date_lo=bb.Y0, date_hi=bb.END, **kw)
            c, eq = r['cal'], r['equity']
            i22 = max(i for i, x in enumerate(c) if x <= bb.Y1)
            yrs = len(c) / 252
            pn = collections.defaultdict(float)
            for t in r['trades']:
                if t['exit'] <= bb.Y1:
                    pn[t['name']] += t['pnl']
            b = [t for t in r['trades'] if t['name'] == 'BRKB']
            row = dict(y2022=eq[i22] / eq[0] - 1, to_jun23=eq[-1] / eq[0] - 1, maxdd=r['maxdd'],
                       fills_yr=r['fills'] / yrs, brkb_fills_yr=len(b) / yrs,
                       brkb_pnl_2022=pn.get('BRKB', 0.0), pnl_2022=dict(pn))
            out[f'{book} | {tag}'] = row
            print(f'{book:7s}{tag:20s} 2022 {row["y2022"]*100:6.1f}%  to Jun23 {row["to_jun23"]*100:6.1f}%'
                  f'  maxDD {row["maxdd"]*100:5.1f}%  fills/yr {row["fills_yr"]:4.0f}'
                  + (f'  | BRKB {row["brkb_fills_yr"]:.0f}/yr, 2022 realised ${row["brkb_pnl_2022"]/1e3:+.0f}k'
                     if b else ''), flush=True)
    bb.run_model = orig
    json.dump(out, open('bear_brkb.json', 'w'), indent=1, default=str)


if __name__ == '__main__':
    main()
