"""
Exercise the entitlement allocation across states the live sheet does not currently reach.

Today only VST's OU sleeve holds, so the cases that decide whether the rule is safe -- both
sleeves of a stock held, several stocks held, and the low-cash case that broke the previous
formulation -- are never evaluated in the delivered workbook. This drives the written arithmetic
through all of them.

Four invariants are asserted on every scenario:

  1. allocations sum to the cash available (nothing starved, nothing over-committed);
  2. no HOLDING sleeve is ever funded;
  3. no allocation is ever negative, at any level of deployed capital -- this is what the
     entitlement form buys over the earlier "cash minus profit" version;
  4. a held sleeve's entitlement never returns to its own stock, which is the concentration
     failure that motivated the change.

Run:  python3 alloc_silo_test.py
"""
from alloc_silo import STOCK_ROWS, allocate, read_inputs, sleeve_rows


def check(inp, held, label, expect_zero=None):
    r = allocate(inp, held)
    nm = dict(zip(STOCK_ROWS, inp['names']))
    tot = sum(r['sleeve'].values())
    print(f'\n{label}')
    print(f"   claim {r['tot']:>12,.0f}   factor {r['factor']:>5.3f}   "
          f"allocated {tot:>13,.2f}   idle {r['idle']:>12,.2f}")
    per = {i: r['sleeve'][sleeve_rows(i)[0]] + r['sleeve'][sleeve_rows(i)[1]]
           for i in STOCK_ROWS}
    print('   ' + '  '.join(f'{nm[i]}={per[i]:>10,.0f}' for i in STOCK_ROWS))

    assert tot <= inp['B5'] + 0.01, f'allocated more than cash: {label}'
    assert abs(tot + r['idle'] - inp['B5']) < 0.01, f'cash unaccounted for: {label}'
    for i in STOCK_ROWS:
        b, o = sleeve_rows(i)
        for row in (b, o):
            assert not (held[row] and r['sleeve'][row] > 1e-9), \
                f'{nm[i]} funded while HOLDING: {label}'
            assert r['sleeve'][row] >= -1e-9, f'negative allocation: {label}'
    # a stock with a held sleeve must receive nothing from the pool
    for i in STOCK_ROWS:
        b, o = sleeve_rows(i)
        if held[b] or held[o]:
            inbound = r['AB'][i] - r['W'][i]
            assert abs(inbound) < 1e-6, \
                f'{nm[i]} received inbound while holding: {label}'
    if expect_zero is not None:
        assert per[expect_zero] < 1e-6, f'{nm[expect_zero]} should get nothing'
    return r, per


def main():
    inp = read_inputs()
    nm = dict(zip(STOCK_ROWS, inp['names']))
    none_held = {r: 0 for r in range(25, 35)}

    def h(**kw):
        d = dict(none_held)
        for k, v in kw.items():
            i = [x for x in STOCK_ROWS if nm[x] == k][0]
            b, o = sleeve_rows(i)
            d[b], d[o] = v
        return d

    check(inp, h(), 'nothing holding')
    r, per = check(inp, h(VST=(0, 1)), 'live today  (VST OU holding)')
    print(f"   -> VST keeps only its own free half; its held half went to the other four")

    r, per = check(inp, h(VST=(1, 1)), 'VST BOTH holding', expect_zero=13)
    print(f"   -> VST gets nothing; its whole entitlement shared evenly over the other four")

    check(inp, h(RKLB=(1, 1)), 'RKLB BOTH holding  (largest profit)', expect_zero=14)
    check(inp, h(RKLB=(1, 1), MU=(1, 1)), 'RKLB + MU BOTH holding')
    check(inp, h(TSM=(0, 1), VRT=(0, 1), VST=(0, 1), RKLB=(0, 1), MU=(0, 1)),
          'one sleeve holding on every stock')
    check(inp, {r: 1 for r in range(25, 35)}, 'every sleeve holding')

    # ---- the case that broke the previous formulation --------------------------
    print('\nlow cash, heavy deployment  (what made "cash minus profit" go negative)')
    lean = dict(inp)
    lean['B5'] = 200_000.0
    lean['deployed'] = 3_611_540.33
    r2, per2 = check(lean, h(TSM=(1, 1), VRT=(1, 1), RKLB=(1, 1), MU=(0, 1)),
                     '   cash 200k, 3.6m deployed, four names largely held')
    print(f"   base capital stays positive at {r2['base']:,.0f}; "
          f"min allocation {min(r2['sleeve'].values()):,.2f}; "
          f"nothing exceeds cash")

    # ---- profit really is siloed ----------------------------------------------
    print('\nprofit siloing: allocation should track own profit, all else equal')
    r3, per3 = check(inp, h(), '   nothing holding, ranked by profit')
    rank = sorted(STOCK_ROWS, key=lambda i: -inp['prof'][i])
    print('   ' + '  '.join(f'{nm[i]}: profit {inp["prof"][i]:>8,.0f} -> '
                            f'{per3[i]:>10,.0f}' for i in rank))
    for x, y in zip(rank, rank[1:]):
        assert per3[x] >= per3[y] - 1e-6, 'more profit did not mean more capital'

    print('\nall scenarios pass: conserves to cash, never funds a holding sleeve, never '
          'negative,\nand a held sleeve never feeds its own stock.')


if __name__ == '__main__':
    main()
