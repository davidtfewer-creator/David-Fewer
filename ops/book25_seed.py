"""
book25_seed.py — the data the 25-slot workbook is built from (HANDOVER 3.102).

  * slot roster and tiers (ops/book25_design.md)
  * each slot's model vector: deployed_book17.json for the 17 live names, and
    lowdd_book.params (fitted if rho >= 0.20, else the neutral x0 vector) for
    the eight Shadow names
  * daily OHLC per slot from 2024-04-01: the live nine-name workbook's Query
    sheet for its nine names (official daily bars, to its last date); the
    5-minute archive's RTH daily bars for every other name
  * daily dollar volume and FIRST-HOUR dollar volume (09:30-10:30) from the
    5-minute archive where it carries volume — the liquidity cap's input

Usage (from premarket_study/):
    python3 ../ops/book25_seed.py <live_workbook.xlsx> <out.json>
"""
import datetime as dt
import json
import os
import sys

import openpyxl

sys.path.insert(0, os.getcwd())
from fresh_opt_cands import daily_from_5min      # noqa: E402
from lowdd_book import params                    # noqa: E402
import participation as P_                        # noqa: E402

SLOTS = [  # (ticker, tier)
    ('TSM', 'Core'), ('VRT', 'Core'), ('VST', 'Core'), ('AVGO', 'Core'), ('MU', 'Core'),
    ('GM', 'Core'), ('VLO', 'Core'), ('CF', 'Core'), ('MRVL', 'Core'), ('RTX', 'Core'),
    ('DE', 'Core'), ('NVDA', 'Core'),
    ('NEM', 'Bench'), ('LEN', 'Bench'), ('DLTR', 'Bench'), ('RKT', 'Bench'), ('TEAM', 'Bench'),
    ('PLTR', 'Shadow'), ('TSLA', 'Shadow'), ('RKLB', 'Shadow'), ('APLD', 'Shadow'),
    ('AAOI', 'Shadow'), ('CEG', 'Shadow'), ('UAL', 'Shadow'), ('LUNR', 'Shadow'),
]
LIVE_NINE = ['TSM', 'VRT', 'VST', 'AVGO', 'MU', 'GM', 'VLO', 'CF', 'MRVL']
KEYS = ('lam', 'phi_L', 'psi', 'k', 'premium', 'peak_cap', 'ou_buf_k', 'ou_prem', 'ou_cap', 'ou_W')
START = dt.date(2024, 4, 1)
EPOCH = dt.datetime(1899, 12, 30)


def as_date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, (int, float)):
        return (EPOCH + dt.timedelta(days=int(v))).date()
    return None


def live_query(path):
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True)['Query']
    rows = list(ws.iter_rows(values_only=True))
    hdr = rows[0]
    out = {n: {} for n in LIVE_NINE}
    for r in rows[1:]:
        d = as_date(r[0])
        if d is None or d < START:
            continue
        for n in LIVE_NINE:
            o, h, l, c = (r[hdr.index(f'{n}_{f}')] for f in 'OHLC')
            if all(isinstance(x, (int, float)) and x > 0 for x in (o, h, l, c)):
                out[n][d] = (float(o), float(h), float(l), float(c))
    return out


def volume(n):
    """{date: (dollar volume, first-hour dollar volume)} or {} without volume."""
    try:
        b = P_.load_bars(n)
    except FileNotFoundError:
        return {}
    if not any(x[3] > 0 for day in list(b.values())[:30] for x in day):
        return {}
    return {d: (sum(x[3] for x in v), sum(x[3] for x in v if x[0] < P_.HOUR1)) for d, v in b.items()}


def main():
    live_path, out_path = sys.argv[1], sys.argv[2]
    lq = live_query(live_path)
    dep = json.load(open('deployed_book17.json'))['params']
    shadow = [t for t, tier in SLOTS if tier == 'Shadow']
    po, basis = params(shadow)
    meta = json.load(open('book25_meta.json'))
    seed = {'slots': [], 'dates': None, 'built': str(dt.date.today())}
    alld = set()
    bars = {}
    for t, tier in SLOTS:
        if t in LIVE_NINE:
            ohlc = lq[t]
            src = 'live workbook Query'
        else:
            dts, O, H, L, C = daily_from_5min(t)
            ohlc = {d: (O[i], H[i], L[i], C[i]) for i, d in enumerate(dts) if d >= START}
            src = '5-minute archive (RTH daily)'
        vol = volume(t)
        bars[t] = (ohlc, vol)
        alld |= set(ohlc)
        vec = dep[t] if t in dep else {k: getattr(po[t], k) for k in KEYS}
        vb = ('deployed (live workbook / fitted)' if t in dep
              else basis.get(t, 'NEUTRAL'))
        seed['slots'].append(dict(ticker=t, tier=tier, vector={k: float(vec[k]) for k in KEYS},
                                  vector_basis=vb, source=src, beta=meta[t]['beta'],
                                  rho=meta[t]['rho'], rho_windows=meta[t]['recent'],
                                  first=str(min(ohlc)), last=str(max(ohlc)),
                                  vol_last=str(max(vol)) if vol else None))
    dates = sorted(d for d in alld if d >= START)
    seed['dates'] = [str(d) for d in dates]
    for s in seed['slots']:
        ohlc, vol = bars[s['ticker']]
        s['rows'] = [list(ohlc[d]) + list(vol.get(d, (None, None))) if d in ohlc else None
                     for d in dates]
        print(f"  {s['ticker']:5s} {s['tier']:6s} {s['first']} -> {s['last']}  vol to {s['vol_last']}"
              f"  {s['vector_basis']}")
    json.dump(seed, open(out_path, 'w'))
    print(f'  {len(dates)} dates {dates[0]} -> {dates[-1]}; wrote {out_path}')


if __name__ == '__main__':
    main()
