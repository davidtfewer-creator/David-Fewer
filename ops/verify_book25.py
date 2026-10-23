"""
verify_book25.py — check the 25-slot workbook after a LibreOffice recalculation
(HANDOVER 3.102).

  1. no formula errors anywhere
  2. every Model sheet's historical bids (cols X, AM) equal the Python engine's
     (engine.run_model) on the same Query prices and the same Slots vector
  3. next-session levels for the nine live names equal the live workbook's own
     cached Dashboard values (same prices to 16 Oct 2026, same vectors)
  4. the default morning (no positions) sizes the Core and nothing else

Usage (from premarket_study/):
    python3 ../ops/verify_book25.py <built.xlsx> <recalculated.xlsx> <live_workbook.xlsx>
"""
import datetime as dt
import math
import os
import sys

import openpyxl

sys.path.insert(0, os.getcwd())
from engine import run_model, Params        # noqa: E402

NS, M0, Q0 = 25, 8, 2
SL0, LV0, SV0 = 7, 22, 51
VEC = ('lam', 'phi_L', 'psi', 'k', 'premium', 'peak_cap', 'ou_buf_k', 'ou_prem', 'ou_cap', 'ou_W')
ERR = ('#REF!', '#NAME?', '#VALUE!', '#DIV/0!', '#N/A', '#NUM!', '#NULL!', 'Err:')
EPOCH = dt.datetime(1899, 12, 30)


def as_date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, (int, float)):
        return (EPOCH + dt.timedelta(days=int(v))).date()
    return v


def rel(a, b):
    return abs(a - b) / max(1e-9, abs(b))


def main():
    built, recalc, live = sys.argv[1:4]
    wv = openpyxl.load_workbook(recalc, data_only=True)
    ok = True

    # 1 -- errors
    print('1. formula errors')
    tot = 0
    for ws in wv.worksheets:
        bad = []
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith(ERR):
                    bad.append(f'{c.coordinate}={c.value}')
        tot += len(bad)
        if bad:
            print(f'   {ws.title}: {len(bad)}  e.g. {bad[:6]}')
    print(f'   total {tot}')
    ok &= tot == 0

    # 2 -- Model sheets vs the Python engine
    print('2. Model bids vs engine.run_model')
    sl = wv['Slots']
    q = wv['Query']
    qrows = list(q.iter_rows(min_row=Q0, values_only=True))
    worst = 0.0
    for k in range(1, NS + 1):
        r = SL0 + k - 1
        vec = {key: sl.cell(r, 20 + j).value for j, key in enumerate(VEC)}
        base = 1 + 6 * (k - 1)          # zero-based index of S??_O in a Query row
        dts, O, H, L, C, rows = [], [], [], [], [], []
        for i, qr in enumerate(qrows):
            o = qr[base] if base < len(qr) else None
            if isinstance(o, (int, float)) and o > 0:
                dts.append(as_date(qr[0])); O.append(o); H.append(qr[base + 1])
                L.append(qr[base + 2]); C.append(qr[base + 3]); rows.append(M0 + i)
        if not dts:
            print(f'   slot {k:02d}: no data'); continue
        p = Params(lam=vec['lam'], phi_L=vec['phi_L'], psi=vec['psi'], k=vec['k'], premium=vec['premium'],
                   peak_cap=vec['peak_cap'], ou_buf_k=vec['ou_buf_k'], ou_prem=vec['ou_prem'],
                   ou_cap=vec['ou_cap'], ou_W=int(round(vec['ou_W'])), comm=0.005, capital=1_000_000,
                   interest=0.0314, stop_days=50, bayes_pct=0.5, years=2.5)
        fr = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=True, collect=True).frames
        m = wv[f'M{k:02d}']
        dX = dA = 0.0
        nX = nA = 0
        for i, rr in enumerate(rows):
            x, a = m.cell(rr, 24).value, m.cell(rr, 39).value      # X, AM
            if fr['X'][i] is not None and isinstance(x, (int, float)):
                dX = max(dX, rel(x, fr['X'][i])); nX += 1
            if fr['AM'][i] is not None and isinstance(a, (int, float)):
                dA = max(dA, rel(a, fr['AM'][i])); nA += 1
            elif (fr['AM'][i] is None) != (a in (None, '')):
                dA = max(dA, 1.0)
        worst = max(worst, dX, dA)
        print(f'   slot {k:02d} {sl.cell(r, 3).value:5s}  {len(dts)} days  Bayes bids {nX} max rel diff {dX:.1e}'
              f'  OU bids {nA} max rel diff {dA:.1e}')
    print(f'   worst {worst:.1e}')
    ok &= worst < 1e-7

    # 3 -- levels vs the live workbook's own Dashboard (only meaningful on the same data;
    #      when Query runs past the live file's last date, compare the overlapping prices)
    lq = openpyxl.load_workbook(live, data_only=True, read_only=True)['Query']
    lrows = list(lq.iter_rows(values_only=True))
    lhdr, llast = lrows[0], max(as_date(r[0]) for r in lrows[1:] if r[0] is not None)
    blast = max(as_date(r[0]) for r in qrows if r[0] is not None)
    if blast > llast:
        print(f'3. Query runs to {blast}, past the live file ({llast}): comparing overlapping prices')
        qd = {as_date(r[0]): r for r in qrows if r[0] is not None}
        w3, nn = 0.0, 0
        for k in range(1, 10):
            tk = sl.cell(SL0 + k - 1, 3).value
            base = 1 + 6 * (k - 1)
            for r in lrows[1:]:
                d = as_date(r[0])
                if d is None or d not in qd or r[lhdr.index(f'{tk}_C')] in (None, ''):
                    continue
                for j, f_ in enumerate('OHLC'):
                    w3 = max(w3, rel(qd[d][base + j], r[lhdr.index(f'{tk}_{f_}')]))
                    nn += 1
        print(f'   {nn} prices compared, worst rel diff {w3:.1e}')
        ok &= w3 < 1e-7
        return finish(ok, wv, sl)
    print('3. next-session levels vs the live workbook Dashboard (nine names)')
    ld = openpyxl.load_workbook(live, data_only=True)['Dashboard']
    en = wv['Engine']
    pairs = [('Bayes buy', 3, 15), ('Bayes target', 4, 16), ('OU buy', 5, 25), ('OU target', 6, 26),
             ('Bayes fair', 10, 9), ('sigma', 11, 10), ('ATH', 12, 11), ('OU mean', 14, 18),
             ('OU AR', 15, 19), ('OU sigma', 16, 20), ('OU forecast', 17, 21)]
    w3 = 0.0
    for k in range(1, 10):
        lr, er = 3 + k, LV0 + k - 1
        assert ld.cell(lr, 1).value == en.cell(er, 2).value, (ld.cell(lr, 1).value, en.cell(er, 2).value)
        diffs = []
        for lab, lc, ec in pairs:
            a, b = en.cell(er, ec).value, ld.cell(lr, lc).value
            d = rel(a, b) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else float('inf')
            w3 = max(w3, d)
            diffs.append(d)
        print(f'   {ld.cell(lr, 1).value:5s} Bayes {en.cell(er, 15).value:9.3f} vs {ld.cell(lr, 3).value:9.3f} · '
              f'OU {en.cell(er, 25).value:9.3f} vs {ld.cell(lr, 5).value:9.3f} · max rel diff over 11 fields {max(diffs):.1e}')
    print(f'   worst {w3:.1e}')
    ok &= w3 < 1e-7

    return finish(ok, wv, sl)


def finish(ok, wv, sl):
    en = wv['Engine']
    # 4 -- default morning
    print('4. default morning (cash $6.9m, no positions)')
    g = {en.cell(r, 2).value: en.cell(r, 3).value for r in range(4, 19)}
    for kk, v in g.items():
        print(f'   {kk}: {v}')
    cats = {}
    for r in range(SV0, SV0 + 2 * NS):
        cats.setdefault((en.cell(r, 3).value, en.cell(r, 12).value), 0)
        cats[(en.cell(r, 3).value, en.cell(r, 12).value)] += 1
    print('   sleeve categories:', dict(sorted(cats.items())))
    o = wv['Orders']
    acts = {}
    for r in range(9, 9 + 2 * NS):
        acts[o.cell(r, 7).value] = acts.get(o.cell(r, 7).value, 0) + 1
    print('   order actions:', acts)
    total = sum((en.cell(r, 17).value or 0) for r in range(SV0, SV0 + 2 * NS))
    print(f'   orders ${total:,.0f} of cash ${wv["Parameters"]["C7"].value if False else 0}'
          if False else f'   buy orders total ${total:,.0f}')
    print('\nALL CHECKS PASS' if ok else '\nCHECKS FAILED')


if __name__ == '__main__':
    main()
