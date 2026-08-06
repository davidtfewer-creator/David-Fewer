"""Regression: with one slot the split runner must BE the engine, to the penny."""
import ramp_premium as R
from split_tranche import run_split

for stock in ('NVDA', 'AVGO'):
    d, O, H, L, C = R.load_feed(stock)
    p, cached = R.load_params(stock, years=2.2)
    idx = R.build_index(stock)
    for mode in ('sheet', 'none', 'verified'):
        sde = {'sheet': True, 'none': False}.get(mode) if mode != 'verified' \
            else R.make_checker(idx, d, O)
        base = R.run(stock, ramp=None, mode=mode, p=p, data=(d, O, H, L, C), idx=idx)
        for treatment in ('split', 'pool'):
            one = run_split(d, O, H, L, C, p, n_slots=1, ou_sigma='level',
                            same_day_exit=sde, treatment=treatment)
            assert abs(one['profit'] - base.profit) < 1e-6, \
                f'{stock}/{mode}/{treatment}: {one["profit"]:.6f} vs {base.profit:.6f}'
            assert one['total_buys'] == base.total_buys, \
                f'{stock}/{mode}/{treatment}: {one["total_buys"]} vs {base.total_buys}'
            print(f'  {stock:5s} {mode:9s} {treatment:5s} n_slots=1 == engine   '
                  f'profit {one["profit"]:15,.2f}  buys {one["total_buys"]:4d}')
    # and the sheet-rule run must still be the workbook itself
    sheet = run_split(d, O, H, L, C, p, n_slots=1, ou_sigma='level', same_day_exit=True)
    assert abs(sheet['profit'] - cached['profit']) < 1e-6
    print(f'  {stock:5s} matches the workbook cached profit {cached["profit"]:,.2f}\n')
print('ALL PASS')
