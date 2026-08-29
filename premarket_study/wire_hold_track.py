"""
Add the average-hold tracking block to the Performance tab (user, 29 Aug 2026).

Table at Performance!A63: per name — historical average hold (the pooled
back-test reference, verified fills Apr 2024 - Aug 2026, HANDOVER 3.27
diagnostic run; calendar days, same-day round trips = 0) vs the LIVE average
hold computed from the blotter's CLOSED trades (sell date minus buy date,
via SUMIFS/COUNTIFS on Active Trading B/D/H/M; open positions excluded until
they close; the discretionary log is deliberately excluded — this tracks the
model book). A BOOK aggregate row closes the table.

Rationale (ops): hold length is a low-noise drift indicator — CF creeping from
~17 toward 30+ days, or the AI names' same-day recycling fading, flags a
harvest change well before weekly returns can say anything honest.

Append-only: new rows below the existing Performance table + a Notes line in
the 29 Aug section. Cell-diff verified.
"""
import copy
import sys

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

HIST = [('TSM', 4.2), ('VRT', 4.4), ('VST', 4.4), ('RKLB', 3.1), ('MU', 6.5),
        ('GM', 6.2), ('VLO', 14.1), ('CF', 16.7), ('MRVL', 7.3)]
BOOK_HIST = 5.9
AT = "'Active Trading'"
RNG = lambda col: f"{AT}!${col}$42:${col}$1041"


def live_formula(name_cell):
    cnt = (f'COUNTIFS({RNG("B")},{name_cell},{RNG("M")},"CLOSED")')
    return (f'=IF({cnt}=0,"—",'
            f'(SUMIFS({RNG("H")},{RNG("B")},{name_cell},{RNG("M")},"CLOSED")'
            f'-SUMIFS({RNG("D")},{RNG("B")},{name_cell},{RNG("M")},"CLOSED"))'
            f'/{cnt})')


def wire(in_path, out_path):
    wb = openpyxl.load_workbook(in_path)
    pf = wb['Performance']
    notes = wb['Notes']
    assert pf.max_row == 60, pf.max_row
    navy = 'FF182644'
    hdr_fill = PatternFill(fill_type='solid', start_color=navy, end_color=navy)
    hdr_font = Font(bold=True, color='FFFFFFFF')

    t = pf.cell(row=63, column=1, value='AVERAGE HOLD (calendar days) — historical vs live')
    t.font = Font(bold=True, size=12, color=navy)
    for j, h in enumerate(['Stock', 'Historical avg (back-test)', 'Live avg (blotter)'],
                          start=1):
        c = pf.cell(row=64, column=j, value=h)
        c.fill = hdr_fill
        c.font = hdr_font
        c.alignment = Alignment(horizontal='center', wrap_text=True)
    for i, (nm, hv) in enumerate(HIST):
        r = 65 + i
        pf.cell(row=r, column=1, value=nm).font = Font(bold=True)
        c = pf.cell(row=r, column=2, value=hv)
        c.number_format = '0.0'
        c = pf.cell(row=r, column=3, value=live_formula(f'$A{r}'))
        c.number_format = '0.0'
    r = 65 + len(HIST)
    pf.cell(row=r, column=1, value='BOOK').font = Font(bold=True, color=navy)
    c = pf.cell(row=r, column=2, value=BOOK_HIST)
    c.number_format = '0.0'
    cnt = f'COUNTIFS({RNG("M")},"CLOSED")'
    c = pf.cell(row=r, column=3,
                value=(f'=IF({cnt}=0,"—",'
                       f'(SUMIFS({RNG("H")},{RNG("M")},"CLOSED")'
                       f'-SUMIFS({RNG("D")},{RNG("M")},"CLOSED"))/{cnt})'))
    c.number_format = '0.0'
    pf.cell(row=r + 1, column=1,
            value=('Same-day round trips count as 0; open positions excluded until closed; '
                   'discretionary log excluded. Historical basis: pooled back-test on '
                   'verified fills, Apr 2024 – Aug 2026. Hold length is a low-noise drift '
                   'indicator — read at the monthly review, not daily.')).font = \
        Font(italic=True, size=9, color='FF5F5F5F')

    style_a = notes['A33']
    style_b = notes['B33']
    row = notes.max_row + 1
    ca = notes.cell(row=row, column=1, value='Hold tracking (Performance tab)')
    ca.font = copy.copy(style_a.font)
    ca.alignment = copy.copy(style_a.alignment)
    cb = notes.cell(row=row, column=2,
                    value=('Performance!A63:C75: per-stock average hold, historical '
                           '(back-test reference) vs live (closed blotter trades, sell date '
                           'minus buy date). Same-day = 0; open positions excluded; '
                           'discretionary log excluded. A drifting hold length flags a '
                           'harvest change before returns can — review monthly.'))
    cb.font = copy.copy(style_b.font)
    cb.alignment = copy.copy(style_b.alignment)

    wb.save(out_path)
    return out_path


def diff(in_path, out_path):
    a = openpyxl.load_workbook(in_path)
    b = openpyxl.load_workbook(out_path)
    changed = []
    for ws_name in b.sheetnames:
        wa, wb_ = a[ws_name], b[ws_name]
        for r in range(1, max(wa.max_row, wb_.max_row) + 1):
            for c in range(1, max(wa.max_column, wb_.max_column) + 1):
                va = wa.cell(row=r, column=c).value
                vb = wb_.cell(row=r, column=c).value
                if va != vb:
                    changed.append((ws_name, wb_.cell(row=r, column=c).coordinate, va, vb))
    return changed


if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]
    wire(src, dst)
    ch = diff(src, dst)
    outside = [c for c in ch
               if not (c[0] == 'Performance' and 63 <= int(''.join(filter(str.isdigit, c[1]))) <= 75)
               and c[0] != 'Notes']
    print(f'changed cells: {len(ch)}; outside intended set: {outside or "NONE"}')
    for ws, coord, va, vb in ch[:3]:
        print(f'  {ws}!{coord}: {str(va)[:40]!r} -> {str(vb)[:80]!r}')
