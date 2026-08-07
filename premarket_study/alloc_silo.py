"""
Silo each stock's profit to that stock, instead of pooling it across the book.

The problem
-----------
Allocation!B5 is the cash on hand, and it contains every dollar of realised profit the book has
made. The old block spread all of B5 across whichever sleeves were free:

    C25 = B5 * free_weight / SUM(free_weights)

so RKLB's $35k of realised profit was funding TSM's next buy. The intent is that a stock
compounds its own winnings.

The new rule
------------
    base            = B5 - (total profit to date)
    released        = profit belonging to stocks that cannot trade today
    stock $ today   = (base + released) * w_stock / SUM(w_eligible)  +  own profit

A stock "cannot trade today" if BOTH its sleeves are HOLDING, or if it is switched off in
column B. Its own profit is then thrown into `released` and shared out over the stocks that can
trade -- for that day only. The next morning, once a sleeve frees up, the profit returns to the
stock that earned it.

Within a stock, the day's money is split across its FREE sleeves by the Bayes share in column
R: both free splits R/(1-R); one free takes the lot; neither free gets nothing (and the stock
was ineligible anyway).

This conserves exactly. Summing the stock allocations gives base + released +
(total profit - released) = base + total profit = B5, so the existing reconciliation in B38
still reads OK and the blotter still receives the whole of the morning's cash.

Where it is written
-------------------
Columns S:W rows 11-15 carry the per-stock working, rows 43-48 the summary and the guards, and
C25:C34 is rewritten to read column W. Nothing else changes: Active Trading D19:D28 and H19:H28
already read Allocation!C25:C34 by INDEX, so the blotter picks the new numbers up untouched.

Two notes on safety. This workbook has no Power Query, no charts and no pivots -- checked --
which is the only reason openpyxl is safe to use on it; it is NOT safe on the per-ticker LIVE
workbooks, which do carry Power Query. And openpyxl discards cached formula results on save, so
every value in the delivered file is blank until Excel opens it and recalculates. The workbook
already carries fullCalcOnLoad, so that happens automatically on open. Because of that this
script cannot read its own output back, and instead mirrors the arithmetic in Python and prints
what Excel should produce.

Run:  python3 alloc_silo.py
"""
import os
import shutil

import openpyxl

SRC = ('/root/.claude/uploads/822d405e-f99b-5b59-9c6b-87e725054402/'
       'c655e5aa-TradingExcel_5stock_live_silo.xlsx')
DST = '/home/user/David-Fewer/TradingExcel_5stock_live_siloed.xlsx'

STOCK_ROWS = (11, 12, 13, 14, 15)          # Allocation rows carrying the five names
SLEEVE_TOP = 25                            # first row of the machine-readable block


def sleeve_rows(i):
    """(Bayes row, OU row) in C25:C34 for stock row i."""
    b = SLEEVE_TOP + 2 * (i - STOCK_ROWS[0])
    return b, b + 1


def write(ws):
    # ---- headers for the new working columns -----------------------------------
    for col, head in (('S', 'Profit to date ($)'), ('T', 'Both sleeves held?'),
                      ('U', 'Eligible today?'), ('V', 'Eligible wt'),
                      ('W', '$ Stock today (silo)')):
        c = ws[f'{col}10']
        c.value = head
        c.font = openpyxl.styles.Font(bold=True, size=9)

    for i in STOCK_ROWS:
        b, o = sleeve_rows(i)
        ws[f'S{i}'] = ("=IFERROR(INDEX('Active Trading'!$C$7:$C$11,"
                       f"MATCH($A{i},'Active Trading'!$A$7:$A$11,0)),0)")
        ws[f'T{i}'] = f'=IF(AND($D${b}=1,$D${o}=1),1,0)'
        ws[f'U{i}'] = f'=IF(AND($B{i}=1,$T{i}=0),1,0)'
        ws[f'V{i}'] = f'=$K{i}*$U{i}'
        ws[f'W{i}'] = (f'=IF($U{i}=0,0,IF(SUM($V$11:$V$15)=0,0,'
                       f'($B$44+$B$45)*$V{i}/SUM($V$11:$V$15))+$S{i})')
        ws[f'S{i}'].number_format = '#,##0.00'
        ws[f'W{i}'].number_format = '#,##0.00'

    # ---- summary and guards ----------------------------------------------------
    block = [
        (42, 'SILO ACCOUNTING  —  each stock reinvests its own profit', None),
        (43, 'Total profit to date ($)', '=SUM($S$11:$S$15)'),
        (44, 'Base capital  =  B5 less total profit', '=$B$5-$B$43'),
        (45, 'Profit released by held / excluded stocks',
             '=SUMPRODUCT((1-$U$11:$U$15)*$S$11:$S$15)'),
        (46, 'Check: stock allocations = cash available',
             '=IF(SUM($V$11:$V$15)=0,"ALL HELD - nothing to allocate today",'
             'IF(ABS(SUM($W$11:$W$15)-$B$5)<0.01,"OK","MISMATCH"))'),
        (47, 'Guard: base capital negative?',
             '=IF($B$44<0,"BASE NEGATIVE - profit to date exceeds cash on hand","")'),
        (48, 'Guard: any negative stock allocation?',
             '=IF(MIN($W$11:$W$15)<-0.01,"NEGATIVE ALLOCATION - check B5 and the P&L","")'),
    ]
    for row, label, formula in block:
        ws[f'A{row}'] = label
        if formula is None:
            ws[f'A{row}'].font = openpyxl.styles.Font(bold=True, size=10)
        else:
            ws[f'B{row}'] = formula
            if row in (43, 44, 45):
                ws[f'B{row}'].number_format = '#,##0.00'

    # ---- rewire the machine-readable allocation block ---------------------------
    for i in STOCK_ROWS:
        b, o = sleeve_rows(i)
        den = f'($R{i}*(1-$D{b})+(1-$R{i})*(1-$D{o}))'
        ws[f'C{b}'] = f'=IF({den}=0,0,$W{i}*$R{i}*(1-$D{b})/{den})'
        ws[f'C{o}'] = f'=IF({den}=0,0,$W{i}*(1-$R{i})*(1-$D{o})/{den})'

    # columns E and F no longer drive C; label them so nobody trusts them
    ws['E24'] = 'Base wt (ref)'
    ws['F24'] = 'Free wt (ref)'
    ws['A49'] = ('C25:C34 now reads $ Stock today (column W) and splits it across that '
                 "stock's free sleeves. E and F are kept for reference only.")


def restore_untouched(src, dst, intended):
    """Put back any numeric literal openpyxl re-serialised that we did not mean to change.

    Saving through openpyxl rewrites every float with Python's own repr, which can move the
    last bit: three trade-log prices came back as 415.97 where the source held
    415.96999999999997 -- one ULP, about 4e-11 dollars on the position, but a silent edit to a
    historical record all the same, and the house rule is that workbooks are edited surgically.
    This walks the saved sheets and restores the source's exact <v> text for every cell outside
    the intended edit set.
    """
    import re
    import zipfile

    src_z, dst_z = zipfile.ZipFile(src), zipfile.ZipFile(dst)
    parts, fixed = {}, 0
    # Match ONLY literal value cells: opening tag, attributes with no slash so a self-closing
    # <c .../> can never match, then <v>…</v> immediately. The lazy <c ...>.*?</c> form is
    # forbidden here -- on a self-closing cell it runs past the end and swallows whole rows,
    # which is what produced the "unreadable content" repair prompt the first time round.
    cell_re = re.compile(rb'<c r="([A-Z]+\d+)"([^>/]*)><v>([^<]*)</v></c>')
    for name in dst_z.namelist():
        data = dst_z.read(name)
        if not name.startswith('xl/worksheets/sheet') or not name.endswith('.xml'):
            parts[name] = data
            continue
        try:
            sdata = src_z.read(name)
        except KeyError:
            parts[name] = data
            continue
        srcvals = {m.group(1).decode(): m.group(3) for m in cell_re.finditer(sdata)}

        def repl(m):
            nonlocal fixed
            coord = m.group(1).decode()
            want = srcvals.get(coord)
            if coord in intended or want is None or m.group(3) == want:
                return m.group(0)
            fixed += 1
            return (b'<c r="' + m.group(1) + b'"' + m.group(2)
                    + b'><v>' + want + b'</v></c>')

        parts[name] = cell_re.sub(repl, data)
    src_z.close(); dst_z.close()
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, d in parts.items():
            z.writestr(n, d)
    return fixed


def mirror(path):
    """Re-derive the new block in Python. openpyxl blanks cached values on save, so the
    delivered file cannot be read back until Excel has opened it."""
    wv = openpyxl.load_workbook(SRC, data_only=True)
    a, t = wv['Allocation'], wv['Active Trading']
    B5 = a['B5'].value
    names = [a[f'A{i}'].value for i in STOCK_ROWS]
    prof = {}
    for i, n in zip(STOCK_ROWS, names):
        for r in range(7, 12):
            if t[f'A{r}'].value == n:
                prof[i] = t[f'C{r}'].value or 0.0
    K = {i: a[f'K{i}'].value or 0.0 for i in STOCK_ROWS}
    R = {i: a[f'R{i}'].value or 0.5 for i in STOCK_ROWS}
    inc = {i: a[f'B{i}'].value or 0 for i in STOCK_ROWS}
    held = {r: (1 if t[f'C{r-6}'].value == 'HOLDING' else 0) for r in range(25, 35)}

    total = sum(prof.values())
    base = B5 - total
    elig = {}
    for i in STOCK_ROWS:
        b, o = sleeve_rows(i)
        both = held[b] and held[o]
        elig[i] = 1 if (inc[i] == 1 and not both) else 0
    released = sum(prof[i] for i in STOCK_ROWS if not elig[i])
    wsum = sum(K[i] * elig[i] for i in STOCK_ROWS)

    print(f'  cash available B5           {B5:>14,.2f}')
    print(f'  total profit to date        {total:>14,.2f}')
    print(f'  base capital                {base:>14,.2f}')
    print(f'  released by held/excluded   {released:>14,.2f}\n')
    print(f"  {'stock':6s} {'profit':>12s} {'elig':>5s} {'base share':>13s} "
          f"{'= $ today':>13s}   {'was':>13s}  {'change':>12s}")
    tot_new = 0.0
    for i in STOCK_ROWS:
        share = (base + released) * K[i] * elig[i] / wsum if wsum else 0.0
        new = (share + prof[i]) if elig[i] else 0.0
        tot_new += new
        b, o = sleeve_rows(i)
        old = (a[f'C{b}'].value or 0) + (a[f'C{o}'].value or 0)
        print(f'  {names[STOCK_ROWS.index(i)]:6s} {prof[i]:>12,.2f} {elig[i]:>5d} '
              f'{share:>13,.2f} {new:>13,.2f}   {old:>13,.2f}  {new-old:>+12,.2f}')
    print(f"\n  {'TOTAL':6s} {total:>12,.2f} {'':5s} {'':13s} {tot_new:>13,.2f}")
    print(f'  conservation check: allocated - B5 = {tot_new - B5:+.4f}'
          f'   {"OK" if abs(tot_new - B5) < 0.01 else "MISMATCH"}')

    print(f'\n  per sleeve (what Active Trading D19:D28 will read):')
    for i in STOCK_ROWS:
        b, o = sleeve_rows(i)
        share = (base + released) * K[i] * elig[i] / wsum if wsum else 0.0
        new = (share + prof[i]) if elig[i] else 0.0
        den = R[i] * (1 - held[b]) + (1 - R[i]) * (1 - held[o])
        cb = new * R[i] * (1 - held[b]) / den if den else 0.0
        co = new * (1 - R[i]) * (1 - held[o]) / den if den else 0.0
        nm = names[STOCK_ROWS.index(i)]
        for lbl, row, val in (('Bayes', b, cb), ('OU', o, co)):
            st = 'HOLDING' if held[row] else 'CASH'
            print(f'    {nm:6s} {lbl:5s} {st:8s} {val:>13,.2f}')


def main():
    shutil.copy(SRC, DST)
    wb = openpyxl.load_workbook(DST)
    write(wb['Allocation'])
    wb.save(DST)

    intended = {f'{c}{i}' for c in 'STUVW' for i in list(STOCK_ROWS) + [10]}
    intended |= {f'C{r}' for r in range(SLEEVE_TOP, SLEEVE_TOP + 10)}
    intended |= {f'A{r}' for r in range(42, 50)} | {f'B{r}' for r in range(42, 50)}
    intended |= {'E24', 'F24'}
    n = restore_untouched(SRC, DST, intended)
    print(f'written: {DST}')
    print(f'  restored {n} numeric literal(s) openpyxl had re-serialised outside the edit set\n')
    mirror(DST)
    print('\n  NOTE: openpyxl blanks cached results on save. Every formula above shows as')
    print('  empty until Excel opens the file and recalculates, which it does automatically')
    print('  (fullCalcOnLoad). Compare the recalculated sheet against this table.')


if __name__ == '__main__':
    main()
