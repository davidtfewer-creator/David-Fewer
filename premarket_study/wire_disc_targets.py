"""
wire_disc_targets.py — the discretionary log sets its own exit price (3 Oct 2026).

User: a discretionary trade should be placed as a BRACKET, with the exit
defined at entry, and the log should derive that exit from the Tranche label
instead of a typed round number — "Bayes" takes that stock's Bayes margin,
"OU" its OU margin, "DISC" the standard 5%.

WHAT THE TWO CONVENTIONS ARE, and why they differ. They are not the same rule
and should not be made the same:
  DISC   target = entry x (1 + AA40)          [AA40 = 5%]
         This is the tested dislocation ticket (3.28d / disc_structure.py):
         a bracket at entry x 1.05. Multiplicative off the fill, by design.
  Bayes  target = entry + prev_close x Bayes premium
  OU     target = entry + prev_close x OU premium
         This is the SLEEVE's own resting sell (the main blotter's Sell @ is
         Buy @ + close x pi), so a re-entry labelled with a sleeve exits on
         that sleeve's rule, off the actual fill (the 3.19 convention).

The previous close is found with LOOKUP(2,1/(...)) — the last Query session
STRICTLY BEFORE the buy date. That matters: at 09:00 the buy date is not in
Query yet (Script 1 pulls after the close), so a MATCH on the buy date would
fail at order time and then silently change the recorded target the next day,
after the GTC order was already placed. "Last session before" gives the same
answer before and after Query catches up, so a placed bracket and the log
never disagree.

WHAT IS LEFT ALONE. Rows whose target was typed by hand (50, 51, 53, 56-59,
61) are history — they record what was actually placed, and a formula must not
rewrite them. Only cells currently holding the DISC formula, or blank, are
written. DISC rows are rewritten to the combined formula but evaluate to the
identical number, so no existing value moves.

Verification: every cell outside the intended set is compared before and after,
and every DISC row's target is re-derived in Python and checked against the
cached value the sheet already holds.

Usage: python wire_disc_targets.py <in.xlsx> <out.xlsx>
"""
import shutil
import sys

import openpyxl
from openpyxl.worksheet.formula import ArrayFormula


def same(a, b):
    """Cell equality that ignores two artefacts of an openpyxl round trip:
    ArrayFormula objects compare by identity, and floats come back with a
    different last digit from the repr they were written with."""
    if isinstance(a, ArrayFormula) or isinstance(b, ArrayFormula):
        return (getattr(a, 'text', a) == getattr(b, 'text', b)
                and getattr(a, 'ref', a) == getattr(b, 'ref', b))
    if isinstance(a, float) and isinstance(b, float):
        return a == b or abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    return a == b

SHEET = 'Active Trading'
ROW0, ROW1 = 42, 231                  # the discretionary log's data rows
C_STOCK, C_TRANCHE, C_BUYD, C_BUYPX, C_TARGET = 21, 22, 23, 24, 27
C_CHECK = 34                          # AH, previously unused


def target_formula(r):
    """Tranche-driven take-profit. Lazy IF keeps the INDEX off DISC rows."""
    prem = (f'IF($V{r}="Bayes",INDEX($E$7:$E$15,MATCH($U{r},$A$7:$A$15,0)),'
            f'IF($V{r}="OU",INDEX($F$7:$F$15,MATCH($U{r},$A$7:$A$15,0)),'
            f'$AA$40))')
    prevc = (f'IFERROR(LOOKUP(2,1/((Query!$A$2:$A$2000<$W{r})'
             f'*(Query!$A$2:$A$2000<>"")),'
             f'INDEX(Query!$B$2:$AK$2000,0,MATCH($U{r}&"_C",Query!$B$1:$AK$1,0)))'
             f',$X{r})')
    base = f'IF(OR($V{r}="Bayes",$V{r}="OU"),{prevc},$X{r})'
    return f'=IF($X{r}="","",$X{r}+{prem}*{base})'


def check_formula(r):
    """Guard: the entry price must be inside that ticker's own range on the buy
    date. Six rows of the live log are VST trades typed as VRT (HANDOVER 3.30),
    which used to mislabel P&L only -- now that the ticker drives the bracket
    price, the same typo would place a wrong order. Blank while the buy date is
    not yet in Query, so same-day entries simply have nothing to check yet."""
    lo = (f'INDEX(Query!$B$2:$AK$2000,MATCH($W{r},Query!$A$2:$A$2000,0),'
          f'MATCH($U{r}&"_L",Query!$B$1:$AK$1,0))')
    hi = (f'INDEX(Query!$B$2:$AK$2000,MATCH($W{r},Query!$A$2:$A$2000,0),'
          f'MATCH($U{r}&"_H",Query!$B$1:$AK$1,0))')
    return (f'=IF(OR($X{r}="",$U{r}=""),"",IFERROR('
            f'IF(OR($X{r}<{lo}*0.98,$X{r}>{hi}*1.02),"CHECK TICKER",""),""))')


def main():
    src, dst = sys.argv[1], sys.argv[2]
    shutil.copyfile(src, dst)

    before_f = {}
    wb = openpyxl.load_workbook(src, data_only=False)
    before_v = {}
    wbv = openpyxl.load_workbook(src, data_only=True)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.value is not None:
                    before_f[(ws.title, c.coordinate)] = c.value
    for ws in wbv.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.value is not None:
                    before_v[(ws.title, c.coordinate)] = c.value
    wbv.close()

    at = wb[SHEET]
    written, kept = [], []
    for r in range(ROW0, ROW1 + 1):
        cur = at.cell(row=r, column=C_TARGET).value
        is_formula = isinstance(cur, str) and cur.startswith('=')
        if cur is not None and not is_formula:
            kept.append((r, at.cell(row=r, column=C_STOCK).value,
                         at.cell(row=r, column=C_TRANCHE).value, cur))
            continue
        at.cell(row=r, column=C_TARGET).value = target_formula(r)
        written.append(r)

    checks = []
    for r in range(ROW0, ROW1 + 1):
        if at.cell(row=r, column=C_CHECK).value is None:
            at.cell(row=r, column=C_CHECK).value = check_formula(r)
            checks.append(r)
    at.cell(row=41, column=C_CHECK).value = 'Check'

    at['AA41'] = 'Target sale'

    # Notes entry, as every wiring change in this workbook carries
    nt = wb['Notes']
    base = max(r for r in range(1, nt.max_row + 1)
               if nt.cell(row=r, column=1).value is not None) + 2
    notes = [
        ('UPDATE — 3 OCTOBER 2026', None),
        ('Disc log: exit price from the Tranche',
         'Discretionary log col AA (Target sale) now derives the bracket exit from col V. '
         '"Bayes" = entry + prev close x that stock\'s Bayes premium (Active Trading E7:E15); '
         '"OU" = entry + prev close x OU premium (F7:F15); anything else (DISC) = entry x '
         '(1 + AA40), the standard 5%, unchanged. Sleeve labels use the SLEEVE\'s own exit '
         'rule (the same bid + close x pi the main blotter\'s Sell @ uses), DISC uses the '
         'tested ticket bracket off the fill. Prev close is the last Query session STRICTLY '
         'BEFORE the buy date, so the number is the same before and after Script 1 adds the '
         'buy date -- a placed GTC and the log cannot drift apart. Rows whose target was '
         'typed by hand are left as typed: they record what was actually placed.'),
        ('Disc log: ticker check (col AH)',
         'Flags CHECK TICKER when the entry price sits outside that ticker\'s own high/low '
         'on the buy date. Six rows of this log were VST trades typed as VRT; now that the '
         'exit price is derived from the ticker, that typo would produce a wrong bracket, '
         'not just mislabelled P&L. Blank until the buy date reaches Query, so a same-day '
         'entry simply has nothing to check yet. ops/disc_bracket_place.py refuses any '
         'ticket this column flags.'),
    ]
    ncells = []
    for i, (a, b) in enumerate(notes):
        nt.cell(row=base + i, column=1).value = a
        ncells.append((nt.title, f'A{base + i}'))
        if b:
            nt.cell(row=base + i, column=2).value = b
            ncells.append((nt.title, f'B{base + i}'))

    wb.save(dst)

    # ---- verification -------------------------------------------------
    wb2 = openpyxl.load_workbook(dst, data_only=False)
    after_f = {}
    for ws in wb2.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.value is not None:
                    after_f[(ws.title, c.coordinate)] = c.value
    intended = ({(SHEET, f'AA{r}') for r in written}
                | {(SHEET, f'AH{r}') for r in checks}
                | {(SHEET, 'AA41'), (SHEET, 'AH41')} | set(ncells))
    changed = {k for k in set(before_f) | set(after_f)
               if not same(before_f.get(k), after_f.get(k))}
    stray = changed - intended
    print(f'rows written      : {len(written)}  (AA{written[0]}..AA{written[-1]})')
    print(f'check column      : {len(checks)} rows (AH)')
    print(f'hand-typed kept   : {len(kept)} -> ' +
          ', '.join(f'r{r} {s}/{t}={v}' for r, s, t, v in kept))
    print(f'cells changed     : {len(changed)}, all intended: {not stray}')
    if stray:
        print('  STRAY:', sorted(stray)[:10])
        sys.exit(1)

    # DISC rows must evaluate to the number the sheet already cached
    pct = before_v.get((SHEET, 'AA40'))
    bad = 0
    for r in range(ROW0, ROW1 + 1):
        if r not in written:
            continue
        tr = before_v.get((SHEET, f'V{r}'))
        px = before_v.get((SHEET, f'X{r}'))
        old = before_v.get((SHEET, f'AA{r}'))
        if tr is None or px is None or old is None or tr not in ('DISC',):
            continue
        want = px + px * pct
        if abs(want - old) > 1e-6:
            print(f'  MISMATCH r{r}: re-derived {want} vs cached {old}')
            bad += 1
    print(f'DISC rows re-derived against the cached value: '
          f'{"all match" if not bad else f"{bad} MISMATCH"}')
    print(f'\nwrote {dst}')
    if bad:
        sys.exit(1)


if __name__ == '__main__':
    main()
