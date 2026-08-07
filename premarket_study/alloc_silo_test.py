"""
Exercise the silo allocation across holding patterns the live sheet does not currently reach.

Today only VST's OU sleeve is holding, so the branch that matters most to the specification --
BOTH sleeves of a stock holding, and that stock's profit going to the others for the day -- is
never evaluated in the delivered workbook. This reimplements the written formulas exactly and
drives them through the cases that will occur.

Every scenario asserts the invariant that makes the change safe: the stock allocations must sum
to the cash available, so the blotter is neither starved nor over-committed.

Run:  python3 alloc_silo_test.py
"""
import itertools

import openpyxl

SRC = ('/root/.claude/uploads/822d405e-f99b-5b59-9c6b-87e725054402/'
       'c655e5aa-TradingExcel_5stock_live_silo.xlsx')
ROWS = (11, 12, 13, 14, 15)


def load():
    wv = openpyxl.load_workbook(SRC, data_only=True)
    a, t = wv['Allocation'], wv['Active Trading']
    names = [a[f'A{i}'].value for i in ROWS]
    prof, K, R, inc = {}, {}, {}, {}
    for i, n in zip(ROWS, names):
        K[i] = a[f'K{i}'].value or 0.0
        R[i] = a[f'R{i}'].value or 0.5
        inc[i] = a[f'B{i}'].value or 0
        prof[i] = next((t[f'C{r}'].value or 0.0) for r in range(7, 12)
                       if t[f'A{r}'].value == n)
    return names, prof, K, R, inc, a['B5'].value


def allocate(prof, K, R, inc, B5, held):
    """Exactly the arithmetic written into S:W and C25:C34."""
    total = sum(prof.values())
    base = B5 - total
    elig = {i: 1 if (inc[i] == 1 and not (held[i][0] and held[i][1])) else 0 for i in ROWS}
    released = sum(prof[i] for i in ROWS if not elig[i])
    vsum = sum(K[i] * elig[i] for i in ROWS)
    stock, sleeve = {}, {}
    for i in ROWS:
        w = 0.0 if not elig[i] else (
            ((base + released) * K[i] * elig[i] / vsum if vsum else 0.0) + prof[i])
        stock[i] = w
        hb, ho = held[i]
        den = R[i] * (1 - hb) + (1 - R[i]) * (1 - ho)
        sleeve[i] = (w * R[i] * (1 - hb) / den if den else 0.0,
                     w * (1 - R[i]) * (1 - ho) / den if den else 0.0)
    return stock, sleeve, base, released


def main():
    names, prof, K, R, inc, B5 = load()
    nm = dict(zip(ROWS, names))
    none_held = {i: (0, 0) for i in ROWS}

    scenarios = [
        ('live today  (VST OU holding)', {**none_held, 13: (0, 1)}, None),
        ('nothing holding', none_held, None),
        ('VST BOTH holding  (zero profit)', {**none_held, 13: (1, 1)}, 13),
        ('RKLB BOTH holding  (largest profit)', {**none_held, 14: (1, 1)}, 14),
        ('RKLB + MU BOTH holding', {**none_held, 14: (1, 1), 15: (1, 1)}, None),
        ('every sleeve holding', {i: (1, 1) for i in ROWS}, None),
        ('one sleeve holding on every stock', {i: (0, 1) for i in ROWS}, None),
    ]

    for label, held, focus in scenarios:
        stock, sleeve, base, released = allocate(prof, K, R, inc, B5, held)
        tot = sum(stock.values())
        allheld = all(held[i][0] and held[i][1] for i in ROWS)
        target = 0.0 if allheld else B5
        ok = abs(tot - target) < 0.01
        print(f'\n{label}')
        print(f'   base {base:>13,.2f}   released {released:>11,.2f}   '
              f'allocated {tot:>14,.2f}   {"OK" if ok else "MISMATCH"}')
        print('   ' + '  '.join(f'{nm[i]}={stock[i]:>11,.0f}' for i in ROWS))
        assert ok, f'conservation failed in: {label}'
        if focus is not None:
            assert abs(stock[focus]) < 1e-9, f'{nm[focus]} should get nothing'
            assert abs(released - prof[focus]) < 1e-9, 'released profit mismatch'
            others = [i for i in ROWS if i != focus]
            gain = sum(stock[i] for i in others) - (B5 - sum(prof.values())) \
                - sum(prof[i] for i in others)
            print(f"   -> {nm[focus]} gets nothing; its {prof[focus]:,.2f} of profit is "
                  f"shared over the other four (+{gain:,.2f} between them)")
        # no sleeve may be funded while holding
        for i in ROWS:
            for k in (0, 1):
                assert not (held[i][k] and sleeve[i][k] > 1e-9), \
                    f'{nm[i]} sleeve {k} funded while HOLDING'

    # ---- the guard case: profit exceeds cash on hand ---------------------------
    print('\nguard: profit to date exceeds cash on hand')
    small = 50_000.0
    stock, _s, base, _r = allocate(prof, K, R, inc, small, none_held)
    print(f'   B5 {small:,.2f} vs profit {sum(prof.values()):,.2f} -> base {base:,.2f}')
    print('   ' + '  '.join(f'{nm[i]}={stock[i]:>10,.0f}' for i in ROWS))
    print(f'   sums to {sum(stock.values()):,.2f} (still conserves); B47/B48 flag it in-sheet')
    assert abs(sum(stock.values()) - small) < 0.01

    print('\nall scenarios pass: allocations always sum to cash available, no holding '
          'sleeve is ever funded,\nand a fully-held stock always releases exactly its own '
          'profit to the rest.')


if __name__ == '__main__':
    main()
