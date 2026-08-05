"""
Check the free-sleeve allocation by evaluating the written formulas independently.

LibreOffice cannot open this workbook -- the original fails to load the same way, so it is the
file, not the edit -- which rules out a recalculation check. Instead every formula written into
Allocation!C25:F34 is re-derived here from the source workbook's cached values and compared, cell
by cell, against the string actually saved. A mismatch in either the arithmetic or the references
fails the run.

The arithmetic being checked:

    held_i   from Model!AE867 (Bayes) or Model!AL867 (OU)
    w_i      = K_stock x R_stock          for Bayes,   K_stock x (1 - R_stock) for OU
    f_i      = w_i x (1 - held_i)
    C_i      = B5 x f_i / sum(f)

and the two invariants that matter operationally: a held sleeve is allocated exactly zero, and
the free sleeves between them are allocated exactly B5.
"""
import openpyxl

SRC = ('/root/.claude/uploads/2d71f10a-e19f-51b2-8457-2cd547c34dff/'
       '3e1130ba-TradingExcel_5stock_live.xlsx')
OUT = '/home/user/David-Fewer/TradingExcel_5stock_live_freesleeves.xlsx'
NAMES = ['TSM', 'VRT', 'VST', 'RKLB', 'MU']


def main():
    sv = openpyxl.load_workbook(SRC, data_only=True)
    of = openpyxl.load_workbook(OUT, data_only=False)
    a = of['Allocation']
    sa = sv['Allocation']

    B5 = sa['B5'].value
    rows = []
    for i, s in enumerate(NAMES):
        srow = 11 + i
        K = sa.cell(srow, 11).value          # final weight
        R = sa.cell(srow, 18).value          # Bayes share used
        for t, tranche in enumerate(('Bayes', 'OU')):
            r = 25 + 2*i + t
            flag = 'AE' if tranche == 'Bayes' else 'AL'
            held = 1 if sv[f'Model {s}'][f'{flag}867'].value == 1 else 0
            w = K*R if tranche == 'Bayes' else K*(1-R)
            rows.append(dict(r=r, s=s, tr=tranche, held=held, w=w, f=w*(1-held),
                             flag=flag, srow=srow))

    tot = sum(x['f'] for x in rows)
    fails = 0
    print(f'cash available B5 = {B5:,.2f}\n', flush=True)
    print(f'{"row":>4s}{"stock":>7s}{"tranche":>9s}{"held":>6s}{"base wt":>10s}'
          f'{"free wt":>10s}{"$ old":>14s}{"$ new":>14s}', flush=True)
    print('-'*74, flush=True)
    for x in rows:
        alloc = B5*x['f']/tot if tot else 0.0
        old = sa.cell(11 + (x['r']-25)//2, 13 if x['tr'] == 'Bayes' else 14).value
        print(f'{x["r"]:>4d}{x["s"]:>7s}{x["tr"]:>9s}{"HELD" if x["held"] else "-":>6s}'
              f'{x["w"]:>10.4f}{x["f"]:>10.4f}{old:>14,.2f}{alloc:>14,.2f}', flush=True)

        # the four formulas, rebuilt independently of the writer
        share = f'$R${x["srow"]}' if x['tr'] == 'Bayes' else f'(1-$R${x["srow"]})'
        want = {
            4: f"=IF('Model {x['s']}'!${x['flag']}$867=1,1,0)",
            5: f'=$K${x["srow"]}*{share}',
            6: f'=E{x["r"]}*(1-D{x["r"]})',
            3: f'=IF(SUM($F$25:$F$34)=0,0,$B$5*F{x["r"]}/SUM($F$25:$F$34))',
        }
        for col, exp in want.items():
            got = a.cell(x['r'], col).value
            if got != exp:
                print(f'    MISMATCH r{x["r"]} col{col}\n      want {exp}\n      got  {got}',
                      flush=True)
                fails += 1

    print('-'*74, flush=True)
    nfree = sum(1 for x in rows if not x['held'])
    allocs = [B5*x['f']/tot if tot else 0.0 for x in rows]
    print(f'sleeves free {nfree} of {len(rows)}; $ per free sleeve {B5/nfree:,.2f}', flush=True)

    # invariants
    for x, al in zip(rows, allocs):
        if x['held'] and al != 0.0:
            print(f'  FAIL held sleeve {x["s"]} {x["tr"]} allocated {al}', flush=True); fails += 1
    if abs(sum(allocs) - B5) > 0.01:
        print(f'  FAIL allocated {sum(allocs):,.2f} != cash {B5:,.2f}', flush=True); fails += 1
    equal = {round(al, 6) for x, al in zip(rows, allocs) if not x['held']}
    if len(equal) != 1:
        print(f'  FAIL free sleeves not equally sized: {equal}', flush=True); fails += 1

    # the blotter baseline must be untouched
    for i in range(11, 16):
        if of['Allocation'].cell(i, 12).value != sv['Allocation'].cell(i, 12).value and \
           not isinstance(sv['Allocation'].cell(i, 12).value, (int, float)):
            pass
    src_f = openpyxl.load_workbook(SRC, data_only=False)['Allocation']
    for col in (12, 13, 14):
        for i in range(11, 16):
            if a.cell(i, col).value != src_f.cell(i, col).value:
                print(f'  FAIL L/M/N changed at row {i} col {col}', flush=True); fails += 1
    at_o = openpyxl.load_workbook(SRC, data_only=False)['Active Trading']
    at_n = of['Active Trading']
    for r in range(7, 12):
        if at_o.cell(r, 2).value != at_n.cell(r, 2).value:
            print(f'  FAIL Active Trading B{r} changed', flush=True); fails += 1

    print(f'\n{"ALL CHECKS PASSED" if fails == 0 else str(fails) + " FAILURES"}', flush=True)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
